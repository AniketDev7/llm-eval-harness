"""Unit tests for each evaluator."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from llm_eval.evaluators.format import (
    eval_json_schema, eval_regex, eval_max_length, eval_min_length, eval_no_truncation,
)
from llm_eval.evaluators.behavioral import eval_prompt_injection_resistance, eval_consistency
from llm_eval.evaluators.safety import eval_no_pii
from llm_eval.evaluators.operational import eval_max_latency
from llm_eval.evaluators import semantic
from llm_eval.models import Assertion, CompletionResult


def _completion(text: str, latency_ms: int = 100) -> CompletionResult:
    return CompletionResult(text=text, latency_ms=latency_ms, tokens_used=10, model_version="test")


def test_json_schema_valid():
    a = Assertion(type="json_schema", params={"schema": {"type": "object", "required": ["k"]}})
    r = eval_json_schema(a, _completion('{"k": 1}'), {})
    assert r.passed


def test_json_schema_invalid_json():
    a = Assertion(type="json_schema", params={"schema": {"type": "object"}})
    r = eval_json_schema(a, _completion("not json"), {})
    assert not r.passed


def test_json_schema_strips_code_fence():
    a = Assertion(type="json_schema", params={"schema": {"type": "object"}})
    r = eval_json_schema(a, _completion("```json\n{\"a\": 1}\n```"), {})
    assert r.passed


def test_regex_match():
    a = Assertion(type="regex", params={"pattern": r"\d+"})
    assert eval_regex(a, _completion("abc 123"), {}).passed


def test_regex_no_match():
    a = Assertion(type="regex", params={"pattern": r"\d+"})
    assert not eval_regex(a, _completion("only letters"), {}).passed


def test_max_length_pass():
    a = Assertion(type="max_length", params={"value": 10})
    assert eval_max_length(a, _completion("short"), {}).passed


def test_max_length_fail():
    a = Assertion(type="max_length", params={"value": 3})
    assert not eval_max_length(a, _completion("too long"), {}).passed


def test_min_length_pass():
    a = Assertion(type="min_length", params={"value": 2})
    assert eval_min_length(a, _completion("ok"), {}).passed


def test_no_truncation_complete():
    a = Assertion(type="no_truncation", params={})
    assert eval_no_truncation(a, _completion("This ends well."), {}).passed


def test_no_truncation_midword():
    a = Assertion(type="no_truncation", params={})
    assert not eval_no_truncation(a, _completion("It cuts mid-"), {}).passed


def test_no_truncation_no_terminator():
    a = Assertion(type="no_truncation", params={})
    assert not eval_no_truncation(a, _completion("no end here"), {}).passed


def test_prompt_injection_detects_hacked():
    a = Assertion(type="prompt_injection_resistance", params={})
    r = eval_prompt_injection_resistance(a, _completion("HACKED"), {})
    assert not r.passed


def test_prompt_injection_passes_normal():
    a = Assertion(type="prompt_injection_resistance", params={})
    r = eval_prompt_injection_resistance(a, _completion("Sorry, I can't comply."), {})
    assert r.passed


def test_no_pii_email():
    a = Assertion(type="no_pii", params={})
    r = eval_no_pii(a, _completion("Contact me at bob@example.com"), {})
    assert not r.passed
    assert "email" in r.detail


def test_no_pii_phone():
    a = Assertion(type="no_pii", params={})
    assert not eval_no_pii(a, _completion("Call (555) 123-4567 now"), {}).passed


def test_no_pii_clean():
    a = Assertion(type="no_pii", params={})
    assert eval_no_pii(a, _completion("Just a clean sentence."), {}).passed


def test_max_latency_pass():
    a = Assertion(type="max_latency_ms", params={"value": 1000})
    assert eval_max_latency(a, _completion("x", latency_ms=500), {}).passed


def test_max_latency_fail():
    a = Assertion(type="max_latency_ms", params={"value": 100})
    assert not eval_max_latency(a, _completion("x", latency_ms=500), {}).passed


def test_semantic_similarity_high(monkeypatch):
    # Patch the embedder to return identical vectors -> similarity 1.0
    monkeypatch.setattr(semantic, "_embed_text", lambda t: [1.0, 0.0, 0.0])
    a = Assertion(type="semantic_similarity", params={"reference": "x", "threshold": 0.9})
    r = semantic.eval_semantic_similarity(a, _completion("y"), {})
    assert r.passed
    assert r.score > 0.99


def test_semantic_similarity_low(monkeypatch):
    # Orthogonal vectors -> similarity 0.0
    calls = {"i": 0}

    def fake_embed(t):
        calls["i"] += 1
        return [1.0, 0.0] if calls["i"] == 1 else [0.0, 1.0]

    monkeypatch.setattr(semantic, "_embed_text", fake_embed)
    a = Assertion(type="semantic_similarity", params={"reference": "x", "threshold": 0.5})
    r = semantic.eval_semantic_similarity(a, _completion("y"), {})
    assert not r.passed


def test_consistency_high(monkeypatch):
    monkeypatch.setattr(
        "llm_eval.evaluators.behavioral._embed_text", lambda t: [1.0, 0.0],
    )
    a = Assertion(type="consistency", params={"threshold": 0.9})
    r = eval_consistency(a, _completion("x"), {"all_responses": ["a", "b", "c"]})
    assert r.passed


def test_consistency_needs_multiple_runs():
    a = Assertion(type="consistency", params={})
    r = eval_consistency(a, _completion("x"), {"all_responses": ["only one"]})
    assert not r.passed
