"""
Generic evidence builder — works for ANY entity in ENTITY_REGISTRY.

Data sources:
  1. SEC EDGAR  — governance filings (10-K, 8-K, DEF 14A, etc.)
  2. GDELT      — adverse media (news articles about fraud, investigation, etc.)

Usage:
    python scripts/build_evidence.py --entity-id tesla_inc_cik_0001318605
    python scripts/build_evidence.py --entity-id ford_motor_cik_0000037996
    python scripts/build_evidence.py --entity-id boeing_cik_0000012927

Prerequisites for each entity (run once, or to refresh):
    python scripts/pull_sec_submissions.py --cik <CIK>
    python scripts/pull_gdelt_news.py --entity-id <entity_id>

The script reads from data/raw/ (cached files only — no live network calls) and
writes to data/processed/<slug>/evidence_<slug>.csv.
If a raw file is missing it prints the exact pull command to run first.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from collections import Counter
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for p in (ROOT, SRC):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from osint_swarm.entities import Entity, Evidence
from osint_swarm.utils.io import read_json, write_csv_dicts

FIELDNAMES = [
    "evidence_id",
    "entity_id",
    "date",
    "source_type",
    "risk_category",
    "summary",
    "source_uri",
    "raw_location",
    "confidence",
    "attributes",
]

RISK_FORMS = {"8-K", "10-K", "10-Q", "DEF 14A", "SC 13G", "SC 13G/A", "SC 13D", "SC 13D/A", "4", "3", "5"}
FORM_RISK_CATEGORY: Dict[str, str] = {
    "8-K": "governance", "10-K": "governance", "10-Q": "governance",
    "DEF 14A": "governance", "4": "governance", "3": "governance", "5": "governance",
    "SC 13G": "network", "SC 13G/A": "network", "SC 13D": "network", "SC 13D/A": "network",
}


def build_sec_evidence(raw_path: Path, entity: Entity) -> List[Evidence]:
    """Build Evidence rows from a cached SEC submissions JSON file."""
    payload = read_json(raw_path)
    filings: Dict[str, Any] = (payload.get("filings") or {}).get("recent") or {}

    forms = filings.get("form") or []
    dates = filings.get("filingDate") or []
    accessions = filings.get("accessionNumber") or []
    primary_docs = filings.get("primaryDocument") or []
    descriptions = filings.get("primaryDocDescription") or []

    cik = entity.identifiers.get("cik", "")
    cik_int = int(cik) if cik.isdigit() else cik

    out: List[Evidence] = []
    for i, form in enumerate(forms):
        if form not in RISK_FORMS:
            continue
        date = dates[i] if i < len(dates) else ""
        accession = accessions[i] if i < len(accessions) else ""
        primary_doc = primary_docs[i] if i < len(primary_docs) else ""
        description = descriptions[i] if i < len(descriptions) else ""
        if not date or not accession:
            continue

        accession_clean = accession.replace("-", "")
        source_uri = (
            f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_clean}/{primary_doc}"
            if primary_doc
            else f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}"
        )
        ev_id = (
            f"{entity.entity_id}_sec_{form.lower().replace(' ', '_').replace('/', '_')}"
            f"_{date}_{accession_clean[:8]}"
        )
        risk_category = FORM_RISK_CATEGORY.get(form, "governance")
        summary = (
            f"{entity.name} filed a {form}"
            + (f" — {description}" if description else "")
            + f" on {date}."
        )
        out.append(
            Evidence(
                evidence_id=ev_id,
                entity_id=entity.entity_id,
                date=str(date)[:10],
                source_type="sec_filing",
                risk_category=risk_category,
                summary=summary.strip(),
                source_uri=source_uri,
                raw_location=str(raw_path),
                confidence=0.85,
                attributes={"form": form, "accession": accession, "description": description, "cik": cik},
            )
        )
    return out


def build_gdelt_evidence(raw_path: Path, entity: Entity) -> List[Evidence]:
    """Build Evidence rows from a cached GDELT news JSON file."""
    import hashlib
    payload = read_json(raw_path)
    articles = payload.get("articles") or []
    out: List[Evidence] = []

    for i, article in enumerate(articles):
        if not isinstance(article, dict):
            continue
        title = (article.get("title") or "").strip()
        url = (article.get("url") or "").strip()
        seen_date = (article.get("seendate") or "").strip()
        domain = (article.get("domain") or "").strip()
        language = (article.get("language") or "").strip()
        source_country = (article.get("sourcecountry") or "").strip()

        if not url or not title:
            continue

        date_str = ""
        if seen_date:
            raw = seen_date.replace("T", "").replace("Z", "").replace("-", "")
            if len(raw) >= 8:
                date_str = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"

        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
        slug = entity.entity_id.split("_")[0]
        ev_id = f"{slug}_gdelt_{url_hash}"

        out.append(
            Evidence(
                evidence_id=ev_id,
                entity_id=entity.entity_id,
                date=date_str,
                source_type="news_article",
                risk_category="network",
                summary=title[:5000],
                source_uri=url,
                raw_location=str(raw_path),
                confidence=0.6,
                attributes={
                    "domain": domain,
                    "language": language,
                    "source_country": source_country,
                    "gdelt_rank": i + 1,
                },
            )
        )
    return out


def get_entity_slug(entity: Entity) -> str:
    return entity.name.lower().split(",")[0].strip().replace(" ", "_").replace(".", "")


def main() -> None:
    from agents.lead_agent.entity_resolution.resolver import ENTITY_REGISTRY
    registry_map = {e.entity_id: e for e in ENTITY_REGISTRY}

    ap = argparse.ArgumentParser(description="Build evidence CSV for any registered entity.")
    ap.add_argument("--entity-id", required=True,
                    help=f"Entity ID. Available: {list(registry_map.keys())}")
    ap.add_argument("--data-root", type=Path, default=ROOT / "data")
    args = ap.parse_args()

    entity = registry_map.get(args.entity_id)
    if not entity:
        raise SystemExit(f"Unknown entity_id: {args.entity_id!r}\nAvailable: {list(registry_map.keys())}")

    data_root = args.data_root
    cik = entity.identifiers.get("cik")
    slug = get_entity_slug(entity)

    raw_sec = data_root / "raw" / "sec" / f"CIK{cik.zfill(10) if cik else ''}.json" if cik else None
    raw_gdelt = data_root / "raw" / "gdelt" / f"news_{slug}.json"

    missing_cmds: List[str] = []
    if cik and (raw_sec is None or not raw_sec.exists()):
        missing_cmds.append(f"  python scripts/pull_sec_submissions.py --cik {cik}")
    if not raw_gdelt.exists():
        missing_cmds.append(f"  python scripts/pull_gdelt_news.py --entity-id {entity.entity_id}")
    if missing_cmds:
        raise SystemExit(f"Missing raw data for {entity.name}. Run first:\n" + "\n".join(missing_cmds))

    evidence: List[Evidence] = []

    if cik and raw_sec and raw_sec.exists():
        sec_rows = build_sec_evidence(raw_sec, entity)
        evidence.extend(sec_rows)
        print(f"  SEC filings:    {len(sec_rows)} rows  ({raw_sec})")

    if raw_gdelt.exists():
        gdelt_rows = build_gdelt_evidence(raw_gdelt, entity)
        evidence.extend(gdelt_rows)
        print(f"  GDELT news:     {len(gdelt_rows)} rows  ({raw_gdelt})")

    if not evidence:
        raise SystemExit(f"No evidence built for {entity.name} — check raw data files.")

    rows = [e.to_dict() for e in evidence]
    for row in rows:
        row["attributes"] = json.dumps(row.get("attributes") or {}, ensure_ascii=False)

    out_path = data_root / "processed" / slug / f"evidence_{slug}.csv"
    write_csv_dicts(out_path, rows, fieldnames=FIELDNAMES)

    print(f"\nWrote: {out_path} ({len(rows)} total rows)")
    print("\nBreakdown by source_type:")
    for k, v in sorted(Counter(e.source_type for e in evidence).items()):
        print(f"  {k}: {v}")
    print("\nBreakdown by risk_category:")
    for k, v in sorted(Counter(e.risk_category for e in evidence).items()):
        print(f"  {k}: {v}")
    dates = sorted(e.date for e in evidence if e.date)
    if dates:
        print(f"\nDate range: {dates[0]} → {dates[-1]}")


if __name__ == "__main__":
    main()
