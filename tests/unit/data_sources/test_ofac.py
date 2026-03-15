"""
Tests for the OFAC SDN connector (src/osint_swarm/data_sources/ofac.py).

Tests cover:
- XML parsing (valid, empty, malformed)
- Name normalization
- Matching: exact, alias, case-insensitive, partial, false-positive prevention
- Clean result (no match) vs hit result
- Entity type filtering
"""

from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from osint_swarm.data_sources.ofac import (
    OfacError,
    _normalize,
    _terms_match,
    parse_sdn_entries,
    search_entries,
)


# ---------------------------------------------------------------------------
# Minimal but realistic OFAC SDN XML fixture
# Names are fictional/composite to avoid referencing real people
# Structure matches the actual OFAC XML schema exactly
# ---------------------------------------------------------------------------

_SDN_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<sdnList xmlns="https://sanctionssearch.ofac.treas.gov/"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <!-- Entity 1: Fictional sanctioned company -->
  <sdnEntry>
    <uid>1001</uid>
    <lastName>BLACKROCK TRADING CORP</lastName>
    <sdnType>Entity</sdnType>
    <programList>
      <program>SDGT</program>
      <program>IRGC</program>
    </programList>
    <akaList>
      <aka>
        <uid>1002</uid>
        <type>a.k.a.</type>
        <lastName>BRT CORP</lastName>
      </aka>
      <aka>
        <uid>1003</uid>
        <type>f.k.a.</type>
        <lastName>BLACKROCK TRADE</lastName>
      </aka>
    </akaList>
    <addressList>
      <address>
        <city>Tehran</city>
        <country>Iran</country>
      </address>
    </addressList>
    <remarks>Involved in illicit financial transactions.</remarks>
  </sdnEntry>
  <!-- Entity 2: Fictional sanctioned individual -->
  <sdnEntry>
    <uid>2001</uid>
    <firstName>IVAN</firstName>
    <lastName>PETROV</lastName>
    <sdnType>Individual</sdnType>
    <programList>
      <program>RUSSIA-EO14024</program>
    </programList>
    <akaList/>
    <addressList>
      <address>
        <city>Moscow</city>
        <country>Russia</country>
      </address>
    </addressList>
    <remarks>Russian oligarch.</remarks>
  </sdnEntry>
  <!-- Entity 3: Vessel -->
  <sdnEntry>
    <uid>3001</uid>
    <lastName>DARK STAR</lastName>
    <sdnType>Vessel</sdnType>
    <programList>
      <program>IRAN</program>
    </programList>
    <akaList/>
    <addressList/>
    <remarks/>
  </sdnEntry>
  <!-- Entity 4: Similar name to "Stanford" to test false-positive prevention -->
  <sdnEntry>
    <uid>4001</uid>
    <lastName>OXFORD FINANCIAL HOLDINGS</lastName>
    <sdnType>Entity</sdnType>
    <programList>
      <program>SDGT</program>
    </programList>
    <akaList/>
    <addressList/>
    <remarks/>
  </sdnEntry>
  <!-- Entity 5: Company with name overlapping common words -->
  <sdnEntry>
    <uid>5001</uid>
    <lastName>GLOBAL MOTORS EXPORT</lastName>
    <sdnType>Entity</sdnType>
    <programList>
      <program>IRAN</program>
    </programList>
    <akaList>
      <aka>
        <uid>5002</uid>
        <type>a.k.a.</type>
        <lastName>GME CORP</lastName>
      </aka>
    </akaList>
    <addressList/>
    <remarks/>
  </sdnEntry>
