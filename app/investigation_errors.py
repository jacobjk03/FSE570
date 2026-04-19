"""Typed investigation failures for strict LLM-only mode."""

from __future__ import annotations


class InvestigationError(RuntimeError):
    """Base error for investigation-stage failures."""


class PlannerLLMError(InvestigationError):
    """Raised when planning LLM output is missing/invalid."""


class ActionPolicyError(InvestigationError):
    """Raised when action-policy selection fails."""


class ReflexionPolicyError(InvestigationError):
    """Raised when reflexion ranking fails."""


class StopPolicyError(InvestigationError):
    """Raised when stop-policy decisioning fails."""


class DataSourceError(InvestigationError):
    """Raised when a required data source call fails."""


class FinalSynthesisError(InvestigationError):
    """Raised when final narrative synthesis fails."""
