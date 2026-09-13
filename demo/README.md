# TARA live demo

> **Prototype scope:** controlled source snapshots and synthetic prepared cases. This is not legal, tax, immigration, or filing advice; a qualified professional must review any real-world action.

The browser demonstrates an **LLM-first, MCP-orchestrated** TARA workflow. The OpenAI model runs server-side, discovers TARA's local MCP tools, chooses the investigation path, and writes a plain-language explanation. Deterministic TARA code separately verifies the source change, applicability, dates, calculations, actions, and evidence result. The recommended judge route is:

```text
Maeve → show the AI/MCP trace → see 41% become 38% → see why the current rule applies
      → follow the action plan → try 41% (needs correction)
      → restore 38% (accepted) → inspect the proof record
```

Maeve is the **tested golden path**. Ciarán, Priya, and Arun are clearly labelled exploratory breadth cases.

## Files

```text
demo/
  api.py              browser adapter: OpenAI orchestration, MCP trace, deterministic backup
  index.html           accessible wizard shell
  _page.html           synchronized artifact fragment
  app.js               interaction and rendering logic
  presets.json         four synthetic prepared profiles
  replay.js            captured real API responses for offline fallback
  capture_replay.py    regenerates replay.js
  Dockerfile           Render-compatible image
  requirements.txt     FastAPI and Uvicorn dependencies
```

## Run locally

```bash
pip install -e '.[dev]'
pip install -r requirements.txt
pip install -r demo/requirements.txt
export OPENAI_API_KEY=...  # enables the default AI/MCP path
python -m uvicorn demo.api:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`.

## Public service

- Demo: [https://tara-demo.onrender.com/](https://tara-demo.onrender.com/)
- Health: [https://tara-demo.onrender.com/api/health](https://tara-demo.onrender.com/api/health)
- Complete guide: [https://tara-demo.onrender.com/guide](https://tara-demo.onrender.com/guide)
- Evaluation card: [https://tara-demo.onrender.com/evaluation-card.md](https://tara-demo.onrender.com/evaluation-card.md)

The free Render service may need time to wake. Open it before presenting.

## How the AI path works

The browser never receives an OpenAI key. When `OPENAI_API_KEY` is configured on the server, `POST /api/ai/run` creates a short-lived OpenAI session that calls TARA's local MCP server over stdio. The model must discover the exact domain, source, and holding IDs before it can investigate. The UI then displays a readable tool trace.

```text
Browser → server-side OpenAI model → local MCP tools → TARA controls → human-readable result
                                          ↓
                               source, dates, actions, evidence
```

The page does not let the model invent decisions, action dates, citations, or evidence results. The main interface uses plain language; internal role names and requirement IDs appear only in optional technical details. The deterministic controls call:

- `tara.pipeline`
- `meridian.survey`
- `almanac.refresh`
- `AtlasStore`

The API now preserves obligation-level facts such as FBAR aggregate balance, FATCA threshold status, reportable-event flags, and India-source income. PLOT uses those facts to distinguish `absent`, `partial`, `not_applicable`, and `indeterminate`. COURSE creates no action for not-applicable or indeterminate duties.

## Backup and replay modes

The **AI/MCP** button defaults to the LLM path. If the OpenAI request, tool session, or model endpoint fails, the page automatically switches to the deterministic `/api/run` backup and explains why. A presenter can also select that backup deliberately. If the whole service is unreachable, the page loads `replay.js`; the header says that the result is captured. Replay covers only pristine prepared profiles; edited profiles require the live engine.

Regenerate after any pack, model, agent, or preset change:

```bash
python -m uvicorn demo.api:app --port 8000 &
python demo/capture_replay.py
```

The capture script calls `/api/run` and `/api/verify`; it provides a deterministic venue fallback and does not compose results.

## Presentation checklist

1. Confirm the health endpoint returns `{"ok": true, "ai_orchestration_available": true, ...}`.
2. Choose **Maeve** and keep **AI/MCP: on**.
3. Show the readable **AI orchestration · MCP** trace. Say: “The model discovered the source and case; it did not guess an ID.”
4. Show the **Before / Now** rule change. Leave the source hashes collapsed unless asked.
5. Open **What applies** and explain that Maeve's 2026 event selects 38% rather than 41%.
6. Open the **Action plan** and point to the task, date, and evidence required.
7. In **Check evidence**, apply the 41% example and show **Needs correction**.
8. Restore the 38% example and show **Accepted**.
9. Open the **Proof record**. Leave the technical event log collapsed unless asked.
10. If an AI call fails, say: “The model layer is unavailable, so TARA has switched to its labelled deterministic backup.” If the service fails entirely, use labelled replay.

## Slide-deck embedding

Prefer a large hyperlink or QR code to the canonical Render URL. Keep screenshots of the source diff and evidence result as backup. A PowerPoint web-view add-in can embed the site, but it depends on venue networking and add-in policy, so it should not be the only route.
