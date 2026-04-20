"""
OFAC SDN (Specially Designated Nationals) connector.

Downloads and parses the US Treasury Office of Foreign Assets Control
Specially Designated Nationals (SDN) list.

Source: https://www.treasury.gov/ofac/downloads/sdn.xml
  - Free, no authentication, no API key required
  - Updated regularly by the US Treasury
  - ~2-3 MB XML file; cached locally after first download

The SDN list contains individuals, entities, vessels, and aircraft that
US persons are prohibited from transacting with. Matching an entity name
against this list is a core component of AML/KYC due diligence.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

SDN_URL = "https://www.treasury.gov/ofac/downloads/sdn.xml"
SDN_NAMESPACE = "https://sanctionssearch.ofac.treas.gov/"


class OfacError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Downloading
# ---------------------------------------------------------------------------

def download_sdn_xml(cache_path: Path, user_agent: str = "OSINT-Swarm research@asu.edu") -> Path:
    """
    Download the OFAC SDN XML to cache_path. Returns the path.

    The file is ~2-3 MB and should be refreshed periodically
    (OFAC updates it on business days).
    """
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        resp = requests.get(SDN_URL, headers={"User-Agent": user_agent}, timeout=60, stream=True)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise OfacError(f"Failed to download OFAC SDN XML: {exc}") from exc

    with open(cache_path, "wb") as fh:
        for chunk in resp.iter_content(chunk_size=65536):
            fh.write(chunk)
    return cache_path


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _strip_ns(tree: ET.Element) -> None:
    """Strip XML namespace prefixes from all tags in-place."""
    for elem in tree.iter():
        if "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]


def parse_sdn_entries(xml_path: Path) -> List[Dict[str, Any]]:
    """
    Parse an OFAC SDN XML file and return a list of SDN entry dicts.

    Each dict has keys:
      uid, name, sdn_type, programs (list), aka_names (list), remarks
    """
    try:
        tree = ET.parse(str(xml_path))
    except ET.ParseError as exc:
        raise OfacError(f"Failed to parse OFAC SDN XML at {xml_path}: {exc}") from exc

    root = tree.getroot()
    _strip_ns(root)

    entries: List[Dict[str, Any]] = []
    for entry in root.findall("sdnEntry"):
        uid = entry.findtext("uid") or ""
        first = (entry.findtext("firstName") or "").strip()
        last = (entry.findtext("lastName") or "").strip()
        # For entities the full name is in lastName; individuals have firstName + lastName
        name = f"{first} {last}".strip() if first else last

        sdn_type = (entry.findtext("sdnType") or "").strip()
        remarks = (entry.findtext("remarks") or "").strip()

        programs: List[str] = []
        prog_list = entry.find("programList")
        if prog_list is not None:
            for prog in prog_list.findall("program"):
                if prog.text:
                    programs.append(prog.text.strip())

        aka_names: List[str] = []
        aka_list = entry.find("akaList")
        if aka_list is not None:
            for aka in aka_list.findall("aka"):
                aka_first = (aka.findtext("firstName") or "").strip()
                aka_last = (aka.findtext("lastName") or "").strip()
                aka_name = f"{aka_first} {aka_last}".strip() if aka_first else aka_last
                if aka_name:
                    aka_names.append(aka_name)

        if name:
            entries.append({
                "uid": uid,
                "name": name,
                "sdn_type": sdn_type,
                "programs": programs,
                "aka_names": aka_names,
                "remarks": remarks,
            })
    return entries


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def _normalize(s: str) -> str:
    """Lowercase, strip punctuation, collapse spaces."""
    s = s.lower()
    s = re.sub(r"[,.\-&'/()]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    # Strip common legal suffixes that vary between sources
    for suffix in (" inc", " llc", " ltd", " corp", " co", " company", " the"):
        if s.endswith(suffix):
            s = s[: -len(suffix)].strip()
    return s


def _terms_match(query_norm: str, target_norm: str) -> bool:
    """
    Return True if query matches target.

    Rules (in order):
    1. Exact match after normalization
    2. query (≥5 chars) appears as whole word(s) inside target
    3. target (≥5 chars) appears as whole word(s) inside query

    Rule 3 handles the case where the SDN entry is a shorter trading name
    of the entity we're searching (e.g. searching "The Boeing Company"
    matches SDN entry "BOEING").
    """
    if query_norm == target_norm:
        return True
    if len(query_norm) >= 5:
        try:
            pattern = r"\b" + re.escape(query_norm) + r"\b"
            if re.search(pattern, target_norm):
                return True
        except re.error:
            if query_norm in target_norm:
                return True
    if len(target_norm) >= 5:
        try:
            pattern = r"\b" + re.escape(target_norm) + r"\b"
            if re.search(pattern, query_norm):
                return True
        except re.error:
            if target_norm in query_norm:
                return True
    return False


def search_entries(
    entries: List[Dict[str, Any]],
    entity_name: str,
    aliases: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Search parsed SDN entries for the entity name and aliases.

    Returns a list of matching SDN entry dicts (may be empty for a clean result).
    False positives are possible due to name similarity; callers should treat
    matches as flags for human review, not automatic disqualification.
    """
    # Build the set of query terms: entity name + all aliases
    # Use the original alias length (not the post-normalized length) to decide
    # whether to include it. This prevents 1-2 char tickers ("F", "BA") from
    # generating false positives, while preserving 3-letter acronyms like "BRT"
    # whose legal suffix ("CORP") was stripped during normalization.
    raw_query_terms: set = {_normalize(entity_name)}
    for alias in (aliases or []):
        if len(alias.strip()) < 3:  # exclude 1-2 char tickers only
            continue
        n = _normalize(alias)
        if n:
            raw_query_terms.add(n)

    # Pre-compile query patterns once — avoids re-compiling inside the 18k-entry loop.
    query_terms = []
    for qterm in raw_query_terms:
        compiled = None
        if len(qterm) >= 5:
            try:
                compiled = re.compile(r"\b" + re.escape(qterm) + r"\b")
            except re.error:
                compiled = None
        query_terms.append((qterm, compiled))

    hits: List[Dict[str, Any]] = []
    seen_uids: set = set()

    for entry in entries:
        if entry["uid"] in seen_uids:
            continue

        sdn_names = [entry["name"]] + entry["aka_names"]
        sdn_norms = [_normalize(n) for n in sdn_names if n]

        for qterm, qpattern in query_terms:
            for sdn_norm in sdn_norms:
                if not sdn_norm:
                    continue
                matched = False
                if qterm == sdn_norm:
                    matched = True
                elif qpattern is not None:
                    try:
                        matched = bool(qpattern.search(sdn_norm))
                    except re.error:
                        matched = qterm in sdn_norm
                elif len(sdn_norm) >= 5:
                    try:
                        sdn_pattern = re.compile(r"\b" + re.escape(sdn_norm) + r"\b")
                        matched = bool(sdn_pattern.search(qterm))
                    except re.error:
                        matched = sdn_norm in qterm
                if matched:
                    seen_uids.add(entry["uid"])
                    hits.append(entry)
                    break
            else:
                continue
            break

    return hits
