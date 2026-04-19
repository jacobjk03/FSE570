"""Task and plan types for the investigation planner."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


@dataclass(frozen=True)
class SubTask:
    """A single sub-task allocated to a specialist agent."""

    task_type: str
    target_agent: str
    description: str
    candidate_tools: Tuple[str, ...] = ()
    priority: str = "medium"
    rationale: str = ""
    origin: str = "planner"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_type": self.task_type,
            "target_agent": self.target_agent,
            "description": self.description,
            "candidate_tools": list(self.candidate_tools),
            "priority": self.priority,
            "rationale": self.rationale,
            "origin": self.origin,
        }


@dataclass(frozen=True)
class InvestigationPlan:
    """Structured plan emitted by the planner before execution begins."""

    investigation_goal: str
    hypotheses: List[str]
    tasks: List[SubTask]
    success_criteria: List[str] = field(default_factory=list)
    max_rounds: int = 1
    planner: str = "rule_based"
    planner_notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "investigation_goal": self.investigation_goal,
            "hypotheses": list(self.hypotheses),
            "tasks": [task.to_dict() for task in self.tasks],
            "success_criteria": list(self.success_criteria),
            "max_rounds": self.max_rounds,
            "planner": self.planner,
            "planner_notes": self.planner_notes,
        }
