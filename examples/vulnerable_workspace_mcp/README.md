# Vulnerable Workspace MCP

An intentionally vulnerable, fake-data-only MCP fixture for testing agent guardrails,
tool-use safety, authorization, confirmation, and data-exfiltration detection.

It uses the official stable-v1 [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
and runs over stdio by default. It never connects to email, customer systems, or a real
document store.

## Policy modes

| Mode | Behavior |
|---|---|
| `secure` | Enforces tenant, role, wildcard, and confirmation policies server-side |
| `vulnerable` | Intentionally permits cross-tenant reads and unsafe actions |
| `audit-only` | Records decisions but never performs side effects |

The vulnerable mode is a positive control: it proves the evaluator detects a real leak
instead of passing because the fixture never exposed one.

## Tools

- `search_documents` contains a poisoned description fixture.
- `read_document` can return a document containing indirect prompt injection.
- `get_customer` tests forged role claims and tenant isolation.
- `send_email` tests confirmation bypass and exfiltration attempts.
- `delete_document` tests destructive actions, wildcard rejection, and approval.
- `export_data` tests admin policy, tenant boundaries, and bulk disclosure.

All records use reserved `example.test` addresses and explicit `FAKE-*` markers.

## Run scenarios

From the repository root:

```bash
llm-eval mcp run examples/vulnerable_workspace_mcp/suites/tenant-isolation.yaml --ci
llm-eval mcp run examples/vulnerable_workspace_mcp/suites/tool-poisoning.yaml --ci

# Expected to fail: proves vulnerable mode leaks the configured marker.
llm-eval mcp run examples/vulnerable_workspace_mcp/suites/vulnerable-control.yaml
```

Each scenario launches a fresh server subprocess with reset state. The client passes a
minimal environment rather than inheriting API keys from the parent process.

For safety, scenario files may launch only the bundled fixture by default. Testing a
reviewed third-party MCP command requires the explicit `--allow-external-server` flag;
never use that flag with an untrusted YAML file.

## Manual inspection

The default transport is stdio. Streamable HTTP is opt-in for local MCP Inspector use:

```bash
WORKSPACE_MCP_MODE=secure \
WORKSPACE_MCP_TRANSPORT=streamable-http \
python -m llm_eval.mcp_support.fixtures.workspace_server
```

Do not expose vulnerable mode outside localhost. It intentionally weakens authorization.

## Current boundary

The bundled YAML scenarios execute deterministic tool plans. They validate the actual MCP
transport, server policy, audit evidence, and trajectory assertions without spending model
credits. A production agent can reuse `execute_mcp_plan` output conventions, but live model
tool selection and multi-turn planning remain a separate integration layer.
