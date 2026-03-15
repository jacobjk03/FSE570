"""Tests for Legal Agent (OFAC sanctions screener + CourtListener court records)."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.lead_agent.context_manager import InvestigationContext
from agents.lead_agent.task_planner import SubTask
from agents.specialist_agents.legal_agent import LegalAgent
from osint_swarm.entities import Entity


# ---------------------------------------------------------------------------
# agent_id
# ---------------------------------------------------------------------------

def test_legal_agent_agent_id():
    agent = LegalAgent()
    assert agent.agent_id == "legal_agent"


# ---------------------------------------------------------------------------
# Sanctions screening (OFAC)
# ---------------------------------------------------------------------------

def test_legal_agent_sanctions_returns_legal_evidence(tmp_path):
    """Sanctions screening returns real Evidence (not old stub), risk_category='legal'."""
    agent = LegalAgent(data_root=tmp_path)  # no SDN cache → graceful fallback
    entity = Entity(entity_id="e1", name="Some Corp", identifiers={})
    task = SubTask("sanctions_screening", "legal_agent", "Screen sanctions")
    ctx = InvestigationContext()
    findings = agent.run(entity, task, ctx)

    assert len(findings) >= 1
    assert findings[0].risk_category == "legal"
    assert findings[0].attributes.get("stub") is False


def test_legal_agent_sanctions_fallback_confidence_zero_without_cache(tmp_path):
    """Without SDN cache, screener returns confidence=0.0 and a helpful message."""
    agent = LegalAgent(data_root=tmp_path)
    entity = Entity(entity_id="e1", name="E Corp", identifiers={})
    task = SubTask("sanctions_screening", "legal_agent", "Screen")
    ctx = InvestigationContext()
    findings = agent.run(entity, task, ctx)

    assert findings[0].confidence == 0.0
    assert "pull_ofac_sdn" in findings[0].summary.lower() or "cache" in findings[0].summary.lower()


# ---------------------------------------------------------------------------
# Litigation (CourtListener)
# ---------------------------------------------------------------------------

def test_legal_agent_litigation_returns_court_evidence(tmp_path):
    """Litigation task returns CourtListener evidence (not stub)."""
    # Write a minimal cache so no network call is needed
    cache_dir = tmp_path / "raw" / "courtlistener"
    cache_dir.mkdir(parents=True)
    payload = {
        "entity_name": "E Corp",
        "query": '"E Corp"',
        "total_found": 0,
        "dockets": [],
    }
    (cache_dir / "dockets_e_corp.json").write_text(json.dumps(payload))

    agent = LegalAgent(data_root=tmp_path)
    entity = Entity(entity_id="e_corp_001", name="E Corp", identifiers={})
    task = SubTask("litigation", "legal_agent", "Court records")
    ctx = InvestigationContext()
    findings = agent.run(entity, task, ctx)

    assert len(findings) >= 1
    assert findings[0].source_type == "court_record"
    assert findings[0].attributes.get("stub") is False


def test_legal_agent_litigation_no_cache_graceful_fallback(tmp_path):
    """Without cache, litigation falls back gracefully on network error."""
    import requests as req_lib

    agent = LegalAgent(data_root=tmp_path)
    entity = Entity(entity_id="e1", name="Unknown Corp", identifiers={})
    task = SubTask("litigation", "legal_agent", "Court records")
    ctx = InvestigationContext()

    with patch(
        "osint_swarm.data_sources.courtlistener.requests.get",
        side_effect=req_lib.exceptions.ConnectionError("refused"),
    ):
        findings = agent.run(entity, task, ctx)

    assert len(findings) == 1
    assert findings[0].confidence == 0.0
    assert findings[0].attributes.get("stub") is False
    assert "pull_courtlistener.py" in findings[0].summary


def test_legal_agent_regulatory_actions_routes_to_court(tmp_path):
    """regulatory_actions task_type also routes to CourtListener."""
    import requests as req_lib

    agent = LegalAgent(data_root=tmp_path)
    entity = Entity(entity_id="e1", name="Any Corp", identifiers={})
    task = SubTask("regulatory_actions", "legal_agent", "Regulatory")
    ctx = InvestigationContext()

    with patch(
        "osint_swarm.data_sources.courtlistener.requests.get",
        side_effect=req_lib.exceptions.ConnectionError("no network"),
    ):
        findings = agent.run(entity, task, ctx)

    assert findings[0].source_type == "court_record"
