"""
Tests for the Structure Mapper
(agents/specialist_agents/corporate_agent/structure_mapper/mapper.py).

Tests cover:
- Cache-hit path: returns real OpenCorporates evidence when cache exists
- Cache-miss + live call: attempts API call, caches result
- Token-missing/network failure: raises strict DataSourceError
- run_stub alias preserved for backward compatibility
- Integration with CorporateAgent for beneficial_ownership task
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from agents.lead_agent.context_manager import InvestigationContext
from agents.lead_agent.task_planner.types import SubTask
from agents.specialist_agents.corporate_agent.structure_mapper.mapper import (
    map_structure,
    run_stub,
)
from app.investigation_errors import DataSourceError
from osint_swarm.entities import Entity


_ENTITY = Entity(
    entity_id="tesla_inc_cik_0001318605",
    name="Tesla, Inc.",
    entity_type="public_company",
    identifiers={"cik": "0001318605"},
    aliases=["Tesla"],
)

_TASK = SubTask("beneficial_ownership", "corporate_agent", "Map beneficial ownership")
_CTX = InvestigationContext()


# Cached detail fixture (mirrors the OpenCorporates normalized structure)
_CACHED_DETAIL = {
    "name": "TESLA, INC.",
    "company_number": "C3259768",
    "jurisdiction_code": "us_ca",
    "company_type": "Stock Corporation",
    "current_status": "Active",
    "incorporation_date": "2003-07-01",
    "dissolution_date": None,
    "inactive": False,
    "opencorporates_url": "https://opencorporates.com/companies/us_ca/C3259768",
    "registered_address_in_full": "PALO ALTO, CA",
    "officers": [
        {"id": 1001, "name": "ELON MUSK", "position": "ceo", "start_date": "2008-10-01", "end_date": None, "opencorporates_url": ""},
        {"id": 1002, "name": "VAIBHAV TANEJA", "position": "cfo", "start_date": "2023-08-01", "end_date": None, "opencorporates_url": ""},
    ],
    "corporate_groupings": [
        {"name": "tesla", "opencorporates_url": "", "wikipedia_id": "Tesla,_Inc."},
    ],
    "previous_names": [{"company_name": "TESLA MOTORS, INC.", "con_date": "2017-02-01"}],
    "controlling_entity": None,
    "ultimate_beneficial_owners": [],
    "ultimate_controlling_company": None,
    "industry_codes": [],
}

_CACHED_PAYLOAD = {
    "search": {"entity_name": "Tesla, Inc.", "total_count": 1, "companies": []},
    "detail": _CACHED_DETAIL,
}


# ---------------------------------------------------------------------------
# Cache-hit path
# ---------------------------------------------------------------------------

def test_map_structure_uses_cache(tmp_path: Path):
    cache_dir = tmp_path / "raw" / "opencorporates"
    cache_dir.mkdir(parents=True)
    cache_file = cache_dir / "oc_tesla.json"
    cache_file.write_text(json.dumps(_CACHED_PAYLOAD))

    results = map_structure(_ENTITY, _TASK, _CTX, data_root=tmp_path)

    assert len(results) >= 1
    # Should include officer evidence + summary
    officer_rows = [r for r in results if r.attributes.get("officer_name")]
    assert len(officer_rows) == 2
    assert any(r.attributes.get("officer_name") == "ELON MUSK" for r in officer_rows)

    summary = [r for r in results if r.evidence_id.endswith("_oc_summary")]
    assert len(summary) == 1
    assert summary[0].attributes.get("stub") is False


def test_map_structure_cache_hit_includes_grouping(tmp_path: Path):
    cache_dir = tmp_path / "raw" / "opencorporates"
    cache_dir.mkdir(parents=True)
    (cache_dir / "oc_tesla.json").write_text(json.dumps(_CACHED_PAYLOAD))

    results = map_structure(_ENTITY, _TASK, _CTX, data_root=tmp_path)
    groups = [r for r in results if r.attributes.get("relationship") == "corporate_grouping"]
    assert len(groups) == 1
    assert groups[0].attributes["grouping_name"] == "tesla"


# ---------------------------------------------------------------------------
# Cache-miss + no token -> strict failure
# ---------------------------------------------------------------------------

def test_map_structure_no_cache_no_token_raises(tmp_path: Path):
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(DataSourceError):
            map_structure(_ENTITY, _TASK, _CTX, data_root=tmp_path)


# ---------------------------------------------------------------------------
# Cache-miss + live API success
# ---------------------------------------------------------------------------

def test_map_structure_live_api_caches_result(tmp_path: Path):
    from osint_swarm.data_sources.opencorporates import _normalize_company_detail

    mock_search = {
        "entity_name": "Tesla, Inc.",
        "total_count": 1,
        "companies": [{
            "name": "TESLA, INC.",
            "company_number": "C3259768",
            "jurisdiction_code": "us_ca",
            "company_type": "Stock Corporation",
            "current_status": "Active",
            "inactive": False,
            "incorporation_date": "2003-07-01",
            "dissolution_date": None,
            "opencorporates_url": "",
            "registered_address_in_full": "",
        }],
    }

    detail_norm = _normalize_company_detail(_CACHED_DETAIL)

    with patch.dict("os.environ", {"OPENCORPORATES_API_TOKEN": "test123"}):
        with patch("osint_swarm.data_sources.opencorporates.search_companies", return_value=mock_search) as mock_s:
            with patch("osint_swarm.data_sources.opencorporates.fetch_company_detail", return_value=detail_norm) as mock_d:
                results = map_structure(_ENTITY, _TASK, _CTX, data_root=tmp_path)

    assert len(results) >= 1
    # Cache should have been written
    cache_file = tmp_path / "raw" / "opencorporates" / "oc_tesla.json"
    assert cache_file.exists()


# ---------------------------------------------------------------------------
# run_stub backward-compatible alias
# ---------------------------------------------------------------------------

def test_run_stub_is_map_structure():
    assert run_stub is map_structure


# ---------------------------------------------------------------------------
# Integration: CorporateAgent delegates to mapper
# ---------------------------------------------------------------------------

def test_corporate_agent_beneficial_ownership_uses_mapper(tmp_path: Path):
    from agents.specialist_agents.corporate_agent import CorporateAgent
    from agents.specialist_agents.corporate_agent import agent as corp_agent_module

    cache_dir = tmp_path / "raw" / "opencorporates"
    cache_dir.mkdir(parents=True)
    (cache_dir / "oc_tesla.json").write_text(json.dumps(_CACHED_PAYLOAD))

    # Keep this test isolated from networked action policy calls.
    with patch.object(
        corp_agent_module,
        "choose_next_tool",
        return_value={
            "selected_tool": "opencorporates",
            "alternatives": [],
            "policy_used": "llm_action_policy",
            "reasoning": "Use ownership source.",
        },
    ):
        agent = CorporateAgent(data_root=tmp_path)
        results = agent.run(_ENTITY, _TASK, _CTX)

    assert len(results) >= 1
    assert any(r.attributes.get("data_source") == "opencorporates" for r in results)
    assert all(r.attributes.get("stub") is not True for r in results)
