"""Generate machine-usable follow-up actions from investigation state."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from typing import Any, Dict, List, Optional

from agents.lead_agent.context_manager import InvestigationContext
from agents.lead_agent.task_planner.types import SubTask
from app.investigation_errors import ReflexionPolicyError
from reflexion_layer.gap_detection import detect_gaps

_MODEL = os.environ.get("REFLEXION_POLICY_MODEL", "llama-3.1-8b-instant")


@dataclass(frozen=True)
class FollowUpAction:
    """A reflexive recommendation for the next investigation step."""

    action_type: str
    reason: str
    description: str
    target_agent: Optional[str] = None
    task_type: Optional[str] = None
    candidate_tools: tuple[str, ...] = ()
    priority: str = "medium"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_type": self.action_type,
            "reason": self.reason,
            "description": self.description,
            "target_agent": self.target_agent,
            "task_type": self.task_type,
            "candidate_tools": list(self.candidate_tools),
            "priority": self.priority,
            "metadata": dict(self.metadata),
        }

    def to_subtask(self) -> Optional[SubTask]:
        if self.action_type != "add_task" or not self.task_type or not self.target_agent:
            return None
        return SubTask(
            task_type=self.task_type,
            target_agent=self.target_agent,
            description=self.description,
            candidate_tools=self.candidate_tools,
            priority=self.priority,
            rationale=self.reason,
            origin="reflexion",
        )


def _has_completed(context: InvestigationContext, task_type: str) -> bool:
    return any(
        item.get("task_type") == task_type and item.get("status") == "completed"
        for item in context.get_action_history()
    )


def _call_llm(prompt: str) -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ReflexionPolicyError("reflexion policy failed: GROQ_API_KEY is not set")
    try:
        from groq import Groq

        client = Groq(api_key=api_key, timeout=30.0)
        response = client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=320,
            temperature=0.1,
        )
        content = response.choices[0].message.content
        if not content or not content.strip():
            raise ReflexionPolicyError("reflexion policy failed: empty LLM response")
        return content.strip()
    except ReflexionPolicyError:
        raise
    except Exception as exc:
        raise ReflexionPolicyError(f"reflexion policy LLM request failed: {exc}") from exc


def _rank_actions_with_llm(
    context: InvestigationContext,
    actions: List[FollowUpAction],
    llm_client: Optional[Any] = None,
) -> tuple[List[FollowUpAction], str, str]:
    if not actions:
        return actions, "llm_reflexion_policy", "No reflexion actions to rank."

    prompt = (
        "You are the Reflexion Policy model in an OSINT agent loop.\n"
        "Your role is to evaluate completeness and prioritize next actions.\n\n"
        "You must:\n"
        "- Rank follow-up actions by expected gap closure and confidence gain.\n"
        "- Use round and budget constraints to avoid low-yield loops.\n"
        "- Indicate whether the loop should stop now based on marginal value.\n\n"
        "Output contract:\n"
        "- Return VALID JSON ONLY.\n"
        "- ranked_indices must reference provided action indices.\n"
        "- stop_now is boolean.\n"
        "- reason is short and audit-readable.\n"
        "- No text outside JSON.\n\n"
        "Return JSON with schema:\n"
        '{ "ranked_indices": [int], "stop_now": bool, "reason": string }\n\n'
        f"round_count={context.round_count}, remaining_budget={context.remaining_budget}\n"
        f"open_questions={json.dumps(context.get_open_questions(), ensure_ascii=True)}\n"
        f"actions={json.dumps([a.to_dict() for a in actions], ensure_ascii=True)}"
    )
    text = llm_client(prompt) if llm_client is not None else _call_llm(prompt)
    if not text or not str(text).strip():
        raise ReflexionPolicyError("reflexion policy failed: empty ranking output")

    try:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            raise ReflexionPolicyError("reflexion policy returned non-JSON output")
        payload = json.loads(text[start : end + 1])
        if "ranked_indices" not in payload:
            raise ReflexionPolicyError("reflexion policy output missing ranked_indices")
        ranked_indices = [int(i) for i in payload.get("ranked_indices", []) if isinstance(i, int) or str(i).isdigit()]
        ranked: List[FollowUpAction] = []
        used = set()
        for idx in ranked_indices:
            if idx < 0 or idx >= len(actions):
                raise ReflexionPolicyError(f"reflexion policy returned out-of-bounds index {idx}")
            if idx not in used:
                ranked.append(actions[idx])
                used.add(idx)
        for idx, action in enumerate(actions):
            if idx not in used:
                ranked.append(action)

        if payload.get("stop_now") and not any(a.action_type == "stop" for a in ranked):
            ranked.append(
                FollowUpAction(
                    action_type="stop",
                    reason=str(payload.get("reason") or "LLM reflexion recommended stop."),
                    description="Stop after reflexion policy recommendation.",
                    priority="medium",
                )
            )
        return ranked, "llm_reflexion_policy", str(payload.get("reason") or "LLM ranked reflexion actions.")
    except ReflexionPolicyError:
        raise
    except Exception as exc:
        raise ReflexionPolicyError(f"reflexion policy output invalid: {exc}") from exc


def propose_follow_up_actions(
    context: InvestigationContext,
    llm_client: Optional[Any] = None,
) -> List[FollowUpAction]:
    """Inspect the context and propose additional tasks or stopping guidance."""
    if not context.get_entity():
        return []

    actions: List[FollowUpAction] = []
    gaps = detect_gaps(context)
    for gap in gaps:
        if gap.area == "Adverse media / network" and not _has_completed(context, "adverse_media"):
            actions.append(
                FollowUpAction(
                    action_type="add_task",
                    reason=gap.description,
                    description="Retry adverse media search to improve public-reporting coverage.",
                    target_agent="social_graph_agent",
                    task_type="adverse_media",
                    candidate_tools=("gdelt",),
                    priority="medium",
                    metadata={"gap_area": gap.area},
                )
            )
        elif gap.area == "Sanctions / legal" and not _has_completed(context, "sanctions_screening"):
            actions.append(
                FollowUpAction(
                    action_type="add_task",
                    reason=gap.description,
                    description="Retry sanctions screening with legal/compliance tools.",
                    target_agent="legal_agent",
                    task_type="sanctions_screening",
                    candidate_tools=("ofac",),
                    priority="high",
                    metadata={"gap_area": gap.area},
                )
            )

    if context.get_discovered_entities():
        unseen = [
            entity
            for entity in context.get_discovered_entities()
            if entity.get("name")
        ]
        if unseen:
            top = unseen[0]
            actions.append(
                FollowUpAction(
                    action_type="open_question",
                    reason="A related entity or officer was discovered during investigation.",
                    description=f"Assess whether related party '{top['name']}' requires a separate investigation.",
                    priority="low",
                    metadata={"discovered_entity": top},
                )
            )

    if not actions and context.round_count >= 1:
        actions.append(
            FollowUpAction(
                action_type="stop",
                reason="Current evidence provides sufficient coverage for the bounded investigation.",
                description="Stop after this round because no additional follow-up task is justified.",
                priority="medium",
            )
        )

    ranked, policy_used, rationale = _rank_actions_with_llm(context, actions, llm_client=llm_client)
    context.record_policy_decision(
        policy_name="reflexion_policy",
        policy_used=policy_used,
        rationale=rationale,
        metadata={"candidate_action_count": len(actions)},
    )
    return ranked
