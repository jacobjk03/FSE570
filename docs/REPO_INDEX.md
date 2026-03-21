# Repository Index & Test Coverage

**Last full run:** All **87 tests** pass (82 unit + 5 e2e).  
**Accuracy:** **100%** for all indexed functionality below.

---

## 1. Project layout

| Path | Purpose |
|------|--------|
| `src/osint_swarm/` | Core entities, data source types, utils |
| `agents/` | Lead Agent + specialist agents (Corporate, Legal, Social Graph) |
| `mcp_layer/` | SEC EDGAR, NHTSA processors; evidence loader; MCP facade |
| `reflexion_layer/` | Cross-check, gap detection, confidence aggregation |
| `knowledge_graph/` | Graph build from evidence (nodes/edges) |
| `output_layer/` | Evidence report (MD/HTML), risk dashboard, audit trail |
| `app/` | Flask web demo (query form → results) |
| `scripts/` | CLI: `run_lead_agent.py`, `pull_sec_submissions.py`, `pull_nhtsa_recalls.py`, `build_evidence_tesla.py` |
| `data/` | `raw/` (cached APIs), `processed/` (normalized evidence) |
| `tests/unit/` | Unit tests (pytest) |
| `tests/e2e/` | End-to-end tests (pipeline + Flask app) |

**Config:** `pyproject.toml` (pytest: `testpaths = ["tests"]`, `pythonpath = ["src", "."]`), `requirements.txt`, `requirements-dev.txt`.

---

## 2. Functionality ↔ test mapping (100% passing)

### Lead Agent (`agents/lead_agent/`)

| Functionality | Test file | Status |
|---------------|-----------|--------|
| Context manager: empty, set/get entity, query, tasks, agent results, copy semantics | `tests/unit/agents/lead_agent/test_context_manager.py` | ✅ 6/6 |
| Entity resolution: empty, Tesla by name/case/alias, unknown, one match | `tests/unit/agents/lead_agent/test_entity_resolution.py` | ✅ 6/6 |
| Lead agent run: unknown entity, Tesla resolve + tasks, MCP evidence, custom stubs | `tests/unit/agents/lead_agent/test_lead_agent.py` | ✅ 4/4 |
| Task planner: money-laundering decomposition (5 tasks, agents), generic default, AML keyword | `tests/unit/agents/lead_agent/test_task_planner.py` | ✅ 5/5 |

### Specialist agents (`agents/specialist_agents/`)

| Functionality | Test file | Status |
|---------------|-----------|--------|
| Corporate agent: id, beneficial ownership stub, SEC task with MCP cache, governance red flags | `tests/unit/agents/specialist_agents/test_corporate_agent.py` | ✅ 5/5 |
| Legal agent: id, sanctions stub, litigation/PACER stub | `tests/unit/agents/specialist_agents/test_legal_agent.py` | ✅ 3/3 |
| Social graph agent: id, adverse media stub, network analysis stub | `tests/unit/agents/specialist_agents/test_social_graph_agent.py` | ✅ 3/3 |

### MCP layer (`mcp_layer/`)

| Functionality | Test file | Status |
|---------------|-----------|--------|
| Data source processor interface | `tests/unit/mcp_layer/test_base.py` | ✅ 1/1 |
| Evidence loader: CSV empty/single row, load for entity from processed dir, nonexistent dir | `tests/unit/mcp_layer/test_evidence_loader.py` | ✅ 4/4 |
| MCP facade: get processor (SEC/NHTSA/unknown), get/load evidence for entity | `tests/unit/mcp_layer/test_mcp_facade.py` | ✅ 5/5 |
| NHTSA processor: source id, empty without make, cache, derive make from name | `tests/unit/mcp_layer/test_nhtsa_processor.py` | ✅ 4/4 |
| SEC EDGAR processor: source id, empty without CIK, cache | `tests/unit/mcp_layer/test_sec_edgar_processor.py` | ✅ 3/3 |

### Reflexion layer (`reflexion_layer/`)

| Functionality | Test file | Status |
|---------------|-----------|--------|
| Confidence: aggregate empty/single/multiple, adjusted by source weight | `tests/unit/reflexion_layer/test_confidence_module.py` | ✅ 5/5 |
| Cross-check: empty, single finding, same-entity date conflict/no-conflict, no-date skipped | `tests/unit/reflexion_layer/test_cross_check.py` | ✅ 5/5 |
| Gap detection: no entity, legal stub, social stub, structure mapper stub, legal empty | `tests/unit/reflexion_layer/test_gap_detection.py` | ✅ 5/5 |

### Knowledge graph (`knowledge_graph/`)

| Functionality | Test file | Status |
|---------------|-----------|--------|
| Build graph: empty, single evidence, multiple same-entity, node attributes | `tests/unit/knowledge_graph/test_graph.py` | ✅ 4/4 |

### Output layer (`output_layer/`)

| Functionality | Test file | Status |
|---------------|-----------|--------|
| Audit trail: empty, record, multiple events, to_json_lines, clear | `tests/unit/output_layer/test_audit_trail.py` | ✅ 5/5 |
| Evidence report: MD empty/with findings/graph, write file, HTML report | `tests/unit/output_layer/test_evidence_report_generator.py` | ✅ 5/5 |
| Risk dashboard: compute scores empty/single/multiple, format CLI | `tests/unit/output_layer/test_risk_dashboard.py` | ✅ 4/4 |

### End-to-end (`tests/e2e/`)

| Functionality | Test file | Status |
|---------------|-----------|--------|
| Full pipeline: Tesla query (entity, tasks, report, dashboard, audit); unknown entity | `tests/e2e/test_pipeline_e2e.py` | ✅ 2/2 |
| Flask app: GET index, POST empty query (error), POST Tesla investigation (results) | `tests/e2e/test_flask_e2e.py` | ✅ 3/3 |

---

## 3. How to run tests

```bash
# From repo root (recommended: use venv and install deps first)
pip install -r requirements-dev.txt   # includes pytest + Flask for e2e

# All tests (unit + e2e)
pytest tests/unit tests/e2e -v

# Unit only
pytest tests/unit -v

# E2E only (requires Flask: pip install -r requirements.txt)
pytest tests/e2e -v
```

---

## 4. Summary: functionality with 100% test accuracy

- **Lead agent:** context, entity resolution, task planning, full run with MCP — **100%**
- **Specialist agents:** Corporate, Legal, Social Graph (ids, stubs, MCP/cache) — **100%**
- **MCP layer:** base interface, evidence loader, facade, SEC EDGAR, NHTSA — **100%**
- **Reflexion:** confidence, cross-check, gap detection — **100%**
- **Knowledge graph:** build from evidence, node attributes — **100%**
- **Output:** audit trail, evidence report (MD/HTML), risk dashboard — **100%**
- **E2E:** full pipeline (Tesla + unknown entity), Flask index + POST flow — **100%**

**Total: 87 tests, 87 passed.**
