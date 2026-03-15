"""Tests for GDELT MCP processor."""

import json
from pathlib import Path

import pytest

from mcp_layer.gdelt_processor import GdeltProcessor
from osint_swarm.entities import Entity


def test_gdelt_processor_source_id():
    proc = GdeltProcessor()
    assert proc.source_id == "gdelt"


def test_gdelt_processor_returns_empty_when_no_cache(tmp_path: Path):
    """No cache file → returns empty list (does not attempt a live call in tests)."""
    # We don't want to hit the real GDELT API in unit tests.
    # The processor falls back to empty list on GdeltError, and no cache means
    # it would try a live call — so we monkey-patch the data source.
    import osint_swarm.data_sources.gdelt as gdelt_mod
    from mcp_layer.gdelt_processor.processor import GdeltProcessor as _GdeltProcessor

    original = gdelt_mod.fetch_news_for_entity

    def _raise(*args, **kwargs):
        raise gdelt_mod.GdeltError("Mocked network error")

    gdelt_mod.fetch_news_for_entity = _raise
    try:
        proc = _GdeltProcessor(data_root=tmp_path)
        entity = Entity(
            entity_id="tesla_inc_cik_0001318605",
            name="Tesla, Inc.",
            identifiers={"cik": "0001318605"},
        )
        result = proc.get_evidence_for_entity(entity)
        assert result == []
    finally:
        gdelt_mod.fetch_news_for_entity = original


def test_gdelt_processor_uses_cache(tmp_path: Path):
    """With a cached GDELT JSON file, processor returns Evidence rows."""
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
                },
                {
                    "url": "https://bloomberg.com/news/tesla-fine",
                    "title": "Tesla fined $2M by regulators",
                    "seendate": "20240310T090000Z",
                    "domain": "bloomberg.com",
                    "language": "English",
                    "sourcecountry": "United States",
                },
            ],
            "query": '"Tesla, Inc." (fraud OR investigation)',
            "entity_name": "Tesla, Inc.",
            "total_returned": 2,
        }),
        encoding="utf-8",
    )

    proc = GdeltProcessor(data_root=tmp_path)
    entity = Entity(
        entity_id="tesla_inc_cik_0001318605",
        name="Tesla, Inc.",
        identifiers={"cik": "0001318605"},
    )
    evidence = proc.get_evidence_for_entity(entity)

    assert len(evidence) == 2
    assert all(e.source_type == "news_article" for e in evidence)
    assert all(e.risk_category == "network" for e in evidence)
    # Relevance scoring: titles contain "Tesla" + risk keywords → high confidence
    assert evidence[0].summary == "Tesla faces fraud investigation"
    assert evidence[0].confidence == pytest.approx(0.75)  # entity + risk keyword
    assert evidence[0].attributes["relevant"] is True
    assert evidence[0].date == "2024-06-01"
    assert evidence[1].summary == "Tesla fined $2M by regulators"
    assert evidence[1].confidence == pytest.approx(0.75)  # "Tesla" + "fined"
    assert evidence[1].attributes["relevant"] is True
    assert evidence[1].date == "2024-03-10"
    assert all(e.entity_id == "tesla_inc_cik_0001318605" for e in evidence)


def test_gdelt_processor_skips_articles_missing_url_or_title(tmp_path: Path):
    """Articles with no URL or no title are skipped."""
    raw_dir = tmp_path / "raw" / "gdelt"
    raw_dir.mkdir(parents=True)
    raw_dir.joinpath("news_tesla.json").write_text(
        json.dumps({
            "articles": [
                {"url": "", "title": "Some title", "seendate": "20240601T000000Z"},
                {"url": "https://example.com/a", "title": "", "seendate": "20240601T000000Z"},
                {"url": "https://reuters.com/valid", "title": "Valid article", "seendate": "20240601T120000Z", "domain": "reuters.com"},
            ],
            "entity_name": "Tesla, Inc.",
        }),
        encoding="utf-8",
    )

    proc = GdeltProcessor(data_root=tmp_path)
    entity = Entity(entity_id="tesla_inc_cik_0001318605", name="Tesla, Inc.", identifiers={"cik": "0001318605"})
    evidence = proc.get_evidence_for_entity(entity)

    assert len(evidence) == 1
    assert evidence[0].summary == "Valid article"


