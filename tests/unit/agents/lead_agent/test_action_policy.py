"""Tests for strict LLM action policy."""

import pytest

from agents.lead_agent.action_policy import choose_next_tool
from agents.lead_agent.task_planner.types import SubTask
from app.investigation_errors import ActionPolicyError


def test_choose_next_tool_llm_json_is_used():
    task = SubTask(
        "litigation",
        "legal_agent",
        "Review courts",
        candidate_tools=("courtlistener",),
    )
    decision = choose_next_tool(
        agent_id="legal_agent",
        task=task,
        available_tools=["ofac", "courtlistener"],
        used_tools=[],
        context_snapshot={"round_count": 1},
        llm_client=lambda _prompt: '{"selected_tool":"courtlistener","alternatives":["ofac"],"reasoning":"Need court corroboration"}',
    )
    assert decision["selected_tool"] == "courtlistener"
    assert decision["policy_used"] == "llm_action_policy"


def test_choose_next_tool_invalid_llm_output_raises():
    task = SubTask("adverse_media", "social_graph_agent", "Find media")
    with pytest.raises(ActionPolicyError):
        choose_next_tool(
            agent_id="social_graph_agent",
            task=task,
            available_tools=["gdelt"],
            used_tools=[],
            context_snapshot={},
            llm_client=lambda _prompt: "not-json",
        )


def test_choose_next_tool_null_with_options_raises():
    task = SubTask("corporate_structure", "corporate_agent", "Analyze structure")
    with pytest.raises(ActionPolicyError):
        choose_next_tool(
            agent_id="corporate_agent",
            task=task,
            available_tools=["sec_edgar"],
            used_tools=[],
            context_snapshot={},
            llm_client=lambda _prompt: '{"selected_tool": null, "alternatives": [], "reasoning":"none"}',
        )


def test_choose_next_tool_recovers_after_null_retry():
    task = SubTask("corporate_structure", "corporate_agent", "Analyze structure")
    responses = iter(
        [
            '{"selected_tool": null, "alternatives": [], "reasoning":"none"}',
            '{"selected_tool":"sec_edgar","alternatives":[],"reasoning":"Best remaining tool"}',
        ]
    )
    decision = choose_next_tool(
        agent_id="corporate_agent",
        task=task,
        available_tools=["sec_edgar"],
        used_tools=[],
        context_snapshot={},
        llm_client=lambda _prompt: next(responses),
    )
    assert decision["selected_tool"] == "sec_edgar"
