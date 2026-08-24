import pytest

from agent.loop import answer_question
from agent.metrics import compute_metrics
from agent.providers import (
    ClientProvider,
    NonRetryableProviderError,
    ProviderConfigurationError,
    ProviderManager,
    RetryableProviderError,
    classify_provider_exception,
    create_provider_manager,
)
from agent.retrieval_registry import (
    RetrievalSetupError,
    build_production_tool_registry,
)
from agent.system_prompt import REFUSAL_TEXT, classify_outcome
from agent.ui import build_default_tool_registry, prepare_display, run_agent_for_ui
from extract.pdf_text import extract_pdf_pages
from extract.sections import extract_sections
from index.build_courses import build_courses_db
from index.build_fts import build_index
from tests.fixtures.fake_anthropic import FakeResponse, TextBlock, ToolUseBlock
from tests.support import REGULATIONS_PDF, YEARBOOK_PDF


EXPECTED_TOOL_NAMES = {
    "list_sections",
    "get_section",
    "search",
    "list_curricula",
    "get_course_table",
    "get_course",
}


class RecordingMessages:
    def __init__(self, responses=None, exc=None):
        self.responses = list(responses or [])
        self.exc = exc
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        return self.responses.pop(0)


class RecordingClient:
    def __init__(self, responses=None, exc=None):
        self.messages = RecordingMessages(responses=responses, exc=exc)


@pytest.fixture(scope="module")
def text_db_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("final-text") / "app.db"
    pages = extract_pdf_pages(YEARBOOK_PDF, "yearbook")
    pages += extract_pdf_pages(REGULATIONS_PDF, "regulations")
    sections = []
    for source_id in {"yearbook", "regulations"}:
        source_pages = [page for page in pages if page.source_id == source_id]
        sections.extend(extract_sections(source_pages))
    build_index(path, sections)
    return path


@pytest.fixture(scope="module")
def course_db_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("final-course") / "course_data.db"
    build_courses_db(YEARBOOK_PDF, path)
    return path


@pytest.fixture(scope="module")
def production_registry(text_db_path, course_db_path):
    return build_production_tool_registry(
        text_db_path=text_db_path,
        course_db_path=course_db_path,
    )


def test_all_six_real_tool_names_are_present_in_production_registry(production_registry):
    assert set(production_registry) == EXPECTED_TOOL_NAMES


def test_person1_real_prose_tool_dispatch_works(production_registry):
    sections = production_registry["list_sections"]()
    assert sections
    section = production_registry["get_section"](section_id=sections[0]["section_id"])
    assert section["text"]
    assert section["citations"]


def test_person2_real_course_tool_dispatch_works(production_registry):
    curricula = production_registry["list_curricula"]()
    assert {row["curriculum_id"] for row in curricula} >= {"single_major_fall"}
    table = production_registry["get_course_table"](
        curriculum="single_major_fall",
        year=2,
        semester=4,
    )
    assert table["rows"]
    courses = production_registry["get_course"](course_number="0122407")
    assert any(course["course_number"] == "0122407" for course in courses)


def test_production_registry_does_not_point_to_fixture_stubs(production_registry):
    assert all("tests.fixtures" not in callable_.__module__ for callable_ in production_registry.values())


def test_missing_db_initialization_becomes_technical_error(tmp_path):
    with pytest.raises(RetrievalSetupError):
        build_production_tool_registry(
            text_db_path=tmp_path / "missing-text.db",
            course_db_path=tmp_path / "missing-course.db",
        )


def test_default_ui_registry_uses_real_registry_builder(monkeypatch, text_db_path, course_db_path):
    monkeypatch.setattr(
        "agent.ui.build_production_tool_registry",
        lambda: build_production_tool_registry(
            text_db_path=text_db_path,
            course_db_path=course_db_path,
        ),
    )
    assert set(build_default_tool_registry()) == EXPECTED_TOOL_NAMES


def test_primary_provider_success_uses_no_fallback():
    primary = RecordingClient([FakeResponse([TextBlock("ok")], "end_turn")])
    secondary = RecordingClient([FakeResponse([TextBlock("fallback")], "end_turn")])
    manager = ProviderManager([
        ClientProvider("primary", primary),
        ClientProvider("secondary", secondary),
    ])

    response = manager.messages.create(model="ignored")

    assert response.content[0].text == "ok"
    assert len(primary.messages.calls) == 1
    assert secondary.messages.calls == []


