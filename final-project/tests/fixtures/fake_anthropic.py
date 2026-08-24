"""
Owner: Person 3

Purpose:
A minimal fake Anthropic client for testing agent/loop.py without a
real API key or network call. Mirrors the small slice of the real SDK
response shape the loop depends on: `client.messages.create(...)`
returning an object with `.content` (a list of blocks with `.type`,
and either `.text` or `.id`/`.name`/`.input`) and `.stop_reason`.
"""


class TextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class ToolUseBlock:
    def __init__(self, id, name, input):
        self.type = "tool_use"
        self.id = id
        self.name = name
        self.input = input


class Usage:
    """Mirrors the slice of the real SDK's response.usage object that
    agent/metrics.py reads. Any field left as None simulates that
    field being absent/unsupported, without raising AttributeError.
    """

    def __init__(
        self,
        input_tokens=None,
        output_tokens=None,
        cache_read_input_tokens=None,
        cache_creation_input_tokens=None,
    ):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_read_input_tokens = cache_read_input_tokens
        self.cache_creation_input_tokens = cache_creation_input_tokens


class FakeResponse:
    def __init__(self, content, stop_reason, usage=None):
        self.content = content
        self.stop_reason = stop_reason
        self.usage = usage


class FakeMessagesResource:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError(
                "FakeAnthropicClient: no more canned responses queued "
                "(the loop called messages.create more times than the "
                "test expected)"
            )
        return self._responses.pop(0)


class FakeAnthropicClient:
    """Queue of canned FakeResponse objects, returned one per `.create()` call."""

    def __init__(self, responses):
        self.messages = FakeMessagesResource(responses)
