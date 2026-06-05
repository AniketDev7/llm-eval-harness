"""Routes for fetching per-run results."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from llm_eval.storage.db import get_results_for_run, get_run

router = APIRouter()


@router.get("/results/{run_id}")
def get_results(run_id: str) -> dict:
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return {
        "run": run,
        "results": get_results_for_run(run_id),
    }
