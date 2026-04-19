"""
Structure Mapper: map corporate networks, beneficial ownership via OpenCorporates.

Uses cached OpenCorporates data (from scripts/pull_opencorporates.py) to produce
Evidence rows for officers, controlling entities, UBOs, and corporate groupings.
Falls back gracefully when the cache is missing or the API token is not set.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from osint_swarm.entities import Entity, Evidence

from agents.lead_agent.context_manager import InvestigationContext
from agents.lead_agent.task_planner.types import SubTask
from app.investigation_errors import DataSourceError


def map_structure(
    entity: Entity,
    task: SubTask,
    context: InvestigationContext,
    data_root: Optional[Path] = None,
) -> List[Evidence]:
    """
    Produce beneficial-ownership / corporate-structure Evidence from OpenCorporates.

    Strategy (cache-first):
    1. Check for cached OpenCorporates data under data/raw/opencorporates/oc_<slug>.json
    2. If cache exists → convert to Evidence (officers, UBOs, controlling entity, groupings)
    3. If cache missing → attempt a live API call (requires OPENCORPORATES_API_TOKEN)
    4. If live call fails (no token or rate-limited) → raise DataSourceError
    """
    from osint_swarm.data_sources.opencorporates import (
        OpenCorporatesError,
        cache_company_json,
        company_detail_to_evidence,
        fetch_company_detail,
        load_cached_company,
        search_companies,
        slug_for_entity_name,
    )

    root = Path(data_root) if data_root else Path("data")
    cache_dir = root / "raw" / "opencorporates"
    slug = slug_for_entity_name(entity.name)
    raw_location = str(cache_dir / f"oc_{slug}.json")

    # 1. Try cache
    cached = load_cached_company(slug, cache_dir)
    if cached and cached.get("detail"):
        return company_detail_to_evidence(
            cached["detail"],
            entity.entity_id,
            entity.name,
            raw_location=raw_location,
        )

    # 2. Try live API
    try:
        search_result = search_companies(entity.name, max_results=5)
        companies = search_result.get("companies", [])
        if not companies:
            return []

        best = companies[0]
        for c in companies:
            if not c.get("inactive") and c.get("current_status", "").lower() in ("active", "active/compliance"):
                best = c
                break

        jc = best.get("jurisdiction_code", "")
        cn = best.get("company_number", "")
        if not jc or not cn:
            return []

        detail = fetch_company_detail(jc, cn)

        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_company_json(slug, {"search": search_result, "detail": detail}, cache_dir)

        return company_detail_to_evidence(
            detail, entity.entity_id, entity.name, raw_location=raw_location,
        )

    except OpenCorporatesError as exc:
        raise DataSourceError(
            "OpenCorporates data unavailable (API token missing, unavailable, or rate-limited). "
            "Set OPENCORPORATES_API_TOKEN in .env and run: python scripts/pull_opencorporates.py --all."
        ) from exc


# Preserve backward-compatible alias
run_stub = map_structure
