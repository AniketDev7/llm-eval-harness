"""Tests for RAGAS/DeepEval-style scorers with an injected fake judge."""
from llm_eval.metrics import (
    deep_equal,
    faithfulness_scored,
    task_completion,
    tool_correctness,
)
from llm_eval.models import CompletionResult, ToolCall


def fake_judge(reply_text: str):
    def _judge(system: str, user: str) -> CompletionResult:
        return CompletionResult(text=reply_text, latency_ms=1, model_version="fake")
    return _judge


def error_judge():
    def _judge(system: str, user: str) -> CompletionResult:
        return CompletionResult(text="", latency_ms=1, model_version="fake", error="boom")
    return _judge


def test_deep_equal_key_order_insensitive():
    assert deep_equal({"a": 1, "b": [1, 2]}, {"b": [1, 2], "a": 1})
    assert not deep_equal({"a": 1}, {"a": 2})
    assert not deep_equal([1, 2], [2, 1])


def test_tool_correctness_right_tool_and_args():
    calls = [ToolCall(name="get_x", arguments={"id": "5", "extra": "ok"})]
    res = tool_correctness(calls, "get_x", {"id": "5"})
    assert res.score == 1.0 and res.tool_called and not res.wrong_args


def test_tool_correctness_wrong_value():
    calls = [ToolCall(name="get_x", arguments={"id": "9"})]
    res = tool_correctness(calls, "get_x", {"id": "5"})
    assert res.score == 0.0 and res.wrong_args == ["id"]


def test_tool_correctness_missing_arg_and_never_called():
    calls = [ToolCall(name="get_x", arguments={})]
    assert tool_correctness(calls, "get_x", {"id": "5"}).missing == ["id"]
    assert tool_correctness([], "get_x", {}).score == 0.0


def test_tool_correctness_predicate():
    calls = [ToolCall(name="get_x", arguments={"uid": "abc123"})]
    res = tool_correctness(calls, "get_x", {"uid": lambda v: v.startswith("abc")})
    assert res.score == 1.0


def test_tool_correctness_errored_call_scores_zero():
    calls = [ToolCall(name="get_x", arguments={"id": "5"})]
    res = tool_correctness(calls, "get_x", {"id": "5"}, errored_tools={"get_x"})
    assert res.score == 0.0 and res.called_with_error


def test_faithfulness_all_supported():
    judge = fake_judge('[{"text": "a", "supported": true}, {"text": "b", "supported": true}]')
    res = faithfulness_scored("answer", "context", judge)
    assert res.score == 1.0 and res.total == 2


def test_faithfulness_one_fabricated():
    judge = fake_judge('[{"text": "a", "supported": true}, {"text": "b", "supported": false}]')
    res = faithfulness_scored("answer", "context", judge)
    assert res.score == 0.5 and res.unsupported == ["b"]


def test_faithfulness_empty_and_no_claims_return_none():
    assert faithfulness_scored("", "ctx", fake_judge("[]")).score is None
    assert faithfulness_scored("ans", "ctx", fake_judge("not json")).score is None
    assert faithfulness_scored("ans", "ctx", error_judge()).score is None


def test_task_completion_boolean_and_numeric():
    assert task_completion("g", "f", [], fake_judge('{"completed": true, "reason": "ok"}')).score == 1.0
    assert task_completion("g", "f", [], fake_judge('{"completed": false}')).score == 0.0
    clamped = task_completion("g", "f", [], fake_judge('{"completed": 1.7}'))
    assert clamped.score == 1.0


def test_task_completion_error_and_unparseable():
    assert task_completion("g", "f", [], error_judge()).score == 0.0
    assert task_completion("g", "f", [], fake_judge("garbage")).score == 0.0
