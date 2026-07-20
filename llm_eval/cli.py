"""Typer CLI entry point. Registered in pyproject.toml as `llm-eval`."""
from __future__ import annotations

import sys
import webbrowser
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv
from rich.console import Console

from llm_eval.drift.detector import capture_baseline, check_drift
from llm_eval.guardrails import load_guardrail_suite, run_guardrail_suite
from llm_eval.quality import assess_risk, compare_run_records
from llm_eval.mcp_support import classify_attack_outcome, load_mcp_scenario, run_mcp_scenario
from llm_eval.reporters.html_reporter import write_html
from llm_eval.reporters.json_reporter import write_json
from llm_eval.reporters.terminal import print_run
from llm_eval.runner.runner import Runner, load_suite
from llm_eval.storage.db import (
    get_audit_results_for_run, get_run, get_results_for_run,
    list_runs, save_run, init_db,
)

load_dotenv()

app = typer.Typer(help="llm-eval-harness: regression tests for LLM outputs.")
baseline_app = typer.Typer(help="Baseline operations.")
drift_app = typer.Typer(help="Drift detection.")
guardrails_app = typer.Typer(help="Run classified AI guardrail suites.")
risk_app = typer.Typer(help="Calculate severity-weighted run risk.")
regression_app = typer.Typer(help="Compare baseline and candidate assertions.")
mcp_app = typer.Typer(help="Run local MCP agent-security scenarios.")
app.add_typer(baseline_app, name="baseline")
app.add_typer(drift_app, name="drift")
app.add_typer(guardrails_app, name="guardrails")
app.add_typer(risk_app, name="risk")
app.add_typer(regression_app, name="regression")
app.add_typer(mcp_app, name="mcp")

console = Console()


@app.command()
def run(
    suite: str = typer.Argument(..., help="Path to a YAML suite file."),
    ci: bool = typer.Option(False, "--ci", help="CI mode: exit non-zero on REVIEW/ALERT/PAUSE."),
    provider: Optional[str] = typer.Option(None, "--provider", help="Override providers list with a single provider."),
    json_out: bool = typer.Option(False, "--json", help="Also write JSON report."),
    html_out: bool = typer.Option(False, "--html", help="Also write HTML report."),
    workers: int = typer.Option(1, "--workers", min=1, help="Run cases concurrently with N workers."),
    max_usd: float = typer.Option(0.0, "--max-usd", min=0.0, help="Budget cap in USD; stop launching cases once reached (0 = uncapped)."),
) -> None:
    """Run an eval suite end-to-end."""
    path = Path(suite)
    if not path.exists():
        console.print(f"[red]Suite file not found:[/red] {suite}")
        raise typer.Exit(code=2)

    eval_suite = load_suite(path)
    if provider:
        eval_suite.providers = [provider]

    runner = Runner(eval_suite, workers=workers, max_usd=max_usd)
    init_db()

    console.print(f"[cyan]Running suite[/cyan] {eval_suite.name} v{eval_suite.version}...")
    records = runner.run()

    worst_status = "PASS"
    status_order = {"PASS": 0, "REVIEW": 1, "ALERT": 2, "PAUSE": 3}
    for rec in records:
        save_run(rec)
        drift = check_drift(rec.suite_name, rec.provider, rec.model)
        print_run(rec, drift=drift)
        if status_order[rec.threshold_status] > status_order[worst_status]:
            worst_status = rec.threshold_status
        if json_out:
            p = write_json(rec)
            console.print(f"  JSON: {p}")
        if html_out:
            p = write_html(rec)
            console.print(f"  HTML: {p}")

    if runner.guard.capped or runner.guard.blocked():
        color = "yellow" if runner.guard.blocked() else "cyan"
        console.print(f"  [{color}]Budget:[/{color}] {runner.guard.summary()}")

    if ci and worst_status != "PASS":
        console.print(f"[red]CI mode: exiting non-zero (status={worst_status})[/red]")
        raise typer.Exit(code=1)


@baseline_app.command("save")
def baseline_save(
    suite: str = typer.Argument(..., help="Path to a YAML suite file."),
    provider: Optional[str] = typer.Option(None, "--provider"),
) -> None:
    """Run the suite then capture the result as the baseline."""
    eval_suite = load_suite(suite)
    if provider:
        eval_suite.providers = [provider]
    runner = Runner(eval_suite)
    init_db()
    records = runner.run()
    for rec in records:
        save_run(rec)
        capture_baseline(rec)
        console.print(f"[green]Baseline saved[/green] for {rec.suite_name}/{rec.provider}: {rec.composite_score:.3f}")


