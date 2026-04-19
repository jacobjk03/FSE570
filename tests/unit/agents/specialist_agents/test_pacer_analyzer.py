"""
Tests for the CourtListener / PACER analyzer
(agents/specialist_agents/legal_agent/pacer_analyzer/analyzer.py).

Covers:
- Cache hit → correct Evidence rows (no network call)
- Cache miss + successful live fetch → Evidence rows written and returned
- Cache miss + network error -> strict DataSourceError
- Empty dockets → clean Evidence row (confidence=0.85)
- Multiple dockets → summary row + one row per docket
- stub flag is False for all real outputs
- Through LegalAgent (litigation task_type)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.lead_agent.context_manager import InvestigationContext
from agents.lead_agent.task_planner import SubTask
from agents.specialist_agents.legal_agent.pacer_analyzer.analyzer import fetch
from app.investigation_errors import DataSourceError
from osint_swarm.data_sources.courtlistener import _normalize_docket
from osint_swarm.entities import Entity

_TASK = SubTask("litigation", "legal_agent", "Find court records")
_CTX = InvestigationContext()

_SAMPLE_DOCKET_RAW = {
    "id": 4622426,
    "caseName": "SECURITIES EXCHANGE COMMISSION v. MUSK et al",
    "docketNumber": "3:18-cv-04865",
    "court_id": "cand",
    "dateFiled": "2018-09-27",
    "dateTerminated": None,
    "suitNature": "Securities (850)",
    "cause": "Securities Exchange Act: Disclosure",
    "absolute_url": "/docket/4622426/sec-v-musk/",
}

_SAMPLE_PAYLOAD = {
    "entity_name": "Tesla, Inc.",
    "query": '"Tesla, Inc."',
    "total_found": 142,
    "dockets": [_normalize_docket(_SAMPLE_DOCKET_RAW)],
}


def _write_cache(tmp_path: Path, slug: str, payload: dict) -> None:
    cache_dir = tmp_path / "raw" / "courtlistener"
    cache_dir.mkdir(parents=True)
    (cache_dir / f"dockets_{slug}.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Cache hit scenarios
# ---------------------------------------------------------------------------

def test_fetch_uses_cache_when_present(tmp_path: Path):
    _write_cache(tmp_path, "tesla", _SAMPLE_PAYLOAD)
    entity = Entity(entity_id="tesla_inc_cik_0001318605", name="Tesla, Inc.", identifiers={})

    with patch("osint_swarm.data_sources.courtlistener.requests.get") as mock_get:
        results = fetch(entity, _TASK, _CTX, data_root=tmp_path)
        mock_get.assert_not_called()  # cache hit → no network call

    assert len(results) >= 1


def test_fetch_cache_hit_returns_summary_and_docket_rows(tmp_path: Path):
    _write_cache(tmp_path, "tesla", _SAMPLE_PAYLOAD)
    entity = Entity(entity_id="tesla_inc_cik_0001318605", name="Tesla, Inc.", identifiers={})
    results = fetch(entity, _TASK, _CTX, data_root=tmp_path)

    # 1 summary row + 1 docket row = 2
    assert len(results) == 2
    summary = results[0]
    assert summary.attributes.get("court_records") == 1
    assert summary.attributes.get("screened") is True
    assert summary.attributes.get("stub") is False
    assert summary.confidence == pytest.approx(0.85)


def test_fetch_docket_row_has_correct_fields(tmp_path: Path):
    _write_cache(tmp_path, "tesla", _SAMPLE_PAYLOAD)
    entity = Entity(entity_id="tesla_inc_cik_0001318605", name="Tesla, Inc.", identifiers={})
    results = fetch(entity, _TASK, _CTX, data_root=tmp_path)

    docket_ev = results[1]  # second row is the docket
    assert docket_ev.source_type == "court_record"
    assert docket_ev.risk_category == "legal"
    assert docket_ev.confidence == pytest.approx(0.85)
    assert docket_ev.attributes.get("stub") is False
    assert "SECURITIES EXCHANGE COMMISSION" in docket_ev.summary
    assert docket_ev.source_uri.startswith("https://www.courtlistener.com/")


# ---------------------------------------------------------------------------
# Cache miss + successful live fetch
# ---------------------------------------------------------------------------

def test_fetch_makes_api_call_when_no_cache(tmp_path: Path):
    entity = Entity(entity_id="tesla_inc_cik_0001318605", name="Tesla, Inc.", identifiers={})

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"count": 1, "results": [_SAMPLE_DOCKET_RAW]}
    mock_resp.raise_for_status.return_value = None

    with patch("osint_swarm.data_sources.courtlistener.requests.get", return_value=mock_resp):
        results = fetch(entity, _TASK, _CTX, data_root=tmp_path)

    assert len(results) >= 1
    # Cache should have been written
    cache_path = tmp_path / "raw" / "courtlistener" / "dockets_tesla.json"
    assert cache_path.exists()


def test_fetch_caches_result_on_live_fetch(tmp_path: Path):
    entity = Entity(entity_id="tesla_inc_cik_0001318605", name="Tesla, Inc.", identifiers={})

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"count": 0, "results": []}
    mock_resp.raise_for_status.return_value = None

    with patch("osint_swarm.data_sources.courtlistener.requests.get", return_value=mock_resp):
        fetch(entity, _TASK, _CTX, data_root=tmp_path)

    cache_path = tmp_path / "raw" / "courtlistener" / "dockets_tesla.json"
    assert cache_path.exists()
    cached = json.loads(cache_path.read_text())
    assert "dockets" in cached


# ---------------------------------------------------------------------------
# Network error -> strict failure
# ---------------------------------------------------------------------------

def test_fetch_raises_on_network_error(tmp_path: Path):
    entity = Entity(entity_id="e1", name="Some Corp", identifiers={})

    import requests as req_lib
    with patch(
        "osint_swarm.data_sources.courtlistener.requests.get",
        side_effect=req_lib.exceptions.ConnectionError("refused"),
    ):
        with pytest.raises(DataSourceError):
            fetch(entity, _TASK, _CTX, data_root=tmp_path)


# ---------------------------------------------------------------------------
# Empty dockets (entity not in CourtListener)
# ---------------------------------------------------------------------------

def test_fetch_clean_result_when_no_dockets(tmp_path: Path):
    empty_payload = {
        "entity_name": "Unknown Corp",
        "query": '"Unknown Corp"',
        "total_found": 0,
        "dockets": [],
    }
    _write_cache(tmp_path, "unknown_corp", empty_payload)
    entity = Entity(entity_id="unknown_corp_001", name="Unknown Corp", identifiers={})
    results = fetch(entity, _TASK, _CTX, data_root=tmp_path)

    assert len(results) == 1
    ev = results[0]
    assert ev.confidence == pytest.approx(0.85)
    assert ev.attributes.get("court_records") == 0
    assert ev.attributes.get("screened") is True
    assert ev.attributes.get("stub") is False
    assert "no court dockets" in ev.summary.lower()


# ---------------------------------------------------------------------------
# Multiple dockets
# ---------------------------------------------------------------------------

def test_fetch_multiple_dockets_returns_summary_plus_n_rows(tmp_path: Path):
    two_docket_payload = {
        "entity_name": "Tesla, Inc.",
        "query": '"Tesla, Inc."',
        "total_found": 200,
        "dockets": [
            _normalize_docket(_SAMPLE_DOCKET_RAW),
            _normalize_docket({
                **_SAMPLE_DOCKET_RAW,
                "id": 7777777,
                "caseName": "IN RE TESLA SECURITIES LITIGATION",
                "docketNumber": "4:20-cv-01200",
                "dateTerminated": "2022-05-01",
            }),
        ],
    }
    _write_cache(tmp_path, "tesla", two_docket_payload)
    entity = Entity(entity_id="tesla_inc_cik_0001318605", name="Tesla, Inc.", identifiers={})
    results = fetch(entity, _TASK, _CTX, data_root=tmp_path)

    # 1 summary + 2 dockets = 3
    assert len(results) == 3
    assert results[0].attributes.get("court_records") == 2


# ---------------------------------------------------------------------------
# Through LegalAgent
# ---------------------------------------------------------------------------

def test_legal_agent_litigation_calls_court_fetch(tmp_path: Path):
    _write_cache(tmp_path, "tesla", _SAMPLE_PAYLOAD)
    from agents.specialist_agents.legal_agent import LegalAgent

    from agents.specialist_agents.legal_agent import agent as legal_agent_module
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            legal_agent_module,
            "choose_next_tool",
            lambda **_kwargs: {
                "selected_tool": "courtlistener",
                "alternatives": [],
                "policy_used": "llm_action_policy",
                "reasoning": "Use litigation source.",
            },
        )
        agent = LegalAgent(data_root=tmp_path)
        entity = Entity(entity_id="tesla_inc_cik_0001318605", name="Tesla, Inc.", identifiers={})
        task = SubTask("litigation", "legal_agent", "Court records")
        ctx = InvestigationContext()
        results = agent.run(entity, task, ctx)

    assert len(results) >= 1
    assert results[0].source_type == "court_record"
    assert results[0].attributes.get("stub") is False
    assert results[0].confidence == pytest.approx(0.85)


def test_legal_agent_regulatory_actions_calls_court_fetch(tmp_path: Path):
    _write_cache(tmp_path, "tesla", _SAMPLE_PAYLOAD)
    from agents.specialist_agents.legal_agent import LegalAgent

    from agents.specialist_agents.legal_agent import agent as legal_agent_module
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            legal_agent_module,
            "choose_next_tool",
            lambda **_kwargs: {
                "selected_tool": "courtlistener",
                "alternatives": [],
                "policy_used": "llm_action_policy",
                "reasoning": "Use litigation source.",
            },
        )
        agent = LegalAgent(data_root=tmp_path)
        entity = Entity(entity_id="tesla_inc_cik_0001318605", name="Tesla, Inc.", identifiers={})
        task = SubTask("regulatory_actions", "legal_agent", "Regulatory filings")
        ctx = InvestigationContext()
        results = agent.run(entity, task, ctx)
    assert results[0].source_type == "court_record"
    assert results[0].attributes.get("stub") is False
