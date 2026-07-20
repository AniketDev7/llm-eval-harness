"""Eval runner: loads a suite, runs each case, collects results."""
from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from llm_eval.adapters.base import BaseAdapter
from llm_eval.adapters import get_adapter
from llm_eval.cost import CostGuard, estimate_cost
from llm_eval.evaluators import REGISTRY
from llm_eval.models import (
    Assertion, AssertionResult, CompletionResult, EvalCase, EvalResult,
    EvalSuite, ModelConfig, RunRecord, Thresholds,
)
from llm_eval.scorer.scorer import score_run, evaluate_threshold


def load_suite(path: str | Path) -> EvalSuite:
    """Load a YAML suite file into an EvalSuite model."""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return parse_suite(data)


def load_suite_text(text: str) -> EvalSuite:
    """Safely parse an in-memory YAML suite, used by the playground API."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid suite YAML: {exc}") from exc
    return parse_suite(data)


def parse_suite(data: object) -> EvalSuite:
    """Validate an already-decoded suite mapping."""

    if not isinstance(data, dict):
        raise ValueError("suite YAML must contain a mapping at the document root")

    mc = data.get("model_config", {}) or {}
    thresholds_data = data.get("thresholds", {}) or {}

    evals: list[EvalCase] = []
    for raw in data.get("evals", []):
        assertions = [Assertion.from_dict(a) for a in raw.get("assertions", [])]
        evals.append(EvalCase(
            name=raw["name"],
            category=raw.get("category", "format"),
            prompt=raw["prompt"],
            variables=raw.get("variables", {}) or {},
            assertions=assertions,
            runs=int(raw.get("runs", 1)),
        ))

    return EvalSuite(
        name=data["name"],
        version=str(data.get("version", "1.0")),
        providers=data.get("providers", ["openai"]),
        model_config_settings=ModelConfig(**mc),
        thresholds=Thresholds(**thresholds_data),
        evals=evals,
    )


class Runner:
    """Executes an EvalSuite against one or more providers."""

    def __init__(
        self,
        suite: EvalSuite,
        adapters: Optional[dict[str, BaseAdapter]] = None,
        *,
        workers: int = 1,
        max_usd: float = 0.0,
    ):
        self.suite = suite
        # Adapters can be injected (handy for tests). Otherwise lazy-created.
        self.adapters = adapters or {}
        self.workers = max(1, int(workers))
        # Guard is shared across providers so the cap covers total run spend.
        self.guard = CostGuard(max_usd=max(0.0, max_usd))

    def _adapter_for(self, provider: str) -> BaseAdapter:
        """Resolve an adapter for a provider string.

        Supports plain provider names ("anthropic") and
        provider-with-model syntax ("anthropic:claude-opus-4-7") used by
        YAML suites that want to pin a specific model.
        """
        if provider not in self.adapters:
            if ":" in provider:
                name, model = provider.split(":", 1)
                self.adapters[provider] = get_adapter(name, model=model)
            else:
                self.adapters[provider] = get_adapter(provider)
        return self.adapters[provider]

    def _render_prompt(self, case: EvalCase) -> str:
        """Substitute {variable} placeholders using the case's variables dict."""
        if not case.variables:
            return case.prompt
        try:
            return case.prompt.format_map(_SafeDict(case.variables))
        except Exception:  # noqa: BLE001
            return case.prompt

    def _run_assertions(
        self,
        assertions: list[Assertion],
        completion: CompletionResult,
        case: EvalCase,
        all_responses: list[str],
    ) -> list[AssertionResult]:
        results: list[AssertionResult] = []
        context = {
            "prompt": case.prompt,
            "case_name": case.name,
            "category": case.category,
            "all_responses": all_responses,
        }
        for assertion in assertions:
            evaluator = REGISTRY.get(assertion.type)
            if evaluator is None:
                results.append(AssertionResult(
                    type=assertion.type, passed=False, score=0.0,
                    detail=f"Unknown assertion type: {assertion.type}",
                ))
                continue
            try:
                results.append(evaluator(assertion, completion, context))
            except Exception as exc:  # noqa: BLE001
                results.append(AssertionResult(
                    type=assertion.type, passed=False, score=0.0,
                    detail=f"Evaluator error: {exc}",
                ))
        return results

    def run(self) -> list[RunRecord]:
        """Run the full suite. Returns one RunRecord per provider."""
        records: list[RunRecord] = []
        for provider in self.suite.providers:
            record = self._run_for_provider(provider)
            records.append(record)
        return records

    def _run_case(self, provider: str, adapter: BaseAdapter, case: EvalCase) -> EvalResult:
        prompt = self._render_prompt(case)

        completions: list[CompletionResult] = []
        for _ in range(case.runs):
            completions.append(adapter.complete(prompt, self.suite.model_config_settings))

        all_response_texts = [c.text for c in completions]
        # For non-consistency cases we evaluate against the first completion.
        primary = completions[0]

        completion_errors = [c.error for c in completions if c.error]
        if completion_errors:
            # Infrastructure failures are not model output and must never be
            # allowed to satisfy assertions such as max_length on an empty string.
            assertion_results = [AssertionResult(
                type="provider_error",
                passed=False,
                score=0.0,
                detail="; ".join(completion_errors),
            )]
        else:
            assertion_results = self._run_assertions(
                case.assertions, primary, case, all_response_texts,
            )

        return EvalResult(
            eval_name=case.name,
            category=case.category,
            provider=provider,
            prompt=prompt,
            response=primary.text,
            latency_ms=primary.latency_ms,
            tokens_used=primary.tokens_used,
            model_version=primary.model_version,
            completions=completions,
            assertions=assertion_results,
            error=primary.error,
        )

    def _charge(self, result: EvalResult) -> None:
        for comp in result.completions:
            self.guard.add(estimate_cost(comp.model_version, comp.tokens_used))

    def _run_for_provider(self, provider: str) -> RunRecord:
        adapter = self._adapter_for(provider)
        eval_results: list[EvalResult] = []

        cases = self.suite.evals
        idx = 0
        while idx < len(cases):
            if self.guard.exceeded():
                self.guard.note_blocked(len(cases) - idx)
                break
            batch = cases[idx:idx + self.workers]
            if self.workers == 1:
                batch_results = [self._run_case(provider, adapter, batch[0])]
            else:
                with ThreadPoolExecutor(max_workers=self.workers) as pool:
                    batch_results = list(pool.map(
                        lambda c: self._run_case(provider, adapter, c), batch,
                    ))
            for result in batch_results:
                eval_results.append(result)
                self._charge(result)
            idx += len(batch)

        scores = score_run(eval_results)
        status = evaluate_threshold(scores["composite"], self.suite.thresholds)

        model = next((r.model_version for r in eval_results if r.model_version), "")

        return RunRecord(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            suite_name=self.suite.name,
            suite_version=self.suite.version,
            provider=provider,
            model=model,
            composite_score=scores["composite"],
            coverage_score=scores["coverage"],
            accuracy_score=scores["accuracy"],
            format_score=scores["format"],
            hallucination_score=scores["hallucination"],
            threshold_status=status,
            results=eval_results,
        )


class _SafeDict(dict):
    """Dict that returns '{key}' for missing keys, so format_map doesn't crash."""

    def __missing__(self, key: str) -> str:  # type: ignore[override]
        return "{" + key + "}"
