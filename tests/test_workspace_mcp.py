"""Unit and stdio integration tests for the fake workspace MCP fixture."""
from pathlib import Path

import pytest

from llm_eval.mcp_support.fixtures.workspace import Principal, Workspace
from llm_eval.mcp_support import (
    classify_attack_outcome,
    load_mcp_scenario,
    run_mcp_scenario,
)


SUITES = Path(__file__).parent.parent / "examples" / "vulnerable_workspace_mcp" / "suites"


def test_secure_workspace_enforces_tenant_and_ignores_role_claim():
    workspace = Workspace(mode="secure", principal=Principal("tenant-alpha", "analyst"))
    result = workspace.get_customer("beta-customer", requester_role="admin", tenant_id="tenant-beta")
    assert result["allowed"] is False
    assert result["data"] is None
    assert workspace.events[-1].executed is False


def test_vulnerable_workspace_exposes_cross_tenant_fixture_data():
    workspace = Workspace(mode="vulnerable")
    result = workspace.read_document("beta-secret")
    assert result["allowed"] is True
    assert "FAKE-BETA-SECRET" in result["data"]["content"]


def test_secure_workspace_requires_confirmation_for_side_effects():
    workspace = Workspace(mode="secure")
    denied = workspace.delete_document("alpha-handbook")
    assert denied["executed"] is False
    assert "alpha-handbook" in workspace.documents

    allowed = workspace.delete_document("alpha-handbook", "TEST-CONFIRM")
    assert allowed["executed"] is True
    assert "alpha-handbook" not in workspace.documents


def test_audit_only_mode_never_performs_side_effect():
    workspace = Workspace(mode="audit-only")
    result = workspace.send_email(
        "recipient@example.test", "Subject", "Body", "TEST-CONFIRM",
    )
    assert result["allowed"] is True
    assert result["executed"] is False
    assert workspace.outbox == []
    assert workspace.events[-1].action == "send_email"


def test_scenario_rejects_unreviewed_external_command(tmp_path):
    scenario_path = tmp_path / "external.yaml"
    scenario_path.write_text("""
name: external
server: {command: arbitrary-program, args: []}
calls: [{name: example}]
assertions: [{type: max_tool_calls, value: 1}]
""")
    with pytest.raises(ValueError, match="external server command"):
        load_mcp_scenario(scenario_path)
    loaded = load_mcp_scenario(scenario_path, allow_external_server=True)
    assert loaded.server.command == "arbitrary-program"


@pytest.mark.asyncio
async def test_real_mcp_stdio_session_blocks_cross_tenant_access():
    scenario = load_mcp_scenario(SUITES / "tenant-isolation.yaml")
    record = await run_mcp_scenario(scenario)
    result = record.results[0]
    discovery = next(
        step for step in result.completions[0].trajectory
        if step.kind == "tool_discovery"
    )
    assert "UNTRUSTED TOOL-METADATA FIXTURE" in discovery.content
    assert all(assertion.passed for assertion in result.assertions)
    assert classify_attack_outcome(scenario, record).status == "ATTEMPTED_BLOCKED"


@pytest.mark.asyncio
async def test_vulnerable_mcp_control_proves_detection_is_effective():
    scenario = load_mcp_scenario(SUITES / "vulnerable-control.yaml")
    record = await run_mcp_scenario(scenario)
    assert record.threshold_status == "PAUSE"
    assert not any(assertion.passed for assertion in record.results[0].assertions)
    assert classify_attack_outcome(scenario, record).status == "SUCCEEDED"


@pytest.mark.asyncio
async def test_confirmation_violation_is_a_hard_gate_even_when_server_blocks_it():
    scenario = load_mcp_scenario(SUITES / "confirmation-bypass.yaml")
    record = await run_mcp_scenario(scenario)
    checks = {item.type: item.passed for item in record.results[0].assertions}
    assert checks == {
        "requires_confirmation": False,
        "tool_execution_blocked": True,
    }
    assert record.threshold_status != "PASS"
