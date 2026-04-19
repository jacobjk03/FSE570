"""Model-guided action policy for specialist tool selection."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable, List, Optional, Sequence

from agents.lead_agent.task_planner.types import SubTask
from app.investigation_errors import ActionPolicyError

_MODEL = os.environ.get("ACTION_POLICY_MODEL", "llama-3.1-8b-instant")


def _extract_json(text: str) -> Dict[str, Any]:
    blob = (text or "").strip()
    if not blob:
        raise ValueError("empty action policy output")
    start = blob.find("{")
    end = blob.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no json object found")
    return json.loads(blob[start : end + 1])


def _build_prompt(
    *,
    agent_id: str,
    task: SubTask,
    available_tools: Sequence[str],
    used_tools: Sequence[str],
    context_snapshot: Dict[str, Any],
) -> str:
    payload = {
        "agent_id": agent_id,
        "task_type": task.task_type,
        "task_description": task.description,
        "task_priority": task.priority,
        "candidate_tools": list(task.candidate_tools),
        "available_tools": list(available_tools),
        "used_tools": list(used_tools),
        "round_count": context_snapshot.get("round_count", 0),
        "remaining_budget": context_snapshot.get("remaining_budget", 0),
        "recent_tool_results": context_snapshot.get("recent_tool_results", []),
        "open_questions": context_snapshot.get("open_questions", []),
    }
    return (
        "You are the Action Policy model for one step in a bounded OSINT investigation.\n"
        "Your job is to choose exactly one next tool call.\n\n"
        "You must:\n"
        "- Select one tool from available_tools that is not in used_tools.\n"
        "- Respect candidate_tools preference and task objective.\n"
        "- Optimize for highest expected information gain now.\n"
        "- Avoid low-yield repetition.\n\n"
        "Output contract:\n"
        "- Return VALID JSON ONLY with keys: selected_tool, alternatives, reasoning.\n"
        "- selected_tool may be null only if no valid tool exists.\n"
        "- alternatives must also be valid available tools.\n"
        "- No markdown or extra text outside JSON.\n\n"
        f"INPUT:\n{json.dumps(payload, ensure_ascii=True)}"
    )


def _call_llm(prompt: str) -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ActionPolicyError("action policy failed: GROQ_API_KEY is not set")
    try:
        from groq import Groq

        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=240,
            temperature=0.1,
        )
        content = response.choices[0].message.content
        if not content or not content.strip():
            raise ActionPolicyError("action policy failed: empty LLM response")
        return content.strip()
    except ActionPolicyError:
        raise
    except Exception as exc:
        raise ActionPolicyError(f"action policy LLM request failed: {exc}") from exc


def choose_next_tool(
    *,
    agent_id: str,
    task: SubTask,
    available_tools: Sequence[str],
    used_tools: Sequence[str],
    context_snapshot: Dict[str, Any],
    llm_client: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Choose the next bounded tool for a specialist agent.

    Uses strict LLM-only policy with schema validation.
    """
    if not available_tools:
        raise ActionPolicyError(f"action policy failed: no tools configured for agent '{agent_id}'")
    remaining_tools = [name for name in available_tools if name not in used_tools]

    prompt = _build_prompt(
        agent_id=agent_id,
        task=task,
        available_tools=available_tools,
        used_tools=used_tools,
        context_snapshot=context_snapshot,
    )
    def _parse_policy_output(text_blob: str) -> Dict[str, Any]:
        if not text_blob or not str(text_blob).strip():
            raise ActionPolicyError("action policy failed: empty policy output")
        try:
            raw = _extract_json(text_blob)
        except Exception as exc:
            raise ActionPolicyError(f"action policy returned invalid JSON: {exc}") from exc

        if "selected_tool" not in raw:
            raise ActionPolicyError("action policy output missing 'selected_tool'")
        selected = raw.get("selected_tool")
        selected = str(selected).strip() if selected is not None else None
        if selected is not None and (selected not in available_tools or selected in used_tools):
            raise ActionPolicyError(
                f"action policy selected invalid tool '{selected}' for available={list(available_tools)} used={list(used_tools)}"
            )

        remaining = [name for name in available_tools if name not in used_tools]
        if remaining and selected is None:
            raise ActionPolicyError("action policy returned null selected_tool while valid options remain")
        if not remaining and selected is not None:
            raise ActionPolicyError("action policy selected a tool even though no tools remain")

        alternatives = [str(item) for item in (raw.get("alternatives") or [])]
        invalid_alternatives = [name for name in alternatives if name not in available_tools or name == selected]
        if invalid_alternatives:
            raise ActionPolicyError(f"action policy returned invalid alternatives: {invalid_alternatives}")

        reasoning = str(raw.get("reasoning") or "").strip()
        if not reasoning:
            raise ActionPolicyError("action policy output missing reasoning")
        return {
            "selected_tool": selected,
            "alternatives": alternatives,
            "policy_used": "llm_action_policy",
            "reasoning": reasoning,
        }

    current_prompt = prompt
    last_error: Optional[ActionPolicyError] = None
    for _ in range(5):
        text = llm_client(current_prompt) if llm_client is not None else _call_llm(current_prompt)
        try:
            return _parse_policy_output(str(text))
        except ActionPolicyError as exc:
            last_error = exc
            if "null selected_tool while valid options remain" in str(exc):
                # Force a strict non-null repair pass when tools remain.
                current_prompt = (
                    f"{prompt}\n\n"
                    "Your previous output selected null while valid tools remain.\n"
                    f"remaining_tools={json.dumps(remaining_tools, ensure_ascii=True)}\n"
                    "Return ONLY VALID JSON with keys selected_tool, alternatives, reasoning.\n"
                    "Hard rules:\n"
                    "- selected_tool MUST be one of remaining_tools.\n"
                    "- selected_tool MUST NOT be null.\n"
                    "- alternatives may be empty but if provided they must be from available_tools and not equal selected_tool.\n"
                    "- No markdown, no prose outside JSON.\n"
                    "Example format only:\n"
                    '{"selected_tool":"one_remaining_tool_name","alternatives":[],"reasoning":"why this tool now"}'
                )
                continue
            current_prompt = (
                f"{prompt}\n\n"
                "Your previous output violated the strict policy contract.\n"
                f"Validation error: {exc}\n"
                f"remaining_tools={json.dumps(remaining_tools, ensure_ascii=True)}\n"
                "Return ONLY VALID JSON with keys selected_tool, alternatives, reasoning.\n"
                "selected_tool MUST be one of remaining_tools (or null only if remaining_tools is empty).\n"
                "If any valid tool remains, selected_tool MUST NOT be null.\n"
                "No markdown, no prose outside JSON."
            )
    assert last_error is not None
    raise last_error
