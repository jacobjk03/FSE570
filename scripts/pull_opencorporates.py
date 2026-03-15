"""
Pull and cache OpenCorporates company data for registered entities.

Source: https://api.opencorporates.com/documentation/API-Reference
  - API key required (free tier: 200 req/month, 50/day)
  - Cache path: data/raw/opencorporates/oc_<slug>.json

Usage:
    python scripts/pull_opencorporates.py --entity-id tesla_inc_cik_0001318605
    python scripts/pull_opencorporates.py --entity-id ford_motor_cik_0000037996
    python scripts/pull_opencorporates.py --all       # pull all registered entities
    python scripts/pull_opencorporates.py --all --us-only  # restrict to US jurisdictions

Required .env key:
    OPENCORPORATES_API_TOKEN=<your-token>
    Get one free at: https://opencorporates.com/api_accounts/new
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for p in (ROOT, SRC):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from agents.lead_agent.entity_resolution.resolver import ENTITY_REGISTRY
from osint_swarm.data_sources.opencorporates import (
    OpenCorporatesError,
    cache_company_json,
    fetch_company_detail,
    search_companies,
    slug_for_entity_name,
)


def pull_entity(entity, data_root: Path, us_only: bool = False) -> None:
    slug = slug_for_entity_name(entity.name)
    cache_dir = data_root / "raw" / "opencorporates"
    cache_path = cache_dir / f"oc_{slug}.json"

    print(f"\n{'─'*60}")
    print(f"Entity  : {entity.name} ({entity.entity_id})")
    print(f"Cache   : {cache_path}")

    # Step 1: Search for the company
    jurisdiction = "us" if us_only else None
    try:
        search_result = search_companies(entity.name, jurisdiction_code=jurisdiction, max_results=5)
    except OpenCorporatesError as exc:
        print(f"  ERROR (search) : {exc}")
        return

    companies = search_result.get("companies", [])
    total = search_result.get("total_count", 0)
    print(f"  Search results : {total:,} total matches, showing top {len(companies)}")

    if not companies:
        print("  No matches found — caching empty result.")
        cache_company_json(slug, {"search": search_result, "detail": None}, cache_dir)
        return

    # Step 2: Pick the best match (first result by score, ideally active)
    best = companies[0]
    for c in companies:
        if not c.get("inactive") and c.get("current_status", "").lower() in ("active", "active/compliance"):
            best = c
            break

    jc = best.get("jurisdiction_code", "")
    cn = best.get("company_number", "")

    print(f"  Best match     : {best.get('name')} ({jc}/{cn})")
    print(f"  Status         : {best.get('current_status', 'unknown')}")
    print(f"  Incorporated   : {best.get('incorporation_date', 'unknown')}")

    # Step 3: Fetch full company detail
    if not jc or not cn:
        print("  ERROR: no jurisdiction/company_number — cannot fetch detail.")
        cache_company_json(slug, {"search": search_result, "detail": None}, cache_dir)
        return

    try:
        detail = fetch_company_detail(jc, cn)
    except OpenCorporatesError as exc:
        print(f"  ERROR (detail) : {exc}")
        cache_company_json(slug, {"search": search_result, "detail": None}, cache_dir)
        return

    # Cache the combined result
    payload = {
        "search": search_result,
        "detail": detail,
    }
    out_path = cache_company_json(slug, payload, cache_dir)

    officers = detail.get("officers") or []
    active = [o for o in officers if not o.get("end_date")]
    ctrl = detail.get("controlling_entity")
    ubos = detail.get("ultimate_beneficial_owners") or []
    groups = detail.get("corporate_groupings") or []
    prev_names = detail.get("previous_names") or []

    print(f"  Officers       : {len(officers)} total ({len(active)} current)")
    if officers:
        print("  Top officers   :")
        for o in officers[:5]:
            status = "current" if not o.get("end_date") else f"ended {o['end_date']}"
            print(f"    {o.get('name', '?')} — {o.get('position', '?')} ({status})")
    if ctrl:
        print(f"  Controlling    : {ctrl}")
    if ubos:
        print(f"  UBOs           : {len(ubos)}")
    if groups:
        print(f"  Corp. groups   : {', '.join(g.get('name', '?') for g in groups)}")
    if prev_names:
        print(f"  Previous names : {', '.join(pn.get('company_name', '?') for pn in prev_names[:3])}")

    print(f"  Cached         : {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Pull OpenCorporates data for entities")
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--entity-id", help="Entity ID from ENTITY_REGISTRY")
    grp.add_argument("--all", action="store_true", help="Pull all registered entities")
    ap.add_argument("--data-root", type=Path, default=ROOT / "data")
    ap.add_argument("--us-only", action="store_true", help="Restrict company search to US jurisdictions")
    args = ap.parse_args()

    if args.all:
        entities = ENTITY_REGISTRY
    else:
        entities = [e for e in ENTITY_REGISTRY if e.entity_id == args.entity_id]
        if not entities:
            print(f"ERROR: entity_id '{args.entity_id}' not found in ENTITY_REGISTRY.")
            print("Known IDs:", [e.entity_id for e in ENTITY_REGISTRY])
            sys.exit(1)

    for entity in entities:
        pull_entity(entity, args.data_root, us_only=args.us_only)

    print(f"\n{'─'*60}")
    print("Done. Verify cached data in: data/raw/opencorporates/")


if __name__ == "__main__":
    main()
