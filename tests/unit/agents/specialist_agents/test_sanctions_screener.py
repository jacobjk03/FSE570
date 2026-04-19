"""
Tests for the OFAC sanctions screener
(agents/specialist_agents/legal_agent/sanctions_screener/screener.py).

Covers:
- Missing cache -> strict DataSourceError
- Clean result (no SDN matches) → correct Evidence structure
- Match found → correct Evidence structure + attributes
- stub flag is False for all real outputs
- confidence is correct (0.90 for live results)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.lead_agent.context_manager import InvestigationContext
from agents.lead_agent.task_planner import SubTask
from agents.specialist_agents.legal_agent.sanctions_screener.screener import screen
from app.investigation_errors import DataSourceError
from osint_swarm.entities import Entity

# Reuse the minimal SDN XML from test_ofac.py
_SDN_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<sdnList xmlns="https://sanctionssearch.ofac.treas.gov/">
  <sdnEntry>
    <uid>1001</uid>
    <lastName>BLACKROCK TRADING CORP</lastName>
    <sdnType>Entity</sdnType>
    <programList>
      <program>SDGT</program>
    </programList>
    <akaList>
      <aka>
        <uid>1002</uid>
        <type>a.k.a.</type>
        <lastName>BRT CORP</lastName>
      </aka>
    </akaList>
    <addressList/>
    <remarks>Sanctioned entity.</remarks>
  </sdnEntry>
  <sdnEntry>
    <uid>2001</uid>
    <lastName>EVIL OIL EXPORT LLC</lastName>
    <sdnType>Entity</sdnType>
    <programList>
      <program>IRAN</program>
    </programList>
    <akaList/>
    <addressList/>
    <remarks/>
  </sdnEntry>
</sdnList>
"""

_TASK = SubTask("sanctions_screening", "legal_agent", "Screen for OFAC sanctions")
_CTX = InvestigationContext()


def _make_sdn_cache(tmp_path: Path) -> Path:
    ofac_dir = tmp_path / "raw" / "ofac"
    ofac_dir.mkdir(parents=True)
    sdn_path = ofac_dir / "sdn.xml"
    sdn_path.write_text(_SDN_XML, encoding="utf-8")
    return sdn_path


# ---------------------------------------------------------------------------
# Strict failure: cache missing
# ---------------------------------------------------------------------------

def test_screener_raises_when_cache_missing(tmp_path: Path):
    entity = Entity(entity_id="tesla_inc_cik_0001318605", name="Tesla, Inc.", identifiers={})
    with pytest.raises(DataSourceError):
        screen(entity, _TASK, _CTX, data_root=tmp_path)


# ---------------------------------------------------------------------------
# Clean result: entity NOT on SDN list
# ---------------------------------------------------------------------------

def test_screener_clean_for_tesla(tmp_path: Path):
    _make_sdn_cache(tmp_path)
    entity = Entity(
        entity_id="tesla_inc_cik_0001318605",
        name="Tesla, Inc.",
        identifiers={"cik": "0001318605"},
        aliases=["Tesla", "Tesla Inc", "Tesla Motors", "TSLA"],
    )
    result = screen(entity, _TASK, _CTX, data_root=tmp_path)

    assert len(result) == 1
    ev = result[0]
    assert ev.confidence == pytest.approx(0.90)
    assert ev.risk_category == "legal"
    assert ev.source_type == "regulator_api"
    assert "no matches" in ev.summary.lower()
    assert ev.attributes.get("sdn_matches") == 0
    assert ev.attributes.get("screened") is True
    assert ev.attributes.get("stub") is False


def test_screener_clean_result_mentions_entry_count(tmp_path: Path):
    """Evidence summary should tell the analyst how many entries were screened."""
    _make_sdn_cache(tmp_path)
    entity = Entity(entity_id="e1", name="Some Unknown Corp", identifiers={})
    result = screen(entity, _TASK, _CTX, data_root=tmp_path)
    # Our test XML has 2 entries; summary should mention a number
    assert any(char.isdigit() for char in result[0].summary)


# ---------------------------------------------------------------------------
# Match found: entity IS on SDN list
# ---------------------------------------------------------------------------

