"""
Pull GDELT adverse media news for a registered entity and cache to data/raw/gdelt/.

Usage:
    python scripts/pull_gdelt_news.py --entity-id tesla_inc_cik_0001318605
    python scripts/pull_gdelt_news.py --entity-id ford_motor_cik_0000037996
    python scripts/pull_gdelt_news.py --entity-id boeing_cik_0000012927

The results are cached to data/raw/gdelt/news_<slug>.json.
Re-run at any time to refresh (GDELT updates continuously).

No authentication required — GDELT is free and public.
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

from osint_swarm.data_sources.gdelt import cache_news_json, fetch_news_for_entity


def main() -> None:
    from agents.lead_agent.entity_resolution.resolver import ENTITY_REGISTRY
    registry_map = {e.entity_id: e for e in ENTITY_REGISTRY}

    ap = argparse.ArgumentParser(description="Fetch GDELT adverse media news for a registered entity.")
    ap.add_argument(
        "--entity-id",
        required=True,
        help=f"Entity ID from registry. Available: {list(registry_map.keys())}",
    )
    ap.add_argument(
        "--max-records",
        type=int,
        default=100,
        help="Max articles to fetch (GDELT caps at 250, default: 100)",
    )
    ap.add_argument(
        "--data-root",
        type=Path,
        default=ROOT / "data",
    )
    args = ap.parse_args()

    entity = registry_map.get(args.entity_id)
    if not entity:
        raise SystemExit(
            f"Unknown entity_id: {args.entity_id!r}\n"
            f"Available: {list(registry_map.keys())}"
        )

    cache_dir = args.data_root / "raw" / "gdelt"
    slug = entity.name.lower().split(",")[0].strip().replace(" ", "_").replace(".", "")

    print(f"Fetching GDELT news for: {entity.name!r}")
    print(f"Query includes risk keywords: fraud, investigation, penalty, fine, ...")

    payload = fetch_news_for_entity(entity.name, max_records=args.max_records)
    out_path = cache_news_json(slug, payload, cache_dir)

    n = payload.get("total_returned", 0)
    print(f"Fetched {n} articles")
    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()
