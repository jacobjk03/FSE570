"""Shared tool abstractions for agentic specialist agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from agents.lead_agent.context_manager import InvestigationContext
from agents.lead_agent.task_planner.types import SubTask
from osint_swarm.entities import Entity, Evidence


@dataclass
class ToolCallResult:
    """Normalized result from a bounded agent tool."""

    tool_name: str
    evidence: List[Evidence]
    observation: str
    discovered_entities: List[Dict[str, Any]] = field(default_factory=list)
    success: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


class InvestigationTool(Protocol):
    """Protocol for any bounded investigation tool."""

    name: str
    description: str
    data_root: Path

    def run(
        self,
        entity: Entity,
        task: SubTask,
        context: InvestigationContext,
    ) -> ToolCallResult:
        ...
