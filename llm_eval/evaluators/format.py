"""Format evaluators: structural checks on the response text."""
from __future__ import annotations

import json
import re
from typing import Any

import jsonschema

from llm_eval.models import Assertion, AssertionResult, CompletionResult


def eval_json_schema(assertion: Assertion, result: CompletionResult, context: dict) -> AssertionResult:
    """Try to parse the response as JSON and validate against a schema."""
    schema = assertion.params.get("schema")
    text = result.text.strip()
    # Strip code fences if present (LLMs love wrapping JSON in ```json blocks)
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return AssertionResult(
            type=assertion.type, passed=False, score=0.0,
            detail=f"Invalid JSON: {exc}",
        )

    if schema is None:
        return AssertionResult(
            type=assertion.type, passed=True, score=1.0,
            detail="Valid JSON (no schema provided)",
        )

    try:
        jsonschema.validate(instance=data, schema=schema)
        return AssertionResult(
            type=assertion.type, passed=True, score=1.0,
            detail="Valid JSON matches schema",
        )
    except jsonschema.ValidationError as exc:
        return AssertionResult(
            type=assertion.type, passed=False, score=0.0,
            detail=f"Schema mismatch: {exc.message}",
        )


def eval_regex(assertion: Assertion, result: CompletionResult, context: dict) -> AssertionResult:
    pattern = assertion.params.get("pattern", "")
    flags = re.DOTALL | re.MULTILINE
    match = re.search(pattern, result.text, flags=flags)
    if match:
        return AssertionResult(
            type=assertion.type, passed=True, score=1.0,
            detail=f"Regex matched: {match.group(0)[:80]}",
        )
    return AssertionResult(
        type=assertion.type, passed=False, score=0.0,
        detail=f"Regex did not match: {pattern}",
    )


def eval_max_length(assertion: Assertion, result: CompletionResult, context: dict) -> AssertionResult:
    limit = int(assertion.params.get("value", 1000))
    length = len(result.text)
    passed = length <= limit
    return AssertionResult(
        type=assertion.type, passed=passed, score=1.0 if passed else 0.0,
        detail=f"Length {length} {'<=' if passed else '>'} max {limit}",
    )


def eval_min_length(assertion: Assertion, result: CompletionResult, context: dict) -> AssertionResult:
    limit = int(assertion.params.get("value", 0))
    length = len(result.text)
    passed = length >= limit
    return AssertionResult(
        type=assertion.type, passed=passed, score=1.0 if passed else 0.0,
        detail=f"Length {length} {'>=' if passed else '<'} min {limit}",
    )


def eval_no_truncation(assertion: Assertion, result: CompletionResult, context: dict) -> AssertionResult:
    """Heuristic: does the response look truncated?

    We check:
      1. The final non-whitespace character is sentence-ending punctuation,
         a closing bracket/brace, or a quote.
      2. The last token isn't obviously mid-word (no trailing hyphen, etc.).
    """
    text = result.text.rstrip()
    if not text:
        return AssertionResult(
            type=assertion.type, passed=False, score=0.0,
            detail="Empty response",
        )

    last_char = text[-1]
    end_chars = set(".!?\"')]}>`")
    ends_ok = last_char in end_chars

    # Mid-word cutoff heuristic: last word should not be very short or look broken.
    last_word = text.split()[-1] if text.split() else ""
    looks_mid_word = last_word.endswith("-")

    passed = ends_ok and not looks_mid_word
    detail = (
        f"Ends with '{last_char}'" if passed else
        f"Looks truncated (last_char='{last_char}', last_word='{last_word[:20]}')"
    )
    return AssertionResult(
        type=assertion.type, passed=passed, score=1.0 if passed else 0.0,
        detail=detail,
    )
