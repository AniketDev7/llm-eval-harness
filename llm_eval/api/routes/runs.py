"""Routes for running ad-hoc evals and listing past runs."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from llm_eval.adapters import get_adapter
from llm_eval.evaluators import REGISTRY
from llm_eval.models import (
    Assertion, AssertionResult, EvalCase, EvalResult, EvalSuite,
    ModelConfig, RunRecord, Thresholds,
)
from llm_eval.runner.runner import Runner
from llm_eval.scorer.scorer import score_run, evaluate_threshold
from llm_eval.storage.db import list_runs, get_run, get_results_for_run, save_run


router = APIRouter()


class ProviderConfig(BaseModel):
    name: str
    model: str | None = None


class RunRequest(BaseModel):
    prompt: str
    providers: list[ProviderConfig] = Field(default_factory=lambda: [ProviderConfig(name="openai")])
    assertions: list[dict[str, Any]] = Field(default_factory=list)
    model_config_settings: dict[str, Any] = Field(default_factory=dict)
    variables: dict[str, Any] = Field(default_factory=dict)


@router.post("/run")
def run_eval(req: RunRequest) -> dict:
    """Build a one-eval suite from the request and run it."""
    mc = ModelConfig(**req.model_config_settings) if req.model_config_settings else ModelConfig()
    assertions = [Assertion.from_dict(a) for a in req.assertions]
    case = EvalCase(
        name="playground_eval",
        category="format",
        prompt=req.prompt,
        variables=req.variables,
        assertions=assertions,
        runs=1,
    )

    # Slot key = "name (model)" so multiple entries of the same provider with
    # different models can coexist (e.g. anthropic Opus vs Sonnet side-by-side).
    def slot_key(p: ProviderConfig) -> str:
        return f"{p.name} ({p.model})" if p.model else p.name

    slots = [slot_key(p) for p in req.providers]
    suite = EvalSuite(
        name="playground",
        version="1.0",
        providers=slots,
        model_config_settings=mc,
        thresholds=Thresholds(),
        evals=[case],
    )

    from llm_eval.adapters import get_adapter
    adapters = {slot_key(p): get_adapter(p.name, model=p.model) for p in req.providers}

    runner = Runner(suite, adapters=adapters)
    try:
        records = runner.run()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc))

    for rec in records:
        save_run(rec)

    return {"runs": [r.model_dump() for r in records]}


@router.get("/runs")
def get_runs(page: int = 1, page_size: int = 20) -> dict:
    offset = (page - 1) * page_size
    rows = list_runs(limit=page_size, offset=offset)
    return {"runs": rows, "page": page, "page_size": page_size}


@router.get("/runs/{run_id}")
def get_run_detail(run_id: str) -> dict:
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    results = get_results_for_run(run_id)
    return {"run": run, "results": results}
