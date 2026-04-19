"""Lead Agent: orchestrate planning, bounded agent loops, and reflexive follow-up."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from osint_swarm.entities import Entity, Evidence

from agents.lead_agent.context_manager import InvestigationContext
from agents.lead_agent.entity_resolution import resolve_one_with_auto as resolve_one
from agents.lead_agent.task_planner import InvestigationPlan, SubTask, build_plan
from agents.tools import get_available_tools_by_agent
from app.investigation_errors import StopPolicyError
from reflexion_layer import propose_follow_up_actions


AgentStub = Callable[[Entity, SubTask, InvestigationContext], List[Evidence]]


def _default_agent_stubs(data_root: Optional[Path] = None) -> Dict[str, AgentStub]:
    """Build stub callables from Phase 4 specialist agents."""
    data_root = data_root or Path("data")
    from agents.specialist_agents import CorporateAgent, LegalAgent, SocialGraphAgent
    corporate = CorporateAgent(data_root=data_root)
    legal = LegalAgent(data_root=data_root)
    social = SocialGraphAgent(data_root=data_root)
    return {
        "corporate_agent": lambda e, t, c: corporate.run(e, t, c),
        "legal_agent": lambda e, t, c: legal.run(e, t, c),
        "social_graph_agent": lambda e, t, c: social.run(e, t, c),
    }


class LeadAgent:
    """
    Lead Agent: accepts a natural-language investigation query, resolves the entity,
    decomposes into sub-tasks, dispatches to specialist agents (stubs), and
    collects results into an InvestigationContext.
    """

    def __init__(
        self,
        data_root: Optional[Path] = None,
        agent_stubs: Optional[Dict[str, AgentStub]] = None,
    ):
        self.data_root = Path(data_root) if data_root else Path("data")
        self._stubs = agent_stubs if agent_stubs is not None else _default_agent_stubs(self.data_root)
        self._stop_model = os.environ.get("STOP_POLICY_MODEL", "llama-3.1-8b-instant")

    def _call_llm(self, prompt: str) -> str:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise StopPolicyError("stop policy failed: GROQ_API_KEY is not set")
        try:
            from groq import Groq

            client = Groq(api_key=api_key)
            response = client.chat.completions.create(
                model=self._stop_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.1,
            )
            content = response.choices[0].message.content
            if not content or not content.strip():
                raise StopPolicyError("stop policy failed: empty LLM response")
            return content.strip()
        except StopPolicyError:
            raise
        except Exception as exc:
            raise StopPolicyError(f"stop policy LLM request failed: {exc}") from exc

    def _hard_stop_reason(
        self,
        context: InvestigationContext,
        plan: InvestigationPlan,
        pending_tasks: Sequence[SubTask],
        new_findings_this_round: int,
    ) -> Optional[str]:
        if context.get_stop_reason():
            return context.get_stop_reason()
        if context.round_count >= plan.max_rounds:
            return "round_budget_exhausted"
        if context.remaining_budget <= 0:
            return "action_budget_exhausted"
        if not pending_tasks:
            return "no_pending_tasks"
        return None

    def _should_stop_llm(
        self,
        context: InvestigationContext,
        plan: InvestigationPlan,
        pending_tasks: Sequence[SubTask],
        new_findings_this_round: int,
    ) -> tuple[bool, str, str]:
        prompt = (
            "You are the Stop Policy model for an OSINT multi-agent investigation loop.\n"
            "Decide whether execution should continue or stop at this state.\n\n"
            "Consider:\n"
            "- Pending tasks\n"
            "- New findings this round\n"
            "- Remaining budget and round count\n"
            "- Open questions and unresolved hypotheses\n\n"
            "Output contract:\n"
            "- Return VALID JSON ONLY: {\"stop\": boolean, \"reason\": string}\n"
            "- reason must be concise and audit-friendly.\n"
            "- No markdown or extra text outside JSON.\n\n"
            f"context={json.dumps({'round_count': context.round_count, 'remaining_budget': context.remaining_budget, 'new_findings_this_round': new_findings_this_round, 'pending_task_count': len(pending_tasks), 'open_questions': context.get_open_questions(), 'discovered_entities': context.get_discovered_entities()[:3], 'plan_max_rounds': plan.max_rounds}, ensure_ascii=True)}"
        )
        text = self._call_llm(prompt)
        try:
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1:
                raise StopPolicyError("stop policy returned non-JSON output")
            payload = json.loads(text[start : end + 1])
            if "stop" not in payload:
                raise StopPolicyError("stop policy output missing 'stop'")
            stop = bool(payload.get("stop"))
            reason = str(payload.get("reason") or "llm_stop_policy")
            return stop, reason, "llm_stop_policy"
        except StopPolicyError:
            raise
        except Exception as exc:
            raise StopPolicyError(f"stop policy output invalid: {exc}") from exc

    def _should_stop(
        self,
        context: InvestigationContext,
        plan: InvestigationPlan,
        pending_tasks: Sequence[SubTask],
        *,
        new_findings_this_round: int,
    ) -> bool:
        # Do not allow LLM stop-policy to terminate before the first execution round
        # when there is actual work queued from the planner.
        if context.round_count == 0 and pending_tasks:
            return False

        hard_reason = self._hard_stop_reason(context, plan, pending_tasks, new_findings_this_round)
        if hard_reason:
            context.set_stop_reason(hard_reason)
            context.record_policy_decision(
                policy_name="stop_policy",
                policy_used="deterministic_hard_stop",
                rationale=hard_reason,
                metadata={"pending_task_count": len(pending_tasks)},
            )
            return True

        stop, reason, policy_used = self._should_stop_llm(context, plan, pending_tasks, new_findings_this_round)
        context.record_policy_decision(
            policy_name="stop_policy",
            policy_used=policy_used,
            rationale=reason,
            metadata={"pending_task_count": len(pending_tasks)},
        )
        if stop:
            context.set_stop_reason(reason or "llm_stop_policy")
            return True
        return False

    def _apply_follow_up_actions(
        self,
        context: InvestigationContext,
        follow_ups: Sequence[dict],
    ) -> List[SubTask]:
        next_tasks: List[SubTask] = []
        for item in follow_ups:
            if item.get("action_type") == "add_task":
                task = SubTask(
                    task_type=item.get("task_type") or "adverse_media",
                    target_agent=item.get("target_agent") or "social_graph_agent",
                    description=item.get("description") or "Reflexive follow-up task.",
                    candidate_tools=tuple(item.get("candidate_tools") or ()),
                    priority=item.get("priority") or "medium",
                    rationale=item.get("reason") or "",
                    origin="reflexion",
                )
                if context.has_completed_task(task):
                    context.record_follow_up_action(item, applied=False)
                    continue
                next_tasks.append(task)
                context.record_follow_up_action(item, applied=True)
            elif item.get("action_type") == "open_question":
                context.add_open_question(item.get("description", ""))
                discovered = item.get("metadata", {}).get("discovered_entity", {})
                related_name = discovered.get("name")
                if related_name:
                    queued = context.enqueue_entity(
                        name=related_name,
                        source=discovered.get("source", "reflexion"),
                        relationship=discovered.get("relationship", "related_party"),
                        identifiers=discovered.get("identifiers", {}),
                        depth=context.follow_up_depth + 1,
                    )
                    if queued and context.get_entity():
                        context.add_entity_graph_edge(
                            from_entity=context.get_entity().name,
                            to_entity=related_name,
                            relationship=discovered.get("relationship", "related_party"),
                            source=discovered.get("source", "reflexion"),
                        )
                context.record_follow_up_action(item, applied=True)
            elif item.get("action_type") == "stop":
                context.set_stop_reason(item.get("reason") or "reflexion_stop")
                context.record_follow_up_action(item, applied=True)
            else:
                context.record_follow_up_action(item, applied=False)
        return next_tasks

    def run(self, query: str) -> InvestigationContext:
        """
        Execute the investigation pipeline with planning, action loops, and reflexion.

        Returns the InvestigationContext with entity, tasks, and results per agent.
        """
        context = InvestigationContext()
        context.set_query(query)
        context.record_action("lead_agent", "entity_resolution", "query_received", rationale=query, status="received", round_no=0)

        entity = resolve_one(query)
        if not entity:
            context.set_stop_reason("entity_unresolved")
            return context
        context.set_entity(entity)
        context.record_action(
            "lead_agent",
            "entity_resolution",
            "entity_resolved",
            rationale=f"Resolved query to {entity.name}.",
            status="completed",
            round_no=0,
            metadata={"entity_id": entity.entity_id, "identifiers": dict(entity.identifiers)},
        )

        available_tools_by_agent = get_available_tools_by_agent(
            data_root=self.data_root,
            entity=entity,
        )
        plan = build_plan(
            query,
            entity=entity,
            available_tools_by_agent=available_tools_by_agent,
        )
        context.set_plan(plan)
        context.set_tasks(plan.tasks)
        context.set_remaining_budget(max(len(plan.tasks), 1) * max(plan.max_rounds, 1))
        context.record_action(
            "lead_agent",
            "planning",
            "plan_created",
            rationale=plan.planner_notes or "Structured plan created.",
            status="completed",
            round_no=0,
            metadata={
                "planner": plan.planner,
                "max_rounds": plan.max_rounds,
                "tool_map": available_tools_by_agent,
                "task_count": len(plan.tasks),
            },
        )
        context.record_policy_decision(
            policy_name="planner",
            policy_used=plan.planner,
            rationale=plan.planner_notes or "Planner selected investigation tasks.",
            metadata={"task_count": len(plan.tasks)},
        )

        pending_tasks: List[SubTask] = list(plan.tasks)
        new_findings_this_round = 0

        while pending_tasks or context.round_count == 0:
            if self._should_stop(context, plan, pending_tasks, new_findings_this_round=new_findings_this_round):
                break

            round_no = context.increment_round()
            before_count = len(context.get_all_findings())
            current_tasks = list(pending_tasks)
            pending_tasks = []

            for task in current_tasks:
                if context.has_completed_task(task):
                    continue
                stub = self._stubs.get(task.target_agent)
                if not stub:
                    continue
                context.record_action(
                    "lead_agent",
                    task.task_type,
                    "dispatch_task",
                    rationale=task.rationale or task.description,
                    status="in_progress",
                    round_no=round_no,
                    metadata={
                        "target_agent": task.target_agent,
                        "candidate_tools": list(task.candidate_tools),
                        "priority": task.priority,
                        "origin": task.origin,
                    },
                )
                findings = stub(entity, task, context)
                context.add_agent_results(task.target_agent, findings)
                context.mark_task_completed(task)

            new_findings_this_round = len(context.get_all_findings()) - before_count

            follow_ups = [item.to_dict() for item in propose_follow_up_actions(context)]
            next_tasks = self._apply_follow_up_actions(context, follow_ups)
            queued = context.dequeue_entity()
            if queued:
                context.add_open_question(
                    f"Related entity queued for later expansion: {queued.get('name')} ({queued.get('relationship', 'related')})."
                )
            context.add_round_summary(
                round_no=round_no,
                task_count=len(current_tasks),
                new_findings=new_findings_this_round,
                pending_follow_ups=len(next_tasks),
            )
            pending_tasks.extend(next_tasks)

            if self._should_stop(context, plan, pending_tasks, new_findings_this_round=new_findings_this_round):
                break

        if not context.get_stop_reason():
            context.set_stop_reason("completed_planned_investigation")

        return context
