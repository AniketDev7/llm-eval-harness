"""Trend history: last 8 runs of composite score, per provider."""
from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter

from llm_eval.storage.db import list_runs


router = APIRouter()


@router.get("/history")
def history(limit: int = 8) -> dict:
    """Return last N runs grouped by provider for trend charts."""
    runs = list_runs(limit=limit * 4)  # over-fetch then group
    by_provider: dict[str, list[dict]] = defaultdict(list)
    for r in runs:
        if len(by_provider[r["provider"]]) < limit:
            by_provider[r["provider"]].append({
                "timestamp": r["timestamp"],
                "composite_score": r["composite_score"],
                "threshold_status": r["threshold_status"],
                "suite_name": r["suite_name"],
                "run_id": r["id"],
            })
    # Reverse each so oldest-first for charting.
    for provider in by_provider:
        by_provider[provider] = list(reversed(by_provider[provider]))
    return {"history": by_provider}
