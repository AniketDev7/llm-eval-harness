"""Tests for structured agent and tool-call assertions."""
from llm_eval.evaluators import REGISTRY
from llm_eval.models import AgentStep, Assertion, CompletionResult, ToolCall


def completion() -> CompletionResult:
    return CompletionResult(
        text="Done",
        latency_ms=10,
        tool_calls=[
            ToolCall(name="lookup", arguments={"id": "42"}),
            ToolCall(name="delete_record", arguments={"id": "42"}),
        ],
        trajectory=[
            AgentStep(kind="tool_call", name="lookup", success=True),
            AgentStep(kind="user_confirmation", success=True),
            AgentStep(kind="tool_call", name="delete_record", success=False),
            AgentStep(kind="tool_call", name="restore_record", success=True),
            AgentStep(kind="final", content="Recovered"),
        ],
    )


def evaluate(kind: str, **params):
    assertion = Assertion(type=kind, params=params)
    return REGISTRY[kind](assertion, completion(), {})


def test_tool_selection_arguments_and_order():
    assert evaluate("tool_selected", name="lookup").passed
    assert evaluate("tool_not_called", name="send_email").passed
    assert evaluate(
        "tool_arguments",
        name="lookup",
        schema={"type": "object", "required": ["id"]},
    ).passed
    assert evaluate("tool_call_order", expected=["lookup", "delete_record"]).passed


def test_confirmation_completion_and_recovery():
    assert evaluate("requires_confirmation", tool="delete_record").passed
    assert evaluate("trajectory_completed").passed
    assert evaluate("recovered_after_error").passed
    assert evaluate("max_tool_calls", value=2).passed


def test_destructive_tool_without_confirmation_fails():
    result = completion()
    result.trajectory = [AgentStep(kind="tool_call", name="delete_record")]
    assertion = Assertion(type="requires_confirmation", params={"tool": "delete_record"})
    assert not REGISTRY[assertion.type](assertion, result, {}).passed
