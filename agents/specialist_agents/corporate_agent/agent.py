"""Corporate Agent: bounded tool-using agent for corporate intelligence."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Set

from osint_swarm.entities import Entity, Evidence

from agents.lead_agent.action_policy import choose_next_tool
from agents.lead_agent.context_manager import InvestigationContext
from agents.lead_agent.task_planner.types import SubTask
from agents.tools import get_tools_for_agent


class CorporateAgent:
    """Corporate intelligence agent for SEC/governance evidence."""

    AGENT_ID = "corporate_agent"

    def __init__(self, data_root: Optional[Path] = None):
        self.data_root = Path(data_root) if data_root else Path("data")

    @property
    def agent_id(self) -> str:
        return self.AGENT_ID

    def _select_next_tool(
        self,
        task: SubTask,
        used_tools: Set[str],
        available_tools: List[str],
        context: InvestigationContext,
    ) -> Optional[str]:
        decision = choose_next_tool(
            agent_id=self.agent_id,
            task=task,
            available_tools=available_tools,
            used_tools=list(used_tools),
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
        return decision.get("selected_tool")

    def _should_continue(self, task: SubTask, used_tools: Set[str], findings: List[Evidence]) -> bool:
        return False

    def run(
        self,
        entity: Entity,
        task: SubTask,
        context: InvestigationContext,
    ) -> List[Evidence]:
        """Run a bounded tool-selection loop for corporate investigation tasks."""
        tools = get_tools_for_agent(self.agent_id, data_root=self.data_root, entity=entity)
        used_tools: Set[str] = set()
        all_findings: List[Evidence] = []
        seen_ids: Set[str] = set()
        available_tools = list(tools.keys())

        while True:
            tool_name = self._select_next_tool(task, used_tools, available_tools, context)
            if not tool_name or tool_name not in tools:
                break

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
            for discovered in result.discovered_entities:
                context.add_discovered_entity(
                    discovered.get("name", ""),
                    source=discovered.get("source", tool_name),
                    relationship=discovered.get("relationship", ""),
                    identifiers=discovered.get("identifiers", {}),
                    metadata=discovered.get("metadata", {}),
                )

            for finding in result.evidence:
                if finding.evidence_id not in seen_ids:
                    seen_ids.add(finding.evidence_id)
                    all_findings.append(finding)

            used_tools.add(tool_name)
            context.consume_budget(1)

            if not self._should_continue(task, used_tools, all_findings):
                break

        context.record_action(
            self.agent_id,
            task.task_type,
            "task_completed",
            rationale=f"Produced {len(all_findings)} evidence rows.",
            status="completed",
            round_no=context.round_count,
        )
        return all_findings
