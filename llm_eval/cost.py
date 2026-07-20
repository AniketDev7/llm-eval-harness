"""Token/USD accounting and a budget circuit breaker.

A run against a strong model over many cases can get expensive fast. The guard
accumulates spend as cases complete and stops launching new work once a cap is
reached. A cap is an intentional ceiling, not a failure: partial runs finish
cleanly rather than crashing.

Pure and standalone — no provider SDK imported here. Prices are approximate
public per-token rates in USD, used only for estimation.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


# Approximate USD per 1M tokens (input, output). Estimation only.
_PRICES: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "claude-3-5-haiku": (0.80, 4.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-sonnet-4": (3.00, 15.00),
    "claude-opus-4-7": (15.00, 75.00),
    "claude-opus-4-8": (15.00, 75.00),
}
_FALLBACK_PRICE = (1.00, 5.00)


def price_for(model: str) -> tuple[float, float]:
    """Return (input, output) USD-per-1M-token rate for a model string.

    Matches on the longest known prefix so version suffixes
    (e.g. ``claude-haiku-4-5-20251001``) resolve to their family price.
    """
    model = (model or "").lower()
    best: tuple[float, float] | None = None
    best_len = -1
    for key, price in _PRICES.items():
        if model.startswith(key) and len(key) > best_len:
            best, best_len = price, len(key)
    return best if best is not None else _FALLBACK_PRICE


def cost_of(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost of one call from its token counts."""
    in_rate, out_rate = price_for(model)
    return (input_tokens / 1_000_000) * in_rate + (output_tokens / 1_000_000) * out_rate


def estimate_cost(model: str, total_tokens: int, output_ratio: float = 0.5) -> float:
    """Estimate cost when only a combined token count is available.

    Adapters report input+output combined, so we split by ``output_ratio`` to
    apply the (usually higher) output rate. Estimation only — for budget gating,
    not billing.
    """
    total = max(0, int(total_tokens or 0))
    out_tok = int(total * output_ratio)
    in_tok = total - out_tok
    return cost_of(model, in_tok, out_tok)


class BudgetExceededError(Exception):
    """Raised when a guard is asked to admit work beyond its cap."""


@dataclass
class CostGuard:
    """Accumulates spend and reports whether a cap has been reached.

    ``max_usd <= 0`` means uncapped: ``exceeded()`` is always False and
    ``remaining()`` is infinite. This keeps existing runs backward-compatible.
    """

    max_usd: float = 0.0
    _spent: float = field(default=0.0, init=False)
    _blocked: int = field(default=0, init=False)

    @property
    def capped(self) -> bool:
        return self.max_usd > 0

    def add(self, usd: float) -> float:
        """Record spend. Non-numeric values are ignored. Returns new total."""
        try:
            amount = float(usd)
        except (TypeError, ValueError):
            amount = 0.0
        if amount != amount:  # NaN
            amount = 0.0
        self._spent += amount
        return self._spent

    def spent(self) -> float:
        return round(self._spent, 6)

    def remaining(self) -> float:
        if not self.capped:
            return float("inf")
        return max(0.0, self.max_usd - self._spent)

    def exceeded(self) -> bool:
        return self.capped and self._spent >= self.max_usd

    def check(self) -> None:
        """Raise BudgetExceededError if the cap has been reached."""
        if self.exceeded():
            raise BudgetExceededError(
                f"budget cap of ${self.max_usd:.4f} reached (spent ${self.spent():.4f})"
            )

    def note_blocked(self, n: int = 1) -> None:
        """Count a unit of work skipped because the cap was hit."""
        self._blocked += max(0, int(n))

    def blocked(self) -> int:
        return self._blocked

    def summary(self) -> str:
        if not self.capped:
            return f"spent ${self.spent():.4f} (uncapped)"
        line = f"spent ${self.spent():.4f} / cap ${self.max_usd:.4f}"
        if self._blocked:
            line += f" — {self._blocked} unit(s) skipped after cap"
        return line


def guard_from_env(explicit: float | None = None) -> CostGuard:
    """Build a CostGuard from an explicit value or the LLM_EVAL_MAX_USD env var."""
    if explicit is not None:
        return CostGuard(max_usd=max(0.0, explicit))
    raw = os.getenv("LLM_EVAL_MAX_USD", "0")
    try:
        return CostGuard(max_usd=max(0.0, float(raw)))
    except (TypeError, ValueError):
        return CostGuard(max_usd=0.0)
