"""Task planner compatibility wrapper."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from osint_swarm.entities import Entity

from agents.lead_agent.task_planner.llm_planner import plan_investigation
from agents.lead_agent.task_planner.types import InvestigationPlan, SubTask


def build_plan(
    query: str,
    entity: Optional[Entity] = None,
    *,
    llm_client: Optional[object] = None,
    available_tools_by_agent: Optional[Dict[str, Iterable[str]]] = None,
) -> InvestigationPlan:
    """Build a structured investigation plan with LLM guidance when available."""
    return plan_investigation(
        query,
        entity=entity,
        llm_client=llm_client,
        available_tools_by_agent=available_tools_by_agent,
    )

def decompose(
    query: str,
    entity: Optional[Entity] = None,
) -> List[SubTask]:
    """Backward-compatible task decomposition entry point."""
    return build_plan(query, entity=entity).tasks
