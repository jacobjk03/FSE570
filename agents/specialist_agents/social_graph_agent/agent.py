"""Social Graph Agent: bounded tool-using media intelligence agent."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from osint_swarm.entities import Entity, Evidence

from agents.lead_agent.action_policy import choose_next_tool
from agents.lead_agent.context_manager import InvestigationContext
from agents.lead_agent.task_planner.types import SubTask
from agents.tools import get_tools_for_agent


class SocialGraphAgent:
    """Social network analysis agent: GDELT adverse media and influence mapping."""

    AGENT_ID = "social_graph_agent"

    def __init__(self, data_root: Optional[Path] = None):
        self.data_root = Path(data_root) if data_root else Path("data")

    @property
    def agent_id(self) -> str:
        return self.AGENT_ID

    def run(
        self,
        entity: Entity,
        task: SubTask,
        context: InvestigationContext,
    ) -> List[Evidence]:
        """Fetch adverse media and network evidence via a bounded GDELT tool."""
        tools = get_tools_for_agent(self.agent_id, data_root=self.data_root)
        decision = choose_next_tool(
            agent_id=self.agent_id,
            task=task,
            available_tools=list(tools.keys()),
            used_tools=[],
            context_snapshot={
                "round_count": context.round_count,
                "remaining_budget": context.remaining_budget,
                "recent_tool_results": context.get_tool_results()[-3:],
                "open_questions": context.get_open_questions(),
            },
        )
        context.record_policy_decision(
            policy_name="action_policy",
            policy_used=decision["policy_used"],
            rationale=decision["reasoning"],
            metadata={"agent_id": self.agent_id, "task_type": task.task_type},
        )
        context.record_selected_alternatives(
            task_type=task.task_type,
            selected_tool=decision.get("selected_tool"),
            alternatives=decision.get("alternatives", []),
            policy_used=decision["policy_used"],
        )
        tool_name = decision.get("selected_tool")
        if tool_name not in tools:
            return []

        context.record_action(
            self.agent_id,
            task.task_type,
            "tool_selected",
            rationale=task.rationale or task.description,
            tool_name=tool_name,
            round_no=context.round_count,
            metadata={"candidate_tools": list(task.candidate_tools)},
        )
        result = tools[tool_name].run(entity, task, context)
        context.record_tool_result(
            tool_name=tool_name,
            observation=result.observation,
            evidence_count=len(result.evidence),
            round_no=context.round_count,
            metadata={"success": result.success, **dict(result.metadata)},
        )
        context.consume_budget(1)
        context.record_action(
            self.agent_id,
            task.task_type,
            "task_completed",
            rationale=f"Produced {len(result.evidence)} evidence rows.",
            status="completed",
            round_no=context.round_count,
        )
        return result.evidence
