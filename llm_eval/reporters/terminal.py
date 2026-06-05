"""Rich-powered terminal reporter (pytest-style)."""
from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from llm_eval.models import DriftReport, RunRecord


STATUS_COLOR = {
    "PASS": "green",
    "REVIEW": "yellow",
    "ALERT": "orange1",
    "PAUSE": "red",
}


def _status_badge(status: str) -> Text:
    color = STATUS_COLOR.get(status, "white")
    return Text(f" {status} ", style=f"bold white on {color}")


def print_run(record: RunRecord, drift: DriftReport | None = None) -> None:
    """Print a colorful summary of a single RunRecord."""
    console = Console()
    console.print()
    header = Text(f"{record.suite_name} v{record.suite_version} -> {record.provider}", style="bold cyan")
    console.print(Panel(header, expand=False))

    # Per-eval table.
    table = Table(title="Eval Results", show_lines=False, header_style="bold magenta")
    table.add_column("Eval", style="cyan", no_wrap=False)
    table.add_column("Category")
    table.add_column("Assertions")
    table.add_column("Status")

    for r in record.results:
        passes = sum(1 for a in r.assertions if a.passed)
        total = len(r.assertions)
        status_txt = "[green]PASS[/green]" if passes == total else "[red]FAIL[/red]"
        if r.error:
            status_txt = "[red]ERROR[/red]"
        table.add_row(r.eval_name, r.category, f"{passes}/{total}", status_txt)

    console.print(table)

    # Per-assertion detail (only failures).
    has_fail = any(not a.passed for r in record.results for a in r.assertions)
    if has_fail:
        fail_table = Table(title="Failed Assertions", show_lines=False, header_style="bold red")
        fail_table.add_column("Eval", style="cyan")
        fail_table.add_column("Assertion")
        fail_table.add_column("Score")
        fail_table.add_column("Detail")
        for r in record.results:
            for a in r.assertions:
                if not a.passed:
                    fail_table.add_row(r.eval_name, a.type, f"{a.score:.2f}", a.detail[:80])
        console.print(fail_table)

    # Score summary.
    summary = Table(title="Scores", show_lines=False, header_style="bold")
    summary.add_column("Metric")
    summary.add_column("Score")
    summary.add_row("Composite (weighted)", f"{record.composite_score * 100:.1f}%")
    summary.add_row("Coverage (40%)", f"{record.coverage_score * 100:.1f}%")
    summary.add_row("Accuracy (30%)", f"{record.accuracy_score * 100:.1f}%")
    summary.add_row("Format (20%)", f"{record.format_score * 100:.1f}%")
    summary.add_row("Hallucination (10%)", f"{record.hallucination_score * 100:.1f}%")
    console.print(summary)

    console.print()
    console.print("Status:", _status_badge(record.threshold_status))

    if drift is not None:
        console.print()
        drift_color = "red" if drift.alert else "green"
        console.print(Panel(
            f"[bold]Drift:[/bold] trend={drift.trend} alert={drift.alert}\n{drift.message}",
            border_style=drift_color, title="Drift Report",
        ))
    console.print()
