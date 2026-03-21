"""End-to-end test: full investigation pipeline from query to report/dashboard/audit."""

from pathlib import Path
import sys

# Ensure repo root and src are on path (conftest does this for tests/; e2e may run standalone)
ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
for p in (ROOT, SRC):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import pytest


def test_pipeline_e2e_tesla_query():
    """Run full pipeline for 'Investigate Tesla for money laundering' and assert output structure."""
    from app.pipeline import run_investigation

    data_root = ROOT / "data"
    result = run_investigation("Investigate Tesla for money laundering", data_root=data_root)

    # Required keys
    assert "query" in result
    assert result["query"] == "Investigate Tesla for money laundering"
    assert "entity" in result
    assert "tasks" in result
    assert "findings_count" in result
    assert "findings_by_agent" in result
    assert "report_md" in result
    assert "report_html" in result
    assert "risk_scores" in result
    assert "risk_dashboard_cli" in result
    assert "gaps" in result
    assert "conflicts" in result
    assert "confidence_scores" in result
    assert "audit_events" in result
    assert "error" in result

    # Entity resolved for Tesla (entity_id/name format may vary: "tesla", "Tesla, Inc.", etc.)
    assert result.get("entity_id") is not None and "tesla" in (result.get("entity_id") or "").lower()
    assert result.get("entity_name") is not None and "tesla" in (result.get("entity_name") or "").lower()

    # Tasks created (task planner decomposes money laundering into multiple tasks)
    assert len(result["tasks"]) >= 1
    task_agents = {t["target_agent"] for t in result["tasks"]}
    assert any("corporate" in a for a in task_agents) or any("legal" in a for a in task_agents) or any("social_graph" in a for a in task_agents)

    # No pipeline error
    assert result["error"] is None

    # Audit trail was recorded
    assert len(result["audit_events"]) >= 1

    # Report content present (may be minimal if no cached evidence)
    assert isinstance(result["report_md"], str)
    assert isinstance(result["report_html"], str)


def test_pipeline_e2e_unknown_entity():
    """Run pipeline for unknown entity; should complete without crash, entity unresolved."""
    from app.pipeline import run_investigation

    data_root = ROOT / "data"
    result = run_investigation("Investigate XYZUnknownCorp for fraud", data_root=data_root)

    assert result["query"] == "Investigate XYZUnknownCorp for fraud"
    assert result.get("entity_id") is None
    assert result.get("entity_name") is None
    assert result["error"] is None
    assert len(result["audit_events"]) >= 1
