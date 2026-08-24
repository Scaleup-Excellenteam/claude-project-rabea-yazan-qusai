"""
Owner: Person 3

Purpose:
UI-adjacent orchestration helpers for the local Streamlit app. This
module keeps status mapping, citation extraction, client setup, and
debug payload preparation testable without launching Streamlit or
calling the real Anthropic API.
"""

import os
from pathlib import Path

from agent.loop import answer_question
from agent.metrics import compute_metrics
from agent.system_prompt import (
    REFUSAL_TEXT,
    STATUS_ANSWERED,
    STATUS_CLARIFICATION_REQUIRED,
    STATUS_MAX_ITERATIONS,
    STATUS_NO_GROUNDED_ANSWER,
    STATUS_REFUSED_MISSING_INFORMATION,
    STATUS_TECHNICAL_ERROR,
    classify_outcome,
)

ENV_KEY_NAME = "ANTHROPIC_API_KEY"
MISSING_API_KEY_MESSAGE = (
    "שגיאת הגדרה טכנית: חסר ANTHROPIC_API_KEY. יש להגדיר אותו בקובץ .env מקומי."
)
TOOLS_NOT_READY_MESSAGE = (
    "שגיאת אינטגרציה טכנית: כלי השליפה האמיתיים עדיין לא מחוברים."
)
MAX_ITERATIONS_MESSAGE = (
    "לא ניתן היה לאמת תשובה מתוך המסמכים לפני מגבלת האיטרציות. נסו לנסח את השאלה מחדש."
)
NO_GROUNDED_ANSWER_MESSAGE = (
    "לא ניתן להציג תשובה כי לא נמצאו אסמכתאות מספקות במסמכים."
)
TECHNICAL_ERROR_TITLE = "שגיאה טכנית"


class TechnicalSetupError(RuntimeError):
    """Raised for local setup/integration problems, never for missing facts."""


def _load_dotenv_value(path, key):
    env_path = Path(path)
    if not env_path.exists():
        return None

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == key:
            return value.strip().strip("\"'")
    return None


def get_api_key(env=None, dotenv_path=".env"):
    """Read the app API key from process env or a local .env file.

    This only reads values; it does not mutate global environment
    variables and never returns placeholder template values.
    """
    source = os.environ if env is None else env
    value = source.get(ENV_KEY_NAME) or _load_dotenv_value(dotenv_path, ENV_KEY_NAME)
    if value in {None, "", "your-api-key-here"}:
        return None
    return value


def create_anthropic_client(env=None, dotenv_path=".env"):
    """Create the real Anthropic client, or raise a UI-safe setup error."""
    api_key = get_api_key(env=env, dotenv_path=dotenv_path)
    if not api_key:
        raise TechnicalSetupError(MISSING_API_KEY_MESSAGE)

    try:
        from anthropic import Anthropic
    except Exception as exc:
        raise TechnicalSetupError(f"שגיאת הגדרה טכנית: ספריית anthropic אינה זמינה: {exc}") from exc

    return Anthropic(api_key=api_key)


def build_default_tool_registry():
    """Wire real retrieval tools when Person 1/2 implementations exist.

    Until those modules expose the expected callables, fail explicitly
    instead of returning fixture data in the production UI.
    """
    try:
        from tools import course_tools, text_tools
    except Exception as exc:
        raise TechnicalSetupError(f"{TOOLS_NOT_READY_MESSAGE} {exc}") from exc

    names = {
        "list_sections": text_tools,
        "get_section": text_tools,
        "search": text_tools,
        "list_curricula": course_tools,
        "get_course_table": course_tools,
        "get_course": course_tools,
    }
    registry = {}
    missing = []
    for name, module in names.items():
        func = getattr(module, name, None)
        if callable(func):
            registry[name] = func
        else:
            missing.append(name)

    if missing:
        raise TechnicalSetupError(f"{TOOLS_NOT_READY_MESSAGE} חסרים: {', '.join(missing)}")
    return registry


def _format_source_ref(citation):
    if not isinstance(citation, dict):
        return str(citation)

    source = citation.get("source") or citation.get("filename") or citation.get("source_id")
    section = citation.get("section_title") or citation.get("title")
    page = citation.get("page")
    page_start = citation.get("page_start")
    page_end = citation.get("page_end")

    parts = [str(part) for part in (source, section) if part]
    if page:
        parts.append(f"עמוד {page}")
    elif page_start and page_end and page_start != page_end:
        parts.append(f"עמודים {page_start}-{page_end}")
    elif page_start:
        parts.append(f"עמוד {page_start}")
    return " | ".join(parts) if parts else str(citation)


