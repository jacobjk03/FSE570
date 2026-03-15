"""
Tests for the CourtListener API connector
(src/osint_swarm/data_sources/courtlistener.py).

Tests cover:
- Field normalization (camelCase + snake_case)
- Evidence conversion: correct fields, IDs, confidence, risk_category
- Slug generation (matches GdeltProcessor convention)
- Cache read/write round-trip
- API error handling (network failure)
- Empty results
- False-positive risk: unrelated dockets are still included (confidence conveys uncertainty)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from osint_swarm.data_sources.courtlistener import (
    CourtListenerError,
    _get_field,
    _normalize_docket,
    cache_dockets_json,
    dockets_to_evidence_rows,
    fetch_dockets,
    load_cached_dockets,
    slug_for_entity_name,
)


# ---------------------------------------------------------------------------
# Sample API response fixtures
# ---------------------------------------------------------------------------

_CAMEL_DOCKET = {
    "id": 4622426,
    "caseName": "SECURITIES EXCHANGE COMMISSION v. MUSK et al",
    "docketNumber": "3:18-cv-04865",
    "court_id": "cand",
    "dateFiled": "2018-09-27",
    "dateTerminated": None,
    "suitNature": "Securities (850)",
    "cause": "Securities Exchange Act: Disclosure",
    "absolute_url": "/docket/4622426/sec-v-musk/",
}

_SNAKE_DOCKET = {
    "id": 9999999,
    "case_name": "IN RE: TESLA, INC. SECURITIES LITIGATION",
    "docket_number": "3:18-cv-04865",
    "court_id": "cand",
    "date_filed": "2020-01-15",
    "date_terminated": "2022-06-01",
    "suit_nature": "Securities (850)",
    "cause": "Securities Exchange Act",
    "absolute_url": "/docket/9999999/tesla-securities/",
}

_MOCK_RESPONSE = {
    "count": 142,
    "results": [_CAMEL_DOCKET, _SNAKE_DOCKET],
}


# ---------------------------------------------------------------------------
# _get_field helper
# ---------------------------------------------------------------------------

def test_get_field_returns_camel_case():
    assert _get_field(_CAMEL_DOCKET, "caseName", "case_name") == "SECURITIES EXCHANGE COMMISSION v. MUSK et al"


def test_get_field_returns_snake_case_fallback():
    assert _get_field(_SNAKE_DOCKET, "caseName", "case_name") == "IN RE: TESLA, INC. SECURITIES LITIGATION"


def test_get_field_returns_default_when_missing():
    assert _get_field({}, "caseName", "case_name", default="Unknown") == "Unknown"


# ---------------------------------------------------------------------------
# _normalize_docket
# ---------------------------------------------------------------------------

def test_normalize_camel_case_docket():
    n = _normalize_docket(_CAMEL_DOCKET)
    assert n["id"] == 4622426
    assert n["case_name"] == "SECURITIES EXCHANGE COMMISSION v. MUSK et al"
    assert n["docket_number"] == "3:18-cv-04865"
    assert n["court_id"] == "cand"
    assert n["date_filed"] == "2018-09-27"
    assert n["date_terminated"] is None
    assert n["suit_nature"] == "Securities (850)"
    assert n["cause"] == "Securities Exchange Act: Disclosure"
    assert n["absolute_url"] == "https://www.courtlistener.com/docket/4622426/sec-v-musk/"


def test_normalize_snake_case_docket():
    n = _normalize_docket(_SNAKE_DOCKET)
    assert n["case_name"] == "IN RE: TESLA, INC. SECURITIES LITIGATION"
    assert n["date_terminated"] == "2022-06-01"


def test_normalize_prepends_base_url_to_relative_path():
    d = {**_CAMEL_DOCKET, "absolute_url": "/docket/123/some-case/"}
    n = _normalize_docket(d)
    assert n["absolute_url"].startswith("https://www.courtlistener.com/")


def test_normalize_preserves_absolute_url():
    d = {**_CAMEL_DOCKET, "absolute_url": "https://www.courtlistener.com/docket/123/"}
    n = _normalize_docket(d)
    assert n["absolute_url"] == "https://www.courtlistener.com/docket/123/"


def test_normalize_handles_empty_record():
    n = _normalize_docket({})
    assert n["case_name"] == "Unknown Case"
    assert n["date_filed"] == ""
    assert n["date_terminated"] is None


# ---------------------------------------------------------------------------
# dockets_to_evidence_rows
# ---------------------------------------------------------------------------

def test_evidence_rows_count_matches_dockets():
    dockets = [_normalize_docket(_CAMEL_DOCKET), _normalize_docket(_SNAKE_DOCKET)]
    rows = dockets_to_evidence_rows(dockets, "tesla_inc_cik_0001318605", "Tesla, Inc.")
    assert len(rows) == 2


def test_evidence_rows_have_correct_fields():
    dockets = [_normalize_docket(_CAMEL_DOCKET)]
    rows = dockets_to_evidence_rows(dockets, "e1", "Test Corp")
    ev = rows[0]
    assert ev.source_type == "court_record"
    assert ev.risk_category == "legal"
    assert ev.confidence == pytest.approx(0.85)
    assert ev.attributes.get("stub") is False
    assert ev.entity_id == "e1"
    assert "courtlistener" in ev.evidence_id


def test_evidence_rows_summary_contains_case_name():
    dockets = [_normalize_docket(_CAMEL_DOCKET)]
    rows = dockets_to_evidence_rows(dockets, "e1", "Test Corp")
    assert "SECURITIES EXCHANGE COMMISSION" in rows[0].summary


def test_evidence_rows_summary_contains_status_ongoing():
    dockets = [_normalize_docket(_CAMEL_DOCKET)]  # date_terminated = None
    rows = dockets_to_evidence_rows(dockets, "e1", "Test Corp")
    assert "Ongoing" in rows[0].summary or "unknown" in rows[0].summary.lower()


def test_evidence_rows_summary_contains_status_closed():
    dockets = [_normalize_docket(_SNAKE_DOCKET)]  # date_terminated = "2022-06-01"
    rows = dockets_to_evidence_rows(dockets, "e1", "Test Corp")
    assert "2022-06-01" in rows[0].summary


def test_evidence_rows_source_uri_is_courtlistener_url():
    dockets = [_normalize_docket(_CAMEL_DOCKET)]
    rows = dockets_to_evidence_rows(dockets, "e1", "Test Corp")
    assert rows[0].source_uri.startswith("https://www.courtlistener.com/")


def test_evidence_rows_ids_are_unique():
    dockets = [_normalize_docket(_CAMEL_DOCKET), _normalize_docket(_SNAKE_DOCKET)]
    rows = dockets_to_evidence_rows(dockets, "e1", "Test Corp")
    ids = [r.evidence_id for r in rows]
    assert len(ids) == len(set(ids))


def test_evidence_rows_empty_input():
    rows = dockets_to_evidence_rows([], "e1", "Test Corp")
    assert rows == []


# ---------------------------------------------------------------------------
# slug_for_entity_name
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
    payload = {
        "entity_name": "Tesla, Inc.",
        "query": '"Tesla, Inc."',
        "total_found": 142,
        "dockets": [_normalize_docket(_CAMEL_DOCKET)],
    }
    cache_dockets_json("tesla", payload, tmp_path)
    loaded = load_cached_dockets("tesla", tmp_path)
    assert loaded is not None
    assert loaded["total_found"] == 142
    assert len(loaded["dockets"]) == 1


def test_load_cached_returns_none_when_missing(tmp_path: Path):
    result = load_cached_dockets("nonexistent_slug", tmp_path)
    assert result is None


def test_cache_file_name_matches_slug(tmp_path: Path):
    payload = {"entity_name": "Test", "query": "Test", "total_found": 0, "dockets": []}
    cache_dockets_json("my_slug", payload, tmp_path)
    assert (tmp_path / "dockets_my_slug.json").exists()


# ---------------------------------------------------------------------------
# fetch_dockets (mocking requests.get)
# ---------------------------------------------------------------------------

def _mock_response(data: dict, status_code: int = 200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = data
    mock.raise_for_status.return_value = None
    return mock


def test_fetch_dockets_returns_normalized_payload():
    with patch("osint_swarm.data_sources.courtlistener.requests.get") as mock_get:
        mock_get.return_value = _mock_response(_MOCK_RESPONSE)
        result = fetch_dockets("Tesla, Inc.", max_results=20)

    assert result["entity_name"] == "Tesla, Inc."
    assert result["total_found"] == 142
    assert len(result["dockets"]) == 2
    # All dockets must be normalized dicts (not raw camelCase)
    for d in result["dockets"]:
        assert "case_name" in d
        assert "date_filed" in d


def test_fetch_dockets_empty_results():
    with patch("osint_swarm.data_sources.courtlistener.requests.get") as mock_get:
        mock_get.return_value = _mock_response({"count": 0, "results": []})
        result = fetch_dockets("Unknown Corp XYZ", max_results=20)

    assert result["dockets"] == []
    assert result["total_found"] == 0


def test_fetch_dockets_raises_on_network_error():
    import requests as req_lib
    with patch("osint_swarm.data_sources.courtlistener.requests.get") as mock_get:
        mock_get.side_effect = req_lib.exceptions.Timeout("timed out")
        with pytest.raises(CourtListenerError, match="failed"):
            fetch_dockets("Tesla, Inc.")


def test_fetch_dockets_raises_on_http_error():
    with patch("osint_swarm.data_sources.courtlistener.requests.get") as mock_get:
        mock = MagicMock()
        mock.raise_for_status.side_effect = __import__("requests").HTTPError("429 Too Many Requests")
        mock_get.return_value = mock
        with pytest.raises(CourtListenerError):
            fetch_dockets("Tesla, Inc.")


def test_fetch_dockets_respects_max_results():
    many_dockets = [_CAMEL_DOCKET] * 15
    with patch("osint_swarm.data_sources.courtlistener.requests.get") as mock_get:
        mock_get.return_value = _mock_response({"count": 15, "results": many_dockets})
        result = fetch_dockets("Tesla, Inc.", max_results=5)

    # max_results=5 → only first 5 returned
    assert len(result["dockets"]) == 5
