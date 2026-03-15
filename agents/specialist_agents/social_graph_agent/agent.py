"""Social Graph Agent: GDELT adverse media + influence analysis."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from osint_swarm.entities import Entity, Evidence

from agents.lead_agent.context_manager import InvestigationContext
from agents.lead_agent.task_planner.types import SubTask


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
        """
        Fetch adverse media and network evidence via GDELT.
        Both adverse_media and network_analysis tasks use the GDELT processor.
        """
        try:
            from mcp_layer import get_evidence_for_entity
            evidence = get_evidence_for_entity(
                entity,
                sources=("gdelt",),
                data_root=self.data_root,
            )
        except Exception:
            evidence = []
        return evidence
