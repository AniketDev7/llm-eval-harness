"""JSON reporter: dumps a RunRecord to a JSON file."""
from __future__ import annotations

import json
import os
from pathlib import Path

from llm_eval.models import RunRecord


def write_json(record: RunRecord, out_dir: str | None = None) -> str:
    """Write the RunRecord as pretty JSON. Returns the file path."""
    out_dir = out_dir or os.getenv("LLM_EVAL_REPORTS_DIR", "./reports")
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    path = Path(out_dir) / f"run_{record.id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record.model_dump(), f, indent=2)
    return str(path)
