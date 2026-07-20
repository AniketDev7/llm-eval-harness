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
app.add_typer(baseline_app, name="baseline")
app.add_typer(drift_app, name="drift")
app.add_typer(guardrails_app, name="guardrails")

console = Console()


@app.command()
def run(
    suite: str = typer.Argument(..., help="Path to a YAML suite file."),
    ci: bool = typer.Option(False, "--ci", help="CI mode: exit non-zero on REVIEW/ALERT/PAUSE."),
    provider: Optional[str] = typer.Option(None, "--provider", help="Override providers list with a single provider."),
    json_out: bool = typer.Option(False, "--json", help="Also write JSON report."),
    html_out: bool = typer.Option(False, "--html", help="Also write HTML report."),
) -> None:
    """Run an eval suite end-to-end."""
    path = Path(suite)
    if not path.exists():
        console.print(f"[red]Suite file not found:[/red] {suite}")
        raise typer.Exit(code=2)

    eval_suite = load_suite(path)
    if provider:
        eval_suite.providers = [provider]

    runner = Runner(eval_suite)
    init_db()

    console.print(f"[cyan]Running suite[/cyan] {eval_suite.name} v{eval_suite.version}...")
    records = runner.run()

    worst_status = "PASS"
    status_order = {"PASS": 0, "REVIEW": 1, "ALERT": 2, "PAUSE": 3}
    for rec in records:
        save_run(rec)
        drift = check_drift(rec.suite_name, rec.provider)
        print_run(rec, drift=drift)
        if status_order[rec.threshold_status] > status_order[worst_status]:
            worst_status = rec.threshold_status
        if json_out:
            p = write_json(rec)
            console.print(f"  JSON: {p}")
        if html_out:
            p = write_html(rec)
            console.print(f"  HTML: {p}")

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
) -> None:
    report = check_drift(suite_name, provider)
    color = "red" if report.alert else "green"
    console.print(f"[bold]{report.suite_name}/{report.provider}[/bold]")
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
    color = "green" if summary.status == "PASS" else "red"
    console.print(
        f"[{color}]Guardrails {summary.status}[/{color}] "
        f"attack={summary.attack_class} severity={summary.severity} "
        f"passed={summary.passed}/{summary.total} errors={summary.provider_errors}"
    )
    if ci and summary.status != "PASS":
        raise typer.Exit(code=1)


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


@app.command()
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
