"""Tests for verdict / synthesis report."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
for p in (ROOT, SRC):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from app.verdict_synthesis import build_verdict_synthesis


def test_verdict_boeing_like():
    result = {
        "query": "Investigate Boeing for money laundering",
        "entity_id": "boeing_cik_0000012927",
        "entity_name": "The Boeing Company",
        "findings_count": 1088,
        "tasks": [{"target_agent": "corporate_agent", "task_type": "x"}] * 6,
        "gaps": [{"area": "beneficial_ownership", "description": "OpenCorporates data unavailable."}],
        "conflicts": [{"dimension": "summary_consistency", "description": "d"}] * 80,
        "risk_scores": {"overall": 0.84, "finding_count": 1088, "by_risk_category": {}},
        "findings_by_data_source": {
            "sec_edgar": 900,
            "gdelt": 63,
            "courtlistener": 20,
            "opencorporates": 1,
        },
        "gdelt_total": 63,
        "gdelt_relevant": 56,
    }
    v = build_verdict_synthesis(result)
    assert v["tier_id"] == "substantial_with_gaps"
    assert "Synthesis" in v["headline"]
    assert len(v["key_observations"]) >= 2
    assert v["headline_html"]
    assert "human" in v["caveat"].lower() or "qualified" in v["caveat"].lower()


def test_verdict_no_entity():
    result = {
        "query": "foo",
        "entity_id": None,
        "findings_count": 0,
        "tasks": [],
        "gaps": [],
        "conflicts": [],
        "findings_by_data_source": {},
    }
    v = build_verdict_synthesis(result)
    assert v["tier_id"] == "unresolved_entity"
    assert "no entity-level verdict" in v["headline"].lower()
