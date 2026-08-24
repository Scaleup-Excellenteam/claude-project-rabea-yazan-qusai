"""
Model-provider abstraction and failover.

The agent loop only needs a client with `messages.create(**kwargs)`.
ProviderManager exposes that shape while trying configured providers in
order for retryable technical failures.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_MODEL = "claude-sonnet-5"
ORDER_ENV = "MODEL_PROVIDER_ORDER"

_SECRET_MARKERS = ("api_key", "apikey", "authorization", "x-api-key", "key")
_RETRYABLE_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504, 529}
_NON_RETRYABLE_STATUS_CODES = {400, 401, 403, 404, 422}
_RETRYABLE_CLASS_MARKERS = (
    "timeout",
    "connection",
    "rate",
    "overloaded",
    "serviceunavailable",
    "internalserver",
    "apierror",
)
_NON_RETRYABLE_CLASS_MARKERS = (
    "authentication",
    "permission",
    "badrequest",
    "notfound",
    "unprocessable",
)


class ProviderConfigurationError(RuntimeError):
    """No usable provider is configured, or a provider is misconfigured."""


class RetryableProviderError(RuntimeError):
    """A temporary provider failure that may be retried on another provider."""


class NonRetryableProviderError(RuntimeError):
    """A provider/configuration failure that must not trigger failover."""


class ProviderUnavailableError(RuntimeError):
    """All configured providers failed with retryable technical errors."""


def _redact(value):
    text = str(value)
    for marker in _SECRET_MARKERS:
        if marker in text.lower():
            return "[redacted]"
    return text


def sanitize_exception(exc) -> str:
    """Return an exception message with common secret-bearing fields hidden."""
    message = str(exc)
    if not message:
        return exc.__class__.__name__
    lowered = message.lower()
    if any(marker in lowered for marker in _SECRET_MARKERS):
        return f"{exc.__class__.__name__}: [redacted]"
    return message


def classify_provider_exception(exc):
    if isinstance(exc, RetryableProviderError):
        return "retryable"
    if isinstance(exc, (NonRetryableProviderError, ProviderConfigurationError)):
        return "non_retryable"

    status_code = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status_code in _RETRYABLE_STATUS_CODES:
        return "retryable"
    if status_code in _NON_RETRYABLE_STATUS_CODES:
        return "non_retryable"

    name = exc.__class__.__name__.lower()
    if any(marker in name for marker in _NON_RETRYABLE_CLASS_MARKERS):
        return "non_retryable"
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return "retryable"
    if any(marker in name for marker in _RETRYABLE_CLASS_MARKERS):
        return "retryable"
    return "non_retryable"


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    api_key: str
    model: str = DEFAULT_MODEL
    provider_type: str = "anthropic"


class _ProviderMessages:
    def __init__(self, manager):
        self._manager = manager

    def create(self, **kwargs):
        return self._manager.create_message(**kwargs)


class ProviderManager:
    """Anthropic-compatible client wrapper with ordered provider failover."""

    def __init__(self, providers):
        self.providers = list(providers)
        self.messages = _ProviderMessages(self)
        self.attempt_log = []
        if not self.providers:
            raise ProviderConfigurationError("no model provider is configured")

    def create_message(self, **kwargs):
        last_error = None
        self.attempt_log = []
        for index, provider in enumerate(self.providers):
            request = dict(kwargs)
            request["model"] = provider.model or request.get("model") or DEFAULT_MODEL
            try:
                self.attempt_log.append({"provider": provider.name, "status": "attempted"})
                return provider.client.messages.create(**request)
            except Exception as exc:
                classification = classify_provider_exception(exc)
                last_error = exc
                self.attempt_log[-1] = {
                    "provider": provider.name,
                    "status": classification,
                    "error": sanitize_exception(exc),
                }
                if classification != "retryable" or index == len(self.providers) - 1:
                    break

        if classify_provider_exception(last_error) == "retryable":
            raise ProviderUnavailableError(
                f"all configured providers failed: {sanitize_exception(last_error)}"
            ) from last_error
        raise NonRetryableProviderError(sanitize_exception(last_error)) from last_error


@dataclass(frozen=True)
class ClientProvider:
    name: str
    client: object
    model: str = DEFAULT_MODEL


def _env_value(env, name):
    source = os.environ if env is None else env
    value = source.get(name)
    if value in {None, "", "your-api-key-here"}:
        return None
    return value


def _configured_names(env):
    order = _env_value(env, ORDER_ENV)
    if order:
        return [name.strip() for name in order.split(",") if name.strip()]
    return ["anthropic", "anthropic_secondary", "anthropic_tertiary"]


def _prefix_for_name(name):
    if name == "anthropic":
        return "ANTHROPIC"
    if name.startswith("anthropic_"):
        suffix = name.removeprefix("anthropic_").upper()
        return f"ANTHROPIC_{suffix}"
    return name.upper()


def load_provider_configs(env=None) -> list[ProviderConfig]:
    configs = []
    for name in _configured_names(env):
        prefix = _prefix_for_name(name)
        api_key = _env_value(env, f"{prefix}_API_KEY")
        if not api_key:
            continue
        configs.append(
            ProviderConfig(
                name=name,
                api_key=api_key,
                model=_env_value(env, f"{prefix}_MODEL") or DEFAULT_MODEL,
                provider_type="anthropic",
            )
        )
    return configs


def create_anthropic_provider(config: ProviderConfig):
    try:
        from anthropic import Anthropic
    except Exception as exc:
        raise ProviderConfigurationError(
            f"anthropic library is unavailable: {sanitize_exception(exc)}"
        ) from exc
    return ClientProvider(
        name=config.name,
        client=Anthropic(api_key=config.api_key),
        model=config.model,
    )


def create_provider_manager(env=None, provider_factory=None) -> ProviderManager:
    configs = load_provider_configs(env=env)
    if not configs:
        raise ProviderConfigurationError("no model provider is configured")

    factory = provider_factory or create_anthropic_provider
    providers = [factory(config) for config in configs]
    return ProviderManager(providers)
