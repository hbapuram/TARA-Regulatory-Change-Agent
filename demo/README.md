# TARA live demo

> **Prototype scope:** controlled source snapshots and synthetic prepared cases. This is not legal, tax, immigration, or filing advice; a qualified professional must review any real-world action.

The browser demonstrates the real TARA pipeline. The recommended judge route is:

```text
Maeve → Section 4.3 source diff → 2026 effective-date selection
      → dated Playbook → submit 41% (returned) → submit 38% (closed)
      → inspect ATLAS trace
```

Maeve is the **tested golden path**. Ciarán, Priya, and Arun are clearly labelled exploratory breadth cases.

## Files

```text
demo/
  api.py              FastAPI adapter over the production pipeline
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
pip install -r demo/requirements.txt
python -m uvicorn demo.api:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`.

## Public service

- Demo: [https://tara-demo.onrender.com/](https://tara-demo.onrender.com/)
- Health: [https://tara-demo.onrender.com/api/health](https://tara-demo.onrender.com/api/health)
- Complete guide: [https://tara-demo.onrender.com/guide](https://tara-demo.onrender.com/guide)
- Evaluation card: [https://tara-demo.onrender.com/evaluation-card.md](https://tara-demo.onrender.com/evaluation-card.md)

The free Render service may need time to wake. Open it before presenting.

## What is computed

The page does not invent determinations, action dates, citations, or closure results. It calls:

- `tara.pipeline`
- `meridian.survey`
- `almanac.refresh`
- `AtlasStore`

The API now preserves obligation-level facts such as FBAR aggregate balance, FATCA threshold status, reportable-event flags, and India-source income. PLOT uses those facts to distinguish `absent`, `partial`, `not_applicable`, and `indeterminate`. COURSE creates no action for not-applicable or indeterminate duties.

## Replay mode

When the live engine is unreachable, the page loads `replay.js`. The header says that the result is captured. Replay covers only pristine prepared profiles; edited profiles require the live engine.

Regenerate after any pack, model, agent, or preset change:

```bash
python -m uvicorn demo.api:app --port 8000 &
python demo/capture_replay.py
```

The capture script calls `/api/run` and `/api/verify`; it does not compose results.

## Presentation checklist

1. Confirm the health endpoint returns `{"ok": true, ...}`.
2. Choose **Maeve**.
3. Show the Section 4.3 diff and both hashes.
4. Explain that 2025 selects 41% while 2026 selects 38%.
5. Open the Playbook and evidence contract.
6. Submit the 41% variant and show `returned`.
7. Submit the 38% variant and show `closed`.
8. Open the ATLAS trace.
9. If the network fails, continue in the clearly labelled replay mode.

## Slide-deck embedding

Prefer a large hyperlink or QR code to the canonical Render URL. Keep screenshots of the source diff and evidence result as backup. A PowerPoint web-view add-in can embed the site, but it depends on venue networking and add-in policy, so it should not be the only route.
