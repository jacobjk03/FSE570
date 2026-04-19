"""Tests for Lead Agent orchestration."""

from pathlib import Path

import pytest

from agents.lead_agent import LeadAgent
from agents.lead_agent.task_planner.types import InvestigationPlan, SubTask
from app.investigation_errors import PlannerLLMError
from osint_swarm.entities import Entity, Evidence


def _fake_plan() -> InvestigationPlan:
    return InvestigationPlan(
        investigation_goal="Investigate Tesla",
        hypotheses=["Tesla may have legal or governance risk indicators."],
        tasks=[
            SubTask("corporate_structure", "corporate_agent", "Review SEC filings", candidate_tools=("sec_edgar",)),
            SubTask("sanctions_screening", "legal_agent", "Run OFAC screening", candidate_tools=("ofac",)),
            SubTask("adverse_media", "social_graph_agent", "Review media", candidate_tools=("gdelt",)),
        ],
        success_criteria=["All lanes executed"],
        max_rounds=1,
        planner="llm",
        planner_notes="mocked",
    )


def test_lead_agent_run_unknown_entity_returns_context_with_no_entity():
    agent = LeadAgent()
    ctx = agent.run("Unknown Company XYZ 12345")
    assert ctx.get_entity() is None
    assert ctx.get_query() == "Unknown Company XYZ 12345"
    assert ctx.get_tasks() == []
    assert ctx.get_all_findings() == []
    assert ctx.get_stop_reason() == "entity_unresolved"


def test_lead_agent_run_tesla_resolves_entity_and_has_tasks():
    from agents.lead_agent import orchestrator as orchestrator_module

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(orchestrator_module, "build_plan", lambda *_args, **_kwargs: _fake_plan())
        mp.setattr(orchestrator_module, "propose_follow_up_actions", lambda *_args, **_kwargs: [])
        mp.setattr(LeadAgent, "_should_stop_llm", lambda self, *_args, **_kwargs: (False, "continue", "llm_stop_policy"))
        stub = lambda _entity, _task, _context: []
        agent = LeadAgent(agent_stubs={
            "corporate_agent": stub,
            "legal_agent": stub,
            "social_graph_agent": stub,
        })
        ctx = agent.run("Investigate Tesla for money laundering")
    assert ctx.get_entity() is not None
    assert ctx.get_entity().entity_id == "tesla_inc_cik_0001318605"
    assert len(ctx.get_tasks()) == 3
    assert ctx.get_query() == "Investigate Tesla for money laundering"
    assert ctx.get_plan() is not None
    assert ctx.get_action_history()
    assert ctx.round_count >= 1
    assert ctx.get_stop_reason() is not None


def test_lead_agent_run_tesla_gets_corporate_evidence_with_mcp(tmp_path: Path):
    """LeadAgent collects findings from specialist stubs."""
    from agents.lead_agent import orchestrator as orchestrator_module
    dummy_evidence = [
        Evidence(
            evidence_id="sec_ev_1",
            entity_id="tesla_inc_cik_0001318605",
            date="2024-01-01",
            source_type="sec_filing",
            risk_category="governance",
            summary="SEC filing evidence",
            source_uri="https://sec.gov",
            confidence=0.9,
        )
    ]
    stub = lambda _entity, _task, _context: dummy_evidence
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(orchestrator_module, "build_plan", lambda *_args, **_kwargs: _fake_plan())
        mp.setattr(orchestrator_module, "propose_follow_up_actions", lambda *_args, **_kwargs: [])
        mp.setattr(LeadAgent, "_should_stop_llm", lambda self, *_args, **_kwargs: (False, "continue", "llm_stop_policy"))
        agent = LeadAgent(agent_stubs={
            "corporate_agent": stub,
            "legal_agent": stub,
            "social_graph_agent": stub,
        })
        ctx = agent.run("Investigate Tesla")
    findings = ctx.get_all_findings()
    assert len(findings) >= 1
    assert any(f.source_type == "sec_filing" for f in findings)


def test_lead_agent_accepts_custom_stubs():
    """Custom agent stubs are used when provided (entity, task, context)."""
    collected = []

    def stub(_entity: Entity, task, _context):
        collected.append(task.task_type)
        return []

    from agents.lead_agent import orchestrator as orchestrator_module
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(orchestrator_module, "build_plan", lambda *_args, **_kwargs: _fake_plan())
        mp.setattr(orchestrator_module, "propose_follow_up_actions", lambda *_args, **_kwargs: [])
        mp.setattr(LeadAgent, "_should_stop_llm", lambda self, *_args, **_kwargs: (False, "continue", "llm_stop_policy"))
        agent = LeadAgent(agent_stubs={
            "corporate_agent": stub,
            "legal_agent": stub,
            "social_graph_agent": stub,
        })
        ctx = agent.run("Investigate Tesla for money laundering")
    assert len(collected) == 3
    assert "corporate_structure" in collected
    assert "sanctions_screening" in collected
    assert "adverse_media" in collected


def test_lead_agent_applies_reflexive_follow_up_once():
    """A follow-up recommendation should be recorded and bounded by the loop."""
    calls = []

    def stub(_entity: Entity, task, context):
        calls.append(task.task_type)
        if task.task_type == "sanctions_screening":
            return []
        return [
            Evidence(
                evidence_id=f"{task.task_type}_ev",
                entity_id="tesla_inc_cik_0001318605",
                date="2024-01-01",
                source_type="news_article" if task.target_agent == "social_graph_agent" else "sec_filing",
                risk_category="network" if task.target_agent == "social_graph_agent" else "governance",
                summary=f"Evidence for {task.task_type}",
                source_uri="https://example.com",
                confidence=0.8,
            )
        ]

    from agents.lead_agent import orchestrator as orchestrator_module
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(orchestrator_module, "build_plan", lambda *_args, **_kwargs: _fake_plan())
        mp.setattr(orchestrator_module, "propose_follow_up_actions", lambda *_args, **_kwargs: [])
        mp.setattr(LeadAgent, "_should_stop_llm", lambda self, *_args, **_kwargs: (False, "continue", "llm_stop_policy"))
        agent = LeadAgent(
            agent_stubs={
                "corporate_agent": stub,
                "legal_agent": stub,
                "social_graph_agent": stub,
            }
        )
        ctx = agent.run("Investigate Tesla for money laundering")

    assert "sanctions_screening" in calls
    assert ctx.round_count >= 1
    assert ctx.get_stop_reason() is not None


def test_lead_agent_raises_when_planner_fails():
    from agents.lead_agent import orchestrator as orchestrator_module

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(orchestrator_module, "build_plan", lambda *_args, **_kwargs: (_ for _ in ()).throw(PlannerLLMError("planner failed")))
        agent = LeadAgent()
        with pytest.raises(PlannerLLMError):
            agent.run("Investigate Tesla")
