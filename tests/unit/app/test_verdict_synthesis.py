"""Tests for strict LLM narrative synthesis."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
for p in (ROOT, SRC):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import types

import pytest

from app.investigation_errors import FinalSynthesisError
from app.llm_narrative import generate_llm_narrative, parse_narrative_sections


def _sample_result():
    return {
        "entity_name": "The Boeing Company",
        "findings_count": 1088,
        "risk_scores": {"overall": 0.84, "by_risk_category": {"governance": 0.7}},
        "gaps": [{"area": "Adverse media / network", "description": "Limited media coverage in this run."}],
        "conflicts": [{"dimension": "summary_consistency", "description": "d"}] * 2,
        "findings_by_data_source": {
            "sec_edgar": 900,
            "gdelt": 63,
            "courtlistener": 20,
        },
        "gdelt_total": 63,
        "gdelt_relevant": 56,
        "eval_metrics": {"citation_rate": 0.98},
    }


def test_generate_llm_narrative_happy_path(monkeypatch):
    fake_content = """Assessment
- Overall assessment is moderate risk based on public records only.

EvidenceBasis
- Citation rate means how many findings include a source link; here it is high.
- Overall risk score means the average trust level of the source types.
- Conflicts means same-day findings with different summaries that need human review.
- Coverage gaps means expected evidence lanes that did not return enough data.

WhyThisAssessment
- Most findings come from SEC and court records, so the evidence base is broad.
- What this means for you: review the highest-impact filings first, then validate media signals.

ConfidenceAndLimits
- Confidence is moderate because data quality is strong but gaps remain in media coverage.

NextActions
- Re-run adverse media collection with expanded terms.
- Escalate high-risk filings for analyst validation.
"""

    class _FakeCompletions:
        @staticmethod
        def create(**_kwargs):
            return types.SimpleNamespace(
                choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=fake_content))]
            )

    class _FakeGroq:
        def __init__(self, api_key: str):
            self.chat = types.SimpleNamespace(completions=_FakeCompletions())

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "groq", types.SimpleNamespace(Groq=_FakeGroq))

    out = generate_llm_narrative(_sample_result())
    assert "Assessment" in out
    assert "NextActions" in out
    parsed = parse_narrative_sections(out)
    assert parsed["Assessment"]
    assert any("What this means for you" in item for item in parsed["WhyThisAssessment"])


def test_generate_llm_narrative_raises_on_missing_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(FinalSynthesisError):
        generate_llm_narrative(_sample_result())


def test_generate_llm_narrative_raises_on_missing_sections(monkeypatch):
    class _FakeCompletions:
        @staticmethod
        def create(**_kwargs):
            return types.SimpleNamespace(
                choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="Assessment\nonly one section"))]
            )

    class _FakeGroq:
        def __init__(self, api_key: str):
            self.chat = types.SimpleNamespace(completions=_FakeCompletions())

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "groq", types.SimpleNamespace(Groq=_FakeGroq))
    with pytest.raises(FinalSynthesisError):
        generate_llm_narrative(_sample_result())
