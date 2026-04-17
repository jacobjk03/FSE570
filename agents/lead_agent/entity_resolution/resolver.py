"""Entity resolution: map query text (e.g. 'Tesla', 'Company X') to Entity or candidates."""

from __future__ import annotations

import re
from typing import List, Optional

from osint_swarm.entities import Entity


# Lookup table: normalized name/alias -> Entity.
# Expand with more entities as needed.
ENTITY_REGISTRY: List[Entity] = [
    Entity(
        entity_id="tesla_inc_cik_0001318605",
        name="Tesla, Inc.",
        entity_type="public_company",
        identifiers={"cik": "0001318605", "ticker": "TSLA"},
        aliases=["Tesla", "Tesla Inc", "Tesla Motors", "TSLA"],
    ),
    Entity(
        entity_id="ford_motor_cik_0000037996",
        name="Ford Motor Company",
        entity_type="public_company",
        identifiers={"cik": "0000037996", "ticker": "F"},
        # "F" ticker excluded from aliases: single-char strings cause false positives
        # via substring matching (e.g. "fraud" contains "f").
        aliases=["Ford", "Ford Motor", "Ford Motor Co", "Ford Motor Company"],
    ),
    Entity(
        entity_id="boeing_cik_0000012927",
        name="The Boeing Company",
        entity_type="public_company",
        identifiers={"cik": "0000012927", "ticker": "BA"},
        aliases=["Boeing", "Boeing Company", "The Boeing Company", "BA"],
    ),
    Entity(
        entity_id="alphabet_inc_cik_0001652044",
        name="Alphabet Inc.",
        entity_type="public_company",
        identifiers={"cik": "0001652044", "ticker": "GOOGL"},
        aliases=["Alphabet", "Alphabet Inc", "Google", "Google LLC", "GOOGL", "Alphabet Google"],
    ),
    Entity(
        entity_id="jpmorgan_chase_cik_0000019617",
        name="JPMorgan Chase & Co.",
        entity_type="public_company",
        identifiers={"cik": "0000019617", "ticker": "JPM"},
        aliases=["JPMorgan", "JPMorgan Chase", "JP Morgan", "JPMorgan Chase & Co", "JPM"],
    ),
]

# Minimum token length for substring matching. Terms shorter than this require
# an exact whole-word match to avoid false positives (e.g. "f" matching "fraud").
_MIN_SUBSTR_LEN = 3


def _normalize(s: str) -> str:
    return s.strip().lower() if s else ""


def _word_in_text(word: str, text: str) -> bool:
    """Return True if `word` appears as a whole word in `text` (case-insensitive)."""
    return bool(re.search(r"\b" + re.escape(word) + r"\b", text, re.IGNORECASE))


def _term_matches_query(term_norm: str, query_norm: str) -> bool:
    """
    Check whether a name/alias term matches a query string.
    - Exact match always passes.
    - For multi-word or sufficiently long terms: substring match (term inside query).
    - For short single-token terms (< _MIN_SUBSTR_LEN chars): require whole-word match
      to prevent single-letter tickers like "F" matching words like "fraud".
    """
    if query_norm == term_norm:
        return True
    if len(term_norm) < _MIN_SUBSTR_LEN:
        return _word_in_text(term_norm, query_norm)
    return term_norm in query_norm


def resolve(query: str) -> List[Entity]:
    """
    Resolve a query string (e.g. 'Tesla', 'Investigate Tesla for money laundering') to candidates.

    Uses a registry and alias match. Returns all entities whose name or any alias
    appears in the query (case-insensitive). Short aliases (< 3 chars) require a
    whole-word match to avoid false positives from ticker symbols like 'F'.
    """
    if not query or not query.strip():
        return []
    norm = _normalize(query)
    if not norm:
        return []
    candidates: List[Entity] = []
    for entity in ENTITY_REGISTRY:
        name_norm = _normalize(entity.name)
        if _term_matches_query(name_norm, norm):
            candidates.append(entity)
            continue
        for alias in entity.aliases:
            alias_norm = _normalize(alias)
            if _term_matches_query(alias_norm, norm):
                candidates.append(entity)
                break
    return candidates


def resolve_one(query: str) -> Optional[Entity]:
    """Return the first resolved entity, or None if no match."""
    candidates = resolve(query)
    return candidates[0] if candidates else None


def resolve_one_with_auto(query: str) -> Optional[Entity]:
    """
    Resolve entity from query — registry first, then auto-resolution via SEC EDGAR.
    If the registry has no match, extracts the company name from the query and
    queries SEC EDGAR full-text search to find the CIK automatically.
    Returns an Entity (possibly auto-resolved) or None.
    """
    entity = resolve_one(query)
    if entity:
        return entity

    # Registry miss — try SEC EDGAR auto-resolution
    from agents.lead_agent.entity_resolution.sec_name_resolver import (
        build_auto_entity,
        extract_company_name,
        resolve_company_name,
    )

    company_name = extract_company_name(query)
    if not company_name:
        return None

    result = resolve_company_name(company_name)
    if not result:
        return None

    cik10, official_name = result
    return build_auto_entity(company_name, cik10, official_name)
