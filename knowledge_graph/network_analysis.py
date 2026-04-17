"""Network analysis on the knowledge graph using NetworkX."""

from __future__ import annotations

from typing import Any, Dict, List

import networkx as nx

from knowledge_graph.types import Edge, Node


def analyze_graph(nodes: List[Node], edges: List[Edge]) -> Dict[str, Any]:
    """
    Compute network metrics on the evidence graph.
    Returns degree centrality, top connected nodes, clustering, and source distribution.
    """
    G = nx.DiGraph()
    for node in nodes:
        G.add_node(node.id, node_type=node.node_type, label=node.label, **node.attributes)
    for edge in edges:
        G.add_edge(edge.source_id, edge.target_id, relation=edge.relation_type)

    G_un = G.to_undirected()

    entity_nodes = [n for n in nodes if n.node_type == "entity"]
    evidence_nodes = [n for n in nodes if n.node_type == "evidence"]

    # Degree centrality across all nodes
    centrality = nx.degree_centrality(G_un)

    # Top 5 most-connected evidence nodes (entities always dominate, so filter them out)
    evidence_ids = {n.id for n in evidence_nodes}
    ev_centrality = {nid: v for nid, v in centrality.items() if nid in evidence_ids}
    top_5 = sorted(ev_centrality.items(), key=lambda x: x[1], reverse=True)[:5]

    label_map = {n.id: n.label for n in nodes}
    source_map = {n.id: n.attributes.get("source_type", "unknown") for n in nodes}

    top_connected_nodes = [
        {
            "id": nid,
            "label": label_map.get(nid, nid)[:90],
            "centrality": round(score, 4),
            "source_type": source_map.get(nid, "unknown"),
            "degree": G_un.degree(nid),
        }
        for nid, score in top_5
    ]

    # Connected components (weakly connected in directed graph)
    components = list(nx.weakly_connected_components(G))

    # Average degree
    degrees = [d for _, d in G_un.degree()]
    avg_degree = round(sum(degrees) / len(degrees), 2) if degrees else 0

    # Network density
    density = round(nx.density(G_un), 6)

    # Source type distribution across evidence nodes
    source_type_dist: Dict[str, int] = {}
    for n in evidence_nodes:
        st = n.attributes.get("source_type", "unknown")
        source_type_dist[st] = source_type_dist.get(st, 0) + 1

    # Most-connected entity node (highest degree among entity nodes)
    entity_ids = {n.id for n in entity_nodes}
    entity_degrees = {nid: G_un.degree(nid) for nid in entity_ids if nid in G_un}
    hub_entity = max(entity_degrees, key=entity_degrees.get) if entity_degrees else None
    hub_entity_degree = entity_degrees.get(hub_entity, 0) if hub_entity else 0
    # Use display label if available, otherwise fall back to id
    hub_entity_label = label_map.get(hub_entity, hub_entity) if hub_entity else None
    if hub_entity_label == hub_entity:
        # label_map for entity nodes stores entity_id as both id and label — use the name part
        hub_entity_label = hub_entity.split("_cik_")[0].replace("_", " ").title() if hub_entity else None

    return {
        "total_nodes": len(nodes),
        "total_edges": len(edges),
        "entity_count": len(entity_nodes),
        "evidence_count": len(evidence_nodes),
        "connected_components": len(components),
        "avg_degree": avg_degree,
        "network_density": density,
        "top_connected_nodes": top_connected_nodes,
        "source_type_distribution": source_type_dist,
        "hub_entity": hub_entity_label,
        "hub_entity_degree": hub_entity_degree,
    }
