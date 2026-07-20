"""RAGAS / DeepEval-style scorers.

Pure functions with an injected ``judge_fn`` so the LLM is never imported here
and every scorer is unit-testable with a fake judge. ``judge_fn`` takes
``(system, user)`` and returns a :class:`CompletionResult`; in production pass
:func:`llm_eval.judge.judge_complete`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from llm_eval.judge import extract_json
from llm_eval.models import CompletionResult, ToolCall

JudgeFn = Callable[[str, str], CompletionResult]


def deep_equal(a: Any, b: Any) -> bool:
    """Recursive structural equality, order-insensitive on dict keys."""
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(deep_equal(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            return False
        return all(deep_equal(x, y) for x, y in zip(a, b))
    return a == b


@dataclass
class ToolCorrectnessResult:
    score: float
    tool_called: bool
    called_with_error: bool
    missing: list[str] = field(default_factory=list)
    wrong_args: list[str] = field(default_factory=list)
    detail: str = ""


def tool_correctness(
    tool_calls: list[ToolCall],
    expected_tool: str,
    expected_args: Optional[dict[str, Any]] = None,
    *,
    errored_tools: Optional[set[str]] = None,
) -> ToolCorrectnessResult:
    """DeepEval "Tool Correctness": right tool with the right arguments.

    Arg matching is a SUBSET check — every expected arg must be present with a
    matching value; extra actual args are fine. Each expected value may be a
    literal (compared with :func:`deep_equal`) OR a predicate ``(value) -> bool``
    (e.g. "must be a UID the agent actually discovered"). A call that errored
    scores 0 even when its arguments matched.
    """
    expected_args = expected_args or {}
    errored_tools = errored_tools or set()

    call = next((c for c in tool_calls if c.name == expected_tool), None)
    if call is None:
        return ToolCorrectnessResult(
            score=0.0, tool_called=False, called_with_error=False,
            detail=f"tool {expected_tool!r} was never called",
        )

    called_with_error = expected_tool in errored_tools
    missing: list[str] = []
    wrong: list[str] = []
    for key, expected in expected_args.items():
        if key not in call.arguments:
            missing.append(key)
            continue
        actual = call.arguments[key]
        if callable(expected):
            if not expected(actual):
                wrong.append(key)
        elif not deep_equal(actual, expected):
            wrong.append(key)

    args_ok = not missing and not wrong
    score = 1.0 if (args_ok and not called_with_error) else 0.0
    if called_with_error:
        detail = f"{expected_tool!r} called but errored"
    elif not args_ok:
        detail = f"{expected_tool!r} arg mismatch (missing={missing}, wrong={wrong})"
    else:
        detail = f"{expected_tool!r} called with correct args"
    return ToolCorrectnessResult(
        score=score, tool_called=True, called_with_error=called_with_error,
        missing=missing, wrong_args=wrong, detail=detail,
    )


@dataclass
class FaithfulnessResult:
    score: Optional[float]
    supported: int
    total: int
    unsupported: list[str] = field(default_factory=list)
    detail: str = ""


def faithfulness_scored(
    answer: str,
    context: str,
    judge_fn: JudgeFn,
) -> FaithfulnessResult:
    """RAGAS faithfulness via atomic-claim decomposition.

    The judge decomposes the answer into atomic factual claims and marks each
    as supported by the context (tool results = ground truth). Score is
    supported/total. Returns ``score=None`` when there is no answer or no
    extractable claim so the caller can skip rather than score 0.
    """
    if not answer or not answer.strip():
        return FaithfulnessResult(score=None, supported=0, total=0, detail="empty answer")

    system = (
        "You verify factual grounding. Decompose the ANSWER into atomic factual "
        "claims, then judge each claim against the CONTEXT. Reply with ONLY a JSON "
        'array of objects like [{"text": "...", "supported": true}].'
    )
    user = f"CONTEXT:\n{context}\n\nANSWER:\n{answer}"
    reply = judge_fn(system, user)
    if reply.error:
        return FaithfulnessResult(score=None, supported=0, total=0, detail=f"judge error: {reply.error}")

    claims = extract_json(reply.text)
    if not isinstance(claims, list) or not claims:
        return FaithfulnessResult(score=None, supported=0, total=0, detail="no claims decomposed")

    total = 0
    supported = 0
    unsupported: list[str] = []
    for claim in claims:
        if not isinstance(claim, dict) or "supported" not in claim:
            continue
        total += 1
        if bool(claim.get("supported")):
            supported += 1
        else:
            unsupported.append(str(claim.get("text", ""))[:120])
    if total == 0:
        return FaithfulnessResult(score=None, supported=0, total=0, detail="no gradable claims")

    score = supported / total
    return FaithfulnessResult(
        score=score, supported=supported, total=total, unsupported=unsupported,
        detail=f"{supported}/{total} claims grounded",
    )


@dataclass
class TaskCompletionResult:
    score: float
    completed: bool
    reason: str = ""


def task_completion(
    goal: str,
    final_text: str,
    tool_calls: list[ToolCall],
    judge_fn: JudgeFn,
) -> TaskCompletionResult:
    """DeepEval "Task Completion": outcome-focused, not path-mandated.

    Judges whether the agent achieved the stated GOAL given its final answer and
    the tools it called. The verdict may be boolean or a 0..1 number (clamped).
    A run can call the right tool yet fail the task, or complete by an
    unexpected route.
    """
    tools_summary = ", ".join(c.name for c in tool_calls) or "(none)"
    system = (
        "You judge whether an agent achieved a goal. Consider the GOAL, the "
        "agent's FINAL answer, and the TOOLS it called. Reply with ONLY JSON "
        '{"completed": <0..1 or true/false>, "reason": "..."}.'
    )
    user = f"GOAL:\n{goal}\n\nTOOLS CALLED: {tools_summary}\n\nFINAL:\n{final_text}"
    reply = judge_fn(system, user)
    if reply.error:
        return TaskCompletionResult(score=0.0, completed=False, reason=f"judge error: {reply.error}")

    parsed = extract_json(reply.text)
    if not isinstance(parsed, dict) or "completed" not in parsed:
        return TaskCompletionResult(score=0.0, completed=False, reason="unparseable judge verdict")

    verdict = parsed["completed"]
    if isinstance(verdict, bool):
        score = 1.0 if verdict else 0.0
    else:
        try:
            score = max(0.0, min(1.0, float(verdict)))
        except (TypeError, ValueError):
            return TaskCompletionResult(score=0.0, completed=False, reason="non-numeric verdict")
    return TaskCompletionResult(
        score=score, completed=score >= 0.5, reason=str(parsed.get("reason", ""))[:200],
    )
