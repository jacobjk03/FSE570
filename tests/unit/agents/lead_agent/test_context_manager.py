"""Tests for context manager."""

import pytest

from agents.lead_agent.context_manager import InvestigationContext
from agents.lead_agent.task_planner import SubTask
from osint_swarm.entities import Entity, Evidence


def test_context_starts_empty():
    ctx = InvestigationContext()
    assert ctx.get_entity() is None
    assert ctx.get_query() == ""
    assert ctx.get_tasks() == []
    assert ctx.get_all_findings() == []
    assert ctx.get_plan() is None
    assert ctx.get_action_history() == []
    assert ctx.get_tool_results() == []
    assert ctx.get_open_questions() == []
    assert ctx.get_discovered_entities() == []
    assert ctx.get_stop_reason() is None
    assert ctx.get_policy_usage() == {}
    assert ctx.get_policy_decisions() == []
    assert ctx.get_selected_alternatives() == []
    assert ctx.get_entity_queue() == []
    assert ctx.get_entity_graph_edges() == []


def test_context_set_get_entity():
    ctx = InvestigationContext()
    entity = Entity(entity_id="e1", name="Test")
    ctx.set_entity(entity)
    assert ctx.get_entity() is entity


def test_context_set_get_query():
    ctx = InvestigationContext()
    ctx.set_query("Investigate X")
    assert ctx.get_query() == "Investigate X"


def test_context_set_get_tasks():
    ctx = InvestigationContext()
    tasks = [SubTask("corporate_structure", "corporate_agent", "Analyze structure")]
    ctx.set_tasks(tasks)
    assert len(ctx.get_tasks()) == 1
    assert ctx.get_tasks()[0].task_type == "corporate_structure"


def test_context_add_and_get_agent_results():
    ctx = InvestigationContext()
    ev = Evidence(
        evidence_id="ev1",
        entity_id="e1",
        date="2024-01-01",
        source_type="sec_filing",
        risk_category="governance",
        summary="Test",
        source_uri="https://sec.gov",
        confidence=0.9,
    )
    ctx.add_agent_results("corporate_agent", [ev])
    assert len(ctx.get_agent_results("corporate_agent")) == 1
    assert ctx.get_agent_results("corporate_agent")[0].evidence_id == "ev1"
    assert len(ctx.get_all_findings()) == 1


def test_context_get_agent_results_returns_copy():
    ctx = InvestigationContext()
    ctx.add_agent_results("legal_agent", [])
    r1 = ctx.get_agent_results("legal_agent")
    r2 = ctx.get_agent_results("legal_agent")
    assert r1 is not r2


def test_context_records_plan_actions_and_memory():
    ctx = InvestigationContext()
    task = SubTask("sec_filings", "corporate_agent", "Review SEC", candidate_tools=("sec_edgar",), rationale="Test")
    ctx.set_plan(
        {
            "investigation_goal": "Investigate Test",
            "hypotheses": ["Hypothesis"],
            "tasks": [task.to_dict()],
            "max_rounds": 2,
        }
    )
    ctx.record_action("lead_agent", task.task_type, "dispatch_task", tool_name="sec_edgar", rationale="Because")
    ctx.record_tool_result(tool_name="sec_edgar", observation="Fetched SEC evidence", evidence_count=2)
    ctx.add_open_question("Need ownership corroboration")
    ctx.add_discovered_entity("Jane Doe", source="sec_edgar", relationship="officer")
    ctx.record_follow_up_action({"action_type": "open_question", "description": "Investigate Jane Doe"}, applied=True)
    ctx.set_stop_reason("completed_planned_investigation")

    assert ctx.get_plan()["investigation_goal"] == "Investigate Test"
    assert ctx.get_action_history()[0]["tool_name"] == "sec_edgar"
    assert ctx.get_tool_results()[0]["evidence_count"] == 2
    assert ctx.get_open_questions() == ["Need ownership corroboration"]
    assert ctx.get_discovered_entities()[0]["name"] == "Jane Doe"
    assert ctx.get_follow_up_actions(applied=True)[0]["action_type"] == "open_question"
    assert ctx.get_stop_reason() == "completed_planned_investigation"
    ctx.record_policy_decision(policy_name="action_policy", policy_used="deterministic_fallback", rationale="fallback")
    ctx.record_selected_alternatives(task_type="sec_filings", selected_tool="sec_edgar", alternatives=["courtlistener"], policy_used="deterministic_fallback")
    queued = ctx.enqueue_entity(name="Acme Holdings", source="courtlistener", relationship="controlling_entity", depth=1)
    assert queued is True
    popped = ctx.dequeue_entity()
    assert popped is not None
    ctx.add_entity_graph_edge(from_entity="Test Corp", to_entity="Acme Holdings", relationship="controlling_entity", source="courtlistener")
    assert ctx.get_policy_usage()["action_policy"] == "deterministic_fallback"
    assert ctx.get_selected_alternatives()[0]["selected_tool"] == "sec_edgar"
    assert ctx.get_entity_graph_edges()[0]["to_entity"] == "Acme Holdings"