@baseline_app.command("show")
def baseline_show(
    suite_name: str = typer.Argument(...),
    provider: str = typer.Argument(...),
) -> None:
    from llm_eval.storage.db import get_baseline
    b = get_baseline(suite_name, provider)
    if not b:
        console.print(f"[yellow]No baseline for {suite_name}/{provider}.[/yellow]")
        return
    console.print(b)


@drift_app.command("check")
def drift_check(
    suite_name: str = typer.Argument(...),
    provider: str = typer.Argument(...),
    model: Optional[str] = typer.Option(None, "--model", help="Scope drift to a specific model version."),
) -> None:
    report = check_drift(suite_name, provider, model)
    color = "red" if report.alert else "green"
    label = f"{report.suite_name}/{report.provider}" + (f"/{report.model}" if report.model else "")
    console.print(f"[bold]{label}[/bold]")
    console.print(f"  Baseline: {report.baseline_score}")
    console.print(f"  Recent:   {report.recent_scores}")
    console.print(f"  Trend:    {report.trend}")
    console.print(f"  [{color}]Alert:    {report.alert} - {report.message}[/{color}]")


@guardrails_app.command("run")
def guardrails_run(
    suite: str = typer.Argument(..., help="Path to a classified guardrail YAML suite."),
    ci: bool = typer.Option(False, "--ci", help="Exit non-zero on any failed guardrail."),
    provider: Optional[str] = typer.Option(None, "--provider"),
) -> None:
    """Run a guardrail suite and print its security-focused result."""
    try:
        definition = load_guardrail_suite(suite)
    except (OSError, ValueError) as exc:
        console.print(f"[red]Invalid guardrail suite:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    if provider:
        definition.suite.providers = [provider]
    records, summary = run_guardrail_suite(definition)
    for record in records:
        save_run(record)
        print_run(record)
        risk_report = assess_risk(record)
        console.print(
            f"  Risk: {risk_report.score:.1f}/100 ({risk_report.level}) "
            f"failures={risk_report.failed_checks}"
        )
    color = "green" if summary.status == "PASS" else "red"
    console.print(
        f"[{color}]Guardrails {summary.status}[/{color}] "
        f"attack={summary.attack_class} severity={summary.severity} "
        f"passed={summary.passed}/{summary.total} errors={summary.provider_errors}"
    )
    if ci and summary.status != "PASS":
        raise typer.Exit(code=1)


def _load_record(run_id: str):
    from llm_eval.api.routes.export import _reconstruct
    row = get_run(run_id)
    if not row:
        console.print(f"[red]Run {run_id} not found.[/red]")
        raise typer.Exit(code=2)
    return _reconstruct(
        row,
        get_results_for_run(run_id),
        get_audit_results_for_run(run_id),
    )


@risk_app.command("show")
def risk_show(run_id: str = typer.Argument(...)) -> None:
    """Show severity-weighted release risk for a stored run."""
    report = assess_risk(_load_record(run_id))
    console.print(
        f"Risk {report.score:.1f}/100 ({report.level}) - "
        f"{report.failed_checks}/{report.total_checks} checks failed"
    )
    for finding in report.findings:
        console.print(
            f"  [{finding.severity}] {finding.eval_name}/{finding.assertion_type}: "
            f"{finding.detail}"
        )


@regression_app.command("compare")
def regression_compare(
    baseline_run: str = typer.Argument(...),
    candidate_run: str = typer.Argument(...),
    tolerance: float = typer.Option(0.05, min=0.0, max=1.0),
    ci: bool = typer.Option(False, "--ci", help="Exit non-zero when regressions exist."),
) -> None:
    """Compare a candidate run against an assertion-level baseline."""
    try:
        report = compare_run_records(
            _load_record(baseline_run),
            _load_record(candidate_run),
            tolerance,
        )
    except ValueError as exc:
        console.print(f"[red]Cannot compare runs:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    status = "FAIL" if report.has_regressions else "PASS"
    console.print(
        f"Regression {status}: delta={report.composite_delta:+.3f} "
        f"new={len(report.newly_failed)} degraded={len(report.degraded)} "
        f"missing={len(report.missing_checks)} resolved={len(report.resolved)}"
    )
    if ci and report.has_regressions:
        raise typer.Exit(code=1)


@mcp_app.command("run")
def mcp_run(
    scenario_path: str = typer.Argument(..., help="Path to an MCP scenario YAML file."),
    ci: bool = typer.Option(False, "--ci", help="Exit non-zero when assertions fail."),
    allow_external_server: bool = typer.Option(
        False,
        "--allow-external-server",
        help="Allow a reviewed scenario to launch a command other than the bundled fixture.",
    ),
) -> None:
    """Execute a deterministic plan through a real MCP stdio session."""
    import asyncio

    try:
        scenario = load_mcp_scenario(
            scenario_path,
            allow_external_server=allow_external_server,
        )
        record = asyncio.run(run_mcp_scenario(scenario))
    except (OSError, ValueError) as exc:
        console.print(f"[red]Invalid MCP scenario:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    save_run(record)
    print_run(record)
    risk_report = assess_risk(record)
    outcome = classify_attack_outcome(scenario, record)
    console.print(
        f"Attack outcome: {outcome.status} | attempted={outcome.attempted_tools} "
        f"completed={outcome.completed_tools}"
    )
    console.print(
        f"Risk: {risk_report.score:.1f}/100 ({risk_report.level}) | "
        f"failed={risk_report.failed_checks}/{risk_report.total_checks}"
    )
    has_failed_assertion = any(
        not assertion.passed
        for result in record.results
        for assertion in result.assertions
    )
    if ci and (record.threshold_status != "PASS" or has_failed_assertion):
        raise typer.Exit(code=1)


@mcp_app.command("generate")
def mcp_generate(
    out_dir: str = typer.Option("generated-scenarios", "--out", help="Directory to write scaffolded scenario YAMLs."),
    depth: int = typer.Option(2, "--depth", min=1, help="Representatives per capability class."),
    command: Optional[str] = typer.Option(None, "--command", help="Server command (default: bundled fixture)."),
    args: Optional[str] = typer.Option(None, "--args", help="Space-separated server args (with --command)."),
    allow_external_server: bool = typer.Option(
        False, "--allow-external-server",
        help="Permit a non-bundled server command.",
    ),
) -> None:
    """Introspect an MCP server and scaffold class-representative scenarios."""
    import asyncio

    from llm_eval.mcp_support.executor import MCPServerConfig
    from llm_eval.mcp_support.generate import discover_tools, scaffold_scenarios, write_scaffolds

    if command and command != "{python}" and not allow_external_server:
        console.print("[red]Refusing external server command without --allow-external-server[/red]")
        raise typer.Exit(code=2)

    if command:
        server = MCPServerConfig(command=command, args=(args or "").split())
    else:
        server = MCPServerConfig(
            command="{python}",
            args=["-m", "llm_eval.mcp_support.fixtures.workspace_server"],
        )

    try:
        tools = asyncio.run(discover_tools(server))
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to introspect server:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    if not tools:
        console.print("[yellow]Server advertised no tools.[/yellow]")
        raise typer.Exit(code=1)

    scenarios = scaffold_scenarios(server, tools, depth=depth)
    written = write_scaffolds(scenarios, out_dir)
    console.print(
        f"[green]Scaffolded {len(written)} scenario(s)[/green] from {len(tools)} tool(s) into {out_dir}/"
    )
    for path in written:
        console.print(f"  {path}")


@app.command()
def report(
    run_id: Optional[str] = typer.Option(None, "--run-id"),
    format: str = typer.Option("html", "--format", help="html or json"),
) -> None:
    """Render a report for an existing run (defaults to the latest)."""
    from llm_eval.api.routes.export import _reconstruct

    if run_id is None:
        rows = list_runs(limit=1)
        if not rows:
            console.print("[yellow]No runs found.[/yellow]")
            raise typer.Exit(code=1)
        run_id = rows[0]["id"]

    run_row = get_run(run_id)
    if not run_row:
        console.print(f"[red]Run {run_id} not found.[/red]")
        raise typer.Exit(code=2)
    results = get_results_for_run(run_id)
    record = _reconstruct(run_row, results, get_audit_results_for_run(run_id))

    if format == "html":
        path = write_html(record)
    elif format == "json":
        path = write_json(record)
    else:
        console.print("[red]format must be html or json[/red]")
        raise typer.Exit(code=2)
    console.print(f"[green]Report written:[/green] {path}")


@app.command()
def playground(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Don't auto-open the browser."),
) -> None:
    """Start the FastAPI server (and open the browser)."""
    import uvicorn

    if not no_browser:
        try:
            webbrowser.open(f"http://{host}:{port}")
        except Exception:  # noqa: BLE001
            pass

    uvicorn.run("llm_eval.api.main:app", host=host, port=port, reload=False)


@app.command("list")
def list_(
    limit: int = typer.Option(20, "--limit"),
) -> None:
    """List recent runs."""
    rows = list_runs(limit=limit)
    if not rows:
        console.print("[yellow]No runs yet.[/yellow]")
        return
    for r in rows:
        console.print(
            f"{r['id'][:8]}  {r['timestamp']}  "
            f"{r['suite_name']}/{r['provider']}  "
            f"score={r['composite_score']:.3f}  status={r['threshold_status']}"
        )


if __name__ == "__main__":  # pragma: no cover
    app()
