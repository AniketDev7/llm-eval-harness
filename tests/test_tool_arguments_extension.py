"""Tests for the extended tool_arguments (subset + declarative predicates)."""
from llm_eval.evaluators.agent import eval_tool_arguments
from llm_eval.judge import extract_json
from llm_eval.models import Assertion, CompletionResult, ToolCall


def completion(name: str, arguments: dict) -> CompletionResult:
    return CompletionResult(
        text="", latency_ms=1, model_version="m",
        tool_calls=[ToolCall(name=name, arguments=arguments)],
    )


def assertion(**params) -> Assertion:
    return Assertion(type="tool_arguments", params=params)


def test_expected_subset_literal_match():
    res = eval_tool_arguments(
        assertion(name="get_x", expected={"id": "5"}),
        completion("get_x", {"id": "5", "extra": "fine"}), {},
    )
    assert res.passed


def test_expected_wrong_literal():
    res = eval_tool_arguments(
        assertion(name="get_x", expected={"id": "5"}),
        completion("get_x", {"id": "9"}), {},
    )
    assert not res.passed


def test_predicate_pattern_and_one_of_and_type():
    call = completion("get_x", {"uid": "abc_123", "kind": "entry", "n": 3})
    res = eval_tool_arguments(
        assertion(name="get_x", expected={
            "uid": {"pattern": "^[a-z0-9_]+$"},
            "kind": {"one_of": ["entry", "asset"]},
            "n": {"type": "integer"},
        }),
        call, {},
    )
    assert res.passed


def test_predicate_type_rejects_bool_as_integer():
    res = eval_tool_arguments(
        assertion(name="get_x", expected={"n": {"type": "integer"}}),
        completion("get_x", {"n": True}), {},
    )
    assert not res.passed


def test_missing_arg_fails():
    res = eval_tool_arguments(
        assertion(name="get_x", expected={"id": "5"}),
        completion("get_x", {}), {},
    )
    assert not res.passed


def test_schema_mode_still_works():
    res = eval_tool_arguments(
        assertion(name="get_x", schema={"type": "object", "required": ["id"]}),
        completion("get_x", {"id": "5"}), {},
    )
    assert res.passed


def test_requires_schema_or_expected():
    res = eval_tool_arguments(
        assertion(name="get_x"),
        completion("get_x", {"id": "5"}), {},
    )
    assert not res.passed


def test_extract_json_handles_fences_and_embedded():
    assert extract_json("```json\n{\"a\": 1}\n```") == {"a": 1}
    assert extract_json("noise [1, 2] trailing") == [1, 2]
    assert extract_json("nothing here") is None
