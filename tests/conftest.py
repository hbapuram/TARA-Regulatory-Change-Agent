from __future__ import annotations

from pathlib import Path

import pytest

from tara.mcp_server.context import build_context

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def ctx(tmp_path):
    """A TaraContext wired to the real domain pack and register, but with
    ATLAS and the ALMANAC version store isolated to a tmp dir so tests never
    share or pollute state.
    """
    return build_context(
        domain_yaml=REPO_ROOT / "domains" / "tax.yaml",
        register_json=REPO_ROOT / "registers" / "holder_register.json",
        atlas_path=tmp_path / "atlas_log.jsonl",
        almanac_version_path=tmp_path / "graph_version.json",
    )


@pytest.fixture
def linked_ctx(tmp_path):
    """Same real register as ``ctx``, but with the primary Ireland pack
    (tax.yaml) plus India, the US, the Irish IRP pack, the Irish CGT property
    pack, and the India-Ireland corridor all linked — the same set the MCP
    server links by default (tara/mcp_server/server.py's
    DEFAULT_LINKED_DOMAIN_YAMLS). Keep the two in step: a pack the server
    loads but this fixture does not is a pack no test covers in the
    configuration that actually ships. The
    corridor is synthesized from domains/interactions.yaml (see
    tara/core/interactions.py) rather than loaded as its own full pack file.
    Used by MERIDIAN tests and anything exercising more than one domain pack
    at once.
    """
    return build_context(
        domain_yaml=REPO_ROOT / "domains" / "tax.yaml",
        register_json=REPO_ROOT / "registers" / "holder_register.json",
        atlas_path=tmp_path / "atlas_log.jsonl",
        almanac_version_path=tmp_path / "graph_version.json",
        linked_domain_yamls=[
            REPO_ROOT / "domains" / "india.yaml",
            REPO_ROOT / "domains" / "us.yaml",
            REPO_ROOT / "domains" / "ireland-irp.yaml",
            REPO_ROOT / "domains" / "ireland-cgt-property.yaml",
            REPO_ROOT / "domains" / "india-nri-securities.yaml",
        ],
        interactions_yaml=REPO_ROOT / "domains" / "interactions.yaml",
    )
