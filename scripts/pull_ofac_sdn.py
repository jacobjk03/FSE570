"""
Download and cache the OFAC SDN (Specially Designated Nationals) XML list.

Source: https://www.treasury.gov/ofac/downloads/sdn.xml
  - Free, no authentication or API key required
  - ~2-3 MB XML file, updated on US Treasury business days
  - Cache path: data/raw/ofac/sdn.xml

Usage:
    python scripts/pull_ofac_sdn.py              # download / refresh
    python scripts/pull_ofac_sdn.py --stats      # show entry counts after download

Run this once before running any sanctions screening, and periodically to refresh.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for p in (ROOT, SRC):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from osint_swarm.data_sources.ofac import download_sdn_xml, parse_sdn_entries


def main() -> None:
    ap = argparse.ArgumentParser(description="Download OFAC SDN XML to data/raw/ofac/sdn.xml")
    ap.add_argument("--data-root", type=Path, default=ROOT / "data")
    ap.add_argument("--stats", action="store_true", help="Print entry count breakdown after download")
    args = ap.parse_args()

    cache_path = args.data_root / "raw" / "ofac" / "sdn.xml"
    user_agent = os.environ.get("SEC_USER_AGENT", "OSINT-Swarm research@asu.edu")

    print(f"Downloading OFAC SDN list from US Treasury...")
    print(f"  URL: https://www.treasury.gov/ofac/downloads/sdn.xml")
    print(f"  Cache: {cache_path}")

    download_sdn_xml(cache_path, user_agent=user_agent)
    size_kb = cache_path.stat().st_size // 1024
    print(f"  Done — {size_kb} KB written")

    if args.stats:
        print("\nParsing for stats...")
        entries = parse_sdn_entries(cache_path)
        by_type: dict = {}
        for e in entries:
            t = e["sdn_type"] or "Unknown"
            by_type[t] = by_type.get(t, 0) + 1
        print(f"  Total SDN entries: {len(entries)}")
        for t, count in sorted(by_type.items(), key=lambda x: -x[1]):
            print(f"    {t}: {count}")

    print("\nDone. Run sanctions screening with:")
    print("  python scripts/run_lead_agent.py 'Investigate Tesla for money laundering'")


if __name__ == "__main__":
    main()
