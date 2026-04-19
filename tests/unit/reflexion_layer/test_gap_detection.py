"""Tests for reflexion gap detection."""

from agents.lead_agent.context_manager import InvestigationContext
from reflexion_layer.gap_detection import detect_gaps
from osint_swarm.entities import Entity, Evidence


def test_detect_gaps_no_entity_returns_entity_resolution_gap():
    ctx = InvestigationContext()
    ctx.set_query("Investigate XYZ")
    gaps = detect_gaps(ctx)
    assert len(gaps) >= 1
    assert any(g.area == "entity_resolution" for g in gaps)


def test_detect_gaps_legal_empty_returns_sanctions_gap():
    """No legal results at all → gap flagged."""
    ctx = InvestigationContext()
    ctx.set_entity(Entity(entity_id="e1", name="E", identifiers={}))
    # No results added for legal_agent
    gaps = detect_gaps(ctx)
    assert any("Sanctions" in g.area or "legal" in g.description.lower() for g in gaps)


def test_detect_gaps_legal_placeholder_returns_gap():
    """Legal evidence without screened flag should still produce legal gap."""
    ctx = InvestigationContext()
    ctx.set_entity(Entity(entity_id="e1", name="E", identifiers={}))
    fallback_ev = Evidence(
        "e1_legal_placeholder", "e1", "2026-03-15",
        "regulator_api", "legal",
        "Legal lane executed without screening metadata.",
        "https://sanctionssearch.ofac.treas.gov/",
        None, 0.0,
        {"stub": False},
    )
    ctx.add_agent_results("legal_agent", [fallback_ev])
    gaps = detect_gaps(ctx)
    assert any("Sanctions" in g.area or "legal" in g.description.lower() for g in gaps)


def test_detect_gaps_legal_real_screening_no_gap():
    """A real OFAC screening result (screened=True, confidence=0.90) → no sanctions gap."""
    ctx = InvestigationContext()
    ctx.set_entity(Entity(entity_id="e1", name="E", identifiers={}))
    clean_ev = Evidence(
        "e1_ofac_clean", "e1", "2026-03-15",
        "regulator_api", "legal",
        "OFAC SDN screening: No matches found for 'E'. Entity does not appear on SDN list (13000 entries screened).",
        "https://sanctionssearch.ofac.treas.gov/",
        "data/raw/ofac/sdn.xml", 0.90,
        {"sdn_matches": 0, "entries_screened": 13000, "screened": True, "stub": False},
    )
    ctx.add_agent_results("legal_agent", [clean_ev])
    # Also add social_graph and corporate_agent results to avoid other gaps
    news_ev = Evidence("e1_gdelt_1", "e1", "2026-03-15", "news_article", "network", "Some news", "https://example.com", None, 0.6, {})
    ctx.add_agent_results("social_graph_agent", [news_ev])
    gaps = detect_gaps(ctx)
    assert not any("Sanctions" in g.area for g in gaps)


def test_detect_gaps_social_empty_returns_gap():
    """Social graph agent returns no evidence → gap flagged (GDELT cache missing)."""
    ctx = InvestigationContext()
    ctx.set_entity(Entity(entity_id="e1", name="E", identifiers={}))
    gaps = detect_gaps(ctx)
    assert any("Adverse" in g.area or "network" in g.description.lower() or "Social" in g.area for g in gaps)


def test_detect_gaps_court_placeholder_returns_gap():
    """Court result without screening metadata should produce legal gap."""
    ctx = InvestigationContext()
    ctx.set_entity(Entity(entity_id="e1", name="E", identifiers={}))
    error_ev = Evidence(
        "e1_courtlistener_placeholder", "e1", "2026-03-15",
        "court_record", "legal",
        "Court lane produced placeholder output.",
        "https://www.courtlistener.com/", None, 0.0,
        {"stub": False},
    )
    ctx.add_agent_results("legal_agent", [error_ev])
    gaps = detect_gaps(ctx)
    assert any("Sanctions" in g.area or "legal" in g.description.lower() for g in gaps)


