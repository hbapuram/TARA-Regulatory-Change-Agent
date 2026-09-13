"""Compliance calendar exporter — a real reference app on top of TARA's MCP
server, not a mockup of one.

What this proves
-----------------
This is the plainest possible "app buildable on TARA": read a holder's
register, ask the MCP server what's confirmed for each holding, turn every
resulting dated action into an .ics calendar file the holder can import into
Google Calendar, Outlook, or Apple Calendar. No UI, no framework — just three
MCP tool calls per holding (``meridian_survey``, then ``course_plan`` per
confirmed domain) and a text-format writer at the end. Anything richer
(a web dashboard, a Slack reminder bot, a client-facing portal) is this same
call sequence with a different last step.

Design note: why course_plan, not meridian_survey, for the actions
--------------------------------------------------------------------
``meridian_survey``'s JSON response summarizes each pack's actions as bare
action-ID strings (``JurisdictionResult.as_dict()`` in
``tara/agents/meridian.py`` only emits ``[a.action_id for a in self.actions]``)
— enough to know an action exists, not enough to calendar it. ``course_plan``
returns the full ``Action.as_dict()`` for each domain — deadline, provision,
owner, required_evidence_type, escalation state — because it's the tool a
tenant-facing client calls once it already knows which domain to ask about.
So this app uses meridian_survey for what demo_scenarios.py already uses it
for (discovering which domains are CONFIRMED for a holding, across every
linked pack, in one call) and then calls course_plan once per confirmed
domain to get the fields an .ics event actually needs. A domain that comes
back INDETERMINATE is reported, not guessed at — this app does not invent an
answer to a compliance question on the holder's behalf.

Run:
    python apps/compliance_calendar.py
    python apps/compliance_calendar.py --register path/to/holder_register.json --out my_calendar.ics
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO_ROOT = Path(__file__).resolve().parent.parent


# ── MCP call wrapper (same pattern as demo_scenarios.py's McpRun) ──────────

class McpRun:
    def __init__(self, session: ClientSession):
        self.session = session

    async def call(self, name: str, **arguments: Any) -> Any:
        result = await self.session.call_tool(name, arguments)
        parts = [b.text for b in result.content if hasattr(b, "text")]
        raw = "\n".join(parts)
        if getattr(result, "is_error", False):
            print(f"  ! {name}({arguments}) -> ERROR: {raw}", file=sys.stderr)
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw


# ── iCalendar writing (hand-rolled, RFC 5545 — no external dependency) ─────

def _ics_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """RFC 5545 line folding at 75 octets, continuation lines start with a space."""
    if len(line) <= 75:
        return line
    out, rest = line[:75], line[75:]
    while rest:
        out += "\r\n " + rest[:74]
        rest = rest[74:]
    return out


def build_ics(events: list[dict[str, Any]]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//TARA//Compliance Calendar Exporter//EN",
        "CALSCALE:GREGORIAN",
    ]
    for ev in events:
        deadline = ev["deadline"].replace("-", "")
        lines += [
            "BEGIN:VEVENT",
            f"UID:{ev['action_id']}@tara.local",
            f"DTSTAMP:{now}",
            f"DTSTART;VALUE=DATE:{deadline}",
            f"DTEND;VALUE=DATE:{deadline}",
            _fold(f"SUMMARY:{_ics_escape(ev['summary'])}"),
            _fold(f"DESCRIPTION:{_ics_escape(ev['description'])}"),
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            "DESCRIPTION:Compliance deadline in 7 days",
            "TRIGGER:-P7D",
            "END:VALARM",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


# ── The app itself ──────────────────────────────────────────────────────────

async def build_calendar(register_path: Path, as_of: str | None) -> tuple[list[dict[str, Any]], list[str]]:
    """Returns (calendar_events, notes). notes records every domain this run
    could NOT calendar and why (EXEMPT, not considered, or INDETERMINATE)."""
    register = json.loads(register_path.read_text(encoding="utf-8"))
    holder = register["holder"]
    holdings = register["holdings"]

    tmpdir = Path(tempfile.mkdtemp(prefix="tara-calendar-"))
    env = dict(os.environ)
    env["TARA_REGISTER_JSON"] = str(register_path.resolve())
    env["TARA_ATLAS_PATH"] = str(tmpdir / "atlas_log.jsonl")
    env["TARA_GRAPH_VERSION_PATH"] = str(tmpdir / "graph_version.json")

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "tara.mcp_server.server"],
        env=env,
        cwd=str(REPO_ROOT),
    )

    # Keyed by (domain_id, obligation_id), not action_id: some obligations
    # (e.g. OBL-CORR-001 in domains/interactions.yaml) are triggered by a
    # holder-level fact — tax_residency_since — not by anything specific to
    # one holding, so course_plan fires an action_id per holding_id surveyed
    # (ACT-OBL-CORR-001-HLD-001, -HLD-002, ...) even though it is the same
    # real-world filing regardless of how many holdings triggered it. This
    # app collapses those into one calendar entry and lists every holding
    # that surfaced it, rather than showing the same deadline N times.
    events: dict[tuple[str, str], dict[str, Any]] = {}
    notes: list[str] = []

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            run = McpRun(session)

            for holding in holdings:
                holding_id = holding["holding_id"]
                survey_kwargs: dict[str, Any] = {"holding_id": holding_id}
                if as_of:
                    survey_kwargs["as_of"] = as_of
                report = await run.call("meridian_survey", **survey_kwargs)
                if report is None:
                    notes.append(f"{holding_id}: meridian_survey failed, skipped")
                    continue

                for r in report.get("results", []):
                    domain_id = r["domain_id"]
                    if not r["considered"]:
                        notes.append(
                            f"{holding_id} / {domain_id}: not considered "
                            f"({r.get('skipped_reason') or 'no reason given'})"
                        )
                        continue
                    status = r["determination"]["status"] if r["determination"] else None
                    if status != "CONFIRMED":
                        reason = (
                            r["determination"].get("missing_question")
                            if status == "INDETERMINATE" and r["determination"]
                            else None
                        )
                        detail = f" — needs an answer to: {reason}" if reason else ""
                        notes.append(f"{holding_id} / {domain_id}: {status}{detail}")
                        continue

                    plan_kwargs: dict[str, Any] = {
                        "holding_id": holding_id,
                        "domain_id": domain_id,
                    }
                    if as_of:
                        plan_kwargs["as_of"] = as_of
                    plan = await run.call("course_plan", **plan_kwargs)
                    if plan is None:
                        notes.append(f"{holding_id} / {domain_id}: course_plan failed, skipped")
                        continue

                    for action in plan.get("actions", []):
                        if not action.get("deadline"):
                            continue
                        key = (domain_id, action["obligation_id"])
                        existing = events.get(key)
                        if existing is not None:
                            existing["holding_ids"].append(holding_id)
                            continue
                        events[key] = {
                            "action_id": action["action_id"],
                            "deadline": action["deadline"],
                            "domain_id": domain_id,
                            "obligation_id": action["obligation_id"],
                            "provision": action.get("provision"),
                            "owner": action.get("owner"),
                            "required_evidence_type": action.get("required_evidence_type"),
                            "escalated": action.get("escalated", False),
                            "escalation_reason": action.get("escalation_reason"),
                            "holding_ids": [holding_id],
                        }

    finished = []
    for ev in events.values():
        holdings_str = ", ".join(ev["holding_ids"])
        finished.append({
            "action_id": ev["action_id"],
            "deadline": ev["deadline"],
            "summary": (
                f"[{ev['domain_id']}] {ev['obligation_id']} due "
                f"({holder.get('name', holder.get('holder_id'))})"
            ),
            "description": (
                f"Holding(s): {holdings_str}\n"
                f"Obligation: {ev['obligation_id']}\n"
                f"Provision: {ev['provision'] or 'n/a'}\n"
                f"Owner: {ev['owner'] or 'unassigned'}\n"
                f"Required evidence: {ev['required_evidence_type'] or 'n/a'}\n"
                f"Escalated: {ev['escalated']}"
                + (f" ({ev['escalation_reason']})" if ev["escalation_reason"] else "")
            ),
        })
    return finished, notes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--register", type=Path, default=REPO_ROOT / "registers" / "holder_register.json",
        help="Path to a holder register JSON file (default: the repo's demo register).",
    )
    parser.add_argument(
        "--out", type=Path, default=REPO_ROOT / "apps" / "compliance_calendar.ics",
        help="Where to write the .ics file.",
    )
    parser.add_argument(
        "--as-of", default=None,
        help="Evaluate as of this date (YYYY-MM-DD). Default: the server's own current date.",
    )
    args = parser.parse_args()

    events, notes = asyncio.run(build_calendar(args.register, args.as_of))

    events.sort(key=lambda e: e["deadline"])
    args.out.write_text(build_ics(events), encoding="utf-8")

    print(f"Wrote {len(events)} calendar event(s) to {args.out}")
    for ev in events:
        print(f"  {ev['deadline']}  {ev['summary']}")
    if notes:
        print(f"\n{len(notes)} domain(s) not calendared this run:")
        for n in notes:
            print(f"  - {n}")


if __name__ == "__main__":
    main()
