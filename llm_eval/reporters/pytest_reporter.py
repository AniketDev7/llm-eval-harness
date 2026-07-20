"""Automatic, self-contained HTML reports for the project's pytest suite."""
from __future__ import annotations

import html
import os
import platform
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pytest


@dataclass
class TestResult:
    nodeid: str
    outcome: str = "passed"
    duration: float = 0.0
    details: str = ""
    phases: set[str] = field(default_factory=set)


@dataclass
class WarningResult:
    message: str
    category: str
    location: str


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _result_rows(results: list[TestResult]) -> str:
    rows: list[str] = []
    for result in results:
        details = ""
        if result.details:
            details = (
                "<details><summary>View details</summary>"
                f"<pre>{_escape(result.details)}</pre></details>"
            )
        rows.append(
            "<tr>"
            f'<td><span class="status {result.outcome}">{result.outcome.upper()}</span></td>'
            f"<td class=\"test-name\">{_escape(result.nodeid)}{details}</td>"
            f"<td>{result.duration * 1000:.1f} ms</td>"
            "</tr>"
        )
    return "".join(rows)


def _warning_rows(warnings: list[WarningResult]) -> str:
    if not warnings:
        return '<div class="empty">No warnings recorded.</div>'
    return "".join(
        "<div class=\"warning\">"
        f"<strong>{_escape(item.category)}</strong>"
        f"<div>{_escape(item.message)}</div>"
        f"<small>{_escape(item.location)}</small>"
        "</div>"
        for item in warnings
    )


def render_pytest_report(
    results: list[TestResult],
    warnings: list[WarningResult],
    *,
    exit_status: int,
    command: str,
    generated_at: datetime | None = None,
) -> str:
    """Render a standalone pytest report without external assets."""
    generated_at = generated_at or datetime.now(timezone.utc)
    counts = {
        outcome: sum(result.outcome == outcome for result in results)
        for outcome in ("passed", "failed", "skipped")
    }
    total = len(results)
    pass_rate = (counts["passed"] / total * 100) if total else 0.0
    overall = "PASS" if exit_status == 0 else "FAIL"
    overall_class = "passed" if exit_status == 0 else "failed"
    duration = sum(result.duration for result in results)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>llm-eval-harness pytest report</title>
