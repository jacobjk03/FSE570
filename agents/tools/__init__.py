"""Bounded tools for agentic specialist agents."""

from agents.tools.base import InvestigationTool, ToolCallResult
from agents.tools.registry import (
    get_available_tools_by_agent,
    get_tools_for_agent,
)

__all__ = [
    "InvestigationTool",
    "ToolCallResult",
    "get_available_tools_by_agent",
    "get_tools_for_agent",
]
