"""
Tests for the OpenCorporates API connector
(src/osint_swarm/data_sources/opencorporates.py).

Tests cover:
- Company search normalization
- Company detail normalization (officers, UBOs, controlling entity, groupings)
- Evidence conversion: correct fields, IDs, confidence, risk_category
- Slug generation (consistent with GDELT/CourtListener)
- Cache read/write round-trip
- API error handling (missing token, network failure)
- Empty results
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from osint_swarm.data_sources.opencorporates import (
    OpenCorporatesError,
    _normalize_company_detail,
    _normalize_company_search,
    cache_company_json,
    company_detail_to_evidence,
    load_cached_company,
    slug_for_entity_name,
)


# ---------------------------------------------------------------------------
# Sample API response fixtures
# ---------------------------------------------------------------------------

_SEARCH_COMPANY_RAW = {
    "name": "TESLA, INC.",
    "company_number": "C3259768",
    "jurisdiction_code": "us_ca",
    "company_type": "Stock Corporation - CA - General",
    "current_status": "Active",
    "incorporation_date": "2003-07-01",
    "dissolution_date": None,
    "inactive": False,
    "opencorporates_url": "https://opencorporates.com/companies/us_ca/C3259768",
    "registered_address_in_full": "3500 DEER CREEK ROAD, PALO ALTO, CA 94304",
}

_DETAIL_COMPANY_RAW = {
    "name": "TESLA, INC.",
    "company_number": "C3259768",
    "jurisdiction_code": "us_ca",
    "company_type": "Stock Corporation - CA - General",
    "current_status": "Active",
    "incorporation_date": "2003-07-01",
    "dissolution_date": None,
    "inactive": False,
    "opencorporates_url": "https://opencorporates.com/companies/us_ca/C3259768",
    "registered_address_in_full": "3500 DEER CREEK ROAD, PALO ALTO, CA 94304",
    "officers": [
        {"officer": {"id": 1001, "name": "ELON MUSK", "position": "chief executive officer", "start_date": "2008-10-01", "end_date": None, "opencorporates_url": "https://opencorporates.com/officers/1001"}},
        {"officer": {"id": 1002, "name": "VAIBHAV TANEJA", "position": "chief financial officer", "start_date": "2023-08-01", "end_date": None, "opencorporates_url": "https://opencorporates.com/officers/1002"}},
        {"officer": {"id": 1003, "name": "ZACHARY KIRKHORN", "position": "chief financial officer", "start_date": "2019-03-01", "end_date": "2023-08-01", "opencorporates_url": "https://opencorporates.com/officers/1003"}},
    ],
    "corporate_groupings": [
        {"corporate_grouping": {"name": "tesla", "opencorporates_url": "https://opencorporates.com/corporate_groupings/tesla", "wikipedia_id": "Tesla,_Inc."}},
    ],
    "previous_names": [
        {"company_name": "TESLA MOTORS, INC.", "con_date": "2017-02-01"},
    ],
    "controlling_entity": {"name": "Elon Musk", "opencorporates_url": "https://opencorporates.com/placeholder/elon-musk"},
    "ultimate_beneficial_owners": [
        {"name": "Elon Musk", "opencorporates_url": "https://opencorporates.com/placeholder/elon-musk"},
    ],
    "ultimate_controlling_company": None,
    "industry_codes": [],
}


# ---------------------------------------------------------------------------
# Normalization tests: company search
# ---------------------------------------------------------------------------

def test_normalize_company_search_extracts_fields():
    n = _normalize_company_search(_SEARCH_COMPANY_RAW)
    assert n["name"] == "TESLA, INC."
    assert n["company_number"] == "C3259768"
    assert n["jurisdiction_code"] == "us_ca"
    assert n["current_status"] == "Active"
    assert n["inactive"] is False


def test_normalize_company_search_handles_empty_record():
    n = _normalize_company_search({})
    assert n["name"] == ""
    assert n["company_number"] == ""


# ---------------------------------------------------------------------------
# Normalization tests: company detail
# ---------------------------------------------------------------------------

def test_normalize_detail_extracts_officers():
    d = _normalize_company_detail(_DETAIL_COMPANY_RAW)
    assert len(d["officers"]) == 3
    assert d["officers"][0]["name"] == "ELON MUSK"
    assert d["officers"][0]["position"] == "chief executive officer"
    assert d["officers"][0]["end_date"] is None
    assert d["officers"][2]["end_date"] == "2023-08-01"


def test_normalize_detail_extracts_corporate_groupings():
    d = _normalize_company_detail(_DETAIL_COMPANY_RAW)
    assert len(d["corporate_groupings"]) == 1
    assert d["corporate_groupings"][0]["name"] == "tesla"


def test_normalize_detail_extracts_previous_names():
    d = _normalize_company_detail(_DETAIL_COMPANY_RAW)
    assert len(d["previous_names"]) == 1
    assert d["previous_names"][0]["company_name"] == "TESLA MOTORS, INC."


def test_normalize_detail_extracts_controlling_entity():
    d = _normalize_company_detail(_DETAIL_COMPANY_RAW)
    assert d["controlling_entity"]["name"] == "Elon Musk"


def test_normalize_detail_extracts_ubos():
    d = _normalize_company_detail(_DETAIL_COMPANY_RAW)
    assert len(d["ultimate_beneficial_owners"]) == 1


def test_normalize_detail_handles_empty_record():
    d = _normalize_company_detail({})
    assert d["officers"] == []
    assert d["corporate_groupings"] == []
    assert d["controlling_entity"] is None
    assert d["ultimate_beneficial_owners"] == []


# ---------------------------------------------------------------------------
# Evidence conversion tests
# ---------------------------------------------------------------------------

def test_evidence_includes_officers():
    d = _normalize_company_detail(_DETAIL_COMPANY_RAW)
    rows = company_detail_to_evidence(d, "tesla_e1", "Tesla, Inc.")
    officer_rows = [r for r in rows if r.attributes.get("officer_name")]
    assert len(officer_rows) == 3
    names = {r.attributes["officer_name"] for r in officer_rows}
    assert "ELON MUSK" in names
    assert "VAIBHAV TANEJA" in names


def test_evidence_officers_have_correct_fields():
    d = _normalize_company_detail(_DETAIL_COMPANY_RAW)
    rows = company_detail_to_evidence(d, "e1", "Tesla")
    officer = next(r for r in rows if r.attributes.get("officer_name") == "ELON MUSK")
    assert officer.source_type == "regulator_api"
    assert officer.risk_category == "governance"
    assert officer.confidence == pytest.approx(0.80)
    assert officer.attributes["stub"] is False
    assert officer.attributes["data_source"] == "opencorporates"
    assert "chief executive officer" in officer.summary.lower()


def test_evidence_includes_controlling_entity():
    d = _normalize_company_detail(_DETAIL_COMPANY_RAW)
    rows = company_detail_to_evidence(d, "e1", "Tesla")
    ctrl_rows = [r for r in rows if r.attributes.get("relationship") == "controlling_entity"]
    assert len(ctrl_rows) == 1
    assert ctrl_rows[0].confidence == pytest.approx(0.85)
    assert "Elon Musk" in ctrl_rows[0].summary


def test_evidence_includes_ubos():
    d = _normalize_company_detail(_DETAIL_COMPANY_RAW)
    rows = company_detail_to_evidence(d, "e1", "Tesla")
    ubo_rows = [r for r in rows if r.attributes.get("relationship") == "ultimate_beneficial_owner"]
    assert len(ubo_rows) == 1
    assert ubo_rows[0].confidence == pytest.approx(0.85)


def test_evidence_includes_corporate_groupings():
    d = _normalize_company_detail(_DETAIL_COMPANY_RAW)
    rows = company_detail_to_evidence(d, "e1", "Tesla")
    group_rows = [r for r in rows if r.attributes.get("relationship") == "corporate_grouping"]
    assert len(group_rows) == 1
    assert group_rows[0].attributes["grouping_name"] == "tesla"
    assert group_rows[0].confidence == pytest.approx(0.75)


def test_evidence_includes_summary_row():
    d = _normalize_company_detail(_DETAIL_COMPANY_RAW)
    rows = company_detail_to_evidence(d, "e1", "Tesla")
    summary = next(r for r in rows if r.evidence_id == "e1_oc_summary")
    assert summary.attributes["officer_count"] == 3
    assert summary.attributes["active_officer_count"] == 2
    assert summary.attributes["has_controlling_entity"] is True
    assert summary.attributes["ubo_count"] == 1
    assert summary.attributes["stub"] is False


def test_evidence_total_count():
    """3 officers + 1 controlling entity + 1 UBO + 1 grouping + 1 summary = 7."""
    d = _normalize_company_detail(_DETAIL_COMPANY_RAW)
    rows = company_detail_to_evidence(d, "e1", "Tesla")
    assert len(rows) == 7


def test_evidence_ids_are_unique():
    d = _normalize_company_detail(_DETAIL_COMPANY_RAW)
    rows = company_detail_to_evidence(d, "e1", "Tesla")
    ids = [r.evidence_id for r in rows]
    assert len(ids) == len(set(ids))


def test_evidence_empty_detail_returns_summary_only():
    d = _normalize_company_detail({})
    rows = company_detail_to_evidence(d, "e1", "Unknown Corp")
    assert len(rows) == 1
    assert rows[0].evidence_id == "e1_oc_summary"


def test_evidence_no_controlling_entity():
    detail = {**_DETAIL_COMPANY_RAW, "controlling_entity": None}
    d = _normalize_company_detail(detail)
    rows = company_detail_to_evidence(d, "e1", "Tesla")
    ctrl = [r for r in rows if r.attributes.get("relationship") == "controlling_entity"]
    assert len(ctrl) == 0


def test_evidence_no_ubos():
    detail = {**_DETAIL_COMPANY_RAW, "ultimate_beneficial_owners": []}
    d = _normalize_company_detail(detail)
    rows = company_detail_to_evidence(d, "e1", "Tesla")
    ubo = [r for r in rows if r.attributes.get("relationship") == "ultimate_beneficial_owner"]
    assert len(ubo) == 0


# ---------------------------------------------------------------------------
# Slug generation
# ---------------------------------------------------------------------------

def test_slug_tesla():
    assert slug_for_entity_name("Tesla, Inc.") == "tesla"


def test_slug_ford():
    assert slug_for_entity_name("Ford Motor Company") == "ford_motor_company"


def test_slug_boeing():
    assert slug_for_entity_name("The Boeing Company") == "the_boeing_company"


# ---------------------------------------------------------------------------
# Cache read/write
# ---------------------------------------------------------------------------

def test_cache_write_and_load_round_trip(tmp_path: Path):
    d = _normalize_company_detail(_DETAIL_COMPANY_RAW)
    payload = {"search": {"entity_name": "Tesla", "total_count": 1, "companies": []}, "detail": d}
    cache_company_json("tesla", payload, tmp_path)
    loaded = load_cached_company("tesla", tmp_path)
    assert loaded is not None
    assert loaded["detail"]["name"] == "TESLA, INC."
    assert len(loaded["detail"]["officers"]) == 3


def test_load_cached_returns_none_when_missing(tmp_path: Path):
    assert load_cached_company("nonexistent", tmp_path) is None


def test_cache_file_name_matches_slug(tmp_path: Path):
    payload = {"search": {}, "detail": {}}
    cache_company_json("my_slug", payload, tmp_path)
    assert (tmp_path / "oc_my_slug.json").exists()


# ---------------------------------------------------------------------------
# API error handling (mocking)
# ---------------------------------------------------------------------------

def test_search_raises_on_missing_token():
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(OpenCorporatesError, match="token"):
            from osint_swarm.data_sources.opencorporates import search_companies
            search_companies("Tesla")


def test_search_raises_on_network_error():
    import requests as req_lib
    with patch.dict("os.environ", {"OPENCORPORATES_API_TOKEN": "test123"}):
        with patch("osint_swarm.data_sources.opencorporates.requests.get") as mock_get:
            mock_get.side_effect = req_lib.exceptions.Timeout("timed out")
            with pytest.raises(OpenCorporatesError, match="failed"):
                from osint_swarm.data_sources.opencorporates import search_companies
                search_companies("Tesla")


def test_fetch_detail_raises_on_http_error():
    with patch.dict("os.environ", {"OPENCORPORATES_API_TOKEN": "test123"}):
        with patch("osint_swarm.data_sources.opencorporates.requests.get") as mock_get:
            mock = MagicMock()
            mock.raise_for_status.side_effect = __import__("requests").HTTPError("403 Forbidden")
            mock_get.return_value = mock
            with pytest.raises(OpenCorporatesError):
                from osint_swarm.data_sources.opencorporates import fetch_company_detail
                fetch_company_detail("us_ca", "C3259768")


# ---------------------------------------------------------------------------
# Mocked successful API calls
# ---------------------------------------------------------------------------

def _mock_response(data: dict, status_code: int = 200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = data
    mock.raise_for_status.return_value = None
    return mock


def test_search_companies_returns_normalized():
    mock_data = {
        "results": {
            "companies": [{"company": _SEARCH_COMPANY_RAW}],
            "total_count": 42,
            "page": 1,
            "per_page": 30,
        }
    }
    with patch.dict("os.environ", {"OPENCORPORATES_API_TOKEN": "test123"}):
        with patch("osint_swarm.data_sources.opencorporates.requests.get") as mock_get:
            mock_get.return_value = _mock_response(mock_data)
            from osint_swarm.data_sources.opencorporates import search_companies
            result = search_companies("Tesla")

    assert result["total_count"] == 42
    assert len(result["companies"]) == 1
    assert result["companies"][0]["name"] == "TESLA, INC."


def test_fetch_company_detail_returns_normalized():
    mock_data = {"results": {"company": _DETAIL_COMPANY_RAW}}
    with patch.dict("os.environ", {"OPENCORPORATES_API_TOKEN": "test123"}):
        with patch("osint_swarm.data_sources.opencorporates.requests.get") as mock_get:
            mock_get.return_value = _mock_response(mock_data)
            from osint_swarm.data_sources.opencorporates import fetch_company_detail
            result = fetch_company_detail("us_ca", "C3259768")

    assert result["name"] == "TESLA, INC."
    assert len(result["officers"]) == 3
    assert result["controlling_entity"]["name"] == "Elon Musk"
