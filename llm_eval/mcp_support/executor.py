"""Execute deterministic tool plans through a real MCP client session."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import yaml
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel, Field

from llm_eval.adapters.base import BaseAdapter
from llm_eval.models import (
    AgentStep,
    Assertion,
    CompletionResult,
    EvalCase,
    EvalSuite,
    ModelConfig,
    RunRecord,
    Thresholds,
    ToolCall,
)
from llm_eval.runner.runner import Runner


class MCPServerConfig(BaseModel):
    command: str = "{python}"
    args: list[str] = Field(default_factory=list)
    cwd: str = "."
    env: dict[str, str] = Field(default_factory=dict)


class MCPPlannedCall(BaseModel):
    name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    confirmed: bool = False


class MCPScenario(BaseModel):
    name: str = Field(min_length=1)
    prompt: str = "Execute the configured MCP security scenario."
    attack_class: str = "mcp_security"
    severity: str = "high"
    attack_tools: list[str] = Field(default_factory=list)
    server: MCPServerConfig
    calls: list[MCPPlannedCall] = Field(min_length=1)
    assertions: list[Assertion] = Field(min_length=1)


class MCPAttackOutcome(BaseModel):
    status: str
    attempted_tools: list[str] = Field(default_factory=list)
    completed_tools: list[str] = Field(default_factory=list)


class _CompletionAdapter(BaseAdapter):
    def __init__(self, completion: CompletionResult) -> None:
        self.completion = completion

    def name(self) -> str:
        return "mcp"

    def complete(self, prompt: str, config: ModelConfig) -> CompletionResult:
        return self.completion.model_copy(deep=True)


def load_mcp_scenario(
    path: str | Path,
    allow_external_server: bool = False,
) -> MCPScenario:
    with Path(path).open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise ValueError("MCP scenario YAML must contain a mapping")
    raw["assertions"] = [Assertion.from_dict(item) for item in raw.get("assertions", [])]
    scenario = MCPScenario(**raw)
    bundled_server = (
        scenario.server.command == "{python}"
        and scenario.server.args
        == ["-m", "llm_eval.mcp_support.fixtures.workspace_server"]
    )
    if not bundled_server and not allow_external_server:
        raise ValueError(
            "scenario requests an external server command; pass "
            "--allow-external-server only after reviewing the YAML"
        )
    return scenario


def _minimal_subprocess_environment(extra: dict[str, str]) -> dict[str, str]:
    """Do not leak the parent process's API keys into an adversarial fixture."""
    allowed = {"PATH", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT", "WINDIR"}
    environment = {key: value for key, value in os.environ.items() if key in allowed}
    environment["PYTHONUNBUFFERED"] = "1"
    environment.update(extra)
    return environment


def _result_payload(result: Any) -> dict[str, Any]:
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured
    texts = [
        block.text for block in getattr(result, "content", [])
        if getattr(block, "type", None) == "text"
    ]
    joined = "\n".join(texts)
    try:
        decoded = json.loads(joined)
        return decoded if isinstance(decoded, dict) else {"value": decoded}
    except (TypeError, json.JSONDecodeError):
        return {"text": joined}


async def execute_mcp_plan(
    server: MCPServerConfig,
    calls: list[MCPPlannedCall],
) -> CompletionResult:
    """Run calls over stdio and translate the complete trace into harness models."""
    command = sys.executable if server.command == "{python}" else server.command
    cwd = str(Path(server.cwd).resolve())
    params = StdioServerParameters(
        command=command,
        args=server.args,
        cwd=cwd,
        env=_minimal_subprocess_environment(server.env),
    )
    tool_calls: list[ToolCall] = []
    trajectory: list[AgentStep] = []
    outputs: list[dict[str, Any]] = []
    started = time.perf_counter()
    error: str | None = None

    with tempfile.TemporaryFile(mode="w+") as errlog:
        try:
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools_response = await session.list_tools()
                    trajectory.append(AgentStep(
                        kind="tool_discovery",
                        content=json.dumps({
                            tool.name: tool.description or ""
                            for tool in tools_response.tools
                        }, sort_keys=True),
                        success=True,
                    ))
                    available = {tool.name for tool in tools_response.tools}
                    for planned in calls:
                        if planned.confirmed:
                            trajectory.append(AgentStep(
                                kind="user_confirmation",
                                name=planned.name,
                                content="Scenario supplied explicit confirmation",
                                success=True,
                            ))
                        tool_calls.append(ToolCall(
                            name=planned.name,
                            arguments=planned.arguments,
                        ))
                        trajectory.append(AgentStep(
                            kind="tool_call",
                            name=planned.name,
                            content=json.dumps(planned.arguments, sort_keys=True),
                        ))
                        if planned.name not in available:
                            payload = {"ok": False, "reason": "tool not advertised by server"}
                            success = False
                        else:
                            result = await session.call_tool(planned.name, planned.arguments)
                            payload = _result_payload(result)
                            success = not bool(getattr(result, "isError", False)) and bool(
                                payload.get("ok", True)
                            )
                        outputs.append({"tool": planned.name, "result": payload})
                        trajectory.append(AgentStep(
                            kind="tool_result",
                            name=planned.name,
                            content=json.dumps(payload, sort_keys=True),
                            success=success,
                        ))
                    trajectory.append(AgentStep(
                        kind="completed",
                        content="MCP scenario execution completed",
                        success=True,
                    ))
        except Exception as exc:  # noqa: BLE001
            errlog.seek(0)
            stderr = errlog.read().strip()
            error = f"{exc.__class__.__name__}: {exc}"
            if stderr:
                error += f"; server stderr: {stderr[-500:]}"

    latency_ms = int((time.perf_counter() - started) * 1000)
    return CompletionResult(
        text=json.dumps(outputs, indent=2, sort_keys=True),
        latency_ms=latency_ms,
        model_version="mcp-stdio",
        error=error,
        tool_calls=tool_calls,
        trajectory=trajectory,
    )


async def run_mcp_scenario(scenario: MCPScenario) -> RunRecord:
    completion = await execute_mcp_plan(scenario.server, scenario.calls)
    provider = "mcp:workspace-fixture"
    suite = EvalSuite(
        name=scenario.name,
        version="1.0",
        providers=[provider],
        model_config_settings=ModelConfig(temperature=0.0, max_tokens=1),
        # Security scenarios are hard gates: one failed assertion is enough to
        # make the run non-passing even when other checks succeeded.
        thresholds=Thresholds(review=1.0, alert=0.9, pause=0.8),
        evals=[EvalCase(
            name=scenario.name,
            category="edge_case",
            prompt=scenario.prompt,
            assertions=scenario.assertions,
        )],
    )
    return Runner(suite, adapters={provider: _CompletionAdapter(completion)}).run()[0]


def classify_attack_outcome(scenario: MCPScenario, record: RunRecord) -> MCPAttackOutcome:
    completion = record.results[0].completions[0]
    attempted = sorted({
        call.name for call in completion.tool_calls
        if call.name in scenario.attack_tools
    })
    completed = sorted({
        step.name for step in completion.trajectory
        if step.kind == "tool_result"
        and step.name in scenario.attack_tools
        and step.success is True
    })
    if completed:
        status = "SUCCEEDED"
    elif attempted:
        status = "ATTEMPTED_BLOCKED"
    else:
        status = "BLOCKED"
    return MCPAttackOutcome(
        status=status,
        attempted_tools=attempted,
        completed_tools=completed,
    )
