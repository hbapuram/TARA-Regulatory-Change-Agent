"""TARA Live Demo API — a thin HTTP surface over the real TARA pipeline.

Every determination, deadline, citation, and closure this service returns is
produced by calling the same pipeline functions the MCP server calls
(``tara.pipeline.*``, ``meridian.survey``, ``almanac.refresh``,
``AtlasStore.verify_chain``) against the checked-in domain packs and controlled
source snapshots. For presentation only, the API also supplies clearly
editable synthetic evidence examples; ANCHOR's verdict on them is computed by
the real pipeline.

Why a JSON API next to the MCP server rather than the MCP server itself:
a browser cannot safely hold an OpenAI key or speak MCP's streamable-HTTP
transport. This module is the browser-facing adapter. Its default `/api/ai/run`
path invokes an OpenAI model server-side, lets it choose guarded local MCP
tools, and returns an inspectable tool trace alongside the independently
rendered deterministic result. `/api/run` remains the no-model fallback.
``tara serve --transport streamable-http`` remains the interface for real MCP
clients and is unaffected by anything in this file.

Stateless by design: every request builds a fresh TaraContext over a
temporary register + ATLAS ledger, so two people driving the demo at once
never see each other's data, and there is no session state to lose on a
cold start.

Run locally:   python -m uvicorn demo.api:app --reload --port 8000
Run deployed:  python -m demo.api            (reads $PORT)
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterator

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from tara import pipeline
from tara.agents import almanac, meridian
from tara.mcp_server.context import TaraContext, build_context

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = Path(__file__).resolve().parent

PRIMARY_YAML = REPO_ROOT / "domains" / "tax.yaml"
LINKED_YAMLS = [
    REPO_ROOT / "domains" / "india.yaml",
    REPO_ROOT / "domains" / "us.yaml",
    REPO_ROOT / "domains" / "ireland-irp.yaml",
    REPO_ROOT / "domains" / "ireland-cgt-property.yaml",
    REPO_ROOT / "domains" / "india-nri-securities.yaml",
]
INTERACTIONS_YAML = REPO_ROOT / "domains" / "interactions.yaml"

# ---------------------------------------------------------------------------
# Pack metadata read straight off the YAML — the wizard renders its interview
# questions and evidence forms from this, so a new domain pack shows up in the
# UI with no frontend change, exactly as it shows up in list_domains with no
# agent change.
# ---------------------------------------------------------------------------


def _load_pack_meta() -> dict[str, dict[str, Any]]:
    meta: dict[str, dict[str, Any]] = {}

    def add(domain_id: str, title: str, tenant: dict[str, Any], is_corridor: bool) -> None:
        meta[domain_id] = {
            "domain_id": domain_id,
            "title": title,
            "is_corridor": is_corridor,
            "questions": {
                q["question_id"]: {
                    "question_id": q["question_id"],
                    "text": q.get("text", "").strip(),
                    "register_field": q.get("register_field"),
                    "expect": q.get("expect"),
                    "answerable_from_register": q.get("register_field") is not None,
                }
                for q in tenant.get("scoping_questions", []) or []
            },
            "evidence": tenant.get("evidence_rules", {}) or {},
        }

    for path in [PRIMARY_YAML, *LINKED_YAMLS]:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        add(doc["domain_id"], doc.get("title", ""), doc.get("tenant", {}) or {}, False)

    inter = yaml.safe_load(INTERACTIONS_YAML.read_text(encoding="utf-8"))
    for entry in inter.get("interactions", []) or []:
        questions: dict[str, Any] = {}
        evidence: dict[str, Any] = {}
        for i, req in enumerate(entry.get("requires", []) or [], start=1):
            qid = f"SQ-CORR-{i:02d}"
            questions[qid] = {
                "question_id": qid,
                "text": f"{req['requirement'].replace('_', ' ')}: {req['value']}",
                "register_field": req["requirement"],
                "expect": None,
                "answerable_from_register": True,
            }
        for obl in entry.get("obligations", []) or []:
            ev = obl.get("evidence", {}) or {}
            evidence[obl["obligation_id"]] = {
                "artefact_type": obl.get("artefact_type"),
                "required_fields": ev.get("required_fields", []),
                "lead_time_days": ev.get("lead_time_days"),
                **({"expected_rate": ev["expected_rate"]} if "expected_rate" in ev else {}),
            }
        meta[entry["domain_id"]] = {
            "domain_id": entry["domain_id"],
            "title": entry.get("title", ""),
            "is_corridor": True,
            "questions": questions,
            "evidence": evidence,
        }
    return meta


PACK_META = _load_pack_meta()

INSTRUMENT_TYPES = [
    {"value": "offshore_fund", "label": "Offshore fund"},
    {"value": "personal_portfolio_investment_undertaking", "label": "Personal portfolio investment undertaking"},
    {"value": "foreign_life_assurance_policy", "label": "Foreign life assurance policy"},
    {"value": "direct_equity", "label": "Direct equity (listed shares)"},
    {"value": "residential_property", "label": "Residential property"},
    {"value": "commercial_property", "label": "Commercial property"},
    {"value": "land", "label": "Land"},
    {"value": "foreign_bank_account", "label": "Foreign bank account"},
    {"value": "immigration_permission", "label": "Immigration permission (IRP)"},
]

RESIDENCY_STATUSES = [
    "Irish tax resident",
    "Irish ordinarily resident",
    "Non-resident",
]

COUNTRIES = ["Ireland", "India", "United States", "United Kingdom", "Other"]


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class Holder(BaseModel):
    holder_id: str = "H-DEMO"
    name: str = "Demo holder"
    citizenships: list[str] = Field(default_factory=list)
    tax_residencies: list[str] = Field(default_factory=list)
    tax_residency_since: str | None = None
    eea_swiss_uk_national: bool = True
    holder_residency: str = "Irish tax resident"


class Holding(BaseModel):
    holding_id: str
    instrument_type: str
    jurisdiction: str
    acquisition_date: str
    status: str = "held"
    disposal_date: str | None = None
    disposal_consideration: float | None = None
    cgt_payment_due_date: str | None = None
    cgt_return_due_date: str | None = None
    irp_registration_due_date: str | None = None
    irp_expiry_date: str | None = None
    # The real Section 139(1) return-due date for the NRI securities pack —
    # carried as a stated register fact for the same reason cgt_return_due_date
    # is: it is a fixed calendar date tied to the assessment year, not an
    # anniversary of the disposal, so the date engine cannot derive it.
    india_itr_due_date: str | None = None
    # Obligation-level applicability facts. These keep pack-wide scope from
    # becoming an assumption that every duty in that pack applies.
    peak_aggregate_value_usd: float | None = None
    fatca_threshold_met: bool | None = None
    form_3520_reportable_event: bool | None = None
    pfic_reportable_event: bool | None = None
    india_source_income: bool | None = None


class RunRequest(BaseModel):
    holder: Holder
    holdings: list[Holding]
    answers: dict[str, Any] = Field(default_factory=dict)
    as_of: str | None = None


class VerifyRequest(RunRequest):
    domain_id: str
    action_id: str
    artefact: dict[str, Any]


# ---------------------------------------------------------------------------
# Register assembly
# ---------------------------------------------------------------------------


def _statutory_cgt_dates(disposal_date: str) -> tuple[str, str]:
    """The two statutory CGT dates the pack carries as register facts rather
    than deriving by interval arithmetic (see ireland-cgt-property.yaml and
    the DT-CGT-03 / DT-CGT-04 trigger descriptions).

    Payment: 15 December of the year of disposal for disposals 1 Jan-30 Nov;
    31 January following for disposals in December.
    Return:  31 October of the year of assessment following the disposal.

    These are stated dates in Revenue's own guidance, not anniversaries, which
    is exactly why TARA's date engine cannot derive them and the register has
    to hold them. The demo prefills them so a viewer is not asked to type a
    statutory deadline; both remain editable.
    """
    d = date.fromisoformat(disposal_date)
    if d.month == 12:
        payment = date(d.year + 1, 1, 31)
    else:
        payment = date(d.year, 12, 15)
    return payment.isoformat(), date(d.year + 1, 10, 31).isoformat()


def _register_from(holder: Holder, holdings: list[Holding]) -> dict[str, Any]:
    holdings_out: list[dict[str, Any]] = []
    for h in holdings:
        entry: dict[str, Any] = {
            "holding_id": h.holding_id,
            "instrument_type": h.instrument_type,
            "jurisdiction": h.jurisdiction,
            "acquisition_date": h.acquisition_date,
            "status": h.status,
            # holder_residency is read off the holding by tax.yaml's SQ-01,
            # so it is copied down from the holder rather than asked per row.
            "holder_residency": holder.holder_residency,
        }
        if h.status == "disposed" and h.disposal_date:
            entry["disposal_date"] = h.disposal_date
            if h.disposal_consideration is not None:
                entry["disposal_consideration"] = h.disposal_consideration
            pay, ret = _statutory_cgt_dates(h.disposal_date)
            entry["cgt_payment_due_date"] = h.cgt_payment_due_date or pay
            entry["cgt_return_due_date"] = h.cgt_return_due_date or ret
        if h.india_itr_due_date:
            entry["india_itr_due_date"] = h.india_itr_due_date
        for field in (
            "peak_aggregate_value_usd",
            "fatca_threshold_met",
            "form_3520_reportable_event",
            "pfic_reportable_event",
            "india_source_income",
        ):
            value = getattr(h, field)
            if value is not None:
                entry[field] = value
        if h.instrument_type == "immigration_permission":
            if h.irp_registration_due_date:
                entry["irp_registration_due_date"] = h.irp_registration_due_date
            if h.irp_expiry_date:
                entry["irp_expiry_date"] = h.irp_expiry_date
        holdings_out.append(entry)

    return {
        "holder": {
            "holder_id": holder.holder_id,
            "name": holder.name,
            "citizenships": holder.citizenships,
            "tax_residencies": holder.tax_residencies,
            "tax_residency_since": holder.tax_residency_since,
            "eea_swiss_uk_national": holder.eea_swiss_uk_national,
        },
        "holdings": holdings_out,
    }


@contextmanager
def _context_for(register: dict[str, Any]) -> Iterator[tuple[TaraContext, Path]]:
    with TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        register_path = tmp_path / "register.json"
        register_path.write_text(json.dumps(register, indent=2), encoding="utf-8")
        ctx = build_context(
            domain_yaml=PRIMARY_YAML,
            register_json=register_path,
            atlas_path=tmp_path / "atlas_log.jsonl",
            almanac_version_path=tmp_path / "graph_version.json",
            linked_domain_yamls=LINKED_YAMLS,
            interactions_yaml=INTERACTIONS_YAML,
        )
        yield ctx, tmp_path


def _as_of(value: str | None) -> date:
    return date.fromisoformat(value) if value else date.today()


def _all_packs(ctx: TaraContext) -> dict[str, Any]:
    return {ctx.domain_pack.domain_id: ctx.domain_pack, **ctx.linked_packs}


def _evidence_for(domain_id: str, obligation_id: str) -> dict[str, Any]:
    return PACK_META.get(domain_id, {}).get("evidence", {}).get(obligation_id, {}) or {}


# ---------------------------------------------------------------------------
# Suggested artefacts
#
# ANCHOR validates a submission the holder makes; the submission itself is the
# holder's own data, not TARA's output. The demo prefills a plausible, valid
# one so a viewer is not asked to invent a CG50A certificate number on camera
# — every field stays editable, and the only thing that is not invented is
# ANCHOR's verdict on it.
#
# A tax_computation deliberately carries deemed_gain even though no pack lists
# it in required_fields, so ANCHOR's exact arithmetic cross-check actually has
# operands to run against (see _arithmetic_checkable in tara/agents/anchor.py)
# rather than being skipped. That is what makes the "€4,560 exactly, not
# approximately" beat demonstrable.
# ---------------------------------------------------------------------------

DEEMED_GAIN = 12000.0
CHARGEABLE_GAIN = 400000.0
CGT_ANNUAL_EXEMPTION = 1270.0  # Section 601 TCA 1997 personal exemption

# Plausible figures for the India NRI securities pack's suggested submission —
# same simplification the Irish CGT constants above already make (a flat
# demo figure rather than a derived cost basis, which no register field here
# tracks): a long-term gain on listed Indian equity, taxed at the 12.5% rate
# domains/india-nri-securities.yaml's OBL-NRI-001 cites (Section 1.3).
NRI_LTCG_GAIN = 95000.0
NRI_LTCG_RATE = 0.125


def _year_of(iso: str | None, fallback: int = 2026) -> int:
    try:
        return date.fromisoformat(iso).year  # type: ignore[arg-type]
    except Exception:
        return fallback


def _suggest_field(
    field: str, holding: dict[str, Any], rate: float | None, deadline: str | None
) -> Any:
    year = _year_of(deadline)
    when = deadline or date.today().isoformat()
    is_nri_equity = holding.get("jurisdiction") == "India" and holding.get("instrument_type") == "direct_equity"
    if field == "rate_applied":
        return rate
    if field == "annual_exemption_applied":
        return CGT_ANNUAL_EXEMPTION
    if field == "disposal_date":
        return holding.get("disposal_date") or when
    if field in ("disposal_proceeds", "consideration"):
        return holding.get("disposal_consideration") or 1250000.0
    if field in ("chargeable_gain", "computed_gain"):
        return NRI_LTCG_GAIN if is_nri_equity else CHARGEABLE_GAIN
    if field == "gain_type":
        return "long_term"
    if field in ("computed_tax", "tax_paid_amount"):
        if is_nri_equity:
            return round(NRI_LTCG_GAIN * NRI_LTCG_RATE, 2)
        r = rate if rate is not None else 0.33
        return round((CHARGEABLE_GAIN - CGT_ANNUAL_EXEMPTION) * r, 2)
    if field == "tds_amount":
        return round(NRI_LTCG_GAIN * NRI_LTCG_RATE, 2)
    if field == "deduction_date":
        return holding.get("disposal_date") or when
    if field == "itr_form":
        return "ITR-2"
    if field.endswith("_date"):
        return when
    if field == "form_type":
        return "CG1"
    if field == "certificate_number":
        return f"CG50A-{year}-004182"
    if field == "reference_number":
        return f"VAL-{year}-77310"
    if field == "irp_number":
        return "IRP-2018-114093"
    if field == "months_occupied":
        return 0
    if field == "months_owned":
        return 122
    if field == "relieved_proportion":
        return 0.0
    if field in ("assessment_year", "tax_year", "calendar_year"):
        return str(year)
    if field == "peak_balance":
        return 84500.0
    if field == "peak_aggregate_value_usd":
        return 96000.0
    if field == "specified_asset_value_usd":
        return 96000.0
    if field == "foreign_income_amount":
        return 3120.0
    if field == "foreign_tax_paid_amount":
        return 468.0
    if field == "account_type":
        return "NRO"
    if field == "new_address":
        return "14 Grand Canal Quay, Dublin 2"
    if field == "asset_description":
        return "Ireland-domiciled accumulating ETF"
    if field == "beneficial_interest_type":
        return "beneficial owner"
    if field == "foreign_trust_or_gift_description":
        return "Distribution from a non-grantor foreign trust"
    if field == "pfic_identifier":
        return "IE00B4L5Y983"
    if field in ("irish_cgt_paid", "credit_claimed"):
        return round((CHARGEABLE_GAIN - CGT_ANNUAL_EXEMPTION) * 0.33, 2)
    if field == "irish_return_reference":
        return f"CG1-{year}-004512"
    if field == "payment_receipt_reference":
        return f"REV-RCT-{year}-118823"
    return "provided"


# The rate a holder plausibly submits by mistake: the one the guidance used to
# say. 41% is the pre-2026 exit-tax rate superseded by Finance Act 2025; 30% is
# simply not the 33% CGT rate. Both produce a real ANCHOR rejection.
SUPERSEDED_RATE = {0.38: 0.41, 0.41: 0.38, 0.33: 0.30}


def _round2(x: float) -> float:
    return int(x * 100 + 0.5) / 100 if x >= 0 else -(int(-x * 100 + 0.5) / 100)


def _artefact_variants(
    domain_id: str, obligation_id: str, holding: dict[str, Any], deadline: str | None
) -> dict[str, Any]:
    """The valid submission plus the specific ways of breaking it the demo
    offers as one-click chips.

    These are built here rather than in the browser so that a live run and a
    replayed one submit byte-identical artefacts — floating-point rounding
    differs between Python and JavaScript, and a demo that silently falls out
    of replay because 119618.99 != 119619.0 is worse than no demo.
    """
    rule = _evidence_for(domain_id, obligation_id)
    valid = _suggest_artefact(domain_id, obligation_id, holding, deadline)
    out: dict[str, Any] = {"valid": {"label": "Reset to a valid submission", "artefact": valid}}

    rate = rule.get("expected_rate")
    if rate is not None and rate in SUPERSEDED_RATE:
        wrong_rate = SUPERSEDED_RATE[rate]
        wrong = dict(valid, rate_applied=wrong_rate)
        if "deemed_gain" in wrong:
            wrong["computed_tax"] = _round2(wrong["deemed_gain"] * wrong_rate)
        elif isinstance(valid.get("computed_tax"), (int, float)):
            # keep the artefact internally coherent: the tax a holder would have
            # computed had they applied the superseded rate throughout
            wrong["computed_tax"] = _round2(valid["computed_tax"] * wrong_rate / rate)
        out["superseded_rate"] = {
            "label": f"Apply {wrong_rate:.0%} instead of {rate:.0%}", "artefact": wrong,
        }

    if "deemed_gain" in valid:
        out["inexact_arithmetic"] = {
            "label": "Round the tax up by €40",
            "artefact": dict(valid, computed_tax=_round2(valid["computed_tax"] + 40)),
        }

    required = rule.get("required_fields", [])
    if required:
        out["missing_field"] = {
            "label": f"Leave {required[0]} empty",
            "artefact": dict(valid, **{required[0]: ""}),
        }
    return out


def _suggest_artefact(domain_id: str, obligation_id: str, holding: dict[str, Any], deadline: str | None) -> dict[str, Any]:
    rule = _evidence_for(domain_id, obligation_id)
    rate = rule.get("expected_rate")
    artefact: dict[str, Any] = {"artefact_type": rule.get("artefact_type")}
    for field in rule.get("required_fields", []):
        artefact[field] = _suggest_field(field, holding, rate, deadline)
    if rule.get("artefact_type") == "tax_computation" and rate is not None:
        artefact["deemed_gain"] = DEEMED_GAIN
        artefact["computed_tax"] = round(DEEMED_GAIN * rate, 2)
    return artefact


def _decorate_action(action: Any, domain_id: str, holding: dict[str, Any] | None = None) -> dict[str, Any]:
    """An action plus the evidence contract ANCHOR will hold it to, so the
    wizard can render the right submission form without hard-coding anything
    per pack.
    """
    d = action.as_dict()
    ev = _evidence_for(domain_id, action.obligation_id)
    d["domain_id"] = domain_id
    d["required_fields"] = ev.get("required_fields", [])
    d["expected_rate"] = ev.get("expected_rate")
    d["lead_time_days"] = ev.get("lead_time_days")
    d["deadline_direction"] = ev.get("deadline_direction", "before")
    d["artefact_type"] = ev.get("artefact_type")
    d["suggested_artefact"] = _suggest_artefact(
        domain_id, action.obligation_id, holding or {}, action.deadline
    )
    d["variants"] = _artefact_variants(
        domain_id, action.obligation_id, holding or {}, action.deadline
    )
    return d


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="TARA Live Demo API",
    description="Browser-facing adapter over the real TARA agent pipeline.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    # The demo page is published as a static artifact and on GitHub Pages, so
    # it is always cross-origin to this service. Nothing here is authenticated
    # and nothing is written to disk outside a per-request temp dir, so a
    # permissive origin policy costs nothing. See docs/reliability-notes.md.
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "tara-demo-api",
        "domain_packs": sorted(PACK_META),
        "pack_count": len(PACK_META),
        "agents": ["SURVEY", "LEGEND", "ALMANAC", "COMPASS", "PLOT", "COURSE", "ANCHOR", "MERIDIAN", "ATLAS"],
        "ai_orchestration_available": _llm_enabled(),
        "ai_orchestration_model": os.environ.get("TARA_LLM_MODEL") if _llm_enabled() else None,
        "server_time": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


@app.get("/api/schema")
def schema() -> dict[str, Any]:
    """Everything the wizard needs to build its forms: the loaded packs, their
    scoping questions, and the allowed register values."""
    return {
        "packs": [
            {
                "domain_id": m["domain_id"],
                "title": m["title"],
                "is_corridor": m["is_corridor"],
                "questions": list(m["questions"].values()),
            }
            for m in PACK_META.values()
        ],
        "instrument_types": INSTRUMENT_TYPES,
        "residency_statuses": RESIDENCY_STATUSES,
        "countries": COUNTRIES,
    }


@app.get("/api/presets")
def presets() -> Any:
    return json.loads((DEMO_DIR / "presets.json").read_text(encoding="utf-8"))


def _run_pipeline(req: RunRequest) -> dict[str, Any]:
    """The whole end-to-end pass: OPEN band once, then MERIDIAN per holding
    across every loaded pack, then the actions and the ATLAS chain."""
    as_of = _as_of(req.as_of)
    register = _register_from(req.holder, req.holdings)

    with _context_for(register) as (ctx, tmp_path):
        packs = _all_packs(ctx)

        # ---- OPEN band: identical for every holder, computed once. ----------
        open_band: dict[str, Any] = {}
        for domain_id, pack in packs.items():
            sources = []
            for source_id in pack.sources:
                from tara.agents import survey as survey_agent
                rec = survey_agent.detect_change(pack, source_id, as_of=as_of, atlas=ctx.atlas)
                sources.append(rec.as_dict())
            obligations = [o.as_dict() for o in pipeline.full_obligation_set(ctx, domain_pack=pack)]
            refresh = almanac.refresh(
                pack, tmp_path / f"graph_version_{domain_id}.json", as_of=as_of, atlas=ctx.atlas
            )
            open_band[domain_id] = {
                "title": pack.title,
                "is_corridor": pack.is_corridor,
                "sources": sources,
                "obligations": obligations,
                "almanac": refresh.as_dict(),
            }

        # ---- TENANT band, per holding, across every pack. -------------------
        per_holding: dict[str, Any] = {}
        pending: list[dict[str, Any]] = []
        all_actions: list[dict[str, Any]] = []

        for holding in req.holdings:
            hid = holding.holding_id
            report = meridian.survey(ctx, hid, req.answers, as_of=as_of)
            rows = []
            for result in report.results:
                det = result.determination.as_dict() if result.determination else None
                gaps: list[dict[str, Any]] = []
                actions: list[dict[str, Any]] = []
                if result.considered and det and det["status"] == "CONFIRMED":
                    _, gap_list = pipeline.gaps_for(
                        ctx, hid, req.answers, as_of=as_of, domain_pack=packs[result.domain_id]
                    )
                    gaps = [g.as_dict() for g in gap_list]
                    reg_entry = next(h for h in register["holdings"] if h["holding_id"] == hid)
                    actions = [_decorate_action(a, result.domain_id, reg_entry) for a in result.actions]
                    all_actions.extend(actions)

                if det and det["status"] == "INDETERMINATE" and det.get("missing_question"):
                    qid = det["missing_question"]
                    meta = PACK_META.get(result.domain_id, {}).get("questions", {}).get(qid)
                    if qid not in req.answers:
                        pending.append({
                            "question_id": qid,
                            "text": (meta or {}).get("text", qid),
                            "domain_id": result.domain_id,
                            "domain_title": result.title,
                            "holding_id": hid,
                            "expect": (meta or {}).get("expect"),
                        })

                rows.append({
                    "domain_id": result.domain_id,
                    "title": result.title,
                    "is_corridor": result.is_corridor,
                    "considered": result.considered,
                    "skipped_reason": result.skipped_reason,
                    "determination": det,
                    "gaps": gaps,
                    "actions": actions,
                })
            per_holding[hid] = {
                "holding": next(h for h in register["holdings"] if h["holding_id"] == hid),
                "results": rows,
            }

        # de-duplicate pending questions (the same question can be missing on
        # several holdings at once; the holder answers it once)
        seen: set[str] = set()
        unique_pending = []
        for q in pending:
            if q["question_id"] in seen:
                continue
            seen.add(q["question_id"])
            unique_pending.append(q)

        entries = ctx.atlas.all_entries()
        atlas = {
            "entry_count": len(entries),
            "chain_verified": ctx.atlas.verify_chain(),
            "agents_seen": sorted({e.get("agent") for e in entries if e.get("agent")}),
            "tail": entries[-14:],
        }

    all_actions.sort(key=lambda a: (a.get("deadline") or "9999-12-31", a["action_id"]))

    return {
        "as_of": as_of.isoformat(),
        "register": register,
        "packs": [
            {"domain_id": k, "title": v["title"], "is_corridor": v["is_corridor"]}
            for k, v in open_band.items()
        ],
        "open_band": open_band,
        "holdings": per_holding,
        "pending_questions": unique_pending,
        "actions": all_actions,
        "atlas": atlas,
    }


@app.post("/api/run")
def run(req: RunRequest) -> dict[str, Any]:
    """Deterministic browser fallback for the prepared demo cases."""
    return _run_pipeline(req)


def _llm_enabled() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def _mcp_subprocess_env(register_path: Path, atlas_path: Path, graph_path: Path) -> dict[str, str]:
    """Pass only execution context to the MCP subprocess, never the OpenAI key.

    The LLM process owns the key. The MCP subprocess sees a request-scoped,
    synthetic register and temporary trace paths, so it cannot read or alter
    the repository's example ledger while serving a browser request.
    """
    env = {key: os.environ[key] for key in ("PATH", "PYTHONPATH", "LANG", "LC_ALL") if os.environ.get(key)}
    env.update({
        "TARA_REGISTER_JSON": str(register_path),
        "TARA_ATLAS_PATH": str(atlas_path),
        "TARA_GRAPH_VERSION_PATH": str(graph_path),
    })
    return env


def _orchestrate(req: RunRequest) -> dict[str, Any]:
    """Run one constrained, server-side OpenAI session against TARA's MCP tools."""
    if not _llm_enabled():
        raise HTTPException(
            status_code=503,
            detail="AI orchestration is not configured. Switch to the deterministic backup mode.",
        )

    from tara.orchestrator import llm

    register = _register_from(req.holder, req.holdings)
    as_of = _as_of(req.as_of).isoformat()
    with TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        register_path = tmp_path / "register.json"
        register_path.write_text(json.dumps(register, indent=2), encoding="utf-8")
        prompt = f"""You are the AI orchestration layer in TARA's prepared demonstration.

Your job is to investigate a regulatory change for one synthetic case, using only MCP tool results.
The event date is {as_of}. The supplied applicability answers are {json.dumps(req.answers, sort_keys=True)}.

First call list_domains and list_holdings. Use the returned titles to choose the relevant domain for the prepared case.
Before investigating a rule change, call list_sources for that exact domain and use only a returned source_id.
For holder-specific work, use only a holding_id returned by list_holdings. You must call survey_detect_change, compass_assess, and course_plan before you answer. Supply the exact event date and the supplied answers to the assessment and action-planning tools.

Return a concise plain-language explanation with: what changed, what applies or what fact is missing, the next actions, and the human-review boundary. Do not invent names, dates, source IDs, rates, or conclusions. This is decision support for a qualified reviewer, not legal or tax advice."""
        try:
            required = {"list_domains", "list_holdings", "list_sources", "survey_detect_change", "compass_assess", "course_plan"}
            result = llm.run(
                prompt,
                model=os.environ.get("TARA_LLM_MODEL", "gpt-4.1-mini"),
                max_turns=int(os.environ.get("TARA_LLM_MAX_TURNS", "12")),
                server_env=_mcp_subprocess_env(
                    register_path,
                    tmp_path / "atlas_log.jsonl",
                    tmp_path / "graph_version.json",
                ),
                required_tools=required,
            )
        except llm.OrchestratorNotConfigured as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"AI orchestration did not complete: {exc}") from exc

    trace = [
        {
            "tool": call.name,
            "arguments": call.arguments,
            "status": "needs attention" if call.result.startswith("ERROR:") else "completed",
        }
        for call in result.tool_calls
    ]
    observed = {step["tool"] for step in trace}
    if not required <= observed:
        raise HTTPException(status_code=502, detail="AI orchestration completed without the required MCP discovery steps.")
    return {
        "summary": result.answer,
        "model": os.environ.get("TARA_LLM_MODEL", "gpt-4.1-mini"),
        "tool_trace": trace,
    }