def test_gdelt_processor_relevance_entity_only(tmp_path: Path):
    """Article with entity name in title but no risk keyword → conf=0.70."""
    raw_dir = tmp_path / "raw" / "gdelt"
    raw_dir.mkdir(parents=True)
    raw_dir.joinpath("news_tesla.json").write_text(
        json.dumps({
            "articles": [
                {"url": "https://example.com/a", "title": "Tesla stock hits new high on earnings beat", "seendate": "20240601T120000Z", "domain": "example.com"},
            ],
            "entity_name": "Tesla, Inc.",
        }),
        encoding="utf-8",
    )
    proc = GdeltProcessor(data_root=tmp_path)
    entity = Entity(entity_id="tesla_inc_cik_0001318605", name="Tesla, Inc.", identifiers={"cik": "0001318605"})
    evidence = proc.get_evidence_for_entity(entity)
    assert len(evidence) == 1
    assert evidence[0].confidence == pytest.approx(0.70)
    assert evidence[0].attributes["relevant"] is True


def test_gdelt_processor_relevance_risk_only(tmp_path: Path):
    """Article with risk keyword but no entity name → conf=0.55."""
    raw_dir = tmp_path / "raw" / "gdelt"
    raw_dir.mkdir(parents=True)
    raw_dir.joinpath("news_tesla.json").write_text(
        json.dumps({
            "articles": [
                {"url": "https://example.com/b", "title": "SEC investigation targets unnamed company", "seendate": "20240601T120000Z", "domain": "example.com"},
            ],
            "entity_name": "Tesla, Inc.",
        }),
        encoding="utf-8",
    )
    proc = GdeltProcessor(data_root=tmp_path)
    entity = Entity(entity_id="tesla_inc_cik_0001318605", name="Tesla, Inc.", identifiers={"cik": "0001318605"})
    evidence = proc.get_evidence_for_entity(entity)
    assert len(evidence) == 1
    assert evidence[0].confidence == pytest.approx(0.55)
    assert evidence[0].attributes["relevant"] is True


def test_gdelt_processor_relevance_noise(tmp_path: Path):
    """Article with neither entity name nor risk keyword → conf=0.30 (noise)."""
    raw_dir = tmp_path / "raw" / "gdelt"
    raw_dir.mkdir(parents=True)
    raw_dir.joinpath("news_tesla.json").write_text(
        json.dumps({
            "articles": [
                {"url": "https://example.com/c", "title": "Kia EV6 Is The Most American Car On Sale", "seendate": "20240601T120000Z", "domain": "example.com"},
            ],
            "entity_name": "Tesla, Inc.",
        }),
        encoding="utf-8",
    )
    proc = GdeltProcessor(data_root=tmp_path)
    entity = Entity(entity_id="tesla_inc_cik_0001318605", name="Tesla, Inc.", identifiers={"cik": "0001318605"})
    evidence = proc.get_evidence_for_entity(entity)
    assert len(evidence) == 1
    assert evidence[0].confidence == pytest.approx(0.30)
    assert evidence[0].attributes["relevant"] is False


def test_gdelt_processor_handles_empty_articles(tmp_path: Path):
    """Payload with empty articles list returns empty evidence."""
    raw_dir = tmp_path / "raw" / "gdelt"
    raw_dir.mkdir(parents=True)
    raw_dir.joinpath("news_tesla.json").write_text(
        json.dumps({"articles": [], "entity_name": "Tesla, Inc."}),
        encoding="utf-8",
    )

    proc = GdeltProcessor(data_root=tmp_path)
    entity = Entity(entity_id="tesla_inc_cik_0001318605", name="Tesla, Inc.", identifiers={"cik": "0001318605"})
    assert proc.get_evidence_for_entity(entity) == []
