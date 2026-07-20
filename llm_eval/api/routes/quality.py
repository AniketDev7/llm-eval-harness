"""Risk and assertion-level regression API routes."""
from fastapi import APIRouter, HTTPException

from llm_eval.api.routes.export import _reconstruct
from llm_eval.quality import assess_risk, compare_run_records
from llm_eval.storage.db import get_audit_results_for_run, get_results_for_run, get_run


router = APIRouter()


def _load(run_id: str):
    row = get_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return _reconstruct(row, get_results_for_run(run_id), get_audit_results_for_run(run_id))


@router.get("/risk/{run_id}")
def risk(run_id: str) -> dict:
    return assess_risk(_load(run_id)).model_dump()


@router.get("/regression")
def regression(baseline_run: str, candidate_run: str, tolerance: float = 0.05) -> dict:
    try:
        report = compare_run_records(_load(baseline_run), _load(candidate_run), tolerance)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return report.model_dump()
