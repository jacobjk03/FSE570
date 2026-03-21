"""Serialize knowledge graph nodes/edges for vis-network (browser) visualization."""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Set

from knowledge_graph.types import Edge, Node

# Theme-aligned palette (matches app/templates base.css :root)
COLORS = {
    "entity": {"bg": "#0ea5e9", "border": "#38bdf8", "highlight": "#7dd3fc"},
    "sec_filing": {"bg": "#0369a1", "border": "#38bdf8", "highlight": "#7dd3fc"},
    "sec_submissions": {"bg": "#0369a1", "border": "#38bdf8", "highlight": "#7dd3fc"},
    "news_article": {"bg": "#b45309", "border": "#fbbf24", "highlight": "#fcd34d"},
    "court_record": {"bg": "#6d28d9", "border": "#a78bfa", "highlight": "#c4b5fd"},
    "sanctions": {"bg": "#b91c1c", "border": "#f87171", "highlight": "#fca5a5"},
    "other": {"bg": "#475569", "border": "#64748b", "highlight": "#94a3b8"},
}


def _filter_group(source_type: str) -> str:
    """Browser filter bucket: sec | news | court | sanctions | other."""
    st = (source_type or "").lower()
    if "sec" in st:
        return "sec"
    if "news" in st:
        return "news"
    if "court" in st:
        return "court"
    if "sanction" in st or "ofac" in st:
        return "sanctions"
    return "other"


def _color_for_evidence(source_type: str) -> Dict[str, str]:
    st = (source_type or "").lower()
    if "sec" in st:
        return COLORS["sec_filing"]
    if "news" in st:
        return COLORS["news_article"]
    if "court" in st:
        return COLORS["court_record"]
    if "sanction" in st or "ofac" in st:
        return COLORS["sanctions"]
    return COLORS["other"]


def _truncate(s: str, max_len: int = 48) -> str:
    s = s.replace("\n", " ").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def serialize_graph_for_vis(
    nodes: List[Node],
    edges: List[Edge],
    *,
    entity_display_name: Optional[str] = None,
    max_evidence_nodes: int = 120,
    random_seed: int = 42,
) -> Dict[str, Any]:
    """
    Build vis-network JSON: star + optional intra-sample links.
    Downsamples evidence nodes for smooth browser rendering; keeps all entity nodes.
    """
    entity_nodes = [n for n in nodes if n.node_type == "entity"]
    evidence_nodes = [n for n in nodes if n.node_type == "evidence"]

    if not entity_nodes and not evidence_nodes:
        return {
            "nodes": [],
            "edges": [],
            "truncated": False,
            "shown_evidence": 0,
            "total_evidence": 0,
            "entity_count": 0,
        }

    kept_evidence = list(evidence_nodes)
    truncated = False
    if len(evidence_nodes) > max_evidence_nodes:
        truncated = True
        rng = random.Random(random_seed)
        kept_evidence = rng.sample(evidence_nodes, max_evidence_nodes)

    kept_ids: Set[str] = {n.id for n in entity_nodes} | {n.id for n in kept_evidence}

    vis_nodes: List[Dict[str, Any]] = []
    for n in entity_nodes:
        label = entity_display_name or _truncate(n.label, 40)
        c = COLORS["entity"]
        vis_nodes.append(
            {
                "id": n.id,
                "label": label,
                "title": f"Entity\n{entity_display_name or n.id}",
                "group": "entity",
                "filterGroup": "entity",
                "shape": "diamond",
                "size": 36,
                "font": {"size": 15, "color": "#f1f5f9", "face": "Inter, system-ui, sans-serif"},
                "color": {
                    "background": c["bg"],
                    "border": c["border"],
                    "highlight": {"background": c["highlight"], "border": "#ffffff"},
                    "hover": {"background": c["highlight"], "border": "#ffffff"},
                },
                "borderWidth": 3,
            }
        )

    for n in kept_evidence:
        st = str(n.attributes.get("source_type") or "other")
        rc = str(n.attributes.get("risk_category") or "")
        conf = n.attributes.get("confidence")
        c = _color_for_evidence(st)
        conf_line = ""
        if conf is not None:
            try:
                conf_line = f"Confidence: {float(conf):.2f}"
            except (TypeError, ValueError):
                conf_line = f"Confidence: {conf}"
        title_lines = [
            f"Evidence: {n.id}",
            f"Source: {st}",
            f"Risk: {rc}" if rc else "",
            conf_line,
        ]
        title = "\n".join(line for line in title_lines if line)
        vis_nodes.append(
            {
                "id": n.id,
                "label": _truncate(n.label, 42),
                "title": title,
                "group": st,
                "filterGroup": _filter_group(st),
                "shape": "dot",
                "size": 10,
                "font": {"size": 11, "color": "#cbd5e1", "face": "Inter, system-ui, sans-serif"},
                "color": {
                    "background": c["bg"],
                    "border": c["border"],
                    "highlight": {"background": c["highlight"], "border": "#e2e8f0"},
                    "hover": {"background": c["highlight"], "border": "#e2e8f0"},
                },
                "borderWidth": 2,
            }
        )

    vis_edges: List[Dict[str, Any]] = []
    seen_has_evidence: Set[tuple] = set()
    for e in edges:
        if e.relation_type != "has_evidence":
            continue
        if e.source_id not in kept_ids or e.target_id not in kept_ids:
            continue
        key = (e.source_id, e.target_id)
        if key in seen_has_evidence:
            continue
        seen_has_evidence.add(key)
        vis_edges.append(
            {
                "from": e.source_id,
                "to": e.target_id,
                "arrows": "to",
                "color": {"color": "#475569", "highlight": "#38bdf8", "opacity": 0.65},
                "width": 1,
            }
        )

    # Omit same_source_type edges in the browser view — they clutter the layout; entity→evidence star is clearer.

    return {
        "nodes": vis_nodes,
        "edges": vis_edges,
        "truncated": truncated,
        "shown_evidence": len(kept_evidence),
        "total_evidence": len(evidence_nodes),
        "entity_count": len(entity_nodes),
    }
