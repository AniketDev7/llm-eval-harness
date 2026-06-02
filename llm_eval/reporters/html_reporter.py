"""HTML reporter: single-file, self-contained dark-themed report with Chart.js."""
from __future__ import annotations

import json
import os
from pathlib import Path

from llm_eval.models import RunRecord
from llm_eval.storage.db import list_runs


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>llm-eval-harness - {suite_name}</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet" integrity="sha384-T3c6CoIi6uLrA9TneNEoa7RxnatzjcDSCmG1MXxSR1GAsXEV/Dwwykc2MPK8M2HN" crossorigin="anonymous">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js" integrity="sha384-2C8DKpsW3y6jaFGy1y3DwfvJK/JpvLM2cR84vWHctI+KqdRyV7B5UqcL40R2nQQ7" crossorigin="anonymous"></script>
<style>
  body {{ background:#0f172a; color:#e2e8f0; font-family:'Inter',system-ui,sans-serif; padding:2rem; }}
  .card {{ background:#1e293b; border:1px solid #334155; color:#e2e8f0; }}
  .card-header {{ background:#0f172a; border-bottom:1px solid #334155; font-weight:600; }}
  .badge-pass {{ background:#16a34a; }}
  .badge-review {{ background:#eab308; color:#000; }}
  .badge-alert {{ background:#f97316; }}
  .badge-pause {{ background:#dc2626; }}
  .score-card {{ text-align:center; padding:1rem; }}
  .score-card .num {{ font-size:2.2rem; font-weight:700; }}
  .score-card .lbl {{ font-size:0.85rem; opacity:0.7; text-transform:uppercase; letter-spacing:0.05em; }}
  table {{ color:#e2e8f0 !important; }}
  table th, table td {{ border-color:#334155 !important; }}
  .response {{ background:#0b1220; padding:0.6rem; border-radius:4px; font-family:ui-monospace,monospace; font-size:0.85rem; max-height:160px; overflow:auto; white-space:pre-wrap; }}
  .pass {{ color:#22c55e; }}
  .fail {{ color:#ef4444; }}
  h1, h2 {{ color:#f1f5f9; }}
  .header {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:2rem; }}
  .subtle {{ color:#94a3b8; font-size:0.9rem; }}
</style>
</head>
<body>
<div class="container-fluid">
  <div class="header">
    <div>
      <h1>llm-eval-harness</h1>
      <div class="subtle">{suite_name} v{suite_version} - {provider} - {timestamp}</div>
    </div>
    <div>
      <span class="badge badge-{status_class} fs-5 p-3">{threshold_status}</span>
    </div>
  </div>

  <div class="row mb-4">
    <div class="col-md-3"><div class="card score-card"><div class="num">{composite_pct}%</div><div class="lbl">Composite</div></div></div>
    <div class="col-md-2"><div class="card score-card"><div class="num">{coverage_pct}%</div><div class="lbl">Coverage 40%</div></div></div>
    <div class="col-md-2"><div class="card score-card"><div class="num">{accuracy_pct}%</div><div class="lbl">Accuracy 30%</div></div></div>
    <div class="col-md-2"><div class="card score-card"><div class="num">{format_pct}%</div><div class="lbl">Format 20%</div></div></div>
    <div class="col-md-3"><div class="card score-card"><div class="num">{hallucination_pct}%</div><div class="lbl">Hallucination 10%</div></div></div>
  </div>

  <div class="card mb-4">
    <div class="card-header">Score Trend (recent runs)</div>
    <div class="card-body"><canvas id="trendChart" height="80"></canvas></div>
  </div>

  <div class="card mb-4">
    <div class="card-header">Per-Eval Results</div>
    <div class="card-body p-0">
      <table class="table table-hover m-0">
        <thead><tr><th>Eval</th><th>Category</th><th>Provider</th><th>Latency</th><th>Assertions</th></tr></thead>
        <tbody>{eval_rows}</tbody>
      </table>
    </div>
  </div>

  <div class="card mb-4">
    <div class="card-header">Detailed Responses</div>
    <div class="card-body">{detail_blocks}</div>
  </div>

  <div class="card">
    <div class="card-header">Raw Run Data</div>
    <div class="card-body"><pre class="response">{raw_json}</pre></div>
  </div>
</div>

<script>
const RUN_DATA = {raw_json_js};
const TREND = {trend_data};
const ctx = document.getElementById('trendChart').getContext('2d');
new Chart(ctx, {{
  type: 'line',
  data: {{
    labels: TREND.labels,
    datasets: [{{
      label: 'Composite Score',
      data: TREND.values,
      borderColor: '#22c55e',
      backgroundColor: 'rgba(34,197,94,0.15)',
      tension: 0.3,
      fill: true,
      pointRadius: 4
    }}]
  }},
  options: {{
    responsive: true,
    scales: {{
      y: {{ min: 0, max: 1, ticks: {{ color: '#cbd5e1' }}, grid: {{ color: '#334155' }} }},
      x: {{ ticks: {{ color: '#cbd5e1' }}, grid: {{ color: '#334155' }} }}
    }},
    plugins: {{ legend: {{ labels: {{ color: '#e2e8f0' }} }} }}
  }}
}});
</script>
</body>
</html>
"""


STATUS_CLASS = {
    "PASS": "pass",
    "REVIEW": "review",
    "ALERT": "alert",
    "PAUSE": "pause",
}


def _build_eval_rows(record: RunRecord) -> str:
    rows: list[str] = []
    for r in record.results:
        passes = sum(1 for a in r.assertions if a.passed)
        total = len(r.assertions)
        assertion_html_parts: list[str] = []
        for a in r.assertions:
            cls = "pass" if a.passed else "fail"
            sym = "PASS" if a.passed else "FAIL"
            assertion_html_parts.append(
                f'<span class="{cls}">[{sym}] {_escape(a.type)} ({a.score:.2f})</span>'
            )
        assertion_html = "<br>".join(assertion_html_parts)
        rows.append(
            f"<tr><td>{_escape(r.eval_name)}</td><td>{_escape(r.category)}</td>"
            f"<td>{_escape(r.provider)}</td><td>{r.latency_ms}ms</td>"
            f"<td>{assertion_html}<br><small class='subtle'>{passes}/{total} passed</small></td></tr>"
        )
    return "".join(rows)


def _build_detail_blocks(record: RunRecord) -> str:
    blocks: list[str] = []
    for r in record.results:
        blocks.append(
            f"<h6>{_escape(r.eval_name)} <small class='subtle'>({_escape(r.category)})</small></h6>"
            f"<div class='subtle mb-1'>Prompt:</div>"
            f"<pre class='response'>{_escape(r.prompt)}</pre>"
            f"<div class='subtle mb-1'>Response:</div>"
            f"<pre class='response'>{_escape(r.response)}</pre>"
            f"<hr>"
        )
    return "".join(blocks)


def _escape(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _safe_json_for_script(obj) -> str:
    # Prevent </script> in string values from breaking out of inline JS context.
    return json.dumps(obj).replace("</", "<\\/")


def _trend_data(suite_name: str, provider: str, current: RunRecord) -> dict:
    """Build trend chart data using recent runs (oldest -> newest)."""
    try:
        runs = list_runs(limit=10, suite_name=suite_name, provider=provider)
        runs = list(reversed(runs))  # oldest first
        labels = [r["timestamp"][:10] for r in runs]
        values = [r["composite_score"] for r in runs]
    except Exception:  # noqa: BLE001
        labels, values = [], []
    if not values:
        # Fall back to just the current run.
        labels = [current.timestamp[:10]]
        values = [current.composite_score]
    return {"labels": labels, "values": values}


def write_html(record: RunRecord, out_dir: str | None = None) -> str:
    out_dir = out_dir or os.getenv("LLM_EVAL_REPORTS_DIR", "./reports")
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    path = Path(out_dir) / f"run_{record.id}.html"

    raw = record.model_dump()
    raw_json = json.dumps(raw, indent=2)
    trend = _trend_data(record.suite_name, record.provider, record)

    html = HTML_TEMPLATE.format(
        suite_name=_escape(record.suite_name),
        suite_version=_escape(record.suite_version),
        provider=_escape(record.provider),
        timestamp=_escape(record.timestamp),
        threshold_status=record.threshold_status,
        status_class=STATUS_CLASS.get(record.threshold_status, "review"),
        composite_pct=f"{record.composite_score * 100:.1f}",
        coverage_pct=f"{record.coverage_score * 100:.1f}",
        accuracy_pct=f"{record.accuracy_score * 100:.1f}",
        format_pct=f"{record.format_score * 100:.1f}",
        hallucination_pct=f"{record.hallucination_score * 100:.1f}",
        eval_rows=_build_eval_rows(record),
        detail_blocks=_build_detail_blocks(record),
        raw_json=_escape(raw_json),
        raw_json_js=_safe_json_for_script(raw),
        trend_data=_safe_json_for_script(trend),
    )

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return str(path)
