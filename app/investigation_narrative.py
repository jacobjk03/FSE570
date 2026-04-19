"""Human-readable summaries and definitions for investigation results (Flask UI)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from markupsafe import Markup, escape


def _format_bold(text: str) -> Markup:
    """Turn **segments** into <strong>; escape everything for HTML safety."""
    parts = re.split(r"(\*\*.+?\*\*)", text)
    chunks: List[str] = []
    for part in parts:
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            inner = escape(part[2:-2])
            chunks.append(f"<strong>{inner}</strong>")
        else:
            chunks.append(str(escape(part)))
    return Markup("".join(chunks))


def _has_summary_consistency_conflicts(conflicts: List[Dict[str, Any]]) -> bool:
    return any((c.get("dimension") or "") == "summary_consistency" for c in conflicts)


def build_investigation_narrative(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build structured copy for Overview + Explanation tabs.
    Uses only fields already on `result` (no re-fetch).
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

    agent_labels = sorted({(t.get("target_agent") or "").replace("_", " ").strip() for t in tasks if t.get("target_agent")})

    # --- Headline ---
    if not entity_id:
        headline = "No registered entity was resolved from your query."
    else:
        headline = (
            f"We analyzed **{entity_name or entity_id}** using {len(tasks)} specialist tasks "
            f"and collected **{findings}** citable findings from public OSINT sources."
        )

    # --- Executive paragraphs (markdown-lite: **bold** only) ---
    paragraphs: List[str] = []
    if entity_id:
        src_bits = []
        if ds.get("sec_edgar"):
            src_bits.append("SEC EDGAR filings")
        if ds.get("gdelt"):
            src_bits.append("GDELT news")
        if ds.get("ofac"):
            src_bits.append("OFAC sanctions screening")
        if ds.get("courtlistener"):
            src_bits.append("federal court dockets (CourtListener)")
        if src_bits:
            if len(src_bits) == 1:
                src_sentence = f"Evidence came from **{src_bits[0]}**."
            else:
                src_sentence = (
                    "Evidence came from **"
                    + "**, **".join(src_bits[:-1])
                    + f"**, and **{src_bits[-1]}**."
                )
            paragraphs.append(src_sentence)
        paragraphs.append(
            "This dashboard does **not** render a legal verdict. It aggregates **what appears in public records** "
            "with source-linked citations. Your query (e.g. money laundering) guides **which tasks run**, not a binary guilt score."
        )
    else:
        paragraphs.append(
            "Try a query that names a **registered company** (e.g. Tesla, Ford, Boeing), or add new entities in the resolver registry."
        )

    if overall_risk is not None and entity_id:
        try:
            r = float(overall_risk)
            paragraphs.append(
                f"The **overall risk score ({r:.2f})** is the **average confidence** of all findings — "
                "it reflects how much *trust we place in the source types*, not how severe a single event is. "
                "See the **Explanation** tab for details."
            )
        except (TypeError, ValueError):
            pass

    # --- What we did ---
    what_we_did: List[str] = []
    if entity_id:
        what_we_did.append(f"Resolved entity **{entity_name or entity_id}** (`{entity_id}`).")
    if tasks:
        what_we_did.append(f"Planned and ran **{len(tasks)}** sub-tasks across: {', '.join(agent_labels) or 'specialist agents'}.")
    what_we_did.append(f"Collected **{findings}** structured evidence rows (each with source metadata where available).")
    what_we_did.append("Applied **reflexion**: cross-check for same-day summary differences, gap detection, and confidence aggregation.")
    what_we_did.append("Built a **knowledge graph** linking the entity to evidence (sampled in the browser for performance).")

    # --- Takeaway ---
    takeaway_parts: List[str] = []
    if entity_id and findings:
        takeaway_parts.append("Review **gaps** for missing data (often API/cache), not proof of wrongdoing.")
        if _has_summary_consistency_conflicts(conflicts):
            takeaway_parts.append(
                "High **conflict** counts usually mean **multiple SEC filings on the same calendar day** with different summaries — expected, not errors."
            )
        if gaps:
            takeaway_parts.append("Address **coverage gaps** where expected data could not be retrieved in this run.")
        if gdelt_total and gdelt_rel < gdelt_total:
            takeaway_parts.append(
                f"**GDELT**: {gdelt_rel} of {gdelt_total} articles are title-scored as highly relevant; the rest may still be useful context."
            )
    takeaway = " ".join(takeaway_parts) if takeaway_parts else "Run an investigation on a resolved entity to see source-specific takeaways."

    # --- Explanation tab: definition cards ---
    definitions: List[Dict[str, str]] = [
        {
            "title": "Risk score vs. confidence",
            "body": (
                "**Confidence** (per finding) reflects **trust in the source** (e.g. SEC filing vs. news), on a 0–1 scale. "
                "**Overall risk score** on this dashboard is computed as the **mean of those confidences** across findings. "
                "So a high score often means **many high-trust sources**, not automatically “high criminal risk.” "
                "It is **not** a substitute for analyst judgment or legal advice."
            ),
        },
        {
            "title": "Why do so many values look like 0.85?",
            "body": (
                "Many rows share the same confidence because they share the **same source tier** (e.g. all SEC filings use one calibrated score). "
                "Future work could vary scores by filing type (8-K restatement vs. routine Form 4)."
            ),
        },
        {
            "title": "What are “Cross-check conflicts”?",
            "body": (
                "The reflexion layer flags groups of findings that share the **same entity and date** but **different short summaries**. "
                "For SEC data, **multiple material events on one day** (two 8-Ks, etc.) create many such flags. "
                "Treat this as **“worth a second look”**, not as 87 separate contradictions."
            ),
        },
        {
            "title": "What are “Coverage gaps”?",
            "body": (
                "Gaps mean **a source was expected but data was missing**, rate-limited, or not configured. "
                "A gap in beneficial ownership **does not** mean the company lacks owners — it means **the current run did not map them here**."
            ),
        },
        {
            "title": "GDELT signal rate",
            "body": (
                "**Signal rate** is the share of news articles whose **titles** match both the entity and risk-oriented keywords. "
                "Articles below that bar are **down-weighted** but kept so you do not lose peripheral context."
            ),
        },
    ]

    # --- Metric hints (short tooltips for stat cards) ---
    metric_hints = {
        "findings": "Structured evidence rows with citations. Count ≠ severity.",
        "tasks": "Sub-tasks dispatched to corporate, legal, and social-graph agents.",
        "gaps": "Missing or unavailable data for an expected source — fix config/cache, not panic.",
        "conflicts": "Same entity + date with differing summaries; often routine for SEC.",
        "runtime": "Wall time for this pipeline run on the server.",
    }

    definitions_html = [
        {"title": escape(d["title"]), "body": _format_bold(d["body"])}
        for d in definitions
    ]

    return {
        "headline": headline,
        "headline_html": _format_bold(headline),
        "executive_paragraphs": paragraphs,
        "executive_paragraphs_html": [_format_bold(p) for p in paragraphs],
        "what_we_did": what_we_did,
        "what_we_did_html": [_format_bold(w) for w in what_we_did],
        "definitions": definitions,
        "definitions_html": definitions_html,
        "takeaway": takeaway,
        "takeaway_html": _format_bold(takeaway),
        "metric_hints": metric_hints,
        "has_entity": bool(entity_id),
        "conflict_count": len(conflicts),
        "gap_count": len(gaps),
        "summary_consistency_note": _has_summary_consistency_conflicts(conflicts),
    }
