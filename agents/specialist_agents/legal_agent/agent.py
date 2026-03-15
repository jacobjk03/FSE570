"""Legal Agent: OFAC sanctions screening + PACER (stub); implements SpecialistAgent contract."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from osint_swarm.entities import Entity, Evidence

from agents.lead_agent.context_manager import InvestigationContext
from agents.lead_agent.task_planner.types import SubTask
from agents.specialist_agents.legal_agent.sanctions_screener.screener import screen as ofac_screen
from agents.specialist_agents.legal_agent.pacer_analyzer.analyzer import run_stub as pacer_run


class LegalAgent:
    """Legal and compliance agent: OFAC sanctions screening (live) + PACER (stub)."""

    AGENT_ID = "legal_agent"

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
        """Dispatch to OFAC screener or PACER stub by task_type."""
        if task.task_type == "sanctions_screening":
            return ofac_screen(entity, task, context, data_root=self.data_root)
        if task.task_type in ("litigation", "regulatory_actions"):
            return pacer_run(entity, task, context)
        # Default: OFAC screening
        return ofac_screen(entity, task, context, data_root=self.data_root)
