"""
Owner: Person 3

Tests for agent/tool_defs.py: tool JSON schemas and the name->callable
dispatch mechanism, per SPEC.md section 5.
"""

import pytest

from agent.tool_defs import TOOL_DEFINITIONS, dispatch_tool_call

EXPECTED_TOOL_NAMES = {
    "list_sections",
    "get_section",
    "search",
    "list_curricula",
    "get_course_table",
    "get_course",
}


def test_tool_definitions_cover_exactly_the_expected_tool_family():
    names = {tool["name"] for tool in TOOL_DEFINITIONS}
    assert names == EXPECTED_TOOL_NAMES


def test_each_tool_definition_has_anthropic_tool_shape():
    for tool in TOOL_DEFINITIONS:
        assert isinstance(tool["name"], str) and tool["name"]
        assert isinstance(tool["description"], str) and tool["description"]
        schema = tool["input_schema"]
        assert schema["type"] == "object"
        assert isinstance(schema["properties"], dict)
        assert isinstance(schema.get("required", []), list)


def _tool_by_name(name):
    return next(tool for tool in TOOL_DEFINITIONS if tool["name"] == name)


def test_list_sections_takes_no_parameters():
    schema = _tool_by_name("list_sections")["input_schema"]
    assert schema["properties"] == {}
    assert schema.get("required", []) == []


def test_list_curricula_takes_no_parameters():
    schema = _tool_by_name("list_curricula")["input_schema"]
    assert schema["properties"] == {}
    assert schema.get("required", []) == []


def test_get_section_requires_section_id():
    schema = _tool_by_name("get_section")["input_schema"]
    assert "section_id" in schema["properties"]
    assert schema["properties"]["section_id"]["type"] == "string"
    assert schema["required"] == ["section_id"]


def test_search_requires_query_and_has_optional_limit():
    schema = _tool_by_name("search")["input_schema"]
    assert schema["properties"]["query"]["type"] == "string"
    assert schema["properties"]["limit"]["type"] == "integer"
    assert schema["required"] == ["query"]


def test_get_course_table_requires_curriculum_year_semester():
    schema = _tool_by_name("get_course_table")["input_schema"]
    assert set(schema["required"]) == {"curriculum", "year", "semester"}
    assert schema["properties"]["year"]["type"] == "integer"
    assert schema["properties"]["semester"]["type"] == "integer"
    assert schema["properties"]["curriculum"]["type"] == "string"


def test_get_course_requires_course_number():
    schema = _tool_by_name("get_course")["input_schema"]
    assert "course_number" in schema["properties"]
    assert schema["required"] == ["course_number"]


def test_dispatch_calls_registered_tool_with_arguments():
    registry = {"search": lambda query, limit=5: {"query": query, "limit": limit}}
    result = dispatch_tool_call("search", {"query": "אלגוריתמים"}, registry)
    assert result == {"query": "אלגוריתמים", "limit": 5}


def test_dispatch_unknown_tool_name_fails_safely():
    result = dispatch_tool_call("delete_everything", {}, registry={})
    assert result["error"] == "unknown_tool"
    assert result["tool_name"] == "delete_everything"


def test_dispatch_tool_exception_fails_safely():
    def boom(**kwargs):
        raise RuntimeError("db is locked")

    registry = {"search": boom}
    result = dispatch_tool_call("search", {"query": "x"}, registry)
    assert result["error"] == "tool_exception"
    assert "db is locked" in result["message"]
