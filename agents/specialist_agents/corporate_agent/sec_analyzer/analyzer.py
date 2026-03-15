"""SEC Analyzer: ingest SEC-derived evidence and surface governance/regulatory red flags."""

from __future__ import annotations

from typing import List

from osint_swarm.entities import Evidence


def summarize_governance_red_flags(evidence: List[Evidence], entity_id: str) -> List[Evidence]:
    """
    Add a summary Evidence row for governance red flags from SEC evidence.

    Counts SEC filings and 8-K executive events.
    """
    if not evidence:
        return []
    sec_count = sum(1 for e in evidence if e.source_type == "sec_filing")
    eight_k = [e for e in evidence if e.source_type == "sec_filing" and e.attributes.get("form") == "8-K"]
    summary = (
        f"Governance summary: {sec_count} SEC filing(s). "
        f"Executive turnover / material events (8-K): {len(eight_k)}."
    )
    summary_ev = Evidence(
        evidence_id=f"{entity_id}_corporate_summary",
        entity_id=entity_id,
        date=evidence[0].date if evidence else "",
        source_type="other",
        risk_category="governance",
        summary=summary,
        source_uri="",
        raw_location=None,
        confidence=0.85,
        attributes={"sec_count": sec_count, "eight_k_count": len(eight_k)},
    )
    return [summary_ev]
