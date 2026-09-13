"""The MCP server — the only door into TARA's agents.

All eight agents are exposed as MCP tools. Our own orchestrator (see
``tara/orchestrator``) connects to this server as an ordinary MCP client,
exactly as any other client would — there is no privileged internal path,
so composability is structural rather than claimed.

Run locally over stdio (what the CLI orchestrator and `tara serve` use):
    python -m tara.mcp_server.server

Run as a standalone, network-reachable service — the same server, the same
agents, a different transport (the MCP Python SDK already supports this;
nothing about the agents or tools below changes for it). This is what a
deployed instance (Render/Railway/Fly.io — any host that will run a
container and expose a port) runs:
    python -m tara.mcp_server.server --transport streamable-http --port 8000
    TARA_MCP_TRANSPORT=streamable-http PORT=8000 python -m tara.mcp_server.server

A deployed instance is reached at ``http://<host>/mcp`` by any MCP client
that speaks streamable-HTTP — a script using the `mcp` Python/JS client
library, another orchestrator (point tara/orchestrator/llm.py's client at
the URL instead of spawning this file as a subprocess), or a custom MCP
connector wherever the calling tool supports adding one by URL. See
deploy/README.md for the actual deploy steps.
"""
from __future__ import annotations

import argparse
import os
from datetime import date
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from .. import pipeline
from ..agents import almanac, anchor, course, meridian, survey
from ..core.domain_pack import DomainPack
from .context import REPO_ROOT, TaraContext, build_context

mcp = MCPServer("tara")

_ctx: TaraContext | None = None

# Every standalone domain pack a fresh server links by default, beyond the
# primary ctx.domain_pack (tax.yaml — the Ireland deemed-disposal pack).
# Each one is independently queryable through the domain_id-scoped tools
# below, and MERIDIAN cross-references them against a holder's own facts.
# Adding a fourth country is adding a fourth path here, never touching an
# agent. Cross-jurisdiction interactions (India-Ireland, and any future
# pair) live separately in DEFAULT_INTERACTIONS_YAML — see
# tara/core/interactions.py for why they're not full pack files here.
DEFAULT_LINKED_DOMAIN_YAMLS: list[str | Path] = [
    REPO_ROOT / "domains" / "india.yaml",
    REPO_ROOT / "domains" / "us.yaml",
    REPO_ROOT / "domains" / "ireland-irp.yaml",
    # Added 2026-09-12 to close a coverage gap a live end-to-end run found:
    # an Irish emigrant disposing of Irish land matched no loaded pack. This
    # line is the entire code change the new pack required — see the header
    # of domains/ireland-cgt-property.yaml.
    REPO_ROOT / "domains" / "ireland-cgt-property.yaml",
    # Added 2026-09-12: NRI capital gains tax on transfer of listed Indian
    # securities — see the header of domains/india-nri-securities.yaml. This
    # line is the entire code change the new pack required.
    REPO_ROOT / "domains" / "india-nri-securities.yaml",
]
DEFAULT_INTERACTIONS_YAML: Path = REPO_ROOT / "domains" / "interactions.yaml"


def get_context() -> TaraContext:
    """Builds the process-wide context on first use.

    The three tenant-state paths below (the holder register, the ATLAS
    ledger, the ALMANAC graph-version file) can each be overridden by an
    environment variable. Without them, an MCP *client* has no way to point
    this server at anything but the one register committed in the repo —
    the server is spawned as a subprocess (or reached over HTTP) and never
    sees a caller's Python objects, so `build_context`'s existing
    `register_json` argument is unreachable from the other side of the
    protocol. That made the MCP layer demo-only for a single hard-coded
    holder, while `--direct` callers (and capture_aoife_example.py) could
    freely pass their own register.

    Every variable is optional and falls back to exactly the previous
    hard-coded default, so `tara serve`, the LLM orchestrator, and any
    existing client are unaffected.
    """
    global _ctx
    if _ctx is None:
        _ctx = build_context(
            register_json=os.environ.get(
                "TARA_REGISTER_JSON", REPO_ROOT / "registers" / "holder_register.json"
            ),
            atlas_path=os.environ.get(
                "TARA_ATLAS_PATH", REPO_ROOT / "registers" / "atlas_log.jsonl"
            ),
            almanac_version_path=os.environ.get(
                "TARA_GRAPH_VERSION_PATH", REPO_ROOT / "registers" / "graph_version.json"
            ),
            linked_domain_yamls=DEFAULT_LINKED_DOMAIN_YAMLS,
            interactions_yaml=DEFAULT_INTERACTIONS_YAML,
        )
    return _ctx


