"""Tests for the budget circuit breaker and cost estimation."""
import pytest

from llm_eval.cost import (
    CostGuard,
    cost_of,
    estimate_cost,
    guard_from_env,
    price_for,
)


def test_uncapped_guard_never_blocks():
    guard = CostGuard(max_usd=0)
    guard.add(1000.0)
    assert not guard.exceeded()
    assert guard.remaining() == float("inf")
    guard.check()  # does not raise


def test_accumulation_and_remaining():
    guard = CostGuard(max_usd=1.0)
    guard.add(0.25)
    guard.add(0.25)
    assert guard.spent() == pytest.approx(0.5)
    assert guard.remaining() == pytest.approx(0.5)
    assert not guard.exceeded()


def test_trips_at_cap_and_clamps_remaining():
    guard = CostGuard(max_usd=1.0)
    guard.add(1.5)
    assert guard.exceeded()
    assert guard.remaining() == 0.0
    with pytest.raises(Exception):
        guard.check()


def test_note_blocked_counts_skipped_work():
    guard = CostGuard(max_usd=0.01)
    guard.add(0.02)
    guard.note_blocked(3)
    assert guard.blocked() == 3
    assert "skipped" in guard.summary()


def test_non_numeric_adds_ignored():
    guard = CostGuard(max_usd=1.0)
    guard.add(None)
    guard.add(float("nan"))
    guard.add("oops")
    assert guard.spent() == 0.0


def test_price_prefix_match_resolves_versioned_model():
    assert price_for("claude-haiku-4-5-20251001") == price_for("claude-haiku-4-5")
    # Unknown model falls back rather than raising.
    assert price_for("totally-unknown") == price_for("")


def test_cost_and_estimate_are_positive():
    assert cost_of("gpt-4o", 1000, 1000) > 0
    blended = estimate_cost("gpt-4o", 2000, output_ratio=0.5)
    assert blended == pytest.approx(cost_of("gpt-4o", 1000, 1000))


def test_guard_from_env(monkeypatch):
    monkeypatch.setenv("LLM_EVAL_MAX_USD", "2.5")
    assert guard_from_env().max_usd == 2.5
    monkeypatch.setenv("LLM_EVAL_MAX_USD", "not-a-number")
    assert guard_from_env().max_usd == 0.0
    assert guard_from_env(explicit=4.0).max_usd == 4.0
