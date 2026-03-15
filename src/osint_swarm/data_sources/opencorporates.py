"""
OpenCorporates REST API connector — corporate structure, officers, beneficial ownership.

Source: https://api.opencorporates.com/documentation/API-Reference
  - API key required (set OPENCORPORATES_API_TOKEN in .env)
  - Free tier: 200 requests/month, 50/day for open-data projects
  - Company search, full company detail (officers, UBOs, controlling entity), officer search

What we pull:
  - Company matches for an entity name (via search endpoint)
  - Detailed company data: officers, controlling_entity, ultimate_beneficial_owners,
    corporate_groupings, previous_names, filings summary
  - Officer positions across companies (director interlocks / key-person exposure)

Evidence confidence: 0.80 — data sourced from official corporate registries worldwide,
but entity name matching introduces moderate uncertainty.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

OC_API_BASE = "https://api.opencorporates.com/v0.4"
DEFAULT_MAX_COMPANIES = 5
DEFAULT_MAX_OFFICERS = 10


class OpenCorporatesError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Auth / helpers
# ---------------------------------------------------------------------------

def _api_token() -> str:
    token = os.environ.get("OPENCORPORATES_API_TOKEN", "").strip()
    if not token:
        raise OpenCorporatesError(
            "Missing OpenCorporates API token. "
            "Set OPENCORPORATES_API_TOKEN in your .env file. "
            "Free keys: https://opencorporates.com/api_accounts/new"
        )
    return token


def _oc_params(**extra: Any) -> Dict[str, Any]:
    params: Dict[str, Any] = {"api_token": _api_token()}
    params.update(extra)
    return params


def _oc_headers() -> Dict[str, str]:
    return {"User-Agent": os.environ.get("SEC_USER_AGENT", "OSINT-Swarm research@asu.edu")}


def _slug_id(value: Any) -> str:
    return hashlib.md5(str(value).encode()).hexdigest()[:10]


# ---------------------------------------------------------------------------
# Company search
# ---------------------------------------------------------------------------

def search_companies(
    entity_name: str,
    jurisdiction_code: Optional[str] = None,
    max_results: int = DEFAULT_MAX_COMPANIES,
) -> Dict[str, Any]:
    """
    Search OpenCorporates for companies matching a name.

    Returns dict with keys:
      entity_name, total_count, companies (list of normalized company dicts)
    """
    params = _oc_params(q=entity_name, per_page=str(min(max_results, 30)), order="score")
    if jurisdiction_code:
        params["jurisdiction_code"] = jurisdiction_code

    url = f"{OC_API_BASE}/companies/search"

    try:
        resp = requests.get(url, params=params, headers=_oc_headers(), timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise OpenCorporatesError(f"OpenCorporates API request failed: {exc}") from exc

    try:
        data = resp.json()
    except Exception as exc:
        raise OpenCorporatesError(f"OpenCorporates returned non-JSON: {exc}") from exc

    results = data.get("results", {})
    raw_companies = results.get("companies") or []
    total_count = results.get("total_count") or len(raw_companies)

    companies = [_normalize_company_search(c.get("company", c)) for c in raw_companies[:max_results]]

    return {
        "entity_name": entity_name,
        "total_count": total_count,
        "companies": companies,
    }


def _normalize_company_search(c: Dict) -> Dict[str, Any]:
    return {
        "name": c.get("name") or "",
        "company_number": c.get("company_number") or "",
        "jurisdiction_code": c.get("jurisdiction_code") or "",
        "company_type": c.get("company_type") or "",
        "current_status": c.get("current_status") or "",
        "incorporation_date": c.get("incorporation_date") or "",
        "dissolution_date": c.get("dissolution_date") or "",
        "inactive": c.get("inactive", False),
        "opencorporates_url": c.get("opencorporates_url") or "",
        "registered_address_in_full": c.get("registered_address_in_full") or "",
    }


# ---------------------------------------------------------------------------
# Company detail (officers, UBOs, controlling entity)
# ---------------------------------------------------------------------------

def fetch_company_detail(
    jurisdiction_code: str,
    company_number: str,
) -> Dict[str, Any]:
    """
    Fetch full company details from OpenCorporates including officers,
    controlling_entity, ultimate_beneficial_owners, and corporate_groupings.
    """
    url = f"{OC_API_BASE}/companies/{jurisdiction_code}/{company_number}"
    params = _oc_params()

    try:
        resp = requests.get(url, params=params, headers=_oc_headers(), timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise OpenCorporatesError(f"OpenCorporates company detail failed: {exc}") from exc

    try:
        data = resp.json()
    except Exception as exc:
        raise OpenCorporatesError(f"OpenCorporates returned non-JSON: {exc}") from exc

    company = data.get("results", {}).get("company", {})
    return _normalize_company_detail(company)


def _normalize_company_detail(c: Dict) -> Dict[str, Any]:
    officers = []
    for o in (c.get("officers") or []):
        off = o.get("officer", o)
        officers.append({
            "id": off.get("id") or "",
            "name": off.get("name") or "",
            "position": off.get("position") or "",
            "start_date": off.get("start_date") or "",
            "end_date": off.get("end_date"),
            "opencorporates_url": off.get("opencorporates_url") or "",
        })

    corporate_groupings = []
    for cg in (c.get("corporate_groupings") or []):
        grp = cg.get("corporate_grouping", cg)
        corporate_groupings.append({
            "name": grp.get("name") or "",
            "opencorporates_url": grp.get("opencorporates_url") or "",
            "wikipedia_id": grp.get("wikipedia_id") or "",
        })

    previous_names = []
    for pn in (c.get("previous_names") or []):
        previous_names.append({
            "company_name": pn.get("company_name") or "",
            "con_date": pn.get("con_date") or "",
        })

    controlling_entity = c.get("controlling_entity")
    ubos = c.get("ultimate_beneficial_owners") or []
    ultimate_controlling = c.get("ultimate_controlling_company")

    return {
        "name": c.get("name") or "",
        "company_number": c.get("company_number") or "",
        "jurisdiction_code": c.get("jurisdiction_code") or "",
        "company_type": c.get("company_type") or "",
        "current_status": c.get("current_status") or "",
        "incorporation_date": c.get("incorporation_date") or "",
        "dissolution_date": c.get("dissolution_date") or "",
        "inactive": c.get("inactive", False),
        "opencorporates_url": c.get("opencorporates_url") or "",
        "registered_address_in_full": c.get("registered_address_in_full") or "",
        "officers": officers,
        "corporate_groupings": corporate_groupings,
        "previous_names": previous_names,
        "controlling_entity": controlling_entity,
        "ultimate_beneficial_owners": ubos,
        "ultimate_controlling_company": ultimate_controlling,
        "industry_codes": c.get("industry_codes") or [],
    }


# ---------------------------------------------------------------------------
# Evidence conversion
# ---------------------------------------------------------------------------

def company_detail_to_evidence(
    detail: Dict[str, Any],
    entity_id: str,
    entity_name: str,
    raw_location: Optional[str] = None,
) -> List:
    """
    Convert a normalized OpenCorporates company detail into Evidence objects.

    Generates evidence for:
    - Each officer (directors, secretaries)
    - Controlling entity / UBOs (if available)
    - Corporate groupings
    - A summary evidence row with company metadata
    """
    from osint_swarm.entities import Evidence

    out: List = []
    oc_url = detail.get("opencorporates_url") or ""
    jurisdiction = detail.get("jurisdiction_code") or ""
    company_name = detail.get("name") or entity_name

    # --- Officers ---
    for off in (detail.get("officers") or []):
        off_name = off.get("name") or "Unknown officer"
        position = off.get("position") or "unknown"
        start = off.get("start_date") or "unknown"
        end = off.get("end_date")
        status = f"left {end}" if end else "current"

        summary = (
            f"Officer: {off_name} | Position: {position} | "
            f"Start: {start} | Status: {status} | "
            f"Company: {company_name} ({jurisdiction})"
        )

        ev_id = f"{entity_id}_oc_officer_{_slug_id(off.get('id', off_name))}"

        out.append(Evidence(
            evidence_id=ev_id,
            entity_id=entity_id,
            date=off.get("start_date") or "",
            source_type="regulator_api",
            risk_category="governance",
            summary=summary[:5000],
            source_uri=off.get("opencorporates_url") or oc_url,
            raw_location=raw_location,
            confidence=0.80,
            attributes={
                "officer_name": off_name,
                "position": position,
                "start_date": start,
                "end_date": end,
                "stub": False,
                "data_source": "opencorporates",
            },
        ))

    # --- Controlling entity ---
    ctrl = detail.get("controlling_entity")
    if ctrl and isinstance(ctrl, dict):
        ctrl_name = ctrl.get("name") or str(ctrl)
        summary = (
            f"Controlling entity: {ctrl_name} | "
            f"Controlled company: {company_name} ({jurisdiction})"
        )
        out.append(Evidence(
            evidence_id=f"{entity_id}_oc_controlling_{_slug_id(ctrl_name)}",
            entity_id=entity_id,
            date="",
            source_type="regulator_api",
            risk_category="governance",
            summary=summary[:5000],
            source_uri=ctrl.get("opencorporates_url", oc_url),
            raw_location=raw_location,
            confidence=0.85,
            attributes={
                "controlling_entity_name": ctrl_name,
                "relationship": "controlling_entity",
                "stub": False,
                "data_source": "opencorporates",
            },
        ))

    # --- Ultimate beneficial owners ---
    for ubo in (detail.get("ultimate_beneficial_owners") or []):
        if isinstance(ubo, dict):
            ubo_name = ubo.get("name") or str(ubo)
        else:
            ubo_name = str(ubo)

        summary = (
            f"Ultimate beneficial owner: {ubo_name} | "
            f"Company: {company_name} ({jurisdiction})"
        )
        out.append(Evidence(
            evidence_id=f"{entity_id}_oc_ubo_{_slug_id(ubo_name)}",
            entity_id=entity_id,
            date="",
            source_type="regulator_api",
            risk_category="governance",
            summary=summary[:5000],
            source_uri=oc_url,
            raw_location=raw_location,
            confidence=0.85,
            attributes={
                "ubo_name": ubo_name,
                "relationship": "ultimate_beneficial_owner",
                "stub": False,
                "data_source": "opencorporates",
            },
        ))

    # --- Corporate groupings ---
    for cg in (detail.get("corporate_groupings") or []):
        cg_name = cg.get("name") or ""
        if not cg_name:
            continue
        summary = (
            f"Corporate grouping: {cg_name} | "
            f"Member: {company_name} ({jurisdiction})"
        )
        out.append(Evidence(
            evidence_id=f"{entity_id}_oc_group_{_slug_id(cg_name)}",
            entity_id=entity_id,
            date="",
            source_type="regulator_api",
            risk_category="governance",
            summary=summary[:5000],
            source_uri=cg.get("opencorporates_url") or oc_url,
            raw_location=raw_location,
            confidence=0.75,
            attributes={
                "grouping_name": cg_name,
                "wikipedia_id": cg.get("wikipedia_id") or "",
                "relationship": "corporate_grouping",
                "stub": False,
                "data_source": "opencorporates",
            },
        ))

    # --- Summary evidence row ---
    officer_count = len(detail.get("officers") or [])
    active_officers = [o for o in (detail.get("officers") or []) if not o.get("end_date")]
    prev_names = detail.get("previous_names") or []

    parts = [f"OpenCorporates profile: {company_name}"]
    parts.append(f"Jurisdiction: {jurisdiction}")
    if detail.get("company_type"):
        parts.append(f"Type: {detail['company_type']}")
    if detail.get("current_status"):
        parts.append(f"Status: {detail['current_status']}")
    if detail.get("incorporation_date"):
        parts.append(f"Incorporated: {detail['incorporation_date']}")
    parts.append(f"Officers: {officer_count} total ({len(active_officers)} current)")
    if prev_names:
        names_str = ", ".join(pn.get("company_name", "") for pn in prev_names[:3])
        parts.append(f"Previous names: {names_str}")
    if ctrl and isinstance(ctrl, dict):
        parts.append(f"Controlling entity: {ctrl.get('name', 'unknown')}")
    if detail.get("ultimate_beneficial_owners"):
        parts.append(f"UBOs: {len(detail['ultimate_beneficial_owners'])}")

    out.append(Evidence(
        evidence_id=f"{entity_id}_oc_summary",
        entity_id=entity_id,
        date=detail.get("incorporation_date") or "",
        source_type="regulator_api",
        risk_category="governance",
        summary=" | ".join(parts)[:5000],
        source_uri=oc_url,
        raw_location=raw_location,
        confidence=0.80,
        attributes={
            "officer_count": officer_count,
            "active_officer_count": len(active_officers),
            "previous_names_count": len(prev_names),
            "has_controlling_entity": ctrl is not None,
            "ubo_count": len(detail.get("ultimate_beneficial_owners") or []),
            "grouping_count": len(detail.get("corporate_groupings") or []),
            "stub": False,
            "data_source": "opencorporates",
        },
    ))

    return out


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def slug_for_entity_name(name: str) -> str:
    """Filesystem-safe slug — same convention as GDELT/CourtListener."""
    return name.lower().split(",")[0].strip().replace(" ", "_").replace(".", "")


def cache_company_json(entity_slug: str, payload: Dict[str, Any], cache_dir: Path) -> Path:
    from osint_swarm.utils.io import write_json, ensure_parent
    out_path = cache_dir / f"oc_{entity_slug}.json"
    ensure_parent(out_path)
    write_json(out_path, payload)
    return out_path


def load_cached_company(entity_slug: str, cache_dir: Path) -> Optional[Dict[str, Any]]:
    from osint_swarm.utils.io import read_json
    path = cache_dir / f"oc_{entity_slug}.json"
    if not path.exists():
        return None
    return read_json(path)
