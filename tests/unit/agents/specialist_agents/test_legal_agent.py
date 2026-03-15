"""Tests for Legal Agent (OFAC sanctions screener + PACER stub)."""

import pytest

from agents.lead_agent.context_manager import InvestigationContext
from agents.lead_agent.task_planner import SubTask
from agents.specialist_agents.legal_agent import LegalAgent
from osint_swarm.entities import Entity


def test_legal_agent_agent_id():
    agent = LegalAgent()
    assert agent.agent_id == "legal_agent"


def test_legal_agent_sanctions_returns_legal_evidence(tmp_path):
    """Sanctions screening returns real Evidence (not old stub), risk_category='legal'."""
    agent = LegalAgent(data_root=tmp_path)  # no SDN cache → graceful fallback
    entity = Entity(entity_id="e1", name="Some Corp", identifiers={})
    task = SubTask("sanctions_screening", "legal_agent", "Screen sanctions")
    ctx = InvestigationContext()
    findings = agent.run(entity, task, ctx)

    assert len(findings) >= 1
    assert findings[0].risk_category == "legal"
    # stub flag must be False — we replaced the stub
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


def test_legal_agent_litigation_returns_pacer_stub():
    agent = LegalAgent()
    entity = Entity(entity_id="e1", name="E", identifiers={})
    task = SubTask("litigation", "legal_agent", "Court records")
    ctx = InvestigationContext()
    findings = agent.run(entity, task, ctx)
    assert len(findings) == 1
    assert "pacer" in findings[0].summary.lower() or "court" in findings[0].summary.lower()