def _parse_as_of(as_of: str | None) -> date | None:
    return date.fromisoformat(as_of) if as_of else None


def _resolve_domain_pack(ctx: TaraContext, domain_id: str | None) -> DomainPack:
    """Every TENANT tool below defaults to ctx.domain_pack (Ireland) exactly
    as before — domain_id is additive and optional, so no existing caller's
    behaviour changes. Passing a domain_id is what makes a linked pack
    "independently queryable": the same tool, a different pack, no new code
    path.
    """
    if domain_id is None or domain_id == ctx.domain_pack.domain_id:
        return ctx.domain_pack
    try:
        return ctx.linked_packs[domain_id]
    except KeyError as exc:
        known = [ctx.domain_pack.domain_id, *sorted(ctx.linked_packs)]
        raise ValueError(f"unknown or unlinked domain_id {domain_id!r}. Linked domains: {known}") from exc


@mcp.tool()
def list_domains() -> dict[str, Any]:
    """Lists every domain pack this server has loaded — the primary pack
    plus every linked one — so a client can discover what domain_id values
    the domain_id-scoped tools accept without hard-coding country names.
    """
    ctx = get_context()
    packs = [ctx.domain_pack, *ctx.linked_packs.values()]
    return {
        "domains": [
            {
                "domain_id": p.domain_id,
                "title": p.title,
                "is_corridor": p.is_corridor,
                "corridor": p.corridor,
                "source_ids": list(p.sources),
            }
            for p in packs
        ]
    }


@mcp.tool()
def list_sources(domain_id: str | None = None) -> dict[str, Any]:
    """Lists the configured regulatory sources for a domain pack.

    Clients must use the returned ``source_id`` values when calling
    ``survey_detect_change`` or ``legend_decompose``. Human descriptions such
    as ``luxembourg_offshore_fund`` are not valid source identifiers.
    """
    ctx = get_context()
    try:
        domain_pack = _resolve_domain_pack(ctx, domain_id)
    except ValueError as exc:
        return {
            "error": str(exc),
            "hint": "Use an exact domain_id returned by list_domains; do not use a country, city, or holding name.",
            "available_domains": list_domains()["domains"],
        }
    return {
        "domain_id": domain_pack.domain_id,
        "sources": [
            {
                "source_id": source.source_id,
                "instrument": source.instrument,
                "issuing_authority": source.issuing_authority,
                "url": source.url,
                "last_verified": source.last_verified,
            }
            for source in domain_pack.sources.values()
        ],
    }


@mcp.tool()
def list_holdings() -> dict[str, Any]:
    """Lists the prepared holdings available to tenant assessment tools.

    Clients must use the exact ``holding_id`` returned here. The response
    contains only routing facts needed to choose a case, not private register
    fields or conclusions.
    """
    ctx = get_context()
    return {
        "holdings": [
            {
                "holding_id": holding["holding_id"],
                "holder_id": holding.get("holder_id"),
                "instrument_type": holding.get("instrument_type"),
                "jurisdiction": holding.get("jurisdiction"),
                "status": holding.get("status"),
            }
            for holding in ctx.register.get("holdings", [])
        ]
    }


@mcp.tool()
def survey_detect_change(source_id: str, domain_id: str | None = None) -> dict[str, Any]:
    """OPEN · SURVEY. Diff a named, configured source against its prior
    indexed version and report what changed, with provision references and
    citations. Never scrapes the open web — configured sources only.
    ``domain_id`` selects which linked pack's sources to look in (see
    list_domains); omit it for the primary pack.
    """
    ctx = get_context()
    domain_pack = _resolve_domain_pack(ctx, domain_id)
    record = survey.detect_change(domain_pack, source_id, atlas=ctx.atlas)
    return record.as_dict()


