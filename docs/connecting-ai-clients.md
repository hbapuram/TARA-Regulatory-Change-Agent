# Connecting an AI client to TARA's MCP server

TARA's MCP server (`tara/mcp_server/server.py`) exposes the same 12 tools to local AI clients over **stdio**. The browser demo uses a server-side OpenAI model with a request-scoped local MCP subprocess; it does not expose a public MCP endpoint.

> **Prototype boundary:** use the current MCP server locally and with synthetic data. Do not expose it to an untrusted network until authentication, authorization, rate limits, tenant isolation, durable storage, and operational controls are in place.

## Claude Desktop or Claude Code

Add this configuration to `claude_desktop_config.json`, `.mcp.json`, or an equivalent local MCP configuration:

```json
{
  "mcpServers": {
    "tara": {
      "command": "python",
      "args": ["-m", "tara.mcp_server.server"],
      "cwd": "/absolute/path/to/tara-project"
    }
  }
}
```

## Cursor

Use the same configuration shape in Cursor's `mcp.json`:

```json
{
  "mcpServers": {
    "tara": {
      "command": "python",
      "args": ["-m", "tara.mcp_server.server"],
      "cwd": "/absolute/path/to/tara-project"
    }
  }
}
```

## Codex CLI

Use the CLI to register a local stdio server:

```bash
codex mcp add tara -- python -m tara.mcp_server.server
```

## Streamable HTTP

A streamable-HTTP transport is available for controlled development environments:

```bash
python -m tara.cli serve --transport streamable-http --port 8000
```

Do not place the current prototype server on a public network. The server has no production authentication or tenant isolation. See [Security, reliability, and observability](reliability-notes.md) for the current operational boundary.
