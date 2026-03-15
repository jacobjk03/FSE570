"""
Build evidence CSV for Tesla, Inc.

This script is a thin wrapper around the generic build_evidence.py.
Kept for backwards compatibility so existing docs/README commands still work.

Preferred usage (works for any entity):
    python scripts/build_evidence.py --entity-id tesla_inc_cik_0001318605

Legacy usage (this file):
    python scripts/build_evidence_tesla.py

Prerequisites:
    python scripts/pull_sec_submissions.py --cik 0001318605
    python scripts/pull_gdelt_news.py --entity-id tesla_inc_cik_0001318605
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for p in (ROOT, SRC):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# Delegate entirely to the generic builder
sys.argv = ["build_evidence.py", "--entity-id", "tesla_inc_cik_0001318605"]

from scripts.build_evidence import main  # noqa: E402

if __name__ == "__main__":
    main()
