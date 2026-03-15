"""Evaluation metrics for OSINT investigation pipeline quality assessment.

Computes:
  - Citation rate: fraction of findings with a non-empty source_uri.
  - Coverage by risk category: which risk categories have evidence.
  - Coverage by data source: which data sources contributed.
  - GDELT signal-to-noise: fraction of relevant GDELT articles.
  - Confidence distribution: mean, min, max, and histogram buckets.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from osint_swarm.entities import Evidence

RISK_CATEGORIES = ("governance", "regulatory", "legal", "network", "other")
DATA_SOURCES = ("sec_edgar", "gdelt", "ofac", "courtlistener", "opencorporates")


@dataclass(frozen=True)
class EvaluationMetrics:
    total_findings: int
    citation_rate: float
    cited_count: int
    uncited_count: int
    coverage_by_risk_category: Dict[str, int]
    coverage_by_data_source: Dict[str, int]
    gdelt_total: int
    gdelt_relevant: int
    gdelt_signal_rate: float
    confidence_mean: float
    confidence_min: float
    confidence_max: float
    confidence_buckets: Dict[str, int]
    runtime_seconds: Optional[float] = None


def _infer_data_source(ev: Evidence) -> str:
    ds = ev.attributes.get("data_source")
    if ds:
        return ds
    if ev.source_type in ("sec_filing", "sec_submissions"):
        return "sec_edgar"
    if ev.source_type == "news_article":
        return "gdelt"
    if ev.source_type == "court_record":
        return "courtlistener"
    if ev.attributes.get("screened"):
        return "ofac"
    if ev.attributes.get("sec_count") is not None:
        return "sec_edgar"
    return "unknown"


def compute_evaluation_metrics(
    findings: List[Evidence],
    runtime_seconds: Optional[float] = None,
) -> EvaluationMetrics:
    if not findings:
        return EvaluationMetrics(
            total_findings=0, citation_rate=0.0, cited_count=0, uncited_count=0,
            coverage_by_risk_category={}, coverage_by_data_source={},
            gdelt_total=0, gdelt_relevant=0, gdelt_signal_rate=0.0,
            confidence_mean=0.0, confidence_min=0.0, confidence_max=0.0,
            confidence_buckets={}, runtime_seconds=runtime_seconds,
        )

    cited = [e for e in findings if e.source_uri and e.source_uri.strip()]
    citation_rate = len(cited) / len(findings) if findings else 0.0

    risk_counts: Dict[str, int] = defaultdict(int)
    for e in findings:
        risk_counts[e.risk_category] += 1

    ds_counts: Dict[str, int] = defaultdict(int)
    for e in findings:
        ds_counts[_infer_data_source(e)] += 1

    gdelt_articles = [e for e in findings if e.source_type == "news_article"]
    gdelt_relevant = [e for e in gdelt_articles if e.attributes.get("relevant")]
    gdelt_signal = len(gdelt_relevant) / len(gdelt_articles) if gdelt_articles else 0.0

    confidences = [e.confidence for e in findings]
    conf_mean = sum(confidences) / len(confidences)
    conf_min = min(confidences)
    conf_max = max(confidences)

    buckets: Dict[str, int] = {"0.0-0.3": 0, "0.3-0.5": 0, "0.5-0.7": 0, "0.7-0.9": 0, "0.9-1.0": 0}
    for c in confidences:
        if c < 0.3:
            buckets["0.0-0.3"] += 1
        elif c < 0.5:
            buckets["0.3-0.5"] += 1
        elif c < 0.7:
            buckets["0.5-0.7"] += 1
        elif c < 0.9:
            buckets["0.7-0.9"] += 1
        else:
            buckets["0.9-1.0"] += 1

    return EvaluationMetrics(
        total_findings=len(findings),
        citation_rate=round(citation_rate, 4),
        cited_count=len(cited),
        uncited_count=len(findings) - len(cited),
        coverage_by_risk_category=dict(risk_counts),
        coverage_by_data_source=dict(ds_counts),
        gdelt_total=len(gdelt_articles),
        gdelt_relevant=len(gdelt_relevant),
        gdelt_signal_rate=round(gdelt_signal, 4),
        confidence_mean=round(conf_mean, 4),
        confidence_min=round(conf_min, 4),
        confidence_max=round(conf_max, 4),
        confidence_buckets=buckets,
        runtime_seconds=runtime_seconds,
    )


def format_metrics_cli(m: EvaluationMetrics) -> str:
    lines = [
        "Evaluation Metrics",
        "==================",
        f"Total findings:       {m.total_findings}",
        f"Citation rate:        {m.citation_rate:.1%} ({m.cited_count} cited / {m.uncited_count} uncited)",
        "",
        "Coverage by risk category:",
    ]
    for cat in RISK_CATEGORIES:
        count = m.coverage_by_risk_category.get(cat, 0)
        if count:
            lines.append(f"  {cat:15s} {count:>5}")
    lines.append("")
    lines.append("Coverage by data source:")
    for ds in DATA_SOURCES:
        count = m.coverage_by_data_source.get(ds, 0)
        if count:
            lines.append(f"  {ds:20s} {count:>5}")
    if m.gdelt_total:
        lines.append(f"\nGDELT signal rate:    {m.gdelt_signal_rate:.1%} ({m.gdelt_relevant}/{m.gdelt_total} relevant)")
    lines.append(f"\nConfidence:  mean={m.confidence_mean:.2f}  min={m.confidence_min:.2f}  max={m.confidence_max:.2f}")
    lines.append("  Distribution:")
    for bucket, count in m.confidence_buckets.items():
        bar = "#" * min(count, 50)
        lines.append(f"    {bucket}  {count:>5}  {bar}")
    if m.runtime_seconds is not None:
        lines.append(f"\nRuntime: {m.runtime_seconds:.3f}s")
    return "\n".join(lines)
