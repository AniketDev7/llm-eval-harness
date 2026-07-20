# Run-tier presets for the eval harness.
# Tiers progress from a cheap PR gate to an exhaustive release check, each with
# an explicit USD budget cap so a run can never overspend silently.

PY := python3
CLI := $(PY) -m llm_eval.cli

.PHONY: help test test-unit smoke nightly release safety guardrails baseline mcp mcp-generate

help:
	@echo "Targets:"
	@echo "  test         Full pytest suite"
	@echo "  test-unit    Fast pure-function unit tests only"
	@echo "  smoke        Cheap PR gate: quickstart suite, capped at \$$0.10"
	@echo "  nightly      All eval suites, capped at \$$2.00"
	@echo "  release      All suites + guardrails + MCP scenarios, capped at \$$5.00"
	@echo "  safety       Guardrail suites only, capped at \$$0.50"
	@echo "  guardrails   Alias for safety"
	@echo "  baseline     Nightly scope, then save as baseline"
	@echo "  mcp          Run all bundled MCP security scenarios"
	@echo "  mcp-generate Scaffold scenarios from the bundled fixture"

test:
	$(PY) -m pytest -q

test-unit:
	$(PY) -m pytest -q tests/test_cost.py tests/test_metrics.py \
		tests/test_case_classes.py tests/test_tool_arguments_extension.py

smoke:
	$(CLI) run evals/quickstart.yaml --ci --max-usd 0.10

nightly:
	@for s in evals/*.yaml; do \
		$(CLI) run $$s --workers 4 --max-usd 2.00 || exit 1; \
	done

release:
	@for s in evals/*.yaml; do \
		$(CLI) run $$s --workers 4 --max-usd 5.00 --html || exit 1; \
	done
	@$(MAKE) safety
	@$(MAKE) mcp

safety:
	@for g in guardrails/*.yaml; do \
		$(CLI) guardrails run $$g --ci || exit 1; \
	done

guardrails: safety

baseline:
	@for s in evals/*.yaml; do \
		$(CLI) baseline save $$s || exit 1; \
	done

mcp:
	@for sc in examples/vulnerable_workspace_mcp/suites/*.yaml; do \
		$(CLI) mcp run $$sc || exit 1; \
	done

mcp-generate:
	$(CLI) mcp generate --out generated-scenarios --depth 2
