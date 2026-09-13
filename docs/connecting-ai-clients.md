# Connecting an AI client to TARA's MCP server

TARA's MCP server (`tara/mcp_server/server.py`) exposes the same 12 tools
regardless of which AI tool is calling it. Two transports, one behavioral
split: local coding tools (Claude Desktop, Claude Code, Cursor, Codex CLI)
spawn the server themselves over **stdio** — nothing to deploy. Cloud-hosted
app builders (Lovable, Replit Agent, Manus) instead connect to a
network-reachable URL, which means **streamable-HTTP**.

> **Important distinction:** the public browser demo at
> [tara-demo.onrender.com](https://tara-demo.onrender.com) now uses a
> server-side OpenAI model to call a **local, request-scoped MCP subprocess**.
> The browser never receives an OpenAI key and no public MCP endpoint is
> exposed. An authenticated public MCP deployment is still future production
> work; keep external MCP use local and synthetic until authentication,
> tenancy, rate limits, and durable storage are added.

## Local tools (stdio — works right now, no deployment needed)

### Claude Desktop / Claude Code

Add to the MCP config (`claude_desktop_config.json` for Desktop, or
`.mcp.json` / `claude mcp add` for Claude Code):

```json
{
  "mcpServers": {
    "tara": {
      "command": "python",
      "args": ["-m", "tara.mcp_server.server"],
      "cwd": "/absolute/path/to/tara-proj"
    }
  }
}
```

### Cursor

Same shape, in Cursor's `mcp.json` (Settings → MCP):

```json
{
  "mcpServers": {
    "tara": {
      "command": "python",
      "args": ["-m", "tara.mcp_server.server"],
      "cwd": "/absolute/path/to/tara-proj"
    }
  }
}
```

### Codex CLI

Verified against Codex's own MCP docs. Global config lives at
`~/.codex/config.toml`; a project-scoped one at `.codex/config.toml` needs
`trust_level = "trusted"` or it won't load. For a local stdio server, use the
CLI rather than hand-editing TOML:

```
codex mcp add tara -- python -m tara.mcp_server.server
```

(The TOML `[mcp_servers.name]` + `url` + `http_headers` block in Codex's docs
is for a *remote* HTTP server with an API key — that's the shape you'd use
once TARA is deployed, not for the local stdio path above.)

## Cloud app builders (streamable-HTTP — future production work)

After building the required security and storage controls, start the server
with `--transport streamable-http` (see `deploy/README.md`) and use the
resulting public URL (`https://your-deployment/mcp`) below. Do not expose the
current prototype MCP server to an untrusted network.

### Replit Agent

Verified against Replit's MCP docs. Settings pane → **"+ Add MCP server"** →
give it a display name, paste the HTTPS server URL, add any custom auth
header if you've put one in front of the server, then **"Test & save."**
Replit's docs don't state SSE vs. streamable-HTTP explicitly; TARA's server
speaks streamable-HTTP, which is the more common of the two today.

### Lovable

Lovable documents connecting custom/third-party MCP servers as **chat
connectors** (`docs.lovable.dev/integrations/mcp-servers`), separate from its
catalog of prebuilt ones. The exact field-level setup (URL entry, auth
headers) lives on Lovable's custom-connector sub-page, which — flagged
honestly rather than guessed at — hasn't been checked in detail for this
write-up; expect the same shape as Replit's (name, URL, optional header)
until confirmed against Lovable's own screen.

### Manus

Manus has an MCP Connectors doc page, but the version checked for this
write-up covered only its prebuilt connectors (select → authenticate → use),
not the steps for adding a custom/remote server. Rather than guess at UI
copy that may be wrong, treat this one as: look for an "add custom server" or
"add MCP server" option in Manus's connector settings, and expect it to ask
for the same three things every other cloud tool here asks for — a name, the
server's HTTPS URL, and optional auth headers.

## What every option above is missing today

The server has **no authentication** — anyone who can reach the URL (local
subprocess or, once deployed, the public endpoint) can call every tool
against whatever register `TARA_REGISTER_JSON` points at. That's a
reasonable line for a hackathon prototype serving its own demo register; it
is not a line to ship a real client's data behind. See the reliability note
(`docs/reliability-notes.md`) for the rest of what's out of scope for this
build.