@app.get("/api/ai/status")
def ai_status() -> dict[str, Any]:
    return {
        "available": _llm_enabled(),
        "mode": "OpenAI orchestrator over local MCP tools" if _llm_enabled() else "deterministic backup only",
        "model": os.environ.get("TARA_LLM_MODEL", "gpt-4.1-mini") if _llm_enabled() else None,
    }


@app.post("/api/ai/run")
def ai_run(req: RunRequest) -> dict[str, Any]:
    """LLM-first demo path: orchestration via MCP plus independently rendered controls."""
    orchestration = _orchestrate(req)
    return {"run": _run_pipeline(req), "orchestration": orchestration}


@app.post("/api/verify")
def verify(req: VerifyRequest) -> dict[str, Any]:
    """ANCHOR on one action. Rebuilds the same context and re-derives the same
    action rather than trusting anything the client sends about it — the client
    supplies only the artefact."""
    as_of = _as_of(req.as_of)
    register = _register_from(req.holder, req.holdings)

    with _context_for(register) as (ctx, _tmp):
        packs = _all_packs(ctx)
        pack = packs.get(req.domain_id)
        if pack is None:
            raise HTTPException(404, f"unknown domain_id: {req.domain_id}")

        target = None
        for holding in req.holdings:
            _, actions = pipeline.actions_for(
                ctx, holding.holding_id, req.answers, as_of=as_of, domain_pack=pack
            )
            for action in actions:
                if action.action_id == req.action_id:
                    target = action
                    break
            if target is not None:
                break
        if target is None:
            raise HTTPException(404, f"no live action {req.action_id} in {req.domain_id}")

        before = len(ctx.atlas.all_entries())
        result = pipeline.verify_action(
            ctx, target, req.artefact, profile_answers=req.answers,
            as_of=as_of, domain_pack=pack,
        )
        entries = ctx.atlas.all_entries()

    return {
        "closure": result.as_dict(),
        "action": _decorate_action(
            target, req.domain_id,
            next((h for h in register["holdings"] if h["holding_id"] == target.holding_id), {}),
        ),
        "atlas": {
            "entries_added": len(entries) - before,
            "chain_verified": True,
            "tail": entries[-4:],
        },
    }


@app.get("/")
def index() -> Any:
    page = DEMO_DIR / "index.html"
    if page.exists():
        return FileResponse(page)
    return JSONResponse({"service": "tara-demo-api", "docs": "/docs", "health": "/api/health"})


# Serve the wizard's own files (app.js, replay.js, presets.json) from the same
# origin, so a single deploy gives both the engine and a working demo page.
# Mounted last: every /api route above is matched first.
app.mount("/", StaticFiles(directory=str(DEMO_DIR), html=True), name="demo")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