def _collect_citation_dicts(value, output):
    if isinstance(value, dict):
        citation_value = value.get("citation")
        citations_value = value.get("citations")
        if citation_value:
            _collect_citation_dicts(citation_value, output)
        if citations_value:
            _collect_citation_dicts(citations_value, output)
        if any(value.get(key) for key in ("source", "filename", "source_id", "page", "page_start")):
            output.append(value)
        for child in value.values():
            if child is not citation_value and child is not citations_value:
                _collect_citation_dicts(child, output)
    elif isinstance(value, list):
        for item in value:
            _collect_citation_dicts(item, output)


def extract_citations(loop_result=None, policy=None):
    """Return display-ready unique citation/source references."""
    collected = []
    if policy:
        _collect_citation_dicts(policy.get("citations", []), collected)
    if loop_result:
        for call in loop_result.get("tool_calls", []):
            if not call.get("is_error"):
                _collect_citation_dicts(call.get("result"), collected)

    labels = []
    seen = set()
    for citation in collected:
        label = _format_source_ref(citation)
        if label not in seen:
            labels.append(label)
            seen.add(label)
    return labels


def prepare_display(policy, *, loop_result=None, metrics=None):
    """Map a policy result into a small, Streamlit-friendly view model."""
    status = policy.get("status")
    citations = extract_citations(loop_result=loop_result, policy=policy)
    debug = {
        "status": status,
        "metrics": metrics or {},
        "tool_trace": (loop_result or {}).get("tool_calls", []),
    }

    if status == STATUS_ANSWERED:
        return {
            "kind": "answer",
            "body": policy.get("answer") or "",
            "citations": citations,
            "options": [],
            "debug": debug,
        }
    if status == STATUS_REFUSED_MISSING_INFORMATION:
        return {
            "kind": "missing_information",
            "body": REFUSAL_TEXT,
            "citations": [],
            "options": [],
            "debug": debug,
        }
    if status == STATUS_CLARIFICATION_REQUIRED:
        return {
            "kind": "clarification",
            "body": policy.get("answer") or "נדרש בירור: איזו תוכנית לימודים רלוונטית לשאלה?",
            "citations": citations,
            "options": list(policy.get("options") or []),
            "debug": debug,
        }
    if status == STATUS_TECHNICAL_ERROR:
        return {
            "kind": "technical_error",
            "title": TECHNICAL_ERROR_TITLE,
            "body": policy.get("message") or "אירעה שגיאה טכנית מקומית.",
            "citations": [],
            "options": [],
            "debug": debug,
        }
    if status == STATUS_MAX_ITERATIONS:
        return {
            "kind": "max_iterations",
            "body": MAX_ITERATIONS_MESSAGE,
            "citations": citations,
            "options": [],
            "debug": debug,
        }
    if status == STATUS_NO_GROUNDED_ANSWER:
        return {
            "kind": "no_grounded_answer",
            "body": NO_GROUNDED_ANSWER_MESSAGE,
            "citations": [],
            "options": [],
            "debug": debug,
        }

    return {
        "kind": "technical_error",
        "title": TECHNICAL_ERROR_TITLE,
        "body": f"סטטוס לא מוכר: {status}",
        "citations": [],
        "options": [],
        "debug": debug,
    }


def run_agent_for_ui(question, *, client=None, tool_registry=None):
    """Run client -> agent loop -> policy -> display model for Streamlit."""
    try:
        active_client = client or create_anthropic_client()
        active_registry = tool_registry or build_default_tool_registry()
        loop_result = answer_question(
            question,
            client=active_client,
            tool_registry=active_registry,
            max_iterations=6,
        )
        policy = classify_outcome(loop_result)
        metrics = compute_metrics(loop_result, policy=policy)
        return prepare_display(policy, loop_result=loop_result, metrics=metrics)
    except TechnicalSetupError as exc:
        policy = {
            "status": STATUS_TECHNICAL_ERROR,
            "answer": None,
            "message": str(exc),
        }
        return prepare_display(policy, loop_result={}, metrics={})
