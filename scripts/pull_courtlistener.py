"""
Pull and cache CourtListener court dockets for registered entities.

Source: https://www.courtlistener.com/api/rest/v4/
  - Free, no API key required (optional token for higher rate limits)
  - Cache path: data/raw/courtlistener/dockets_<slug>.json

Usage:
    python scripts/pull_courtlistener.py --entity-id tesla_inc_cik_0001318605
    python scripts/pull_courtlistener.py --entity-id ford_motor_cik_0000037996
    python scripts/pull_courtlistener.py --entity-id boeing_cik_0000012927
    python scripts/pull_courtlistener.py --all       # pull all registered entities

Optional .env key (free account):
    COURTLISTENER_API_TOKEN=<token>   # https://www.courtlistener.com/sign-in/

No token needed for the demo — anonymous rate limit is enough for a few entities.
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
from osint_swarm.data_sources.courtlistener import (
    CourtListenerError,
    cache_dockets_json,
    fetch_dockets,
    slug_for_entity_name,
)


def pull_entity(entity, data_root: Path, max_results: int = 20) -> None:
    slug = slug_for_entity_name(entity.name)
    cache_dir = data_root / "raw" / "courtlistener"
    cache_path = cache_dir / f"dockets_{slug}.json"

    print(f"\n{'─'*55}")
    print(f"Entity  : {entity.name} ({entity.entity_id})")
    print(f"Query   : \"{entity.name}\"")
    print(f"Cache   : {cache_path}")

    try:
        payload = fetch_dockets(entity.name, max_results=max_results)
    except CourtListenerError as exc:
        print(f"  ERROR : {exc}")
        return

    dockets = payload.get("dockets", [])
    total = payload.get("total_found", 0)

    out_path = cache_dockets_json(slug, payload, cache_dir)
    print(f"  Total found (API): {total:,}  |  Cached: {len(dockets)} dockets → {out_path}")

    if dockets:
        print("  Top 3 cases:")
        for d in dockets[:3]:
            status = "closed" if d.get("date_terminated") else "ongoing"
            print(f"    [{status}] {d.get('case_name', '?')} | {d.get('docket_number', '')} | filed {d.get('date_filed', '?')}")
    else:
        print("  No court dockets found (entity may not appear in CourtListener).")


def main() -> None:
    ap = argparse.ArgumentParser(description="Pull CourtListener dockets for entities")
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--entity-id", help="Entity ID from ENTITY_REGISTRY")
    grp.add_argument("--all", action="store_true", help="Pull all registered entities")
    ap.add_argument("--data-root", type=Path, default=ROOT / "data")
    ap.add_argument("--max-results", type=int, default=20)
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
        pull_entity(entity, args.data_root, max_results=args.max_results)

    print(f"\n{'─'*55}")
    print("Done. Run the investigation with:")
    print("  python scripts/run_lead_agent.py 'Investigate Tesla for money laundering'")


if __name__ == "__main__":
    main()
