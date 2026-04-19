"""End-to-end tests for strict LLM-only pipeline behavior."""

from pathlib import Path
import sys

# Ensure repo root and src are on path (conftest does this for tests/; e2e may run standalone)
ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
for p in (ROOT, SRC):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

def test_pipeline_e2e_missing_groq_key_returns_explicit_error(monkeypatch):
    from app.pipeline import run_investigation

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    data_root = ROOT / "data"
    result = run_investigation("Investigate Tesla for money laundering", data_root=data_root)

    assert result["query"] == "Investigate Tesla for money laundering"
    assert result["error"] is not None
    assert "LLM planner failed." in result["error"]
    assert len(result["audit_events"]) >= 1


def test_pipeline_e2e_unknown_entity_still_reports_error_on_missing_llm(monkeypatch):
    from app.pipeline import run_investigation

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    data_root = ROOT / "data"
    result = run_investigation("Investigate XYZUnknownCorp for fraud", data_root=data_root)

    assert result["query"] == "Investigate XYZUnknownCorp for fraud"
    assert result.get("entity_id") is None
    assert result.get("entity_name") is None
    assert result["error"] is not None
    assert len(result["audit_events"]) >= 1


def test_pipeline_tool_map_has_only_sec_for_corporate(tmp_path):
    from agents.tools import get_available_tools_by_agent
    from osint_swarm.entities import Entity

    entity = Entity(entity_id="tesla_inc_cik_0001318605", name="Tesla, Inc.", identifiers={"cik": "0001318605"})
    available = get_available_tools_by_agent(data_root=tmp_path, entity=entity)
    assert available["corporate_agent"] == ["sec_edgar"]
