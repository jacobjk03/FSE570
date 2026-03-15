"""Tests for Social Graph Agent (GDELT adverse media)."""

import json
from pathlib import Path

import pytest

from agents.lead_agent.context_manager import InvestigationContext
from agents.lead_agent.task_planner import SubTask
from agents.specialist_agents.social_graph_agent import SocialGraphAgent
from osint_swarm.entities import Entity


def test_social_graph_agent_agent_id():
    agent = SocialGraphAgent()
    assert agent.agent_id == "social_graph_agent"


def test_social_graph_agent_returns_empty_without_cache(tmp_path: Path):
    """No GDELT cache → returns empty list (no live network call in tests)."""
    import osint_swarm.data_sources.gdelt as gdelt_mod

    original = gdelt_mod.fetch_news_for_entity

    def _raise(*args, **kwargs):
        raise gdelt_mod.GdeltError("Mocked network error")

    gdelt_mod.fetch_news_for_entity = _raise
    try:
        agent = SocialGraphAgent(data_root=tmp_path)
        entity = Entity(entity_id="e1", name="E Corp", identifiers={})
        task = SubTask("adverse_media", "social_graph_agent", "Adverse media")
        ctx = InvestigationContext()
        findings = agent.run(entity, task, ctx)
        assert findings == []
    finally:
        gdelt_mod.fetch_news_for_entity = original


def test_social_graph_agent_returns_gdelt_evidence_with_cache(tmp_path: Path):
    """With a GDELT cache, both adverse_media and network_analysis return news articles."""
    raw_dir = tmp_path / "raw" / "gdelt"
    raw_dir.mkdir(parents=True)
    raw_dir.joinpath("news_tesla.json").write_text(
        json.dumps({
            "articles": [
                {
                    "url": "https://reuters.com/article/tesla-fraud",
                    "title": "Tesla faces fraud investigation",
                    "seendate": "20240601T120000Z",
                    "domain": "reuters.com",
                    "language": "English",
                    "sourcecountry": "United States",
                }
            ],
            "entity_name": "Tesla, Inc.",
            "total_returned": 1,
        }),
        encoding="utf-8",
    )

    entity = Entity(entity_id="tesla_inc_cik_0001318605", name="Tesla, Inc.", identifiers={"cik": "0001318605"})
    ctx = InvestigationContext()

    for task_type in ("adverse_media", "network_analysis", "influence_mapping"):
        agent = SocialGraphAgent(data_root=tmp_path)
        task = SubTask(task_type, "social_graph_agent", "Test")
        findings = agent.run(entity, task, ctx)
        assert len(findings) == 1
        assert findings[0].source_type == "news_article"
        assert findings[0].risk_category == "network"
        # "Tesla faces fraud investigation" → entity + risk keyword → 0.75
        assert findings[0].confidence == pytest.approx(0.75)
        assert findings[0].attributes["relevant"] is True
