# TARA browser demo

> **Prototype scope:** the demo runs controlled source snapshots against synthetic prepared cases. Do not enter real personal, legal, tax, immigration, financial, or filing data.

The browser demonstrates an **LLM-first, MCP-orchestrated** TARA workflow. When configured, a server-side OpenAI model discovers TARA's local MCP tools, selects the investigation path, and writes a plain-language explanation. Deterministic TARA controls independently verify the source change, applicability, dates, calculations, actions, and evidence result.

## Run locally

```bash
pip install -e '.[dev]'
pip install -r demo/requirements.txt
export OPENAI_API_KEY=...  # enables the optional LLM-first path
python -m uvicorn demo.api:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`.

## Components

```text
demo/
  api.py              FastAPI adapter for orchestration and deterministic controls
  index.html          accessible browser shell
  app.js              interaction and rendering logic
  presets.json        synthetic prepared profiles
  replay.js           captured deterministic responses for offline inspection
  capture_replay.py   regenerates replay.js
  Dockerfile          browser-demo image
  requirements.txt    FastAPI and Uvicorn dependencies
```

## Execution modes

When `OPENAI_API_KEY` is configured on the server, `POST /api/ai/run` starts a short-lived OpenAI session that calls TARA's local MCP server over stdio. The browser never receives the API key. The model must discover canonical domain, source, and holding identifiers before it can investigate; the UI displays the resulting tool trace.

```text
Browser → server-side OpenAI model → local MCP tools → deterministic TARA controls → result
```

If AI orchestration is unavailable, the interface visibly switches to the deterministic `/api/run` path. The deterministic path uses the same controlled sources, synthetic facts, and evidence rules. `replay.js` provides captured deterministic results when the service itself is unavailable; it supports only pristine prepared profiles.

Regenerate replay data after changing a pack, agent, model adapter, or preset:

```bash
python -m uvicorn demo.api:app --port 8000 &
python demo/capture_replay.py
```

## Safety and scope

The server creates a fresh temporary register, graph version, and ATLAS ledger for each browser request. The public demo is intentionally stateless and has no production authentication, authorization, rate limiting, tenant storage, or service-level guarantee. A qualified professional must review any real-world action.
