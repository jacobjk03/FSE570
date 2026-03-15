"""Tests for evaluation metrics module."""

import pytest

from osint_swarm.entities import Evidence
from output_layer.evaluation_metrics import (
    EvaluationMetrics,
    compute_evaluation_metrics,
    format_metrics_cli,
)


def _ev(source_uri="https://example.com", source_type="sec_filing", risk_category="governance", confidence=0.85, **extra_attrs):
    attrs = dict(extra_attrs)
    return Evidence(
        evidence_id="e1",
        entity_id="t1",
        date="2024-01-01",
        source_type=source_type,
        risk_category=risk_category,
        summary="test",
        source_uri=source_uri,
        raw_location=None,
        confidence=confidence,
        attributes=attrs,
    )


def test_empty_findings():
    m = compute_evaluation_metrics([])
    assert m.total_findings == 0
    assert m.citation_rate == 0.0
    assert m.gdelt_signal_rate == 0.0


def test_citation_rate_all_cited():
    findings = [_ev(source_uri="https://a.com"), _ev(source_uri="https://b.com")]
    m = compute_evaluation_metrics(findings)
    assert m.citation_rate == pytest.approx(1.0)
    assert m.cited_count == 2
    assert m.uncited_count == 0


def test_citation_rate_some_uncited():
    findings = [_ev(source_uri="https://a.com"), _ev(source_uri=""), _ev(source_uri="   ")]
    m = compute_evaluation_metrics(findings)
    assert m.citation_rate == pytest.approx(1 / 3, abs=0.01)
    assert m.cited_count == 1
    assert m.uncited_count == 2


def test_coverage_by_risk_category():
    findings = [
        _ev(risk_category="governance"),
        _ev(risk_category="governance"),
        _ev(risk_category="legal"),
    ]
    m = compute_evaluation_metrics(findings)
    assert m.coverage_by_risk_category["governance"] == 2
    assert m.coverage_by_risk_category["legal"] == 1


def test_coverage_by_data_source_inferred():
    findings = [
        _ev(source_type="sec_filing"),
        _ev(source_type="news_article"),
        _ev(source_type="court_record"),
        _ev(source_type="other", screened=True),
    ]
    m = compute_evaluation_metrics(findings)
    assert m.coverage_by_data_source["sec_edgar"] == 1
    assert m.coverage_by_data_source["gdelt"] == 1
    assert m.coverage_by_data_source["courtlistener"] == 1
    assert m.coverage_by_data_source["ofac"] == 1


def test_coverage_by_data_source_explicit():
    findings = [_ev(data_source="opencorporates")]
    m = compute_evaluation_metrics(findings)
    assert m.coverage_by_data_source["opencorporates"] == 1


def test_gdelt_signal_rate():
    findings = [
        _ev(source_type="news_article", confidence=0.75, relevant=True),
        _ev(source_type="news_article", confidence=0.30, relevant=False),
        _ev(source_type="news_article", confidence=0.55, relevant=True),
        _ev(source_type="news_article", confidence=0.30, relevant=False),
    ]
    m = compute_evaluation_metrics(findings)
    assert m.gdelt_total == 4
    assert m.gdelt_relevant == 2
    assert m.gdelt_signal_rate == pytest.approx(0.5)


def test_confidence_stats():
    findings = [_ev(confidence=0.1), _ev(confidence=0.5), _ev(confidence=0.9)]
    m = compute_evaluation_metrics(findings)
    assert m.confidence_mean == pytest.approx(0.5, abs=0.01)
    assert m.confidence_min == pytest.approx(0.1)
    assert m.confidence_max == pytest.approx(0.9)
    assert m.confidence_buckets["0.0-0.3"] == 1
    assert m.confidence_buckets["0.5-0.7"] == 1  # 0.5 lands here (>= 0.5, < 0.7)
    assert m.confidence_buckets["0.9-1.0"] == 1


def test_runtime_passed_through():
    m = compute_evaluation_metrics([_ev()], runtime_seconds=1.234)
    assert m.runtime_seconds == 1.234


def test_format_metrics_cli():
    m = compute_evaluation_metrics([_ev(), _ev(source_type="news_article", relevant=True)], runtime_seconds=0.5)
    text = format_metrics_cli(m)
    assert "Evaluation Metrics" in text
    assert "Citation rate" in text
    assert "Runtime" in text
