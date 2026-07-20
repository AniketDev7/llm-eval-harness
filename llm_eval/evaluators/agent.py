"""Structured tool-call and agent-trajectory evaluators."""
from __future__ import annotations

import jsonschema

from llm_eval.models import Assertion, AssertionResult, CompletionResult, ToolCall


def _result(assertion: Assertion, passed: bool, detail: str) -> AssertionResult:
    return AssertionResult(
        type=assertion.type,
        passed=passed,
        score=1.0 if passed else 0.0,
        detail=detail,
    )


def _tool_calls(completion: CompletionResult) -> list[ToolCall]:
    if completion.tool_calls:
        return completion.tool_calls
    return [
        ToolCall(name=step.name)
        for step in completion.trajectory
        if step.kind == "tool_call" and step.name
    ]


def eval_tool_selected(assertion: Assertion, result: CompletionResult, context: dict) -> AssertionResult:
    expected = str(assertion.params.get("name", ""))
    names = [call.name for call in _tool_calls(result)]
    return _result(assertion, expected in names, f"Expected tool {expected!r}; observed {names}")


def eval_tool_not_called(assertion: Assertion, result: CompletionResult, context: dict) -> AssertionResult:
    forbidden = str(assertion.params.get("name", ""))
    names = [call.name for call in _tool_calls(result)]
    return _result(assertion, forbidden not in names, f"Forbidden tool {forbidden!r}; observed {names}")


def eval_tool_arguments(assertion: Assertion, result: CompletionResult, context: dict) -> AssertionResult:
    name = str(assertion.params.get("name", ""))
    schema = assertion.params.get("schema")
    call = next((item for item in _tool_calls(result) if item.name == name), None)
    if call is None:
        return _result(assertion, False, f"Tool {name!r} was not called")
    if not isinstance(schema, dict):
        return _result(assertion, False, "tool_arguments requires a JSON schema")
    try:
        jsonschema.validate(call.arguments, schema)
    except jsonschema.ValidationError as exc:
        return _result(assertion, False, f"Arguments for {name!r} failed schema: {exc.message}")
    return _result(assertion, True, f"Arguments for {name!r} match schema")


def eval_tool_call_order(assertion: Assertion, result: CompletionResult, context: dict) -> AssertionResult:
    expected = [str(item) for item in assertion.params.get("expected", [])]
    observed = [call.name for call in _tool_calls(result)]
    allow_extra = bool(assertion.params.get("allow_extra", False))
    matches = observed[:len(expected)] == expected if allow_extra else observed == expected
    return _result(assertion, matches, f"Expected order {expected}; observed {observed}")


def eval_requires_confirmation(assertion: Assertion, result: CompletionResult, context: dict) -> AssertionResult:
    tool_name = str(assertion.params.get("tool", ""))
    confirmed = False
    for step in result.trajectory:
        if step.kind == "user_confirmation" and step.success is True:
            confirmed = True
        if step.kind == "tool_call" and step.name == tool_name:
            return _result(
                assertion,
                confirmed,
                f"Tool {tool_name!r} was {'properly preceded by' if confirmed else 'called without'} confirmation",
            )
    return _result(assertion, True, f"Tool {tool_name!r} was not called")


def eval_max_tool_calls(assertion: Assertion, result: CompletionResult, context: dict) -> AssertionResult:
    limit = int(assertion.params.get("value", 10))
    count = len(_tool_calls(result))
    return _result(assertion, count <= limit, f"Observed {count} tool calls; maximum {limit}")


def eval_trajectory_completed(assertion: Assertion, result: CompletionResult, context: dict) -> AssertionResult:
    completed = bool(result.trajectory) and result.trajectory[-1].kind in {"final", "completed"}
    return _result(assertion, completed, "Trajectory completed" if completed else "Trajectory has no final step")


def eval_recovered_after_error(assertion: Assertion, result: CompletionResult, context: dict) -> AssertionResult:
    failure_index = next(
        (i for i, step in enumerate(result.trajectory) if step.success is False),
        None,
    )
    if failure_index is None:
        return _result(assertion, False, "Trajectory contains no observable failure")
    recovered = any(
        step.success is True or step.kind in {"final", "completed"}
        for step in result.trajectory[failure_index + 1:]
    )
    return _result(assertion, recovered, "Agent recovered after failure" if recovered else "Agent did not recover after failure")
