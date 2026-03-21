"""Full investigation pipeline: Lead Agent -> reflexion -> knowledge graph -> report -> dashboard -> audit."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

# Path setup for running as app
import sys
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for p in (ROOT, SRC):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from agents.lead_agent import LeadAgent
from knowledge_graph import build_graph_from_evidence
from output_layer.audit_trail import AuditTrail
from output_layer.evidence_report_generator import generate_markdown_report
from output_layer.risk_dashboard import compute_risk_scores, format_dashboard_cli
from output_layer.evaluation_metrics import compute_evaluation_metrics, format_metrics_cli
from reflexion_layer import aggregate_confidence, cross_check_findings, detect_gaps

from app.graph_viz import serialize_graph_for_vis
from app.investigation_narrative import build_investigation_narrative
from app.verdict_synthesis import build_verdict_synthesis


def get_registered_entities() -> List[Dict[str, str]]:
    """Return list of registered entities for the UI dropdown."""
    from agents.lead_agent.entity_resolution.resolver import ENTITY_REGISTRY
    return [{"entity_id": e.entity_id, "name": e.name} for e in ENTITY_REGISTRY]


QUERY_TEMPLATES = [
    "Investigate {entity} for money laundering",
    "Investigate {entity}",
]


def run_investigation(query: str, data_root: Optional[Path] = None) -> Dict[str, Any]:
    """
    Run the full pipeline for one investigation query.
    Returns a dict with keys: query, entity, tasks, findings_count, findings_by_agent,
    report_md, report_html, risk_scores, risk_dashboard_cli, gaps, conflicts,
    confidence_scores, audit_events, error (if any).
    """
    data_root = data_root or ROOT / "data"
    audit = AuditTrail()
    result: Dict[str, Any] = {
        "query": query,
        "entity": None,
        "entity_id": None,
        "entity_name": None,
        "tasks": [],
        "findings_count": 0,
        "findings_by_agent": {},
        "report_md": "",
        "report_html": "",
        "risk_scores": None,
        "risk_dashboard_cli": "",
        "gaps": [],
        "conflicts": [],
        "confidence_scores": None,
        "audit_events": [],
        "error": None,
        "graph_vis": None,
        "narrative": None,
        "verdict": None,
    }

    import time as _time
    t0 = _time.perf_counter()

    try:
        audit.record("query_received", query=query)
        agent = LeadAgent(data_root=data_root)
        ctx = agent.run(query)
        audit.record("pipeline_completed", entity_resolved=ctx.get_entity() is not None, task_count=len(ctx.get_tasks()))

        entity = ctx.get_entity()
        if entity:
            result["entity_id"] = entity.entity_id
            result["entity_name"] = entity.name
            result["entity"] = {"entity_id": entity.entity_id, "name": entity.name, "identifiers": dict(entity.identifiers)}

        result["tasks"] = [{"task_type": t.task_type, "target_agent": t.target_agent, "description": t.description} for t in ctx.get_tasks()]
        findings = ctx.get_all_findings()
        result["findings_count"] = len(findings)
        result["findings_by_agent"] = {aid: len(evs) for aid, evs in ctx.results.items()}

        # Source-type breakdown for the UI
        source_counts: Dict[str, int] = {}
        for f in findings:
            src = f.source_type
            source_counts[src] = source_counts.get(src, 0) + 1
        result["findings_by_source"] = source_counts

        # Data-source breakdown (SEC, GDELT, OFAC, CourtListener, OpenCorporates)
        ds_counts: Dict[str, int] = {}
        for f in findings:
            ds = f.attributes.get("data_source")
            if ds:
                ds_counts[ds] = ds_counts.get(ds, 0) + 1
            elif f.source_type == "sec_filing" or f.source_type == "sec_submissions":
                ds_counts["sec_edgar"] = ds_counts.get("sec_edgar", 0) + 1
            elif f.source_type == "news_article":
                ds_counts["gdelt"] = ds_counts.get("gdelt", 0) + 1
            elif f.source_type == "court_record":
                ds_counts["courtlistener"] = ds_counts.get("courtlistener", 0) + 1
            elif f.attributes.get("screened"):
                ds_counts["ofac"] = ds_counts.get("ofac", 0) + 1
            elif f.attributes.get("sec_count") is not None:
                ds_counts["sec_edgar"] = ds_counts.get("sec_edgar", 0) + 1
        result["findings_by_data_source"] = ds_counts

        # Relevance stats for GDELT
        gdelt_findings = [f for f in findings if f.source_type == "news_article"]
        gdelt_relevant = [f for f in gdelt_findings if f.attributes.get("relevant")]
        result["gdelt_total"] = len(gdelt_findings)
        result["gdelt_relevant"] = len(gdelt_relevant)

        # Reflexion
        result["conflicts"] = [{"dimension": c.dimension, "description": c.description, "evidence_ids": list(c.evidence_ids)} for c in cross_check_findings(findings)]
        result["gaps"] = [{"area": g.area, "description": g.description, "suggested_follow_up": g.suggested_follow_up} for g in detect_gaps(ctx)]
        conf_scores = aggregate_confidence(findings)
        result["confidence_scores"] = {"overall": conf_scores.overall, "by_risk_category": conf_scores.by_risk_category, "by_source_type": conf_scores.by_source_type}

        # Knowledge graph
        nodes, edges = build_graph_from_evidence(findings)
        result["graph_summary"] = {"nodes": len(nodes), "edges": len(edges), "entity_nodes": sum(1 for n in nodes if n.node_type == "entity"), "evidence_nodes": sum(1 for n in nodes if n.node_type == "evidence")}
        result["graph_vis"] = serialize_graph_for_vis(
            nodes,
            edges,
            entity_display_name=result.get("entity_name"),
            max_evidence_nodes=72,
        )

        # Report
        result["report_md"] = generate_markdown_report(findings, entity_id=result["entity_id"], query=query, graph=(nodes, edges))
        from output_layer.evidence_report_generator.report import generate_html_report
        result["report_html"] = generate_html_report(findings, entity_id=result["entity_id"], query=query, graph=(nodes, edges))

        # Risk dashboard
        risk_scores = compute_risk_scores(findings)
        result["risk_scores"] = {"overall": risk_scores.overall, "by_risk_category": risk_scores.by_risk_category, "finding_count": risk_scores.finding_count}
        result["risk_dashboard_cli"] = format_dashboard_cli(risk_scores)

        # Evaluation metrics
        elapsed = _time.perf_counter() - t0
        eval_metrics = compute_evaluation_metrics(findings, runtime_seconds=round(elapsed, 3))
        result["eval_metrics"] = {
            "total_findings": eval_metrics.total_findings,
            "citation_rate": eval_metrics.citation_rate,
            "cited_count": eval_metrics.cited_count,
            "uncited_count": eval_metrics.uncited_count,
            "coverage_by_risk_category": eval_metrics.coverage_by_risk_category,
            "coverage_by_data_source": eval_metrics.coverage_by_data_source,
            "gdelt_total": eval_metrics.gdelt_total,
            "gdelt_relevant": eval_metrics.gdelt_relevant,
            "gdelt_signal_rate": eval_metrics.gdelt_signal_rate,
            "confidence_mean": eval_metrics.confidence_mean,
            "confidence_min": eval_metrics.confidence_min,
            "confidence_max": eval_metrics.confidence_max,
            "confidence_buckets": eval_metrics.confidence_buckets,
        }
        result["eval_metrics_cli"] = format_metrics_cli(eval_metrics)

        result["audit_events"] = audit.get_events()
        result["narrative"] = build_investigation_narrative(result)
        result["verdict"] = build_verdict_synthesis(result)
    except Exception as e:
        result["error"] = str(e)
        audit.record("pipeline_error", error=str(e))
        result["audit_events"] = audit.get_events()

    result["runtime_seconds"] = round(_time.perf_counter() - t0, 3)
    return result