<style>
:root {{ color-scheme:dark; --bg:#08111f; --panel:#111c2e; --line:#26344a; --text:#e7edf7; --muted:#91a1b9; --green:#22c55e; --red:#ef4444; --amber:#f59e0b; }}
* {{ box-sizing:border-box }}
body {{ margin:0; background:var(--bg); color:var(--text); font:14px/1.5 Inter,ui-sans-serif,system-ui,sans-serif }}
main {{ width:min(1180px,calc(100% - 32px)); margin:32px auto 64px }}
header {{ display:flex; justify-content:space-between; align-items:flex-start; gap:24px; margin-bottom:24px }}
h1 {{ margin:0 0 4px; font-size:30px }} h2 {{ margin:0; padding:18px 20px; font-size:17px; border-bottom:1px solid var(--line) }}
.muted,small {{ color:var(--muted) }} .badge,.status {{ display:inline-block; border-radius:999px; font-weight:750 }}
.badge {{ padding:10px 18px; font-size:16px }} .status {{ min-width:72px; padding:4px 9px; text-align:center; font-size:11px }}
.passed {{ color:#b7f7ca; background:#14532d }} .failed {{ color:#fecaca; background:#7f1d1d }} .skipped {{ color:#fde68a; background:#713f12 }}
.cards {{ display:grid; grid-template-columns:repeat(5,1fr); gap:12px; margin-bottom:20px }}
.card,.panel {{ background:var(--panel); border:1px solid var(--line); border-radius:12px }}
.card {{ padding:17px }} .number {{ font-size:28px; font-weight:760 }} .label {{ color:var(--muted); text-transform:uppercase; letter-spacing:.06em; font-size:11px }}
.panel {{ overflow:hidden; margin-top:18px }} table {{ width:100%; border-collapse:collapse }} th,td {{ padding:12px 16px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top }} th {{ color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.06em }} tr:last-child td {{ border:0 }}
.test-name {{ width:75%; font-family:ui-monospace,SFMono-Regular,Menlo,monospace; overflow-wrap:anywhere }}
details {{ margin-top:8px }} summary {{ cursor:pointer; color:#93c5fd }} pre {{ max-height:360px; overflow:auto; padding:12px; border-radius:8px; background:#060b14; color:#d8e2f1; white-space:pre-wrap }}
.warning {{ padding:14px 20px; border-bottom:1px solid var(--line) }} .warning:last-child {{ border:0 }} .warning strong {{ color:#fcd34d }} .warning div {{ margin:4px 0 }} .empty {{ padding:18px 20px; color:var(--muted) }}
.meta {{ padding:16px 20px; display:grid; grid-template-columns:1fr 1fr; gap:8px 24px }} code {{ color:#bfdbfe; overflow-wrap:anywhere }}
@media(max-width:760px) {{ header {{ display:block }} .badge {{ margin-top:14px }} .cards {{ grid-template-columns:1fr 1fr }} .meta {{ grid-template-columns:1fr }} }}
</style>
</head>
<body><main>
<header><div><h1>Pytest test report</h1><div class="muted">llm-eval-harness · generated {_escape(generated_at.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z'))}</div></div><span class="badge {overall_class}">{overall}</span></header>
<section class="cards">
  <div class="card"><div class="number">{total}</div><div class="label">Tests</div></div>
  <div class="card"><div class="number">{counts['passed']}</div><div class="label">Passed</div></div>
  <div class="card"><div class="number">{counts['failed']}</div><div class="label">Failed</div></div>
  <div class="card"><div class="number">{counts['skipped']}</div><div class="label">Skipped</div></div>
  <div class="card"><div class="number">{pass_rate:.1f}%</div><div class="label">Pass rate</div></div>
</section>
<section class="panel"><h2>Test results</h2><table><thead><tr><th>Status</th><th>Test</th><th>Duration</th></tr></thead><tbody>{_result_rows(results)}</tbody></table></section>
<section class="panel"><h2>Warnings ({len(warnings)})</h2>{_warning_rows(warnings)}</section>
<section class="panel"><h2>Run information</h2><div class="meta">
  <div><span class="muted">Command</span><br><code>{_escape(command)}</code></div>
  <div><span class="muted">Duration</span><br>{duration:.3f} seconds</div>
  <div><span class="muted">Python</span><br>{_escape(platform.python_version())}</div>
  <div><span class="muted">Platform</span><br>{_escape(platform.platform())}</div>
</div></section>
</main></body></html>"""


class PytestHtmlReporter:
    def __init__(self, config: pytest.Config) -> None:
        self.config = config
        self.results: dict[str, TestResult] = {}
        self.warnings: list[WarningResult] = []
        self.report_path: Path | None = None

    @pytest.hookimpl
    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        result = self.results.setdefault(report.nodeid, TestResult(nodeid=report.nodeid))
        result.duration += report.duration
        result.phases.add(report.when)
        if report.failed:
            result.outcome = "failed"
            result.details = str(report.longrepr)
        elif report.skipped and result.outcome != "failed":
            result.outcome = "skipped"

    @pytest.hookimpl
    def pytest_warning_recorded(
        self,
        warning_message: pytest.WarningRecord,
        when: str,
        nodeid: str,
        location: tuple[str, int, str] | None,
    ) -> None:
        del when
        source = nodeid or ""
        if location:
            source = f"{location[0]}:{location[1]}"
        self.warnings.append(
            WarningResult(
                message=str(warning_message.message),
                category=warning_message.category.__name__,
                location=source,
            )
        )

    @pytest.hookimpl
    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        if os.getenv("LLM_EVAL_PYTEST_HTML", "1").lower() in {"0", "false", "no"}:
            return
        report_dir = Path(os.getenv("LLM_EVAL_REPORTS_DIR", session.config.rootpath / "reports"))
        report_dir.mkdir(parents=True, exist_ok=True)
        self.report_path = (report_dir / "pytest_report.html").resolve()
        command = " ".join([Path(sys.executable).name, "-m", "pytest", *session.config.invocation_params.args])
        rendered = render_pytest_report(
            sorted(self.results.values(), key=lambda item: item.nodeid),
            self.warnings,
            exit_status=int(exitstatus),
            command=command,
        )
        self.report_path.write_text(rendered, encoding="utf-8")

    @pytest.hookimpl
    def pytest_terminal_summary(self, terminalreporter: pytest.TerminalReporter) -> None:
        if self.report_path:
            terminalreporter.section("custom HTML test report", sep="=")
            terminalreporter.write_line(f"Report: {self.report_path}", green=True, bold=True)
            terminalreporter.write_line(f"Open:   open {self.report_path}")


def pytest_configure(config: pytest.Config) -> None:
    config.pluginmanager.register(PytestHtmlReporter(config), "llm-eval-pytest-html-reporter")
