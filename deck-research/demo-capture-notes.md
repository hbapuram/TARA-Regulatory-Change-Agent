# TARA public-repo demo capture notes

Source of truth: `hbapuram/TARA-Regulatory-Change-Agent`, commit `290d417` (`main`).

## Verified UI flow and screenshot paths

1. **Choose case / product entry** — Maeve is explicitly labelled recommended; Ciarán, Priya, and Arun are exploratory breadth cases. Screenshot: `/home/ubuntu/screenshots/8000-i24yb250v0kqva0_2026-09-13_03-10-47_8225.webp`.
2. **Source chart** — 9 packs, 12 source snapshots hashed, 31 cited obligations, one source changed. Section 4.3 diff shows 41% replaced by 38% for deemed disposals on or after 1 January 2026. Screenshot: `/home/ubuntu/screenshots/8000-i24yb250v0kqva0_2026-09-13_03-10-55_1855.webp`.
3. **Parallel scan** — Maeve's one asset is checked against nine packs; four actions are opened in the `tax` pack and all three corridor packs are explicitly ruled out. Screenshot: `/home/ubuntu/screenshots/8000-i24yb250v0kqva0_2026-09-13_03-11-04_4212.webp`.
4. **Playbook** — four source-backed actions ordered and dated for Maeve; OBL-002B is the 38% current-rate action. Screenshot: `/home/ubuntu/screenshots/8000-i24yb250v0kqva0_2026-09-13_03-11-13_7520.webp`.
5. **Evidence form** — ANCHOR requires a tax computation with `rate_applied` and `computed_tax`, plus `deemed_gain` for the arithmetic check. Screenshot: `/home/ubuntu/screenshots/8000-i24yb250v0kqva0_2026-09-13_03-11-21_4086.webp`.
6. **Returned evidence** — the coherent 41% artefact (`rate_applied=0.41`, `computed_tax=4920`, `deemed_gain=12000`) is returned because it does not match the 38% rule for OBL-002B. Screenshot: `/home/ubuntu/screenshots/8000-i24yb250v0kqva0_2026-09-13_03-11-36_2193.webp`.
7. **Closed evidence** — the exact 38% artefact (`rate_applied=0.38`, `computed_tax=4560`, `deemed_gain=12000`) closes OBL-002B. Screenshot: `/home/ubuntu/screenshots/8000-i24yb250v0kqva0_2026-09-13_03-11-52_2500.webp`.
8. **ATLAS audit trail** — the run displays 152 pipeline entries, verified chain integrity, and seven agents that wrote during the scan; the latest ANCHOR check is shown as a separate verified server trace. Screenshot: `/home/ubuntu/screenshots/8000-i24yb250v0kqva0_2026-09-13_03-11-59_3246.webp`.

## Canonical public claims

- 9 named agents.
- 9 domain packs: 6 standalone + 3 corridor packs.
- 10 MCP tools.
- 112 automated tests at the repository's latest documented verification; rerun locally before final delivery.
- 8 executable acceptance checks.
- Controlled, versioned source snapshots and synthetic prepared profiles; not continuous current-law monitoring or real client data.
- Human professional review is required before real-world action or reliance.
- Recommended pitch route: Maeve → Section 4.3 source diff → 2026 effective-date selection → Playbook → submit 41% (returned) → submit 38% (closed) → ATLAS trace.
