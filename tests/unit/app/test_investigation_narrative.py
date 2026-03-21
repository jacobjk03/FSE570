"""Tests for investigation narrative / explanation copy."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
for p in (ROOT, SRC):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from app.investigation_narrative import build_investigation_narrative


def test_narrative_resolved_entity():
    result = {
        "query": "Investigate Tesla for money laundering",
        "entity_id": "tesla_inc",
        "entity_name": "Tesla, Inc.",
        "findings_count": 100,
        "tasks": [{"target_agent": "corporate_agent", "task_type": "x"}],
        "gaps": [],
        "conflicts": [{"dimension": "summary_consistency", "description": "d"}],
        "risk_scores": {"overall": 0.82, "finding_count": 100, "by_risk_category": {}},
        "findings_by_data_source": {"sec_edgar": 90, "gdelt": 10},
        "gdelt_total": 10,
        "gdelt_relevant": 5,
    }
    n = build_investigation_narrative(result)
    assert n["has_entity"] is True
    assert "tesla" in n["headline"].lower() or "Tesla" in n["headline"]
    assert n["headline_html"]
    assert len(n["definitions_html"]) >= 3
    assert n["summary_consistency_note"] is True
    assert "takeaway" in n


def test_narrative_no_entity():
    result = {
        "query": "foo",
        "entity_id": None,
        "findings_count": 0,
        "tasks": [],
        "gaps": [],
        "conflicts": [],
        "findings_by_data_source": {},
    }
    n = build_investigation_narrative(result)
    assert n["has_entity"] is False
    assert "no registered entity" in n["headline"].lower()
