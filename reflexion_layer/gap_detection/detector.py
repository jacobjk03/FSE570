"""Gap detection: identify missing information from investigation context."""

from __future__ import annotations

from typing import TYPE_CHECKING, List

from reflexion_layer.gap_detection.types import Gap

if TYPE_CHECKING:
    from agents.lead_agent.context_manager import InvestigationContext


def _legal_has_real_screening(results: list) -> bool:
    """
    Return True if the legal agent performed a real screening
    (OFAC or CourtListener) — at least one result with screened=True and confidence > 0.
    """
    return any(
        getattr(e, "attributes", {}).get("screened") and e.confidence > 0
        for e in results
    )


def detect_gaps(context: "InvestigationContext") -> List[Gap]:
    """
    Inspect investigation results and flag coverage gaps.

    Gaps are flagged when:
    - No entity was resolved
    - Legal agent returned no findings, only old stubs, or cache-missing fallbacks
    - Social graph agent returned no findings (GDELT cache missing)
    - Beneficial ownership (structure_mapper) returned a stub
    """
    gaps: List[Gap] = []
    if not context.get_entity():
        gaps.append(
            Gap(
                area="entity_resolution",
                description="No entity resolved from query.",
                suggested_follow_up="Rephrase query with a known entity name or identifier.",
            )
        )
        return gaps

    # --- Legal agent: OFAC sanctions ---
    legal_results = context.get_agent_results("legal_agent")
    if not legal_results:
        gaps.append(Gap(
            area="Sanctions / legal",
            description="Legal agent returned no findings.",
            suggested_follow_up=(
                "Ensure OFAC SDN cache exists: python scripts/pull_ofac_sdn.py"
            ),
        ))
    elif not _legal_has_real_screening(legal_results):
        # Either old stub placeholders or cache-missing fallback (confidence=0)
        cache_missing = any(
            getattr(e, "attributes", {}).get("cache_missing") for e in legal_results
        )
        if cache_missing:
            gaps.append(Gap(
                area="Sanctions / legal",
                description="OFAC SDN cache not found. Sanctions screening was not performed.",
                suggested_follow_up="Run: python scripts/pull_ofac_sdn.py — then re-run investigation.",
            ))
        else:
            gaps.append(Gap(
                area="Sanctions / legal",
                description="Sanctions screening returned only placeholder data (not yet integrated).",
                suggested_follow_up="Run: python scripts/pull_ofac_sdn.py to enable real OFAC screening.",
            ))

    # --- Social graph agent: GDELT adverse media ---
    social_results = context.get_agent_results("social_graph_agent")
    if not social_results:
        gaps.append(Gap(
            area="Adverse media / network",
            description="Social graph agent returned no adverse media findings. GDELT cache may be missing.",
            suggested_follow_up="Run: python scripts/pull_gdelt_news.py --entity-id <entity_id>",
        ))

    # --- Corporate: beneficial ownership stub ---
    corp_results = context.get_agent_results("corporate_agent")
    if any("structure_mapper" in e.evidence_id and e.attributes.get("stub") for e in corp_results):
        gaps.append(
            Gap(
                area="beneficial_ownership",
                description="Beneficial ownership / structure mapping not yet integrated (OpenCorporates planned).",
                suggested_follow_up="Integrate OpenCorporates API for corporate network data.",
            )
        )

    return gaps
