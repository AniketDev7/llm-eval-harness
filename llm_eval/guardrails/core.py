"""Guardrail-specific orchestration layered on the general eval engine."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from llm_eval.adapters.base import BaseAdapter
from llm_eval.models import EvalSuite, RunRecord
from llm_eval.runner.runner import Runner, load_suite


ATTACK_CLASSES = frozenset({
    "prompt_injection",
    "jailbreak",
    "pii_leakage",
    "tool_permission",
    "system_prompt_leak",
    "role_escalation",
})
SEVERITIES = frozenset({"low", "medium", "high", "critical"})


@dataclass(frozen=True)
class GuardrailDefinition:
    suite: EvalSuite
    attack_class: str
    severity: str
    description: str = ""


@dataclass(frozen=True)
class GuardrailSummary:
    attack_class: str
    severity: str
    total: int
    passed: int
    failed: int
    provider_errors: int

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def status(self) -> str:
        if self.provider_errors:
            return "ERROR"
        return "PASS" if self.failed == 0 else "FAIL"


def load_guardrail_suite(path: str | Path) -> GuardrailDefinition:
    """Load a normal eval suite plus required guardrail classification."""
    suite_path = Path(path)
    with suite_path.open("r", encoding="utf-8") as handle:
        raw: Any = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise ValueError("guardrail YAML must contain a mapping")
    metadata = raw.get("guardrail")
    if not isinstance(metadata, dict):
        raise ValueError("guardrail suite requires a top-level 'guardrail' mapping")
    attack_class = str(metadata.get("attack_class", ""))
    severity = str(metadata.get("severity", "")).lower()
    if attack_class not in ATTACK_CLASSES:
        allowed = ", ".join(sorted(ATTACK_CLASSES))
        raise ValueError(f"unknown attack_class {attack_class!r}; expected one of: {allowed}")
    if severity not in SEVERITIES:
        raise ValueError("guardrail severity must be low|medium|high|critical")
    suite = load_suite(suite_path)
    if any(not case.assertions for case in suite.evals):
        raise ValueError("every guardrail case must contain at least one assertion")
    return GuardrailDefinition(
        suite=suite,
        attack_class=attack_class,
        severity=severity,
        description=str(metadata.get("description", "")),
    )


def summarize_guardrails(
    definition: GuardrailDefinition,
    records: list[RunRecord],
) -> GuardrailSummary:
    total = passed = provider_errors = 0
    for record in records:
        for result in record.results:
            total += 1
            if result.error:
                provider_errors += 1
            elif result.assertions and all(item.passed for item in result.assertions):
                passed += 1
    return GuardrailSummary(
        attack_class=definition.attack_class,
        severity=definition.severity,
        total=total,
        passed=passed,
        failed=total - passed,
        provider_errors=provider_errors,
    )


def run_guardrail_suite(
    definition: GuardrailDefinition,
    adapters: dict[str, BaseAdapter] | None = None,
) -> tuple[list[RunRecord], GuardrailSummary]:
    records = Runner(definition.suite, adapters=adapters).run()
    return records, summarize_guardrails(definition, records)