@mcp.tool()
def legend_decompose(source_id: str, domain_id: str | None = None) -> dict[str, Any]:
    """OPEN · LEGEND. Decompose a source's currently-catalogued obligations
    into discrete, cited, individually testable requirements. Excludes any
    obligation already superseded by a later one. ``domain_id`` selects
    which linked pack (see list_domains); omit it for the primary pack.
    """
    ctx = get_context()
    domain_pack = _resolve_domain_pack(ctx, domain_id)
    change_record = survey.detect_change(domain_pack, source_id, atlas=ctx.atlas)
    from ..agents import legend as legend_module

    records = legend_module.decompose(domain_pack, change_record, atlas=ctx.atlas)
    live = [
        r for r in records
        if domain_pack.obligation(r.obligation_id).superseded_by is None
    ]
    return {"source_id": source_id, "domain_id": domain_pack.domain_id, "obligations": [r.as_dict() for r in live]}


@mcp.tool()
def almanac_refresh(domain_id: str | None = None) -> dict[str, Any]:
    """OPEN · ALMANAC. Runs SURVEY across every configured source, asserts
    per-source coverage, and versions the obligation graph — marking each
    obligation unchanged, amended, superseded or withdrawn since the last
    refresh. Superseded obligations trigger ANCHOR to reopen any closures
    made against them. ``domain_id`` selects which linked pack (see
    list_domains); omit it for the primary pack. Each pack versions its own
    graph, in its own file next to the others under registers/.
    """
    ctx = get_context()
    domain_pack = _resolve_domain_pack(ctx, domain_id)
    version_path = (
        ctx.almanac_version_path if domain_pack is ctx.domain_pack
        else ctx.almanac_version_path.with_name(f"graph_version_{domain_pack.domain_id}.json")
    )
    result = almanac.refresh(domain_pack, version_path, atlas=ctx.atlas)
    return result.as_dict()


@mcp.tool()
def compass_assess(
    holding_id: str, profile_answers: dict[str, Any] | None = None, domain_id: str | None = None
) -> dict[str, Any]:
    """TENANT · COMPASS. Runs the applicability interview for one holding
    against one domain pack. Returns CONFIRMED, EXEMPT or INDETERMINATE —
    INDETERMINATE means a fact is missing and ``profile_answers`` should
    supply it on the next call. ``domain_id`` selects which linked pack
    (see list_domains) to assess against; omit it for the primary pack.
    This is what makes each linked jurisdiction independently queryable —
    call it once per domain_id to see how each rules on its own, or use
    meridian_survey to get all of them, plus any matching corridor, in one
    call.
    """
    ctx = get_context()
    domain_pack = _resolve_domain_pack(ctx, domain_id)
    determination = pipeline.determination_for(ctx, holding_id, profile_answers or {}, domain_pack=domain_pack)
    return determination.as_dict()


@mcp.tool()
def plot_align(
    holding_id: str,
    profile_answers: dict[str, Any] | None = None,
    as_of: str | None = None,
    domain_id: str | None = None,
) -> dict[str, Any]:
    """TENANT · PLOT. Aligns a holding's applicable obligations against the
    register, firing calendar-driven date triggers. Internally runs COMPASS
    first — PLOT can never be reached for a holding COMPASS has not
    confirmed. ``domain_id`` selects which linked pack (see list_domains);
    omit it for the primary pack.
    """
    ctx = get_context()
    domain_pack = _resolve_domain_pack(ctx, domain_id)
    determination, gaps = pipeline.gaps_for(
        ctx, holding_id, profile_answers or {}, as_of=_parse_as_of(as_of), domain_pack=domain_pack
    )
    return {
        "determination": determination.as_dict(),
        "gaps": [g.as_dict() for g in gaps],
    }


@mcp.tool()
def course_plan(
    holding_id: str,
    profile_answers: dict[str, Any] | None = None,
    as_of: str | None = None,
    domain_id: str | None = None,
) -> dict[str, Any]:
    """TENANT · COURSE. Converts a holding's gaps into dated, owned actions,
    sequenced by dependency. Internally runs COMPASS then PLOT first.
    ``domain_id`` selects which linked pack (see list_domains); omit it for
    the primary pack.
    """
    ctx = get_context()
    domain_pack = _resolve_domain_pack(ctx, domain_id)
    determination, actions = pipeline.actions_for(
        ctx, holding_id, profile_answers or {}, as_of=_parse_as_of(as_of), domain_pack=domain_pack
    )
    return {
        "determination": determination.as_dict(),
        "actions": [a.as_dict() for a in actions],
    }


