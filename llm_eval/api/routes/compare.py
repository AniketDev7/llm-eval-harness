"""Side-by-side run comparison."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from llm_eval.storage.db import get_run, get_results_for_run


router = APIRouter()


@router.get("/compare")
def compare(run_a: str, run_b: str) -> dict:
    a = get_run(run_a)
    b = get_run(run_b)
    if not a or not b:
        raise HTTPException(status_code=404, detail="One or both runs not found")
    return {
        "run_a": {"run": a, "results": get_results_for_run(run_a)},
        "run_b": {"run": b, "results": get_results_for_run(run_b)},
    }
