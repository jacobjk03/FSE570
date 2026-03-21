"""
Synthesis / 'verdict' report: aggregates all pipeline outputs into an analyst-style summary.

This is a **deterministic synthesis layer** (rule-based), not a generative LLM — it behaves like an
agent that has already consumed the structured result dict and issues a cautious, evidence-grounded
assessment. Wording avoids legal conclusions; it describes **what the data supports** and **what is missing**.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.investigation_narrative import _format_bold


def _tier_for_result(
    entity_id: Any,
    findings: int,
    gaps: List[Dict[str, Any]],
    ds: Dict[str, Any],
) -> Tuple[str, str, str]:
    """
    Returns (tier_id, short_label, css_modifier).
    css_modifier: success | warning | danger | neutral
    """
    if not entity_id:
        return ("unresolved_entity", "Entity not resolved", "danger")

    gap_areas = {str(g.get("area") or "").lower() for g in gaps}
    has_bo_gap = "beneficial_ownership" in gap_areas
    has_ofac_gap = any("sanction" in a or "legal" in a for a in gap_areas)
    has_gdelt_gap = any("adverse" in a or "network" in a for a in gap_areas)

    if findings < 5:
        return ("limited_evidence", "Limited evidence retrieved", "warning")

    # Substantial record but known coverage holes
    if findings >= 50 and (has_bo_gap or (len(gaps) >= 2 and (has_ofac_gap or has_gdelt_gap))):
        return ("substantial_with_gaps", "Substantial record — coverage gaps", "warning")

    if findings >= 50:
        return ("substantial_public_record", "Substantial public record", "success")

    if len(gaps) >= 1:
        return ("partial_coverage", "Partial coverage", "warning")

    return ("moderate_record", "Moderate record", "neutral")


def build_verdict_synthesis(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build agent-style synthesis. All strings may use **bold** markers; HTML fields are escaped.
    """
    query = (result.get("query") or "").strip()
    entity_name = result.get("entity_name")
    entity_id = result.get("entity_id")
    findings = int(result.get("findings_count") or 0)
    gaps: List[Dict[str, Any]] = result.get("gaps") or []
    conflicts: List[Dict[str, Any]] = result.get("conflicts") or []
    tasks: List[Dict[str, Any]] = result.get("tasks") or []
    risk_scores = result.get("risk_scores") or {}
    overall_risk = risk_scores.get("overall")
    ds = result.get("findings_by_data_source") or {}
    gdelt_total = int(result.get("gdelt_total") or 0)
    gdelt_rel = int(result.get("gdelt_relevant") or 0)
    n_conflicts = len(conflicts)
    summary_conflicts = any((c.get("dimension") or "") == "summary_consistency" for c in conflicts)

    tier_id, tier_label, tier_css = _tier_for_result(entity_id, findings, gaps, ds)

    # --- Headline "verdict" (one sentence, careful wording) ---
    if not entity_id:
        headline = (
            "**Synthesis:** No registered entity could be matched to this query, so **no entity-level verdict** "
            "is possible. Refine the query or add the company to the entity registry."
        )
    else:
        en = entity_name or entity_id
        headline = (
            f"**Synthesis:** For **{en}**, the swarm ingested **{findings}** citable findings from "
            f"**{len(tasks)}** orchestrated tasks. This constitutes **public-record intelligence only** — "
            "not a legal or compliance **determination**."
        )

    # --- Assessment paragraphs ---
    paragraphs: List[str] = []

    if entity_id:
        # Source coverage sentence
        parts = []
        if ds.get("sec_edgar"):
            parts.append(f"**{ds['sec_edgar']}** governance/disclosure-oriented rows from **SEC EDGAR**")
        if ds.get("gdelt"):
            parts.append(f"**{ds['gdelt']}** news articles via **GDELT**")
        if ds.get("courtlistener"):
            parts.append(f"**{ds['courtlistener']}** court docket references via **CourtListener**")
        if ds.get("ofac"):
            parts.append(f"**{ds['ofac']}** sanctions-screening related rows (**OFAC** pipeline)")
        if ds.get("opencorporates"):
            parts.append(f"**{ds['opencorporates']}** corporate-structure rows (**OpenCorporates**)")

        if parts:
            if len(parts) == 1:
                paragraphs.append(f"**Coverage:** The record includes {parts[0]}.")
            else:
                paragraphs.append(
                    "**Coverage:** The record includes "
                    + ", ".join(parts[:-1])
                    + f", and {parts[-1]}."
                )

        # Risk score interpretation (critical — user confusion)
        if overall_risk is not None:
            try:
                r = float(overall_risk)
                paragraphs.append(
                    f"**Score interpretation:** The dashboard’s **overall score ({r:.2f})** is the **mean source-confidence** "
                    "across findings (how trustworthy the *source type* is), **not** a calibrated AML guilt index. "
                    "High values often appear when **many SEC filings** are present at **0.85** confidence."
                )
            except (TypeError, ValueError):
                pass

        if gdelt_total:
            pct = round(100.0 * gdelt_rel / gdelt_total) if gdelt_total else 0
            paragraphs.append(
                f"**Adverse media:** **{gdelt_rel}** of **{gdelt_total}** GDELT articles ({pct}%) are **title-scored** "
                "as highly relevant; others are retained at lower weight for completeness."
            )

        if n_conflicts:
            if summary_conflicts:
                paragraphs.append(
                    f"**Cross-check:** **{n_conflicts}** reflexion flags were raised — mostly **same-calendar-day SEC filings** "
                    "with different one-line summaries. This is **expected** for active issuers and **does not** by itself indicate fraud."
                )
            else:
                paragraphs.append(
                    f"**Cross-check:** **{n_conflicts}** consistency flags were raised; review the **Analysis** tab for detail."
                )

    # --- Key observation bullets ---
    bullets: List[str] = []
    if entity_id:
        bullets.append(
            f"**Entity locked:** **{entity_name or entity_id}** (`{entity_id}`) — downstream agents used this identity for all retrieval."
        )
        bullets.append(
            f"**Task depth:** **{len(tasks)}** sub-tasks executed (corporate, legal, network lanes per planner)."
        )
        if not gaps:
            bullets.append("**Gaps:** No automated coverage gaps were flagged for this run.")
        else:
            for g in gaps[:4]:
                area = g.get("area") or "unknown"
                desc = (g.get("description") or "")[:160]
                bullets.append(f"**Gap ({area}):** {desc}{'…' if len(g.get('description') or '') > 160 else ''}")
            if len(gaps) > 4:
                bullets.append(f"**…** plus **{len(gaps) - 4}** additional gap(s) — see **Analysis** tab.")

        if query:
            bullets.append(
                f"**Query focus:** Your question (“{query[:100]}{'…' if len(query) > 100 else ''}”) **shaped task selection**, "
                "not a binary **verdict** output."
            )

    # --- Closing caveat (always) ---
    caveat = (
        "**Analyst note:** This synthesis is **machine-aggregated** from public OSINT. It **must** be validated by a "
        "qualified human, internal policy, and (where required) legal/compliance review. **No automated system can issue "
        "a regulatory or criminal verdict.**"
    )

    return {
        "tier_id": tier_id,
        "tier_label": tier_label,
        "tier_css": tier_css,
        "headline": headline,
        "headline_html": _format_bold(headline),
        "assessment_paragraphs": paragraphs,
        "assessment_paragraphs_html": [_format_bold(p) for p in paragraphs],
        "key_observations": bullets,
        "key_observations_html": [_format_bold(b) for b in bullets],
        "caveat": caveat,
        "caveat_html": _format_bold(caveat),
    }
