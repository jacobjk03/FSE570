"""
Build structured Evidence CSV for Ford Motor Company from cached raw data.

Prerequisites (run once):
    python scripts/pull_sec_submissions.py --cik 0000037996
    python scripts/pull_nhtsa_recalls.py --make FORD

Output:
    data/processed/ford/evidence_ford.csv
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from osint_swarm.entities import Evidence
from osint_swarm.utils.io import read_json, write_csv_dicts

FORD_ENTITY_ID = "ford_motor_cik_0000037996"
FORD_CIK = "0000037996"

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


def _safe_get(d: Dict[str, Any], *keys: str) -> Any:
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def build_sec_evidence(raw_path: Path) -> List[Evidence]:
    """Convert cached SEC submissions JSON into Evidence rows (recent filings)."""
    payload = read_json(raw_path)
    filings: Dict[str, Any] = _safe_get(payload, "filings", "recent") or {}

    forms = filings.get("form") or []
    dates = filings.get("filingDate") or []
    accessions = filings.get("accessionNumber") or []
    primary_docs = filings.get("primaryDocument") or []
    descriptions = filings.get("primaryDocDescription") or []

    out: List[Evidence] = []
    for i, form in enumerate(forms):
        date = dates[i] if i < len(dates) else ""
        accession = accessions[i] if i < len(accessions) else ""
        primary_doc = primary_docs[i] if i < len(primary_docs) else ""
        description = descriptions[i] if i < len(descriptions) else ""

        if not date:
            continue

        # Only include filings relevant to governance/regulatory risk.
        risk_forms = {"8-K", "10-K", "10-Q", "DEF 14A", "SC 13G", "SC 13D", "4", "3", "5"}
        if form not in risk_forms:
            continue

        accession_clean = accession.replace("-", "")
        source_uri = (
            f"https://www.sec.gov/Archives/edgar/data/{int(FORD_CIK)}"
            f"/{accession_clean}/{primary_doc}"
            if primary_doc
            else f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={FORD_CIK}"
        )

        ev_id = f"ford_sec_{form.lower().replace(' ', '_').replace('/', '_')}_{date}_{accession_clean[:8]}"

        risk_category = "governance"
        if form in {"10-K", "10-Q"}:
            risk_category = "governance"
        elif form in {"8-K"}:
            risk_category = "governance"
        elif form in {"DEF 14A"}:
            risk_category = "governance"
        elif form in {"SC 13G", "SC 13D"}:
            risk_category = "network"

        summary = (
            f"Ford Motor Company filed a {form}"
            + (f" — {description}" if description else "")
            + f" on {date}."
        )

        out.append(
            Evidence(
                evidence_id=ev_id,
                entity_id=FORD_ENTITY_ID,
                date=str(date)[:10],
                source_type="sec_filing",
                risk_category=risk_category,
                summary=summary.strip(),
                source_uri=source_uri,
                raw_location=str(raw_path),
                confidence=0.95,
                attributes={
                    "form": form,
                    "accession": accession,
                    "description": description,
                    "cik": FORD_CIK,
                },
            )
        )

    return out


def build_nhtsa_evidence(raw_path: Path) -> List[Evidence]:
    """Convert cached NHTSA recalls JSON into Evidence rows."""
    payload = read_json(raw_path)
    records = payload.get("results") or payload.get("Results") or []
    out: List[Evidence] = []

    for r in records:
        if not isinstance(r, dict):
            continue

        nhtsa_id = r.get("nhtsa_id") or r.get("NHTSA_ID")
        report_date = r.get("report_received_date") or r.get("ReportReceivedDate")
        subject = r.get("subject") or r.get("Subject") or ""
        component = r.get("component") or r.get("Component") or ""
        defect_summary = r.get("defect_summary") or r.get("Summary") or ""
        consequence = r.get("consequence_summary") or r.get("Consequence") or ""
        corrective_action = r.get("corrective_action") or r.get("Remedy") or ""
        recall_type = r.get("recall_type") or ""
        potentially_affected = r.get("potentially_affected") or ""
        mfr_campaign_number = r.get("mfr_campaign_number") or ""
        manufacturer = r.get("manufacturer") or ""

        recall_link = r.get("recall_link") if isinstance(r.get("recall_link"), dict) else {}
        recall_url = (recall_link or {}).get("url") or ""

        if not report_date:
            continue

        source_uri = recall_url or "https://www.nhtsa.gov/recalls"
        ev_id = f"ford_nhtsa_{(nhtsa_id or mfr_campaign_number or report_date)}".lower().replace(" ", "_")

        out.append(
            Evidence(
                evidence_id=ev_id,
                entity_id=FORD_ENTITY_ID,
                date=str(report_date)[:10],
                source_type="regulator_api",
                risk_category="regulatory",
                summary=(defect_summary or subject or "").strip()[:5000],
                source_uri=source_uri,
                raw_location=str(raw_path),
                confidence=0.8,
                attributes={
                    "nhtsa_id": nhtsa_id,
                    "manufacturer": manufacturer,
                    "subject": subject,
                    "component": component,
                    "recall_type": recall_type,
                    "potentially_affected": potentially_affected,
                    "mfr_campaign_number": mfr_campaign_number,
                    "consequence_summary": (consequence or "").strip()[:5000],
                    "corrective_action": (corrective_action or "").strip()[:5000],
                },
            )
        )

    return out


def main() -> None:
    raw_sec = Path(f"data/raw/sec/CIK{FORD_CIK}.json")
    raw_nhtsa = Path("data/raw/nhtsa/recalls_make_FORD.json")

    missing = []
    if not raw_sec.exists():
        missing.append(f"  SEC:   python scripts/pull_sec_submissions.py --cik {FORD_CIK}")
    if not raw_nhtsa.exists():
        missing.append("  NHTSA: python scripts/pull_nhtsa_recalls.py --make FORD")
    if missing:
        raise SystemExit(
            "Missing raw files. Run the following first:\n" + "\n".join(missing)
        )

    evidence: List[Evidence] = []
    evidence.extend(build_sec_evidence(raw_sec))
    evidence.extend(build_nhtsa_evidence(raw_nhtsa))

    rows = [e.to_dict() for e in evidence]
    for row in rows:
        row["attributes"] = json.dumps(row.get("attributes") or {}, ensure_ascii=False)

    out_path = Path("data/processed/ford/evidence_ford.csv")
    write_csv_dicts(out_path, rows, fieldnames=FIELDNAMES)
    print(f"Wrote: {out_path} ({len(rows)} rows)")

    from collections import Counter
    src_counts = Counter(e.source_type for e in evidence)
    cat_counts = Counter(e.risk_category for e in evidence)
    print("\nSource type breakdown:")
    for k, v in sorted(src_counts.items()):
        print(f"  {k}: {v}")
    print("\nRisk category breakdown:")
    for k, v in sorted(cat_counts.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
