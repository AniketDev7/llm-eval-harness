"""Export a run as JSON or HTML."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from llm_eval.models import AssertionResult, CompletionResult, EvalResult, RunRecord
from llm_eval.reporters.html_reporter import write_html
from llm_eval.reporters.json_reporter import write_json
from llm_eval.storage.db import get_audit_results_for_run, get_run, get_results_for_run


router = APIRouter()


def _reconstruct(
    run_row: dict,
    result_rows: list[dict],
    audit_rows: list[dict] | None = None,
) -> RunRecord:
    """Build a RunRecord from raw DB rows (results table is flattened per-assertion)."""
    if audit_rows:
        exact_results: list[EvalResult] = []
        for row in audit_rows:
            exact_results.append(EvalResult(
                eval_name=row["eval_name"],
                category=row["category"],
                provider=row["provider"],
                prompt=row["prompt"],
                response=row["response_text"],
                latency_ms=row["latency_ms"],
                tokens_used=row["tokens_used"],
                model_version=row["model_version"],
                error=row["error"],
                assertions=[AssertionResult(
                    type=a["assertion_type"],
                    passed=bool(a["assertion_passed"]),
                    score=a["assertion_score"],
                    detail=a["assertion_detail"],
                ) for a in row["assertions"]],
                completions=[CompletionResult(
                    text=c["response_text"],
                    latency_ms=c["latency_ms"],
                    tokens_used=c["tokens_used"],
                    model_version=c["model_version"],
                    error=c["error"],
                    tool_calls=c.get("tool_calls", []),
                    trajectory=c.get("trajectory", []),
                ) for c in row["completions"]],
            ))
        return _record_from_results(run_row, exact_results)

    by_eval: dict[str, EvalResult] = {}
    for r in result_rows:
        key = r["eval_name"]
        if key not in by_eval:
            by_eval[key] = EvalResult(
                eval_name=r["eval_name"],
                category=r["category"],
                provider=r["provider"],
                prompt=r["prompt"],
                response=r["response_text"],
                latency_ms=r["latency_ms"],
                tokens_used=r["tokens_used"],
                assertions=[],
            )
        by_eval[key].assertions.append(AssertionResult(
            type=r["assertion_type"],
            passed=bool(r["assertion_passed"]),
            score=r["assertion_score"],
            detail=r["assertion_detail"],
        ))

    return _record_from_results(run_row, list(by_eval.values()))


def _record_from_results(run_row: dict, results: list[EvalResult]) -> RunRecord:
    return RunRecord(
        id=run_row["id"],
        timestamp=run_row["timestamp"],
        suite_name=run_row["suite_name"],
        suite_version=run_row["suite_version"],
        provider=run_row["provider"],
        model=run_row.get("model", ""),
        composite_score=run_row["composite_score"],
        coverage_score=run_row["coverage_score"],
        accuracy_score=run_row["accuracy_score"],
        format_score=run_row["format_score"],
        hallucination_score=run_row["hallucination_score"],
        threshold_status=run_row["threshold_status"],
        results=results,
    )


@router.get("/export/{run_id}")
def export(run_id: str, format: str = "json"):
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    results = get_results_for_run(run_id)
    record = _reconstruct(run, results, get_audit_results_for_run(run_id))

    if format == "html":
        path = write_html(record)
        return FileResponse(path, media_type="text/html", filename=Path(path).name)
    if format == "json":
        path = write_json(record)
        return FileResponse(path, media_type="application/json", filename=Path(path).name)
    raise HTTPException(status_code=400, detail="format must be json|html")
