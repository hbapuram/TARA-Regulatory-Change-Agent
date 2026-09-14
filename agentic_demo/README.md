# TARA Agentic Demo

This directory is an **isolated copy** of TARA's existing browser demonstration. It preserves the original `demo/` directory and its deployment without modification.

**Deployed demonstration:** [https://tara-agentic-demo.onrender.com](https://tara-agentic-demo.onrender.com)

The agentic copy adds two visible, server-side AI capabilities for **prepared synthetic cases and controlled source snapshots only**:

1. **Live Case Investigator.** A model discovers TARA's guarded MCP tools, investigates the prepared case, and returns a short plain-language explanation with its tool trace. The deterministic pipeline remains authoritative for the source version, effective date, threshold, arithmetic, action plan, and evidence outcome.
2. **Live Missing-Fact Interview.** When deterministic controls return `INDETERMINATE`, the model explains the one canonical question that the controls selected. The user must explicitly choose and confirm Yes or No before the deterministic pipeline re-runs. The agent cannot answer, replace, or silently update a case fact.

## Run locally

```bash
pip install -e '.[dev]'
pip install -r agentic_demo/requirements.txt
export OPENAI_API_KEY=...  # enables the live investigator and interview guide
python -m uvicorn agentic_demo.api:app --host 127.0.0.1 --port 8001
```

Open `http://127.0.0.1:8001`.

Without `OPENAI_API_KEY`, the copied workflow remains available with its labelled deterministic path and captured replay. In the separate hosted service, `TARA_AGENT_RELAY_URL` may be configured to the existing controlled TARA AI/MCP service. That relay accepts **only exact, unchanged checked-in synthetic profiles**; typed or modified browser data stays in the isolated service and receives deterministic controls only. It forwards no API key.

## Safety boundary

The agentic features do not provide legal, tax, immigration, financial, or filing advice. They do not use open-web retrieval or accept real client data. The public interface has no production authentication, authorization, tenant storage, or retention controls. A qualified professional must review any real-world action.

## Verification

```bash
pytest -q tests/test_agentic_demo_api.py
node --check agentic_demo/app.js
```

Use `render-agentic.yaml` to create a separate hosted service named `tara-agentic-demo`. It configures the prepared-case relay by default. To replace the relay with a fully independent agent, configure its own `OPENAI_API_KEY` secret; the key is never sent to the browser or the request-scoped MCP subprocess.
