"""Auto-resolve a company name to a SEC CIK using EDGAR full-text search index."""

from __future__ import annotations

import os
import re
from typing import Optional, Tuple

import requests

EFTS_URL = "https://efts.sec.gov/LATEST/search-index"

# Words stripped from query before extracting company name
_PREAMBLE = {"investigate", "investigating", "research", "analyze", "analyse", "check", "look", "into"}
_NOISE = {
    "for", "and", "or", "the", "a", "an", "is", "are", "was", "in", "of", "with",
    "money", "laundering", "fraud", "corruption", "sanctions", "governance", "risk",
    "aml", "regulatory", "legal", "compliance", "violations", "misconduct", "bribery",
    "about", "on", "regarding", "related", "to", "its", "their",
}


def _sec_headers() -> dict:
    ua = os.environ.get("SEC_USER_AGENT") or os.environ.get("SEC_UA", "OSINT Swarm research@example.com")
    return {"User-Agent": ua, "Accept-Encoding": "gzip, deflate"}


def extract_company_name(query: str) -> Optional[str]:
    """
    Extract the likely company name from a natural-language investigation query.
    E.g.: "Investigate Microsoft for money laundering" -> "Microsoft"
         "Investigate Goldman Sachs"                  -> "Goldman Sachs"
    """
    tokens = query.split()
    # Skip leading preamble verbs
    start = 0
    for i, t in enumerate(tokens):
        if t.lower() in _PREAMBLE:
            start = i + 1
        else:
            break

    # Collect tokens until we hit a noise/stop word
    company_tokens = []
    for t in tokens[start:]:
        if t.lower().rstrip(".,") in _NOISE:
            break
        company_tokens.append(t)

    name = " ".join(company_tokens).strip().strip(".,")
    return name if len(name) >= 2 else None


def resolve_company_name(name: str) -> Optional[Tuple[str, str]]:
    """
    Query SEC EDGAR full-text search to resolve a company name to (cik10, official_name).
    Returns None if not found or on network error.
    """
    if not name or len(name.strip()) < 2:
        return None

    params = {
        "q": f'"{name}"',
        "forms": "10-K",
        "dateRange": "custom",
        "startdt": "2018-01-01",
        "enddt": "2026-12-31",
    }

    try:
        resp = requests.get(EFTS_URL, params=params, headers=_sec_headers(), timeout=12)
        if resp.status_code != 200:
            return None
        data = resp.json()
        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            return None

        # Fields: ciks (list), display_names (e.g. "MICROSOFT CORP  (MSFT)  (CIK 0000789019)")
        name_lower = name.lower()
        best = None
        for hit in hits[:10]:
            src = hit.get("_source", {})
            ciks = src.get("ciks") or []
            display_names = src.get("display_names") or []
            if not ciks or not display_names:
                continue
            cik = ciks[0].strip().zfill(10)
            # Parse company name from display string (format: "NAME  (TICKER)  (CIK XXXXXXXXXX)")
            raw = display_names[0]
            company_part = raw.split("(")[0].strip()
            if name_lower in company_part.lower() or company_part.lower() in name_lower:
                best = (cik, company_part)
                break

        # Fallback: take first hit regardless of name match
        if not best:
            src = hits[0].get("_source", {})
            ciks = src.get("ciks") or []
            display_names = src.get("display_names") or []
            if ciks and display_names:
                cik = ciks[0].strip().zfill(10)
                company_part = display_names[0].split("(")[0].strip()
                best = (cik, company_part)

        if not best:
            return None

        return best[0], best[1]

    except Exception:
        return None


def build_auto_entity(company_name: str, cik10: str, official_name: str):
    """Build a temporary Entity dataclass from auto-resolved SEC data."""
    from osint_swarm.entities import Entity

    # Sanitise for entity_id
    slug = re.sub(r"[^a-z0-9]+", "_", official_name.lower())[:35].strip("_")
    entity_id = f"auto_{slug}_cik_{cik10}"

    display_name = official_name.title()

    return Entity(
        entity_id=entity_id,
        name=display_name,
        entity_type="public_company",
        identifiers={"cik": cik10},
        aliases=[company_name, display_name, official_name],
    )
