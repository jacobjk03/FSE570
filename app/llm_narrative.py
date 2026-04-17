"""
LLM-powered narrative synthesis using Groq (Llama 3).

Generates a concise analyst-style summary from structured pipeline results.
Gracefully degrades to None if GROQ_API_KEY is not set or the call fails.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional


_MODEL = "llama-3.1-8b-instant"


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
        "You are a financial crime intelligence analyst. Based on the structured OSINT investigation "
        "results below, write a concise 3-4 sentence analyst narrative. Be factual, cautious, and "
        "evidence-grounded. Do NOT make legal conclusions. Reference specific numbers from the data.\n\n"
        "INVESTIGATION DATA:\n"
        f"- Entity: {entity}\n"
        f"- Total findings: {findings} (citation rate: {citation_pct})\n"
        f"- Overall risk score: {risk_str}\n"
        f"- Top risk categories: {top_cats_str}\n"
        f"- Data sources: {sources_used}\n"
        f"- Adverse media: {gdelt_rel}/{gdelt_total} articles ({gdelt_pct}%) flagged as highly relevant\n"
        f"- Coverage gaps: {gap_areas}\n"
        f"- Cross-check conflicts: {len(conflicts)}\n\n"
        "Write only the analyst narrative — no headers, no bullet points. Begin with the entity name."
    )


def generate_llm_narrative(result: Dict[str, Any]) -> Optional[str]:
    """
    Call Groq Llama to produce an LLM-generated analyst narrative.
    Returns None if GROQ_API_KEY is missing or the call fails.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None

    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        prompt = _build_prompt(result)
        response = client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.3,
        )
        text = response.choices[0].message.content
        return text.strip() if text else None
    except Exception as e:
        import sys
        print(f"[llm_narrative] ERROR: {e}", file=sys.stderr)
        return None
