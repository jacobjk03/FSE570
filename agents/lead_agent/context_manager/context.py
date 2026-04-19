"""Context manager: holds investigation state, memory, and action history."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from osint_swarm.entities import Entity, Evidence

from agents.lead_agent.task_planner.types import InvestigationPlan, SubTask


@dataclass
class InvestigationContext:
    """
    Holds the current investigation context for the Lead Agent and specialists.

    Beyond the canonical entity/query/tasks/results fields, the context now acts
    as the working memory for the agentic investigation loop.
    """

    entity: Optional[Entity] = None
    query: str = ""
    tasks: List[SubTask] = field(default_factory=list)
    results: Dict[str, List[Evidence]] = field(default_factory=dict)
    plan: Optional[Dict[str, Any]] = None
    action_history: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)
    discovered_entities: List[Dict[str, Any]] = field(default_factory=list)
    follow_up_actions: List[Dict[str, Any]] = field(default_factory=list)
    skipped_follow_up_actions: List[Dict[str, Any]] = field(default_factory=list)
    policy_decisions: List[Dict[str, Any]] = field(default_factory=list)
    policy_usage: Dict[str, str] = field(default_factory=dict)
    selected_alternatives: List[Dict[str, Any]] = field(default_factory=list)
    round_count: int = 0
    remaining_budget: int = 0
    stop_reason: Optional[str] = None
    entity_queue: List[Dict[str, Any]] = field(default_factory=list)
    entity_graph_edges: List[Dict[str, Any]] = field(default_factory=list)
    follow_up_depth: int = 0
    max_follow_up_depth: int = 1
    completed_task_keys: Set[str] = field(default_factory=set)
    round_summaries: List[Dict[str, Any]] = field(default_factory=list)

    def set_entity(self, entity: Optional[Entity]) -> None:
        self.entity = entity

    def get_entity(self) -> Optional[Entity]:
        return self.entity

    def set_query(self, query: str) -> None:
        self.query = query

    def get_query(self) -> str:
        return self.query

    def set_tasks(self, tasks: List[SubTask]) -> None:
        self.tasks = tasks

    def get_tasks(self) -> List[SubTask]:
        return self.tasks.copy()

    def set_plan(self, plan: Optional[InvestigationPlan | Dict[str, Any]]) -> None:
        if plan is None:
            self.plan = None
        elif isinstance(plan, InvestigationPlan):
            self.plan = plan.to_dict()
        else:
            self.plan = dict(plan)

    def get_plan(self) -> Optional[Dict[str, Any]]:
        return dict(self.plan) if self.plan is not None else None

    def add_agent_results(self, agent_id: str, findings: List[Evidence]) -> None:
        if agent_id not in self.results:
            self.results[agent_id] = []
        self.results[agent_id].extend(findings)

    def get_agent_results(self, agent_id: str) -> List[Evidence]:
        return self.results.get(agent_id, []).copy()

    def get_all_findings(self) -> List[Evidence]:
        out: List[Evidence] = []
        for findings in self.results.values():
            out.extend(findings)
        return out

    def record_action(
        self,
        agent_id: str,
        task_type: str,
        action_type: str,
        *,
        rationale: str = "",
        tool_name: Optional[str] = None,
        status: str = "completed",
        round_no: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.action_history.append(
            {
                "agent_id": agent_id,
                "task_type": task_type,
                "action_type": action_type,
                "tool_name": tool_name,
                "rationale": rationale,
                "status": status,
                "round_no": round_no if round_no is not None else self.round_count,
                "metadata": dict(metadata or {}),
            }
        )

    def get_action_history(self) -> List[Dict[str, Any]]:
        return [dict(item) for item in self.action_history]

    def record_tool_result(
        self,
        *,
        tool_name: str,
        observation: str,
        evidence_count: int,
        round_no: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.tool_results.append(
            {
                "tool_name": tool_name,
                "observation": observation,
                "evidence_count": evidence_count,
                "round_no": round_no if round_no is not None else self.round_count,
                "metadata": dict(metadata or {}),
            }
        )

    def get_tool_results(self) -> List[Dict[str, Any]]:
        return [dict(item) for item in self.tool_results]

    def add_open_question(self, question: str) -> None:
        if question and question not in self.open_questions:
            self.open_questions.append(question)

    def get_open_questions(self) -> List[str]:
        return list(self.open_questions)

    def clear_open_questions(self) -> None:
        self.open_questions.clear()

    def add_discovered_entity(
        self,
        name: str,
        *,
        source: str,
        relationship: str = "",
        identifiers: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not name:
            return
        key = (name.strip().lower(), relationship.strip().lower(), source.strip().lower())
        existing_keys = {
            (
                item.get("name", "").strip().lower(),
                item.get("relationship", "").strip().lower(),
                item.get("source", "").strip().lower(),
            )
            for item in self.discovered_entities
        }
        if key in existing_keys:
            return
        self.discovered_entities.append(
            {
                "name": name,
                "source": source,
                "relationship": relationship,
                "identifiers": dict(identifiers or {}),
                "metadata": dict(metadata or {}),
            }
        )

    def get_discovered_entities(self) -> List[Dict[str, Any]]:
        return [dict(item) for item in self.discovered_entities]

    def record_follow_up_action(self, action: Dict[str, Any], *, applied: bool) -> None:
        target = self.follow_up_actions if applied else self.skipped_follow_up_actions
        target.append(dict(action))

    def get_follow_up_actions(self, *, applied: bool = True) -> List[Dict[str, Any]]:
        items = self.follow_up_actions if applied else self.skipped_follow_up_actions
        return [dict(item) for item in items]

    def record_policy_decision(
        self,
        *,
        policy_name: str,
        policy_used: str,
        rationale: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.policy_usage[policy_name] = policy_used
        entry = {
            "policy_name": policy_name,
            "policy_used": policy_used,
            "rationale": rationale,
            "round_no": self.round_count,
            "metadata": dict(metadata or {}),
        }
        self.policy_decisions.append(entry)

    def get_policy_decisions(self) -> List[Dict[str, Any]]:
        return [dict(item) for item in self.policy_decisions]

    def get_policy_usage(self) -> Dict[str, str]:
        return dict(self.policy_usage)

    def record_selected_alternatives(
        self,
        *,
        task_type: str,
        selected_tool: Optional[str],
        alternatives: List[str],
        policy_used: str,
    ) -> None:
        self.selected_alternatives.append(
            {
                "task_type": task_type,
                "selected_tool": selected_tool,
                "alternatives": list(alternatives),
                "policy_used": policy_used,
                "round_no": self.round_count,
            }
        )

    def get_selected_alternatives(self) -> List[Dict[str, Any]]:
        return [dict(item) for item in self.selected_alternatives]

    def enqueue_entity(
        self,
        *,
        name: str,
        source: str,
        relationship: str = "",
        identifiers: Optional[Dict[str, str]] = None,
        depth: Optional[int] = None,
    ) -> bool:
        if not name:
            return False
        depth_val = self.follow_up_depth if depth is None else int(depth)
        if depth_val > self.max_follow_up_depth:
            return False
        candidate = {
            "name": name,
            "source": source,
            "relationship": relationship,
            "identifiers": dict(identifiers or {}),
            "depth": depth_val,
        }
        key = (candidate["name"].strip().lower(), candidate["source"].strip().lower(), candidate["relationship"].strip().lower())
        existing = {
            (item.get("name", "").strip().lower(), item.get("source", "").strip().lower(), item.get("relationship", "").strip().lower())
            for item in self.entity_queue
        }
        if key in existing:
            return False
        self.entity_queue.append(candidate)
        return True

    def dequeue_entity(self) -> Optional[Dict[str, Any]]:
        if not self.entity_queue:
            return None
        item = self.entity_queue.pop(0)
        self.follow_up_depth = max(self.follow_up_depth, int(item.get("depth", 0)))
        return dict(item)

    def get_entity_queue(self) -> List[Dict[str, Any]]:
        return [dict(item) for item in self.entity_queue]

    def add_entity_graph_edge(
        self,
        *,
        from_entity: str,
        to_entity: str,
        relationship: str,
        source: str,
    ) -> None:
        edge = {
            "from_entity": from_entity,
            "to_entity": to_entity,
            "relationship": relationship,
            "source": source,
        }
        if edge not in self.entity_graph_edges:
            self.entity_graph_edges.append(edge)

    def get_entity_graph_edges(self) -> List[Dict[str, Any]]:
        return [dict(item) for item in self.entity_graph_edges]

    def increment_round(self) -> int:
        self.round_count += 1
        return self.round_count

    def set_remaining_budget(self, budget: int) -> None:
        self.remaining_budget = max(0, int(budget))

    def consume_budget(self, amount: int = 1) -> None:
        self.remaining_budget = max(0, self.remaining_budget - max(0, int(amount)))

    def set_stop_reason(self, reason: Optional[str]) -> None:
        self.stop_reason = reason

    def get_stop_reason(self) -> Optional[str]:
        return self.stop_reason

    def _task_key(self, task: SubTask) -> str:
        tools = ",".join(task.candidate_tools)
        return f"{task.target_agent}:{task.task_type}:{tools}"

    def mark_task_completed(self, task: SubTask) -> None:
        self.completed_task_keys.add(self._task_key(task))

    def has_completed_task(self, task: SubTask) -> bool:
        return self._task_key(task) in self.completed_task_keys

    def add_round_summary(self, *, round_no: int, task_count: int, new_findings: int, pending_follow_ups: int) -> None:
        self.round_summaries.append(
            {
                "round_no": round_no,
                "task_count": task_count,
                "new_findings": new_findings,
                "pending_follow_ups": pending_follow_ups,
            }
        )

    def get_round_summaries(self) -> List[Dict[str, Any]]:
        return [dict(item) for item in self.round_summaries]
