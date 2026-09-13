from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from demo import api

ROOT = Path(__file__).resolve().parent.parent
CLIENT = TestClient(api.app)


def maeve_request() -> api.RunRequest:
    preset = json.loads((ROOT / "demo" / "presets.json").read_text())[0]
    return api.RunRequest(
        holder=preset["holder"],
        holdings=preset["holdings"],
        answers=preset["answers"],
        as_of="2026-09-13",
    )


def test_health_reports_the_complete_loaded_surface():
    health = api.health()
    assert health["ok"] is True
    assert health["pack_count"] == 9
    assert len(health["agents"]) == 9


def test_recommended_preset_is_the_certified_maeve_path():
    presets = api.presets()
    assert presets[0]["id"] == "maeve"
    assert presets[0]["recommended"] is True
    assert presets[0]["focus_obligation_id"] == "OBL-002B"


def test_public_reference_routes_are_served_from_the_canonical_origin():
    guide = CLIENT.get("/guide")
    card = CLIENT.get("/evaluation-card.md")
    assert guide.status_code == 200
    assert "TARA — Complete Project Guide" in guide.text
    assert card.status_code == 200
    assert "# TARA Evaluation Card" in card.text


def test_maeve_run_selects_38_percent_and_not_41_percent():
    result = api.run(maeve_request())
    actions = {action["obligation_id"]: action for action in result["actions"]}

    assert "OBL-002" not in actions
    assert actions["OBL-002B"]["expected_rate"] == 0.38
    assert actions["OBL-002B"]["suggested_artefact"]["computed_tax"] == 4560.0
    assert result["atlas"]["chain_verified"] is True


def test_maeve_evidence_returns_old_rate_and_closes_current_rate():
    request = maeve_request()
    run = api.run(request)
    action = next(a for a in run["actions"] if a["obligation_id"] == "OBL-002B")

    old = api.verify(api.VerifyRequest(
        **request.model_dump(),
        domain_id="tax",
        action_id=action["action_id"],
        artefact={
            "artefact_type": "tax_computation",
            "rate_applied": 0.41,
            "deemed_gain": 12000.0,
            "computed_tax": 4920.0,
        },
    ))
    current = api.verify(api.VerifyRequest(
        **request.model_dump(),
        domain_id="tax",
        action_id=action["action_id"],
        artefact={
            "artefact_type": "tax_computation",
            "rate_applied": 0.38,
            "deemed_gain": 12000.0,
            "computed_tax": 4560.0,
        },
    ))

    assert old["closure"]["outcome"] == "returned"
    assert current["closure"]["outcome"] == "closed"
    assert current["atlas"]["chain_verified"] is True
