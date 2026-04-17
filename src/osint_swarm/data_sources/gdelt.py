"""
GDELT DOC 2.0 connector — adverse media / news events for corporate risk.

Queries the GDELT Document 2.0 API for news articles mentioning an entity
alongside risk-related keywords (fraud, investigation, fine, lawsuit, etc.).

GDELT is free, public, and requires no authentication.
API docs: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/

Endpoint: https://api.gdeltproject.org/api/v2/doc/doc
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests

# Risk-relevant keywords for adverse media screening (AML / OSINT context)
RISK_KEYWORDS = (
    "fraud OR investigation OR penalty OR fine OR violation "
    "OR lawsuit OR scandal OR misconduct OR bribery OR corruption "
    "OR sanction OR money laundering OR settlement OR indictment"
)

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"
DEFAULT_MAX_RECORDS = 100
DEFAULT_LOOKBACK_DAYS = 730  # ~2 years


class GdeltError(RuntimeError):
    pass


def _gdelt_headers() -> Dict[str, str]:
    agent = os.environ.get("SEC_USER_AGENT", "OSINT-Swarm research@asu.edu")
    return {"User-Agent": agent}


def fetch_news_for_entity(
    entity_name: str,
    max_records: int = DEFAULT_MAX_RECORDS,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> Dict[str, Any]:
    """
    Query GDELT DOC 2.0 for news articles about an entity.

    Returns a dict with keys:
      - articles: list of article dicts
      - query: the query string used
      - entity_name: the entity name queried
    """
    # Build query: entity name quoted + risk keywords
    query = f'"{entity_name}" ({RISK_KEYWORDS})'

    params = {
        "query": query,
        "mode": "artlist",
        "maxrecords": str(min(max_records, 250)),  # GDELT caps at 250
        "format": "json",
        "sort": "DateDesc",
        "sourcelang": "english",  # filter to English-language sources only
    }

    url = f"{GDELT_DOC_API}?{urlencode(params)}"

    try:
        resp = requests.get(url, headers=_gdelt_headers(), timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise GdeltError(f"GDELT API request failed: {exc}") from exc

    try:
        payload = resp.json()
    except Exception as exc:
        raise GdeltError(f"GDELT API returned non-JSON response: {exc}") from exc

    # GDELT returns None body when no results (not an empty articles list)
    if payload is None:
        payload = {}

    articles = payload.get("articles") or []

    return {
        "articles": articles,
        "query": query,
        "entity_name": entity_name,
        "total_returned": len(articles),
    }


def extract_article_records(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract the articles list from a cached or live GDELT payload."""
    return payload.get("articles") or []


def cache_news_json(entity_slug: str, payload: Dict[str, Any], cache_dir: Path) -> Path:
    """Write GDELT payload to cache. Returns the written path."""
    from osint_swarm.utils.io import write_json, ensure_parent
    out_path = cache_dir / f"news_{entity_slug}.json"
    ensure_parent(out_path)
    write_json(out_path, payload)
    return out_path
