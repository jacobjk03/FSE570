"""Tests for Legal Agent (OFAC sanctions screener + CourtListener court records)."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.lead_agent.context_manager import InvestigationContext
from agents.lead_agent.task_planner import SubTask
from agents.specialist_agents.legal_agent import LegalAgent
from app.investigation_errors import DataSourceError
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
    """Sanctions screening returns legal evidence with SDN cache present."""
    from tests.unit.agents.specialist_agents.test_sanctions_screener import _make_sdn_cache
    from agents.specialist_agents.legal_agent import agent as legal_agent_module

    _make_sdn_cache(tmp_path)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            legal_agent_module,
            "choose_next_tool",
            lambda **_kwargs: {
                "selected_tool": "ofac",
                "alternatives": [],
                "policy_used": "llm_action_policy",
                "reasoning": "Use OFAC screening.",
            },
        )
        agent = LegalAgent(data_root=tmp_path)
        entity = Entity(entity_id="e1", name="Some Corp", identifiers={})
        task = SubTask("sanctions_screening", "legal_agent", "Screen sanctions")
        ctx = InvestigationContext()
        findings = agent.run(entity, task, ctx)

    assert len(findings) >= 1
    assert findings[0].risk_category == "legal"
    assert findings[0].attributes.get("stub") is False


def test_legal_agent_sanctions_without_cache_raises(tmp_path):
    """Without SDN cache, strict mode should raise DataSourceError."""
    from agents.specialist_agents.legal_agent import agent as legal_agent_module
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            legal_agent_module,
            "choose_next_tool",
            lambda **_kwargs: {
                "selected_tool": "ofac",
                "alternatives": [],
                "policy_used": "llm_action_policy",
                "reasoning": "Use OFAC screening.",
            },
        )
        agent = LegalAgent(data_root=tmp_path)
        entity = Entity(entity_id="e1", name="E Corp", identifiers={})
        task = SubTask("sanctions_screening", "legal_agent", "Screen")
        ctx = InvestigationContext()
        with pytest.raises(DataSourceError):
            agent.run(entity, task, ctx)


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

    from agents.specialist_agents.legal_agent import agent as legal_agent_module
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            legal_agent_module,
            "choose_next_tool",
            lambda **_kwargs: {
                "selected_tool": "courtlistener",
                "alternatives": [],
                "policy_used": "llm_action_policy",
                "reasoning": "Use court records.",
            },
        )
        agent = LegalAgent(data_root=tmp_path)
        entity = Entity(entity_id="e_corp_001", name="E Corp", identifiers={})
        task = SubTask("litigation", "legal_agent", "Court records")
        ctx = InvestigationContext()
        findings = agent.run(entity, task, ctx)

    assert len(findings) >= 1
    assert findings[0].source_type == "court_record"
    assert findings[0].attributes.get("stub") is False


def test_legal_agent_litigation_no_cache_raises(tmp_path):
    """Without cache and with network error, strict mode should raise."""
    import requests as req_lib
    from agents.specialist_agents.legal_agent import agent as legal_agent_module

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            legal_agent_module,
            "choose_next_tool",
            lambda **_kwargs: {
                "selected_tool": "courtlistener",
                "alternatives": [],
                "policy_used": "llm_action_policy",
                "reasoning": "Use court records.",
            },
        )
        agent = LegalAgent(data_root=tmp_path)
        entity = Entity(entity_id="e1", name="Unknown Corp", identifiers={})
        task = SubTask("litigation", "legal_agent", "Court records")
        ctx = InvestigationContext()
        with patch(
            "osint_swarm.data_sources.courtlistener.requests.get",
            side_effect=req_lib.exceptions.ConnectionError("refused"),
        ):
            with pytest.raises(DataSourceError):
                agent.run(entity, task, ctx)


def test_legal_agent_regulatory_actions_routes_to_court(tmp_path):
    """regulatory_actions task_type also routes to CourtListener."""
    import requests as req_lib

    from agents.specialist_agents.legal_agent import agent as legal_agent_module
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            legal_agent_module,
            "choose_next_tool",
            lambda **_kwargs: {
                "selected_tool": "courtlistener",
                "alternatives": [],
                "policy_used": "llm_action_policy",
                "reasoning": "Use court records.",
            },
        )
        agent = LegalAgent(data_root=tmp_path)
        entity = Entity(entity_id="e1", name="Any Corp", identifiers={})
        task = SubTask("regulatory_actions", "legal_agent", "Regulatory")
        ctx = InvestigationContext()
        with patch(
            "osint_swarm.data_sources.courtlistener.requests.get",
            side_effect=req_lib.exceptions.ConnectionError("no network"),
        ):
            with pytest.raises(DataSourceError):
                agent.run(entity, task, ctx)
