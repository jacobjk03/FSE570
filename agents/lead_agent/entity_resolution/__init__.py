"""Entity resolution: query string -> Entity candidates."""

from agents.lead_agent.entity_resolution.resolver import (
    ENTITY_REGISTRY,
    resolve,
    resolve_one,
    resolve_one_with_auto,
)

__all__ = ["ENTITY_REGISTRY", "resolve", "resolve_one", "resolve_one_with_auto"]
