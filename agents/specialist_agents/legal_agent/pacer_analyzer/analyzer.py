"""
CourtListener court records analyzer.

Replaces the former PACER stub. PACER itself is paywalled ($0.10/page), but
CourtListener (Free Law Project) mirrors PACER content for free and exposes
a REST API — making US federal court dockets publicly accessible.

Source: https://www.courtlistener.com/api/rest/v4/
  - Free, no auth required for basic searches
  - Optional: set COURTLISTENER_API_TOKEN in .env for higher rate limits
  - Cache: data/raw/courtlistener/dockets_<slug>.json

Confidence: 0.85 — court records are public, authoritative legal documents.

Workflow:
  1. Check for cached dockets JSON.
  2. If cache exists → load and convert to Evidence.
  3. If no cache → fetch live from CourtListener API → cache → convert.
  4. If fetch fails → return a single Evidence row with confidence=0.0 and
     a clear message telling the user to run pull_courtlistener.py.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import List, Optional

from osint_swarm.data_sources import courtlistener
from osint_swarm.entities import Entity, Evidence

from agents.lead_agent.context_manager import InvestigationContext
from agents.lead_agent.task_planner.types import SubTask

COURTLISTENER_HOME = "https://www.courtlistener.com/"
CONFIDENCE = 0.85


def fetch(
    entity: Entity,
    task: SubTask,
    context: InvestigationContext,
    data_root: Optional[Path] = None,
) -> List[Evidence]:
    """
    Fetch court dockets for an entity from CourtListener.

    Returns:
    - One Evidence row per docket found (risk_category="legal", confidence=0.85)
    - One clean-result Evidence row if no dockets found (also confidence=0.85)
    - One fallback Evidence row on API error (confidence=0.0)
    """
    data_root = Path(data_root) if data_root else Path("data")
    cache_dir = data_root / "raw" / "courtlistener"
    entity_id = entity.entity_id
    today = datetime.date.today().isoformat()
    slug = courtlistener.slug_for_entity_name(entity.name)

    # --- Try cache first ---
    cached = courtlistener.load_cached_dockets(slug, cache_dir)
    raw_location = str(cache_dir / f"dockets_{slug}.json")

    if cached is not None:
        payload = cached
    else:
        # --- Live fetch and cache ---
        try:
            payload = courtlistener.fetch_dockets(entity.name)
            cache_dir.mkdir(parents=True, exist_ok=True)
            courtlistener.cache_dockets_json(slug, payload, cache_dir)
        except courtlistener.CourtListenerError as exc:
            return [Evidence(
                evidence_id=f"{entity_id}_courtlistener_error",
                entity_id=entity_id,
                date=today,
                source_type="court_record",
                risk_category="legal",
                summary=(
                    f"CourtListener fetch failed: {exc}. "
                    "Pre-fetch with: python scripts/pull_courtlistener.py "
                    f"--entity-id {entity_id}"
                ),
                source_uri=COURTLISTENER_HOME,
                raw_location=None,
                confidence=0.0,
                attributes={"stub": False, "fetch_error": True},
            )]

    dockets = payload.get("dockets") or []
    total_found = payload.get("total_found") or len(dockets)

    # --- No dockets: clean result ---
    if not dockets:
        return [Evidence(
            evidence_id=f"{entity_id}_courtlistener_clean",
            entity_id=entity_id,
            date=today,
            source_type="court_record",
            risk_category="legal",
            summary=(
                f"CourtListener search: No court dockets found for '{entity.name}'. "
                f"Entity does not appear as a party in CourtListener's database "
                f"(total API result count: {total_found})."
            ),
            source_uri=COURTLISTENER_HOME,
            raw_location=raw_location,
            confidence=CONFIDENCE,
            attributes={
                "court_records": 0,
                "total_found_api": total_found,
                "screened": True,
                "stub": False,
            },
        )]

    # --- Convert dockets to Evidence rows ---
    evidence = courtlistener.dockets_to_evidence_rows(
        dockets, entity_id, entity.name, raw_location=raw_location
    )

    # Prepend a summary row with counts, then the individual docket rows
    summary_ev = Evidence(
        evidence_id=f"{entity_id}_courtlistener_summary",
        entity_id=entity_id,
        date=today,
        source_type="court_record",
        risk_category="legal",
        summary=(
            f"CourtListener: {len(dockets)} court docket(s) found for '{entity.name}' "
            f"(API total: {total_found:,}). See individual evidence rows for case details."
        ),
        source_uri=COURTLISTENER_HOME,
        raw_location=raw_location,
        confidence=CONFIDENCE,
        attributes={
            "court_records": len(dockets),
            "total_found_api": total_found,
            "screened": True,
            "stub": False,
        },
    )

    return [summary_ev] + evidence


# Keep run_stub as a named alias so existing imports in tests/external code
# don't break. It now calls the real implementation with no data_root,
# which will attempt a live API fetch (or return a graceful fallback).
def run_stub(
    entity: Entity,
    task: SubTask,
    context: InvestigationContext,
) -> List[Evidence]:
    return fetch(entity, task, context, data_root=None)
