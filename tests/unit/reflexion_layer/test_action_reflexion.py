"""Tests for reflexion follow-up action generation."""

from agents.lead_agent.context_manager import InvestigationContext
from reflexion_layer.action_reflexion import FollowUpAction, propose_follow_up_actions
from osint_swarm.entities import Entity, Evidence


def test_propose_follow_up_actions_adds_media_follow_up_when_missing():
    ctx = InvestigationContext()
    ctx.set_entity(Entity(entity_id="e1", name="Entity One", identifiers={"cik": "0000000001"}))
    ctx.round_count = 1
    ctx.add_agent_results(
        "legal_agent",
        [
            Evidence(
                "e1_ofac_clean",
                "e1",
                "2024-01-01",
                "regulator_api",
                "legal",
                "Clean OFAC result",
                "https://ofac.example",
                confidence=0.9,
                attributes={"screened": True},
            )
        ],
    )
    actions = propose_follow_up_actions(
        ctx,
        llm_client=lambda _prompt: '{"ranked_indices":[0],"stop_now":false,"reason":"Close media gap first"}',
    )
    assert any(action.action_type == "add_task" and action.task_type == "adverse_media" for action in actions)


def test_propose_follow_up_actions_surfaces_discovered_entity_question():
    ctx = InvestigationContext()
    ctx.set_entity(Entity(entity_id="e1", name="Entity One", identifiers={}))
    ctx.round_count = 1
    ctx.add_discovered_entity("Jane Doe", source="sec_edgar", relationship="officer")

    actions = propose_follow_up_actions(
        ctx,
        llm_client=lambda _prompt: '{"ranked_indices":[0],"stop_now":false,"reason":"Open question only"}',
    )
    assert any(action.action_type == "open_question" for action in actions)


def test_follow_up_action_to_subtask_round_trips():
    action = FollowUpAction(
        action_type="add_task",
        reason="Need more media evidence",
        description="Retry adverse media search",
        target_agent="social_graph_agent",
        task_type="adverse_media",
        candidate_tools=("gdelt",),
    )
    task = action.to_subtask()
    assert task is not None
    assert task.task_type == "adverse_media"
    assert task.origin == "reflexion"


def test_propose_follow_up_actions_llm_ranker_changes_order():
    ctx = InvestigationContext()
    ctx.set_entity(Entity(entity_id="e1", name="Entity One", identifiers={}))
    ctx.round_count = 1
    ctx.add_agent_results(
        "legal_agent",
        [Evidence("e1_ofac_clean", "e1", "", "regulator_api", "legal", "No sanctions matches", "", confidence=0.9, attributes={"screened": True})],
    )
    actions = propose_follow_up_actions(
        ctx,
        llm_client=lambda _prompt: '{"ranked_indices":[0],"stop_now":false,"reason":"Prioritize media follow-up first"}',
    )
    assert len(actions) >= 1
    assert ctx.get_policy_usage().get("reflexion_policy") == "llm_reflexion_policy"
