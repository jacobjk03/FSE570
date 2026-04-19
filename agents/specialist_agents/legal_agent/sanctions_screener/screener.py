"""
OFAC Sanctions Screener — screens entities against the US Treasury SDN list.

Data source: OFAC SDN XML (cached at data/raw/ofac/sdn.xml)
Pull/refresh with: python scripts/pull_ofac_sdn.py

Confidence: 0.90 — the SDN list is an authoritative government source.
Matches should be treated as flags for human review (false positives possible
due to name similarity), not as automatic disqualification.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import List, Optional

from osint_swarm.data_sources import ofac
from osint_swarm.entities import Entity, Evidence

from agents.lead_agent.context_manager import InvestigationContext
from agents.lead_agent.task_planner.types import SubTask
from app.investigation_errors import DataSourceError

OFAC_SEARCH_URL = "https://sanctionssearch.ofac.treas.gov/"
CONFIDENCE = 0.90


def screen(
    entity: Entity,
    task: SubTask,
    context: InvestigationContext,
    data_root: Optional[Path] = None,
) -> List[Evidence]:
    """
    Screen an entity against the OFAC SDN list.

    Returns:
    - One Evidence row per SDN match found (risk_category="legal", confidence=0.90)
    - One clean-result Evidence row if no matches (also confidence=0.90 — clean is still evidence)
    Raises DataSourceError if SDN data is unavailable or unreadable.
    """
    data_root = Path(data_root) if data_root else Path("data")
    sdn_path = data_root / "raw" / "ofac" / "sdn.xml"
    entity_id = entity.entity_id
    today = datetime.date.today().isoformat()

    if not sdn_path.exists():
        raise DataSourceError(
            f"OFAC SDN cache not found at {sdn_path}. Run: python scripts/pull_ofac_sdn.py."
        )

    # --- Parse SDN list ---
    try:
        entries = ofac.parse_sdn_entries(sdn_path)
    except ofac.OfacError as exc:
        raise DataSourceError(
            f"OFAC SDN parse error: {exc}. Re-download with: python scripts/pull_ofac_sdn.py."
        ) from exc

    # --- Search for entity ---
    matches = ofac.search_entries(entries, entity.name, aliases=list(entity.aliases))

    # --- No matches: clean result ---
    if not matches:
        return [Evidence(
            evidence_id=f"{entity_id}_ofac_clean",
            entity_id=entity_id,
            date=today,
            source_type="regulator_api",
            risk_category="legal",
            summary=(
                f"OFAC SDN screening: No matches found for '{entity.name}'. "
                f"Entity does not appear on the US Treasury Specially Designated Nationals list "
                f"({len(entries):,} entries screened)."
            ),
            source_uri=OFAC_SEARCH_URL,
            raw_location=str(sdn_path),
            confidence=CONFIDENCE,
            attributes={
                "sdn_matches": 0,
                "entries_screened": len(entries),
                "screened": True,
                "stub": False,
            },
        )]

    # --- Matches found: one Evidence row per match ---
    results: List[Evidence] = []
    for i, match in enumerate(matches):
        programs_str = ", ".join(match["programs"]) if match["programs"] else "Unknown"
        aka_str = (
            f" (also known as: {', '.join(match['aka_names'][:3])})"
            if match["aka_names"]
            else ""
        )
        results.append(Evidence(
            evidence_id=f"{entity_id}_ofac_match_{match['uid']}",
            entity_id=entity_id,
            date=today,
            source_type="regulator_api",
            risk_category="legal",
            summary=(
                f"⚠ OFAC SDN MATCH [{i + 1}/{len(matches)}]: '{match['name']}'{aka_str} "
                f"— SDN Type: {match['sdn_type']} — Programs: {programs_str}. "
                f"Requires immediate compliance review."
            ),
            source_uri=OFAC_SEARCH_URL,
            raw_location=str(sdn_path),
            confidence=CONFIDENCE,
            attributes={
                "sdn_uid": match["uid"],
                "sdn_name": match["name"],
                "sdn_type": match["sdn_type"],
                "programs": match["programs"],
                "aka_names": match["aka_names"][:5],
                "remarks": match["remarks"][:200] if match["remarks"] else "",
                "sdn_matches": len(matches),
                "screened": True,
                "stub": False,
            },
        ))
    return results


# Keep run_stub as a named alias so old imports don't break during transition.
def run_stub(
    entity: Entity,
    task: SubTask,
    context: InvestigationContext,
) -> List[Evidence]:
    return screen(entity, task, context, data_root=None)
