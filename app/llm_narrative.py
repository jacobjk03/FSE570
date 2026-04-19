"""
LLM-powered narrative synthesis using Groq (Llama 3).

Generates the strict final analyst narrative from structured pipeline results.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Tuple

from app.investigation_errors import FinalSynthesisError


_MODEL = "llama-3.1-8b-instant"
_REQUIRED_SECTIONS = (
    "Assessment",
    "EvidenceBasis",
    "WhyThisAssessment",
    "ConfidenceAndLimits",
    "NextActions",
)
_SECTION_KEYS = {name.lower(): name for name in _REQUIRED_SECTIONS}


def _build_prompt(result: Dict[str, Any]) -> str:
    entity = result.get("entity_name") or result.get("entity_id") or "Unknown Entity"
    findings = result.get("findings_count", 0)
    risk_scores = result.get("risk_scores") or {}
    overall_risk = risk_scores.get("overall")
    by_cat = risk_scores.get("by_risk_category") or {}
    gaps = result.get("gaps") or []
    conflicts = result.get("conflicts") or []
    gdelt_total = result.get("gdelt_total", 0)
    gdelt_rel = result.get("gdelt_relevant", 0)
    ds = result.get("findings_by_data_source") or {}
    eval_metrics = result.get("eval_metrics") or {}
    citation_rate = eval_metrics.get("citation_rate", 0)

    top_cats = sorted(by_cat.items(), key=lambda x: x[1], reverse=True)[:3]
    top_cats_str = ", ".join(f"{k} ({v:.2f})" for k, v in top_cats) if top_cats else "N/A"
    gap_areas = ", ".join(g.get("area", "") for g in gaps[:3]) if gaps else "none detected"
    gdelt_pct = round(100 * gdelt_rel / gdelt_total) if gdelt_total else 0
    sources_used = ", ".join(ds.keys()) if ds else "unknown"
    risk_str = f"{overall_risk:.2f}" if overall_risk is not None else "N/A"
    citation_pct = f"{citation_rate:.1%}" if citation_rate else "N/A"

    return (
        "You are the Final Analyst Narrative model for a financial-risk OSINT system.\n"
        "Write a beginner-friendly final answer for a first-time reviewer with no AML or OSINT background.\n\n"
        "You must:\n"
        "- Use ONLY provided metrics and source summaries.\n"
        "- Keep every section in short bullet points.\n"
        "- Use plain language and define each metric in simple terms.\n"
        "- Provide one clear final assessment statement (non-legal, non-criminal determination).\n"
        "- Explain why the assessment follows from evidence.\n"
        "- State uncertainty and limits explicitly.\n"
        "- End with concrete next actions.\n\n"
        "Output contract:\n"
        "- Use exactly these headings in order:\n"
        "Assessment\n"
        "EvidenceBasis\n"
        "WhyThisAssessment\n"
        "ConfidenceAndLimits\n"
        "NextActions\n"
        "- Under EACH heading, provide bullet points only (start each line with '-' ).\n"
        "- Include plain-language definitions for:\n"
        "  - citation rate\n"
        "  - overall risk score\n"
        "  - conflicts\n"
        "  - coverage gaps\n"
        "- Include one bullet containing the exact phrase: 'What this means for you'.\n"
        "- No fabricated facts or sources.\n"
        "- No legal conclusions.\n\n"
        "INVESTIGATION DATA:\n"
        f"- Entity: {entity}\n"
        f"- Total findings: {findings} (citation rate: {citation_pct})\n"
        f"- Overall risk score: {risk_str}\n"
        f"- Top risk categories: {top_cats_str}\n"
        f"- Data sources: {sources_used}\n"
        f"- Adverse media: {gdelt_rel}/{gdelt_total} articles ({gdelt_pct}%) flagged as highly relevant\n"
        f"- Coverage gaps: {gap_areas}\n"
        f"- Cross-check conflicts: {len(conflicts)}\n"
    )


def _normalize_heading(line: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "", line.lower())
    return _SECTION_KEYS.get(cleaned, "")


def _is_bullet(line: str) -> bool:
    return bool(re.match(r"^\s*(?:[-*]\s+|\d+[.)]\s+)", line))


def parse_narrative_sections(text: str) -> Dict[str, List[str]]:
    sections: Dict[str, List[str]] = {name: [] for name in _REQUIRED_SECTIONS}
    current = ""
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading = _normalize_heading(line.replace("##", "").rstrip(":").strip())
        if heading:
            current = heading
            continue
        if current:
            if _is_bullet(line):
                sections[current].append(re.sub(r"^\s*(?:[-*]\s+|\d+[.)]\s+)", "", line).strip())
            elif sections[current]:
                sections[current][-1] = f"{sections[current][-1]} {line}".strip()
            else:
                sections[current].append(line)
    return sections


def _validate_required_sections(text: str) -> Tuple[bool, str]:
    sections = parse_narrative_sections(text)
    for section in _REQUIRED_SECTIONS:
        if not sections.get(section):
            return False, section
    return True, ""


def _validate_bullet_contract(text: str) -> Tuple[bool, str]:
    lines = (text or "").splitlines()
    current = ""
    saw_bullet: Dict[str, bool] = {name: False for name in _REQUIRED_SECTIONS}
    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped:
            continue
        heading = _normalize_heading(stripped.replace("##", "").rstrip(":").strip())
        if heading:
            current = heading
            continue
        if current and _is_bullet(raw_line):
            saw_bullet[current] = True

    for section in _REQUIRED_SECTIONS:
        if not saw_bullet.get(section, False):
            return False, section
    return True, ""


def _validate_metric_definitions(text: str) -> Tuple[bool, str]:
    lowered = (text or "").lower()
    required_terms = (
        "citation rate",
        "overall risk score",
        "conflicts",
        "coverage gaps",
        "what this means for you",
    )
    for term in required_terms:
        if term not in lowered:
            return False, term
    return True, ""


def generate_llm_narrative(result: Dict[str, Any]) -> str:
    """
    Call Groq Llama to produce an LLM-generated analyst narrative.
    Returns strict narrative text, otherwise raises FinalSynthesisError.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise FinalSynthesisError("final synthesis failed: GROQ_API_KEY is not set")

    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        prompt = _build_prompt(result)
        messages = [{"role": "user", "content": prompt}]
        last_narrative = ""
        for _ in range(2):
            response = client.chat.completions.create(
                model=_MODEL,
                messages=messages,
                max_tokens=650,
                temperature=0.2,
            )
            text = response.choices[0].message.content
            if not text or not text.strip():
                raise FinalSynthesisError("final synthesis failed: empty LLM response")
            narrative = text.strip()
            last_narrative = narrative
            ok_sections, missing_section = _validate_required_sections(narrative)
            ok_bullets, bad_bullet_section = _validate_bullet_contract(narrative)
            ok_terms, missing_term = _validate_metric_definitions(narrative)
            if ok_sections and ok_bullets and ok_terms:
                return narrative
            messages = [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": narrative},
                {
                    "role": "user",
                    "content": (
                        "Your previous answer violated the required section contract. "
                        f"section_ok={ok_sections}, bullets_ok={ok_bullets}, metric_terms_ok={ok_terms}. "
                        f"missing_section={missing_section or 'none'}, bullet_section={bad_bullet_section or 'none'}, missing_term={missing_term or 'none'}. "
                        "Rewrite from scratch and output only these exact headings in order with bullet lines under each heading:\n"
                        "Assessment\nEvidenceBasis\nWhyThisAssessment\nConfidenceAndLimits\nNextActions\n"
                        "Also include beginner explanations for citation rate, overall risk score, conflicts, coverage gaps, and one bullet with 'What this means for you'."
                    ),
                },
            ]
        ok, missing = _validate_required_sections(last_narrative)
        if not ok:
            raise FinalSynthesisError(f"final synthesis missing required section '{missing}'")
        ok, bad_section = _validate_bullet_contract(last_narrative)
        if not ok:
            raise FinalSynthesisError(f"final synthesis missing bullets under section '{bad_section}'")
        ok, missing_term = _validate_metric_definitions(last_narrative)
        if not ok:
            raise FinalSynthesisError(f"final synthesis missing required metric explanation '{missing_term}'")
        return last_narrative
    except FinalSynthesisError:
        raise
    except Exception as e:
        raise FinalSynthesisError(f"final synthesis request failed: {e}") from e
