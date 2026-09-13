# Deploying the TARA MCP server

This closes a gap the repo had been pointing at without filling in: both
`Dockerfile` and `tara/mcp_server/server.py`'s own `--help` text say "see
deploy/README.md" — this file is that pointer, written from what's
actually in the Dockerfile and CLI, not aspirational.

The server (`tara/mcp_server/server.py`) exposes the same 10 MCP tools
either way — `stdio` (a local subprocess, what `tara demo` and the MCP
Inspector use) or `streamable-http` (a standalone, network-reachable
service). Nothing about the agents, domain packs, or ATLAS ledger changes
between the two; only the transport does.

> **Current deployment boundary:** the browser demo is live at
> [https://tara-demo.onrender.com](https://tara-demo.onrender.com), but that
> service exposes the safe browser-facing FastAPI adapter—not `/mcp`. The MCP
> server described here is a local or controlled-environment prototype. Do not
> deploy it publicly with real data until authentication, tenant isolation,
> rate limits, durable state, and operational monitoring are implemented.

## Build and run locally

```
docker build -t tara-mcp .
docker run -p 8000:8000 -e PORT=8000 tara-mcp
```

`server.py` reads `PORT` directly (falling back to `TARA_MCP_PORT`, then
8000), so no extra env wiring is required beyond what's already in the
Dockerfile. Verify it's up with a real MCP client rather than hand-rolled
curl — `demo_scenarios.py` in the repo root, pointed at
`http://localhost:8000/mcp` instead of spawning a subprocess, is the
fastest check; a bare `curl -X POST` against `/mcp` needs a full,
correctly-shaped JSON-RPC `initialize` handshake to get anything back.

## Render / Railway / Fly.io

All three inject `PORT` at container start and build directly from a
`Dockerfile` in the repo root — no platform-specific config file is
needed beyond pointing the service at this repo:

- **Render**: New → Web Service → connect the repo → it detects the
  Dockerfile automatically. Leave the port blank; Render sets `PORT` and
  the container already reads it.
- **Railway**: New Project → Deploy from GitHub repo → it detects the
  Dockerfile the same way. `PORT` is injected the same way.
- **Fly.io**: `fly launch` in the repo root detects the Dockerfile and
  writes a `fly.toml`; confirm the internal port in that generated file
  matches `8000` (or override with `-e PORT=<port>` at deploy time).

Whichever platform, the environment variables worth setting explicitly:

| Variable | Purpose | Default if unset |
|---|---|---|
| `TARA_MCP_TRANSPORT` | force `streamable-http` without passing `--transport` | `stdio` |
| `TARA_REGISTER_JSON` | which tenant register the server reads | `registers/holder_register.json` (the demo register, committed to the repo) |
| `TARA_ATLAS_PATH` | where the ATLAS ledger is appended | `registers/atlas_log.jsonl` |
| `TARA_GRAPH_VERSION_PATH` | ALMANAC's versioned graph store | `registers/graph_version.json` |

Deploying with the defaults serves the same demo register and ledger
that ships in the repo — appropriate only for a locally controlled synthetic
demonstration, not an untrusted public endpoint or a real multi-tenant setup. Pointing
`TARA_REGISTER_JSON` (and the two paths alongside it) at a different
file is what actually changes whose data the server answers from; there
is no other tenancy boundary in this prototype.

## What's not done here

This repo has never had its `docker build` actually run end to end — the
cloud sandbox used to build out this repo's later features has outbound
Docker Hub access blocked by its own network policy, so the image
described above is unverified past a manual read of the Dockerfile. Build
and run it once locally (`docker build -t tara-mcp .` takes under a
minute; nothing in it needs network access at runtime beyond what the
container itself reaches) before relying on a deployed instance for a
live demo. Actually deploying to any of the three platforms above needs
your own account on that platform — nothing here can do that from a
Claude session.
