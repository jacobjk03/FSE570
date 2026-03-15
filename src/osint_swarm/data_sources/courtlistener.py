"""
CourtListener REST API connector — US federal court dockets for corporate risk.

Source: https://www.courtlistener.com/api/rest/v4/
  - Free, no authentication required for basic searches
  - Optional: set COURTLISTENER_API_TOKEN in .env for higher rate limits
    (free account at https://www.courtlistener.com/sign-in/)
  - Anonymous limit: ~100 requests/hour — sufficient for demo (3 entities = 3 calls)

What we pull: court dockets where the entity is mentioned as a party.
The dockets cover US federal (district + circuit) and many state courts.
Cases include: SEC enforcement, DOJ criminal prosecution, class action suits,
patent disputes, RICO, antitrust, bankruptcy.

Evidence confidence: 0.85 — court records are public, authoritative documents.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

COURTLISTENER_SEARCH_URL = "https://www.courtlistener.com/api/rest/v4/search/"
COURTLISTENER_BASE_URL = "https://www.courtlistener.com"

DEFAULT_MAX_RESULTS = 20
DEFAULT_PAGE_SIZE = 20


class CourtListenerError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _headers() -> Dict[str, str]:
    token = os.environ.get("COURTLISTENER_API_TOKEN", "").strip()
    user_agent = os.environ.get("SEC_USER_AGENT", "OSINT-Swarm research@asu.edu")
    h = {"User-Agent": user_agent}
    if token:
        h["Authorization"] = f"Token {token}"
    return h


def _get_field(record: Dict, *keys: str, default: Any = "") -> Any:
    """
    Try multiple key names (camelCase + snake_case) and return the first that is not None/empty.
    CourtListener search results use camelCase; the dockets endpoint uses snake_case.
    """
    for key in keys:
        val = record.get(key)
        if val is not None and val != "":
            return val
    return default


def _absolute_url(relative: str) -> str:
    if not relative:
        return ""
    if relative.startswith("http"):
        return relative
    return f"{COURTLISTENER_BASE_URL}{relative}"


def _slug_from_docket_id(docket_id: Any) -> str:
    """Short deterministic ID for evidence_id generation."""
    return hashlib.md5(str(docket_id).encode()).hexdigest()[:10]


# ---------------------------------------------------------------------------
# API fetch
# ---------------------------------------------------------------------------

def fetch_dockets(
    entity_name: str,
    max_results: int = DEFAULT_MAX_RESULTS,
) -> Dict[str, Any]:
    """
    Search CourtListener for federal court dockets mentioning the entity.

    Returns a dict with keys:
      entity_name, query, total_found (int), dockets (list of normalized dicts)

    Each docket dict has:
      id, case_name, docket_number, court_id, date_filed, date_terminated,
      suit_nature, cause, absolute_url
    """
    query = f'"{entity_name}"'
    params: Dict[str, Any] = {
        "type": "d",
        "q": query,
        "order_by": "score desc",
        "page_size": min(max_results, DEFAULT_PAGE_SIZE),
    }

    try:
        resp = requests.get(
            COURTLISTENER_SEARCH_URL,
            params=params,
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise CourtListenerError(f"CourtListener API request failed: {exc}") from exc

    try:
        data = resp.json()
    except Exception as exc:
        raise CourtListenerError(f"CourtListener returned non-JSON: {exc}") from exc

    raw_results: List[Dict] = data.get("results") or []
    total_found: int = data.get("count") or len(raw_results)

    dockets = [_normalize_docket(r) for r in raw_results[:max_results]]

    return {
        "entity_name": entity_name,
        "query": query,
        "total_found": total_found,
        "dockets": dockets,
    }


def _normalize_docket(record: Dict) -> Dict[str, Any]:
    """
    Normalize a raw CourtListener search result into a consistent dict.

    Handles both camelCase (v4 search results) and snake_case (dockets endpoint).
    """
    docket_id = _get_field(record, "id", default="")
    case_name = _get_field(record, "caseName", "case_name", default="Unknown Case")
    docket_number = _get_field(record, "docketNumber", "docket_number", default="")
    court_id = _get_field(record, "court_id", "court", default="")
    date_filed = _get_field(record, "dateFiled", "date_filed", default="")
    date_terminated = _get_field(record, "dateTerminated", "date_terminated", default=None)
    suit_nature = _get_field(record, "suitNature", "suit_nature", "nature_of_suit", default="")
    cause = _get_field(record, "cause", default="")
    abs_url = _get_field(record, "absolute_url", default="")

    # Strip trailing None/null that sometimes comes through
    if date_terminated in (None, "None", "null", ""):
        date_terminated = None

    return {
        "id": docket_id,
        "case_name": str(case_name),
        "docket_number": str(docket_number),
        "court_id": str(court_id),
        "date_filed": str(date_filed) if date_filed else "",
        "date_terminated": date_terminated,
        "suit_nature": str(suit_nature),
        "cause": str(cause),
        "absolute_url": _absolute_url(str(abs_url)),
    }


# ---------------------------------------------------------------------------
# Evidence conversion
# ---------------------------------------------------------------------------

def dockets_to_evidence_rows(
    dockets: List[Dict[str, Any]],
    entity_id: str,
    entity_name: str,
    raw_location: Optional[str] = None,
) -> list:
    """
    Convert normalized docket dicts into Evidence objects.

    Imported here to avoid circular imports — Evidence is defined in osint_swarm.entities.
    """
    from osint_swarm.entities import Evidence

    out = []
    for docket in dockets:
        docket_id = docket.get("id") or _slug_from_docket_id(docket.get("case_name", ""))
        ev_id = f"{entity_id}_courtlistener_{_slug_from_docket_id(docket_id)}"

        case_name = docket.get("case_name") or "Unknown case"
        docket_number = docket.get("docket_number") or ""
        date_filed = docket.get("date_filed") or ""
        date_terminated = docket.get("date_terminated")
        suit_nature = docket.get("suit_nature") or ""
        cause = docket.get("cause") or ""
        court_id = docket.get("court_id") or ""
        abs_url = docket.get("absolute_url") or ""

        status = f"Closed {date_terminated}" if date_terminated else "Ongoing / status unknown"

        parts = [f"Court case: {case_name}"]
        if docket_number:
            parts.append(f"Docket: {docket_number}")
        if suit_nature:
            parts.append(f"Type: {suit_nature}")
        if cause:
            parts.append(f"Cause: {cause}")
        if court_id:
            parts.append(f"Court: {court_id}")
        parts.append(f"Filed: {date_filed or 'unknown'}")
        parts.append(f"Status: {status}")

        summary = " | ".join(parts)

        out.append(Evidence(
            evidence_id=ev_id,
            entity_id=entity_id,
            date=date_filed,
            source_type="court_record",
            risk_category="legal",
            summary=summary[:5000],
            source_uri=abs_url,
            raw_location=raw_location,
            confidence=0.85,
            attributes={
                "docket_id": docket_id,
                "docket_number": docket_number,
                "court_id": court_id,
                "suit_nature": suit_nature,
                "cause": cause,
                "date_terminated": date_terminated,
                "stub": False,
            },
        ))
    return out


# ---------------------------------------------------------------------------
# Cache helpers (mirror the GDELT pattern)
# ---------------------------------------------------------------------------

def slug_for_entity_name(name: str) -> str:
    """Filesystem-safe slug — same logic as GdeltProcessor._slug_for_entity."""
    return name.lower().split(",")[0].strip().replace(" ", "_").replace(".", "")


def cache_dockets_json(entity_slug: str, payload: Dict[str, Any], cache_dir: Path) -> Path:
    """Write CourtListener payload to cache. Returns path."""
    from osint_swarm.utils.io import write_json, ensure_parent
    out_path = cache_dir / f"dockets_{entity_slug}.json"
    ensure_parent(out_path)
    write_json(out_path, payload)
    return out_path


def load_cached_dockets(entity_slug: str, cache_dir: Path) -> Optional[Dict[str, Any]]:
    """Load cached payload; returns None if not found."""
    from osint_swarm.utils.io import read_json
    path = cache_dir / f"dockets_{entity_slug}.json"
    if not path.exists():
        return None
    return read_json(path)
