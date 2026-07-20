from datetime import datetime, timezone

from llm_eval.reporters.pytest_reporter import TestResult as ReportTestResult
from llm_eval.reporters.pytest_reporter import WarningResult, render_pytest_report


def test_pytest_report_contains_summary_and_test_details():
    report = render_pytest_report(
        [
            ReportTestResult("tests/test_one.py::test_pass", "passed", 0.01),
            ReportTestResult("tests/test_one.py::test_fail", "failed", 0.02, "expected 1"),
        ],
        [],
        exit_status=1,
        command="python3 -m pytest tests/ -q",
        generated_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
    )

    assert "Pytest test report" in report
    assert "tests/test_one.py::test_pass" in report
    assert "expected 1" in report
    assert ">FAIL<" in report
    assert "50.0%" in report


def test_pytest_report_escapes_test_and_warning_content():
    report = render_pytest_report(
        [ReportTestResult("tests/test_x.py::test_<script>")],
        [WarningResult("unsafe <script>", "ExampleWarning", "test_x.py:1")],
        exit_status=0,
        command="pytest <tests>",
    )

    assert "test_&lt;script&gt;" in report
    assert "unsafe &lt;script&gt;" in report
    assert "pytest &lt;tests&gt;" in report
    assert ">PASS<" in report