def test_screener_finds_match_by_name(tmp_path: Path):
    _make_sdn_cache(tmp_path)
    entity = Entity(entity_id="bad_co_001", name="BLACKROCK TRADING CORP", identifiers={})
    result = screen(entity, _TASK, _CTX, data_root=tmp_path)

    assert len(result) == 1
    ev = result[0]
    assert ev.confidence == pytest.approx(0.90)
    assert ev.risk_category == "legal"
    assert "match" in ev.summary.lower() or "sdnt" in ev.summary.lower() or "⚠" in ev.summary
    assert ev.attributes.get("sdn_matches") == 1
    assert ev.attributes.get("sdn_uid") == "1001"
    assert ev.attributes.get("screened") is True
    assert ev.attributes.get("stub") is False


def test_screener_finds_match_via_alias(tmp_path: Path):
    """Searching by alias 'BRT CORP' should match SDN entry 1001."""
    _make_sdn_cache(tmp_path)
    entity = Entity(
        entity_id="some_company",
        name="Unknown Name",
        identifiers={},
        aliases=["BRT CORP"],
    )
    result = screen(entity, _TASK, _CTX, data_root=tmp_path)

    assert len(result) == 1
    assert result[0].attributes.get("sdn_uid") == "1001"
    assert result[0].attributes.get("stub") is False


def test_screener_returns_multiple_rows_for_multiple_matches(tmp_path: Path):
    """Two separate SDN entries should produce two separate Evidence rows."""
    _make_sdn_cache(tmp_path)
    # Use an alias list that matches both SDN entries
    entity = Entity(
        entity_id="e_multi",
        name="BLACKROCK TRADING CORP",
        identifiers={},
        aliases=["EVIL OIL EXPORT LLC"],
    )
    result = screen(entity, _TASK, _CTX, data_root=tmp_path)
    assert len(result) == 2
    uids = {ev.attributes.get("sdn_uid") for ev in result}
    assert "1001" in uids
    assert "2001" in uids


# ---------------------------------------------------------------------------
# Evidence ID uniqueness
# ---------------------------------------------------------------------------

def test_screener_evidence_ids_are_unique(tmp_path: Path):
    _make_sdn_cache(tmp_path)
    entity = Entity(
        entity_id="e_multi",
        name="BLACKROCK TRADING CORP",
        identifiers={},
        aliases=["EVIL OIL EXPORT LLC"],
    )
    result = screen(entity, _TASK, _CTX, data_root=tmp_path)
    ids = [ev.evidence_id for ev in result]
    assert len(ids) == len(set(ids)), "Duplicate evidence_ids returned"


# ---------------------------------------------------------------------------
# Integration: through LegalAgent
# ---------------------------------------------------------------------------

def test_legal_agent_uses_real_screener_with_data_root(tmp_path: Path):
    """LegalAgent.run() should call the real screener when data_root has an SDN cache."""
    _make_sdn_cache(tmp_path)
    from agents.specialist_agents.legal_agent import LegalAgent

    from agents.specialist_agents.legal_agent import agent as legal_agent_module

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            legal_agent_module,
            "choose_next_tool",
            lambda **_kwargs: {
                "selected_tool": "ofac",
                "alternatives": [],
                "policy_used": "llm_action_policy",
                "reasoning": "Use sanctions screening first.",
            },
        )
        agent = LegalAgent(data_root=tmp_path)
        entity = Entity(entity_id="tesla_inc_cik_0001318605", name="Tesla, Inc.", identifiers={})
        task = SubTask("sanctions_screening", "legal_agent", "Screen for OFAC")
        ctx = InvestigationContext()

        findings = agent.run(entity, task, ctx)

    assert len(findings) == 1
    ev = findings[0]
    # Tesla should be clean
    assert ev.attributes.get("sdn_matches") == 0
    assert ev.attributes.get("stub") is False
    assert ev.confidence == pytest.approx(0.90)


def test_legal_agent_no_cache_raises_data_error(tmp_path: Path):
    """Without SDN cache, LegalAgent should hard-fail in strict mode."""
    from agents.specialist_agents.legal_agent import LegalAgent
    from agents.specialist_agents.legal_agent import agent as legal_agent_module

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            legal_agent_module,
            "choose_next_tool",
            lambda **_kwargs: {
                "selected_tool": "ofac",
                "alternatives": [],
                "policy_used": "llm_action_policy",
                "reasoning": "Use sanctions screening first.",
            },
        )
        agent = LegalAgent(data_root=tmp_path)  # no sdn.xml in tmp_path
        entity = Entity(entity_id="e1", name="Any Corp", identifiers={})
        task = SubTask("sanctions_screening", "legal_agent", "Screen")
        ctx = InvestigationContext()

        with pytest.raises(DataSourceError):
            agent.run(entity, task, ctx)
