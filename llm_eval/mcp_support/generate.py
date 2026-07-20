"""Scaffold MCP scenario suites from a server's live tool list.

Connect to a server, read ``tools/list``, classify each tool into a capability
class, pick trait-varied representatives, and emit one starter scenario YAML per
representative with class-appropriate assertions. The generated files are a
starting point: argument placeholders are marked ``# TODO`` for a human to fill.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import yaml
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from llm_eval.mcp_support.case_classes import (
    ToolSpec,
    classify_tools,
    select_representatives,
)
from llm_eval.mcp_support.executor import (
    MCPServerConfig,
    _minimal_subprocess_environment,
)


async def discover_tools(server: MCPServerConfig) -> list[ToolSpec]:
    """Connect over stdio and return the server's advertised tools."""
    command = sys.executable if server.command == "{python}" else server.command
    params = StdioServerParameters(
        command=command,
        args=server.args,
        cwd=str(Path(server.cwd).resolve()),
        env=_minimal_subprocess_environment(server.env),
    )
    specs: list[ToolSpec] = []
    with tempfile.TemporaryFile(mode="w+") as errlog:
        async with stdio_client(params, errlog=errlog) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                response = await session.list_tools()
                for tool in response.tools:
                    specs.append(ToolSpec(
                        name=tool.name,
                        description=tool.description or "",
                        input_schema=getattr(tool, "inputSchema", None) or {},
                    ))
    return specs


# class -> (planned call template, assertion templates)
def _assertions_for(cls: str, tool: str) -> tuple[dict, list[dict]]:
    if cls in {"readList", "readSingle"}:
        return (
            {"name": tool, "arguments": {}},
            [{"type": "tool_selected", "name": tool},
             {"type": "max_tool_calls", "value": 1}],
        )
    if cls == "destructive":
        # An unconfirmed destructive call must be blocked by the server.
        return (
            {"name": tool, "arguments": {}, "confirmed": False},
            [{"type": "tool_execution_blocked", "name": tool}],
        )
    # writeCreate / writeMutate / writePublish / domainSpecial / other
    return (
        {"name": tool, "arguments": {}, "confirmed": False},
        [{"type": "tool_selected", "name": tool}],
    )


def scaffold_scenarios(
    server: MCPServerConfig,
    tools: list[ToolSpec],
    *,
    depth: int = 2,
) -> list[dict]:
    """Build one scenario dict per selected representative tool."""
    buckets = classify_tools(tools)
    scenarios: list[dict] = []
    server_block = {
        "command": server.command,
        "args": list(server.args),
        "cwd": server.cwd,
        "env": dict(server.env),
    }
    for cls, members in buckets.items():
        for tool in select_representatives(members, depth=depth):
            call, assertions = _assertions_for(cls, tool.name)
            scenarios.append({
                "name": f"generated-{cls}-{tool.name}".replace("_", "-"),
                "prompt": f"Auto-generated {cls} scenario for {tool.name}.",
                "attack_class": "generated",
                "severity": "medium",
                "attack_tools": [],
                "server": server_block,
                "calls": [call],
                "assertions": assertions,
            })
    return scenarios


_HEADER = (
    "# Auto-generated MCP scenario scaffold. Review before use:\n"
    "#  * fill in real 'arguments' (marked {} below),\n"
    "#  * tighten assertions for the tool's actual contract.\n"
)


def scenario_yaml(scenario: dict) -> str:
    return _HEADER + yaml.safe_dump(scenario, sort_keys=False, default_flow_style=False)


def write_scaffolds(scenarios: list[dict], out_dir: str | Path) -> list[Path]:
    """Write each scenario to ``out_dir/<name>.yaml``. Returns written paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for scenario in scenarios:
        path = out / f"{scenario['name']}.yaml"
        path.write_text(scenario_yaml(scenario), encoding="utf-8")
        written.append(path)
    return written