</sdnList>
"""


@pytest.fixture()
def sdn_xml_path(tmp_path: Path) -> Path:
    p = tmp_path / "sdn.xml"
    p.write_text(_SDN_XML, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Parsing tests
# ---------------------------------------------------------------------------

def test_parse_returns_correct_entry_count(sdn_xml_path):
    entries = parse_sdn_entries(sdn_xml_path)
    assert len(entries) == 5


def test_parse_entity_fields(sdn_xml_path):
    entries = parse_sdn_entries(sdn_xml_path)
    corp = next(e for e in entries if e["uid"] == "1001")
    assert corp["name"] == "BLACKROCK TRADING CORP"
    assert corp["sdn_type"] == "Entity"
    assert "SDGT" in corp["programs"]
    assert "IRGC" in corp["programs"]
    assert "BRT CORP" in corp["aka_names"]
    assert "BLACKROCK TRADE" in corp["aka_names"]
    assert "illicit financial" in corp["remarks"]


def test_parse_individual_fields(sdn_xml_path):
    entries = parse_sdn_entries(sdn_xml_path)
    person = next(e for e in entries if e["uid"] == "2001")
    assert person["name"] == "IVAN PETROV"
    assert person["sdn_type"] == "Individual"
    assert "RUSSIA-EO14024" in person["programs"]
    assert person["aka_names"] == []


def test_parse_vessel(sdn_xml_path):
    entries = parse_sdn_entries(sdn_xml_path)
    vessel = next(e for e in entries if e["uid"] == "3001")
    assert vessel["name"] == "DARK STAR"
    assert vessel["sdn_type"] == "Vessel"


def test_parse_empty_xml(tmp_path: Path):
    p = tmp_path / "empty.xml"
    p.write_text(
        '<?xml version="1.0"?><sdnList xmlns="https://sanctionssearch.ofac.treas.gov/"></sdnList>',
        encoding="utf-8",
    )
    entries = parse_sdn_entries(p)
    assert entries == []


def test_parse_malformed_xml_raises(tmp_path: Path):
    p = tmp_path / "bad.xml"
    p.write_text("<not valid xml <<>>", encoding="utf-8")
    with pytest.raises(OfacError, match="parse"):
        parse_sdn_entries(p)


# ---------------------------------------------------------------------------
# Normalization tests
# ---------------------------------------------------------------------------

def test_normalize_strips_punctuation():
    assert _normalize("Tesla, Inc.") == "tesla"


def test_normalize_removes_legal_suffixes():
    assert _normalize("Ford Motor Company") == "ford motor"
    assert _normalize("Goldman Sachs LLC") == "goldman sachs"
    assert _normalize("BLACKROCK TRADING CORP") == "blackrock trading"


def test_normalize_case_insensitive():
    assert _normalize("BOEING") == "boeing"
    assert _normalize("Boeing") == "boeing"


def test_normalize_collapses_spaces():
    assert _normalize("  Acme   Corp  ") == "acme"


# ---------------------------------------------------------------------------
# Matching function tests
# ---------------------------------------------------------------------------

def test_terms_match_exact():
    assert _terms_match("blackrock trading", "blackrock trading") is True


def test_terms_match_query_in_target():
    assert _terms_match("blackrock", "blackrock trading corp") is True


def test_terms_match_target_in_query():
    # Searching for "BLACKROCK TRADING CORP" matches shorter SDN entry "BLACKROCK"
    assert _terms_match("blackrock trading corp", "blackrock") is True


def test_terms_match_false_positive_oxford_vs_ford():
    # "ford" should NOT match "oxford" because "ford" is NOT a whole word in "oxford"
    assert _terms_match("ford", "oxford financial") is False


def test_terms_match_false_positive_stanford():
    assert _terms_match("ford", "stanford chemicals") is False


def test_terms_match_too_short_query():
    # Terms shorter than 5 chars don't trigger substring rule
    assert _terms_match("ba", "bagram air base") is False


def test_terms_match_case_handled_before_call():
    # _terms_match works on already-normalized (lowercased) strings
    assert _terms_match("global motors", "global motors export") is True


# ---------------------------------------------------------------------------
# Search (end-to-end matching) tests
# ---------------------------------------------------------------------------

def test_search_finds_entity_by_exact_name(sdn_xml_path):
    entries = parse_sdn_entries(sdn_xml_path)
    matches = search_entries(entries, "BLACKROCK TRADING CORP")
    assert len(matches) == 1
    assert matches[0]["uid"] == "1001"


def test_search_finds_entity_case_insensitive(sdn_xml_path):
    entries = parse_sdn_entries(sdn_xml_path)
    matches = search_entries(entries, "blackrock trading corp")
    assert len(matches) == 1
    assert matches[0]["uid"] == "1001"


def test_search_finds_entity_by_alias(sdn_xml_path):
    entries = parse_sdn_entries(sdn_xml_path)
    # "BRT CORP" is an alias for entry 1001
    matches = search_entries(entries, "BRT CORP")
    assert len(matches) == 1
    assert matches[0]["uid"] == "1001"


def test_search_finds_entity_via_caller_aliases(sdn_xml_path):
    """If entity's own alias list matches an SDN entry, it's found."""
    entries = parse_sdn_entries(sdn_xml_path)
    # Entity registered as "SomeCompany" but has alias "GLOBAL MOTORS EXPORT"
    matches = search_entries(
        entries, "SomeCompany Inc", aliases=["GLOBAL MOTORS EXPORT"]
    )
    assert len(matches) == 1
    assert matches[0]["uid"] == "5001"


def test_search_clean_for_known_us_companies(sdn_xml_path):
    """Tesla, Ford, Boeing should return zero matches in our test XML."""
    entries = parse_sdn_entries(sdn_xml_path)
    for name in ["Tesla, Inc.", "Ford Motor Company", "The Boeing Company"]:
        matches = search_entries(entries, name)
        assert matches == [], f"Unexpected match for {name!r}: {matches}"


def test_search_no_false_positive_ford_in_oxford(sdn_xml_path):
    """'Ford Motor Company' must NOT match 'OXFORD FINANCIAL HOLDINGS'."""
    entries = parse_sdn_entries(sdn_xml_path)
    ford_matches = search_entries(entries, "Ford Motor Company")
    uids = {m["uid"] for m in ford_matches}
    assert "4001" not in uids  # OXFORD entry should NOT be a hit


def test_search_returns_empty_list_for_unknown(sdn_xml_path):
    entries = parse_sdn_entries(sdn_xml_path)
    matches = search_entries(entries, "XYZ Completely Unknown Corp 99999")
    assert matches == []


def test_search_no_duplicate_uids(sdn_xml_path):
    """Same entry must not appear twice even if multiple terms hit it."""
    entries = parse_sdn_entries(sdn_xml_path)
    matches = search_entries(
        entries, "BLACKROCK TRADING CORP", aliases=["BRT CORP", "BLACKROCK TRADE"]
    )
    uids = [m["uid"] for m in matches]
    assert len(uids) == len(set(uids)), "Duplicate UIDs returned"
    assert len(matches) == 1