def test_retryable_primary_provider_failure_falls_back_to_secondary():
    primary = RecordingClient(exc=TimeoutError("timeout"))
    secondary = RecordingClient([FakeResponse([TextBlock("ok")], "end_turn")])
    manager = ProviderManager([
        ClientProvider("primary", primary),
        ClientProvider("secondary", secondary),
    ])

    response = manager.messages.create(model="ignored")

    assert response.content[0].text == "ok"
    assert [entry["provider"] for entry in manager.attempt_log] == ["primary", "secondary"]


def test_secondary_can_fall_back_to_third_provider():
    first = RecordingClient(exc=RetryableProviderError("rate limit"))
    second = RecordingClient(exc=ConnectionError("network"))
    third = RecordingClient([FakeResponse([TextBlock("ok")], "end_turn")])
    manager = ProviderManager([
        ClientProvider("first", first),
        ClientProvider("second", second),
        ClientProvider("third", third),
    ])

    assert manager.messages.create(model="ignored").content[0].text == "ok"
    assert [entry["provider"] for entry in manager.attempt_log] == ["first", "second", "third"]


def test_valid_refusal_result_does_not_trigger_provider_failover():
    primary = RecordingClient([FakeResponse([TextBlock(REFUSAL_TEXT)], "end_turn")])
    secondary = RecordingClient([FakeResponse([TextBlock("fallback")], "end_turn")])
    manager = ProviderManager([
        ClientProvider("primary", primary),
        ClientProvider("secondary", secondary),
    ])

    assert manager.messages.create(model="ignored").content[0].text == REFUSAL_TEXT
    assert secondary.messages.calls == []


def test_non_retryable_configuration_failures_are_classified_correctly():
    assert classify_provider_exception(NonRetryableProviderError("bad key")) == "non_retryable"
    manager = ProviderManager([
        ClientProvider("primary", RecordingClient(exc=NonRetryableProviderError("bad key"))),
        ClientProvider("secondary", RecordingClient([FakeResponse([TextBlock("fallback")], "end_turn")])),
    ])

    with pytest.raises(NonRetryableProviderError):
        manager.messages.create(model="ignored")


def test_provider_api_keys_are_not_exposed_in_errors_or_attempt_logs():
    secret = "sk-ant-secret-value"
    manager = ProviderManager([
        ClientProvider("primary", RecordingClient(exc=RetryableProviderError(f"api_key={secret}"))),
    ])

    with pytest.raises(Exception) as exc:
        manager.messages.create(model="ignored")

    assert secret not in str(exc.value)
    assert secret not in repr(manager.attempt_log)
    assert "[redacted]" in repr(manager.attempt_log)


def test_no_configured_provider_fails_gracefully():
    with pytest.raises(ProviderConfigurationError):
        create_provider_manager(env={}, provider_factory=lambda config: None)


def test_existing_agent_caching_and_metrics_work_through_provider_abstraction(production_registry):
    provider = RecordingClient([
        FakeResponse(
            [ToolUseBlock("c1", "get_course", {"course_number": "0122407"})],
            "tool_use",
        ),
        FakeResponse([TextBlock("answer")], "end_turn"),
    ])
    manager = ProviderManager([ClientProvider("primary", provider)])

    result = answer_question(
        "question",
        client=manager,
        tool_registry=production_registry,
        max_iterations=5,
    )
    metrics = compute_metrics(result, policy=classify_outcome(result))

    assert result["status"] == "answered"
    assert metrics["tool_call_count"] == 1
    assert provider.messages.calls[0]["system"][-1]["cache_control"] == {"type": "ephemeral"}


def test_existing_ui_agent_path_works_with_production_registry(production_registry):
    client = RecordingClient([
        FakeResponse(
            [ToolUseBlock("c1", "get_course", {"course_number": "0122407"})],
            "tool_use",
        ),
        FakeResponse([TextBlock("answer")], "end_turn"),
    ])

    display = run_agent_for_ui(
        "question",
        client=client,
        tool_registry=production_registry,
    )

    assert display["kind"] == "answer"
    assert display["debug"]["metrics"]["tool_call_count"] == 1


def test_missing_retrieval_db_display_is_technical_not_refusal():
    display = prepare_display(
        {"status": "technical_error", "answer": None, "message": "missing prose index database"},
        loop_result={},
        metrics={},
    )

    assert display["kind"] == "technical_error"
    assert display["body"] != REFUSAL_TEXT
