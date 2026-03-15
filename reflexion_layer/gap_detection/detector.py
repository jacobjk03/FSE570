"""Gap detection: identify missing information from investigation context."""

from __future__ import annotations

from typing import TYPE_CHECKING, List

from reflexion_layer.gap_detection.types import Gap

if TYPE_CHECKING:
    from agents.lead_agent.context_manager import InvestigationContext


def detect_gaps(context: "InvestigationContext") -> List[Gap]:
    """
    Inspect investigation results and flag coverage gaps.

    Gaps are flagged when:
    - No entity was resolved
    - An agent returned no findings at all
    - An agent returned only stub placeholders (confidence == 0.0 and stub=True)
    - Beneficial ownership (structure mapper) returned a stub
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

    # Legal agent: sanctions + court records (still stubs — OFAC/CourtListener not yet integrated)
    legal_results = context.get_agent_results("legal_agent")
    if not legal_results:
        gaps.append(Gap(
            area="Sanctions / legal",
            description="Legal agent returned no findings.",
            suggested_follow_up="Integrate OFAC sanctions list and CourtListener API.",
        ))
    elif all(getattr(e, "attributes", {}).get("stub") for e in legal_results):
        gaps.append(Gap(
            area="Sanctions / legal",
            description="Sanctions screening and court records not yet integrated. Only stub placeholders returned.",
            suggested_follow_up="Integrate OFAC SDN list and CourtListener REST API.",
        ))

    # Social graph agent: GDELT is now integrated — only flag a gap if truly empty
    social_results = context.get_agent_results("social_graph_agent")
    if not social_results:
        gaps.append(Gap(
            area="Adverse media / network",
            description="Social graph agent returned no adverse media findings. GDELT cache may be missing.",
            suggested_follow_up="Run: python scripts/pull_gdelt_news.py --entity-id <entity_id>",
        ))

    # Corporate beneficial_ownership: structure_mapper stub still present
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