@mcp.tool()
def anchor_verify(
    holding_id: str,
    obligation_id: str,
    artefact: dict[str, Any],
    profile_answers: dict[str, Any] | None = None,
    as_of: str | None = None,
    domain_id: str | None = None,
) -> dict[str, Any]:
    """TENANT · ANCHOR. Verifies a submitted artefact against the evidence
    rules for one obligation. Closes only where responsive, and every
    numeric check is exact — never an approximate match. Internally runs
    COMPASS first, exactly like plot_align and course_plan — ANCHOR raises
    if this holding is not CONFIRMED (EXEMPT/INDETERMINATE holdings cannot
    have obligations closed against them), so supply the same
    ``profile_answers`` this holding needed for compass_assess/course_plan.
    ``domain_id`` selects which linked pack the obligation belongs to (see
    list_domains); omit it for the primary pack.
    """
    ctx = get_context()
    domain_pack = _resolve_domain_pack(ctx, domain_id)
    action = course.Action(
        action_id=f"ACT-{obligation_id}-{holding_id}",
        obligation_id=obligation_id,
        holding_id=holding_id,
        owner=ctx.owner_name(),
        deadline=None,
        required_evidence_type="",
        depends_on=(),
        escalated=False,
        escalation_reason=None,
    )
    result = pipeline.verify_action(
        ctx, action, artefact, profile_answers=profile_answers or {}, as_of=_parse_as_of(as_of), domain_pack=domain_pack
    )
    return result.as_dict()


@mcp.tool()
def meridian_survey(
    holding_id: str,
    profile_answers: dict[str, Any] | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    """TENANT · MERIDIAN. The cross-jurisdiction layer: runs compass_assess
    -> plot_align -> course_plan for this holding against the primary pack
    AND every linked pack (see list_domains), applying each corridor pack's
    own applicability check first. A holder who is only, say, Irish tax
    resident sees every non-matching corridor listed with
    considered=false and the reason it was ruled out — not silently
    dropped. A holder whose citizenships and tax_residencies match a
    corridor sees it CONFIRMED alongside the standalone jurisdictions, with
    its own obligations and actions, exactly as any other domain pack would
    produce them.
    """
    ctx = get_context()
    report = meridian.survey(ctx, holding_id, profile_answers or {}, as_of=_parse_as_of(as_of))
    return report.as_dict()


@mcp.tool()
def atlas_reconstruct(obligation_id: str) -> dict[str, Any]:
    """Cross-cutting · ATLAS. Reconstructs the full chain — from source
    provision to closed action — for one obligation, in recorded order.
    """
    ctx = get_context()
    chain = ctx.atlas.reconstruct(obligation_id)
    return {"obligation_id": obligation_id, "chain": chain, "chain_verified": ctx.atlas.verify_chain()}


def main(argv: list[str] | None = None) -> None:
    """Reads transport/host/port from CLI flags (``argv`` — passed explicitly
    by ``tara serve`` so this module never has to parse the outer `tara`
    command's own argv; None means "parse sys.argv", for running this file
    directly), falling back to environment variables, falling back to the
    original zero-config stdio behaviour — so every existing caller
    (`tara serve` with no flags, the LLM orchestrator, which spawns this
    module as a subprocess and speaks stdio to it) is unaffected. Only a
    deployed instance needs to pass anything at all.

    PORT is read bare (not TARA_MCP_PORT) because that is the environment
    variable Render, Railway and most other container platforms set
    automatically for the port your process must bind — one less thing to
    configure by hand when deploying.
    """
    parser = argparse.ArgumentParser(prog="tara-mcp-server")
    parser.add_argument(
        "--transport", choices=["stdio", "sse", "streamable-http"],
        default=os.environ.get("TARA_MCP_TRANSPORT", "stdio"),
        help="stdio (default; local subprocess use) or streamable-http (a deployed, network-reachable service).",
    )
    parser.add_argument(
        "--host", default=os.environ.get("TARA_MCP_HOST", "0.0.0.0"),
        help="Bind address for streamable-http/sse. 0.0.0.0 (default) is required inside a container.",
    )
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("PORT", os.environ.get("TARA_MCP_PORT", 8000))),
        help="Bind port for streamable-http/sse (default: $PORT, else $TARA_MCP_PORT, else 8000).",
    )
    args = parser.parse_args(argv)

    if args.transport == "stdio":
        mcp.run()
    else:
        mcp.run(transport=args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
