# Project Status Report — Autonomous OSINT Investigation Swarm

**Course**: FSE 570 Data Science Capstone
**Team**: Taljinder Singh · Aditya Pokharna · Raj Kumar Mahto · Arnab Mitra · Jacob Kuriakose
**Last Updated**: 2026-03-15
**Version**: 2.0 — Full rewrite with workflow, agent map, data inventory, and clear next steps.

---

## Table of Contents

1. [What This Project Does — Plain English](#1-what-this-project-does--plain-english)
2. [The Big Picture — Where We Are Right Now](#2-the-big-picture--where-we-are-right-now)
3. [How the Pipeline Works — Full Workflow](#3-how-the-pipeline-works--full-workflow)
4. [Every Agent Explained — What It Does and What State It Is In](#4-every-agent-explained--what-it-does-and-what-state-it-is-in)
5. [Data We Are Pulling — Sources, Commands, Files](#5-data-we-are-pulling--sources-commands-files)
6. [How to Run Everything Right Now](#6-how-to-run-everything-right-now)
7. [Test Results — 2026-03-15](#7-test-results--2026-03-15)
8. [Data Inventory — What Has Been Collected](#8-data-inventory--what-has-been-collected)
9. [Feasibility Assessment](#9-feasibility-assessment)
10. [What Is Working vs What Is a Stub](#10-what-is-working-vs-what-is-a-stub)
11. [What Is Left and Immediate Next Steps](#11-what-is-left-and-immediate-next-steps)
12. [Timeline](#12-timeline)
13. [Repository Structure](#13-repository-structure)
14. [Schema Reference](#14-schema-reference)

---

## 1. What This Project Does — Plain English

This project is an **automated investigation tool** for corporate risk assessment. You type a question like:

> *"Investigate Tesla for money laundering"*

…and the system automatically:

1. Figures out **which company** you mean (resolves "Tesla" → Tesla Inc with its SEC CIK, NHTSA make code, etc.)
2. Decides **what to investigate** (breaks the question into sub-tasks: corporate structure, sanctions check, legal records, adverse media, etc.)
3. Sends each sub-task to a **specialist agent** (Corporate Agent, Legal Agent, Social Graph Agent)
4. Each agent **retrieves real evidence** from government databases (SEC filings, NHTSA safety recalls) — structured, cited, with source URLs
5. A **Reflexion layer** checks for conflicts, detects gaps, and scores confidence
6. A **Knowledge Graph** is built from the evidence
7. The system generates a **full HTML/Markdown report**, a **Risk Dashboard** (scores by category), and an **Audit Trail**
8. All of this shows up in a **Flask web browser** at `http://127.0.0.1:5000`

The core principle: every finding is an `Evidence` row — it has a source URL, a date, a confidence score, and a risk category. Nothing is made up. Everything is citable.

---

## 2. The Big Picture — Where We Are Right Now

### Progress at a Glance

```
DONE ██████████████████░░░░░░░░░░░  ~65%
```

| Area | Status | Detail |
|---|---|---|
| Architecture & schemas | ✅ Complete | `Entity` + `Evidence` dataclasses, layered design |
| Data ingestion (SEC + NHTSA) | ✅ Complete | 2 companies, real data |
| MCP data layer | ✅ Complete | Abstract processors, caching, facade |
| Lead Agent (orchestrator) | ✅ Complete | Resolves entity, decomposes tasks, dispatches |
| Corporate Agent | ✅ Working (real data) | SEC filings + NHTSA recalls via MCP |
| Legal Agent | ⚠️ Stub | Returns placeholder — OFAC + CourtListener not integrated |
| Social Graph Agent | ⚠️ Stub | Returns placeholder — GDELT not integrated |
| Reflexion layer | ✅ Complete | Cross-check, gap detection, confidence scoring |
| Knowledge Graph | ✅ Complete | Builds in-memory graph; no visualization yet |
| Output layer | ✅ Complete | HTML/Markdown report, risk dashboard, audit trail |
| Flask web demo | ✅ Working | End-to-end pipeline in browser |
| Test suite | ✅ 82/82 pass | All unit tests passing, 0 failures |
| Entity support | ✅ 2 entities | Tesla + Ford Motor Company |

---

## 3. How the Pipeline Works — Full Workflow

This section explains the exact flow from a user query to a final report.

### Step-by-Step: What Happens When You Submit a Query

```
User types: "Investigate Ford for money laundering"
                        │
                        ▼
             ┌─────────────────────┐
             │  1. ENTITY          │   File: agents/lead_agent/entity_resolution/resolver.py
             │     RESOLUTION      │
             │                     │   Looks up "Ford" in ENTITY_REGISTRY →
             │                     │   Returns Entity(
             │                     │     entity_id = "ford_motor_cik_0000037996",
             │                     │     name = "Ford Motor Company",
             │                     │     identifiers = {cik: "0000037996",
             │                     │                    ticker: "F",
             │                     │                    make: "FORD"}
             │                     │   )
             └────────┬────────────┘
                      │
                      ▼
             ┌─────────────────────┐
             │  2. TASK PLANNER    │   File: agents/lead_agent/task_planner/planner.py
             │                     │
             │  Detects keywords   │   "money laundering" → 5 sub-tasks:
             │  in the query       │     • corporate_structure  → corporate_agent
             │                     │     • beneficial_ownership → corporate_agent
             │                     │     • sanctions_screening  → legal_agent
             │                     │     • transaction_patterns → corporate_agent
             │                     │     • adverse_media        → social_graph_agent
             │                     │
             │  Generic query      │   "Investigate Ford" → 3 default tasks:
             │  (no AML keywords)  │     • sec_filings          → corporate_agent
             │                     │     • sanctions_screening  → legal_agent
             │                     │     • adverse_media        → social_graph_agent
             └────────┬────────────┘
                      │
                      ▼
             ┌─────────────────────┐
             │  3. CONTEXT MANAGER │   File: agents/lead_agent/context_manager/context.py
             │                     │
             │  Holds:             │   • The resolved Entity
             │  InvestigationContext   • The query string
             │                     │   • The list of SubTasks
             │                     │   • Results from each agent (populated below)
             └────────┬────────────┘
                      │
           ┌──────────┼──────────────────┐
           │          │                  │
           ▼          ▼                  ▼
    ┌────────────┐ ┌──────────┐ ┌───────────────┐
    │ CORPORATE  │ │  LEGAL   │ │ SOCIAL GRAPH  │
    │   AGENT    │ │  AGENT   │ │     AGENT     │
    │            │ │          │ │               │
    │ ✅ REAL    │ │ ⚠️ STUB  │ │ ⚠️ STUB      │
    │   DATA     │ │          │ │               │
    └─────┬──────┘ └────┬─────┘ └──────┬────────┘
          │              │              │
          └──────────────┴──────────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │  4. MCP LAYER       │   File: mcp_layer/__init__.py (facade)
              │                     │
              │  get_evidence_for_  │   Called by Corporate Agent.
              │  entity(entity,     │   Dispatches to:
              │  sources=[          │     • SecEdgarProcessor  → reads data/raw/sec/
              │    "sec_edgar",     │     • NhtsaProcessor     → reads data/raw/nhtsa/
              │    "nhtsa"          │   Returns List[Evidence]
              │  ])                 │
              └─────────┬───────────┘
                        │
                        ▼
         ┌──────────────────────────────┐
         │  5. REFLEXION LAYER          │   File: reflexion_layer/
         │                              │
         │  cross_check_findings()  →   │   Compares evidence rows; flags conflicts
         │  detect_gaps()           →   │   Lists what's missing (e.g. no sanctions data)
         │  aggregate_confidence()  →   │   Mean confidence score per category/source
         └──────────────┬───────────────┘
                        │
                        ▼
         ┌──────────────────────────────┐
         │  6. KNOWLEDGE GRAPH          │   File: knowledge_graph/graph.py
         │                              │
         │  build_graph_from_evidence() │   Nodes: entity + each evidence row
         │                              │   Edges: has_evidence, same_source_type
         └──────────────┬───────────────┘
                        │
                        ▼
         ┌──────────────────────────────┐
         │  7. OUTPUT LAYER             │   File: output_layer/
         │                              │
         │  generate_html_report()  →   │   Full cited evidence report (HTML)
         │  compute_risk_scores()   →   │   Risk scores: governance, regulatory, legal, network
         │  format_dashboard_cli()  →   │   Terminal-friendly risk summary
         │  AuditTrail              →   │   Every step logged with timestamps
         └──────────────┬───────────────┘
                        │
                        ▼
         ┌──────────────────────────────┐
         │  8. FLASK WEB APP            │   File: app/app.py  +  app/pipeline.py
         │                              │
         │  GET  /  → query form        │   User enters query
         │  POST /  → full pipeline     │   Runs steps 1–7, returns results page
         │                              │
         │  Shows: entity resolved,     │
         │  tasks, findings count,      │
         │  risk dashboard, gaps,       │
         │  evidence report, audit log  │
         └──────────────────────────────┘
```

### Live Output of Pipeline (Tesla, 2026-03-15)

Running `python scripts/run_lead_agent.py` gives:

```
Query:  Investigate Tesla for money laundering
Entity: tesla_inc_cik_0001318605  Tesla, Inc.  {cik: 0001318605, ticker: TSLA, make: TESLA}
Tasks:  5
  - corporate_structure  → corporate_agent
  - beneficial_ownership → corporate_agent
  - sanctions_screening  → legal_agent
  - transaction_patterns → corporate_agent
  - adverse_media        → social_graph_agent
Findings: 1185
   corporate_agent    : 1183 evidence items   ← real SEC + NHTSA data
   legal_agent        : 1 evidence item       ← stub placeholder
   social_graph_agent : 1 evidence item       ← stub placeholder
```

---

## 4. Every Agent Explained — What It Does and What State It Is In

### 4.1 Lead Agent (Orchestrator)
**File**: `agents/lead_agent/orchestrator.py`
**Status**: ✅ Complete
**What it does**: The brain. It receives the raw query, coordinates all other agents, and returns the complete `InvestigationContext`. It does not do any investigation itself — it delegates.

Sub-components:

| Sub-component | File | Status | What it does |
|---|---|---|---|
| Entity Resolution | `entity_resolution/resolver.py` | ✅ Works (2 entities) | Looks up "Tesla" or "Ford" in ENTITY_REGISTRY, returns structured Entity with CIK, ticker, make |
| Task Planner | `task_planner/planner.py` | ✅ Complete | Detects keywords (money laundering, AML, fraud, etc.) → 5 tasks; generic query → 3 default tasks |
| Context Manager | `context_manager/context.py` | ✅ Complete | Stores entity, query, tasks, and per-agent findings; thread-safe copies on read |

**Entities currently in registry**:

| Entity | entity_id | CIK | Ticker | NHTSA Make |
|---|---|---|---|---|
| Tesla, Inc. | `tesla_inc_cik_0001318605` | 0001318605 | TSLA | TESLA |
| Ford Motor Company | `ford_motor_cik_0000037996` | 0000037996 | F | FORD |

---

### 4.2 Corporate Agent
**File**: `agents/specialist_agents/corporate_agent/agent.py`
**Status**: ✅ Working — produces REAL evidence from government data sources

**What it does**: Handles corporate structure, governance, regulatory compliance, and beneficial ownership tasks. It fetches data via the MCP layer.

Sub-components:

| Sub-component | File | Status | Real Data Source | What it produces |
|---|---|---|---|---|
| SEC Analyzer | `sec_analyzer/analyzer.py` | ✅ Real | SEC EDGAR submissions API | Counts SEC filings and 8-K events; creates 1 governance summary Evidence row |
| MCP call (main) | via `mcp_layer/` | ✅ Real | SEC EDGAR + NHTSA DOT DataHub | All recall + filing Evidence rows for the entity |
| Structure Mapper | `structure_mapper/mapper.py` | ⚠️ Stub | OpenCorporates (planned) | Returns 1 placeholder Evidence row with `stub=True` |

**Evidence it produces for Tesla** (example from live run):
- 90 NHTSA recall records → `source_type=regulator_api`, `risk_category=regulatory`
- 1 SEC governance summary → `source_type=sec_filing`, `risk_category=governance`
- 1 structure mapper placeholder → `source_type=other`, stub

**Evidence it produces for Ford**:
- 1,693 NHTSA recall records → `risk_category=regulatory`
- 877 SEC filing records → `risk_category=governance` (8-K, 10-K, 10-Q, DEF 14A, etc.)
- 5 SC 13G/D records → `risk_category=network`
- 1 structure mapper placeholder → stub

---

### 4.3 Legal Agent
**File**: `agents/specialist_agents/legal_agent/agent.py`
**Status**: ⚠️ Stub — dispatcher exists but both sub-components return placeholder data

**What it is supposed to do**: Screen entities against government sanctions lists and search for court records / litigation.

Sub-components:

| Sub-component | File | Status | Planned Real Source | What it currently returns |
|---|---|---|---|---|
| Sanctions Screener | `sanctions_screener/screener.py` | ⚠️ Stub | OFAC SDN list (free XML at treasury.gov) | 1 placeholder Evidence row: `"Sanctions screening not yet integrated"` |
| PACER Analyzer | `pacer_analyzer/analyzer.py` | ⚠️ Stub | CourtListener/RECAP (free REST API) | 1 placeholder Evidence row: `"PACER/legal docs not yet integrated"` |

**Impact**: When any query triggers `sanctions_screening` or `litigation` tasks, the Legal Agent returns only 1 meaningless placeholder row. The gap detector correctly flags this as a coverage gap in every run.

**To fix**: See Section 11 — OFAC and CourtListener integrations are the top priority.

---

### 4.4 Social Graph Agent
**File**: `agents/specialist_agents/social_graph_agent/agent.py`
**Status**: ⚠️ Stub — dispatcher exists but both sub-components return placeholder data

**What it is supposed to do**: Find adverse media coverage and map influence networks around the entity.

Sub-components:

| Sub-component | File | Status | Planned Real Source | What it currently returns |
|---|---|---|---|---|
| GNN / Adverse Media Analyzer | `gnn_analyzer/analyzer.py` | ⚠️ Stub | GDELT DOC 2.0 API (free) | 1 placeholder Evidence row: `"Social graph / GNN not yet integrated"` |
| Influence Mapper | `influence_mapper/mapper.py` | ⚠️ Stub | GDELT co-mentions (free) | 1 placeholder Evidence row: `"Influence mapping not yet integrated"` |

**Note on GNN**: The original proposal mentions "Graph Neural Networks" and Twitter/LinkedIn. Twitter/LinkedIn APIs are paid/restricted. GNNs require labeled training data we don't have. The correct academic substitution — which is fully defensible — is **GDELT adverse media** (free, citable news events) + **NetworkX graph analysis** for co-mention networks.

**Impact**: `adverse_media` and `network_analysis` tasks return 1 placeholder each. The gap detector flags these as coverage gaps.

---

### 4.5 Reflexion Layer (not an agent — a QA layer)
**File**: `reflexion_layer/`
**Status**: ✅ Complete — all three components are real and working

| Component | File | What it does |
|---|---|---|
| Cross-check | `cross_check/checker.py` | Groups all evidence by `(entity_id, date)`; flags any pair with conflicting summaries as a `Conflict` |
| Gap Detector | `gap_detection/detector.py` | Inspects context: if entity unresolved → entity_resolution gap; if legal results are stub-only → sanctions gap; if social results are stub-only → adverse media gap; if structure mapper is stub → beneficial_ownership gap |
| Confidence Scorer | `confidence_module/scorer.py` | Computes mean confidence overall + by risk_category + by source_type; applies source reliability weights (SEC=0.95, NHTSA=0.85, court=0.80, news=0.60, other=0.50) |

---

### 4.6 Knowledge Graph (not an agent — a graph builder)
**File**: `knowledge_graph/graph.py`
**Status**: ✅ Complete (no visualization yet)

What it builds:
- **Entity node**: one node per entity (e.g. `ford_motor_cik_0000037996`)
- **Evidence nodes**: one node per Evidence row
- **`has_evidence` edges**: entity → each evidence row
- **`same_source_type` edges**: between evidence rows sharing the same source_type

Currently the graph is in-memory (no database, no visualization). Node and edge counts appear in the HTML report. Visualization with NetworkX + matplotlib or D3.js is a planned next step.

---

### 4.7 MCP Layer (not an agent — the data access layer)
**File**: `mcp_layer/`
**Status**: ✅ Complete

This is the **single controlled gateway** through which all agents access data. No agent calls SEC or NHTSA directly — they go through the MCP facade. This enforces the `Evidence-as-input` contract.

| Processor | File | Status | Data it delivers |
|---|---|---|---|
| SEC EDGAR Processor | `sec_edgar_processor/processor.py` | ✅ Real | Reads `data/raw/sec/CIK{}.json`, converts submissions to `Evidence` with `source_type=sec_filing` |
| NHTSA Processor | `nhtsa_processor/processor.py` | ✅ Real | Reads `data/raw/nhtsa/recalls_make_{MAKE}.json`, converts recalls to `Evidence` with `source_type=regulator_api` |
| Evidence Loader | `evidence_loader.py` | ✅ Real | Loads pre-built evidence CSVs from `data/processed/<entity>/evidence_*.csv` |
| Facade | `__init__.py` | ✅ Real | `get_evidence_for_entity(entity, sources)` — aggregates all requested processors into one `List[Evidence]` |

---

## 5. Data We Are Pulling — Sources, Commands, Files

### Data Sources

| Source | Type | API / URL | Auth Required | What We Get |
|---|---|---|---|---|
| **SEC EDGAR** | Government (US SEC) | `https://data.sec.gov/submissions/CIK{CIK10}.json` | `SEC_USER_AGENT` in `.env` | All company filings: 8-K (events), 10-K (annual), 10-Q (quarterly), DEF 14A (proxy), etc. |
| **NHTSA DOT DataHub** | Government (US DOT) | `https://datahub.transportation.gov/resource/6axg-epim.json` | None (public) | Vehicle safety recall campaigns by manufacturer name |

### Commands to Pull Data for Any Company

```bash
# Step 1: Pull SEC filings (requires .env with SEC_USER_AGENT set)
python scripts/pull_sec_submissions.py --cik <CIK_NUMBER>
# Output: data/raw/sec/CIK<CIK_NUMBER>.json

# Step 2: Pull NHTSA recalls (only for vehicle manufacturers, no auth needed)
python scripts/pull_nhtsa_recalls.py --make <MANUFACTURER_NAME>
# Output: data/raw/nhtsa/recalls_make_<MAKE>.json

# Step 3: Build structured evidence CSV
python scripts/build_evidence_tesla.py    # for Tesla
python scripts/build_evidence_ford.py     # for Ford
# Output: data/processed/<entity>/evidence_<entity>.csv
```

### How to Find a CIK Number

Go to: `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company=COMPANY+NAME&type=10-K&dateb=&owner=include&count=10`

Or search directly: `https://efts.sec.gov/LATEST/search-index?q=%22Apple%22&dateRange=custom&startdt=2024-01-01`

### Data Files On Disk (Current State)

```
data/
├── raw/
│   ├── sec/
│   │   ├── CIK0001318605.json      Tesla SEC submissions (fetched 2026-03-15)
│   │   └── CIK0000037996.json      Ford SEC submissions  (fetched 2026-03-15)
│   └── nhtsa/
│       ├── recalls_make_TESLA.json  Tesla NHTSA recalls   (fetched 2026-03-15)
│       └── recalls_make_FORD.json   Ford NHTSA recalls    (fetched 2026-03-15)
└── processed/
    ├── tesla/
    │   └── evidence_tesla.csv       91 evidence rows
    └── ford/
        └── evidence_ford.csv        2,570 evidence rows
```

> **Note**: The `data/` directory is in `.gitignore` and is NOT committed to GitHub. Each teammate must run the pull scripts locally. The `.env` file is also gitignored — each teammate creates their own.

---

## 6. How to Run Everything Right Now

### First-Time Setup (do this once)

```bash
# 1. Clone and enter the repo
git clone <repo-url>
cd FSE570

# 2. Create a virtual environment and activate it
python -m venv .venv
source .venv/bin/activate          # macOS/Linux
# .venv\Scripts\activate           # Windows

# 3. Install all dependencies
pip install -r requirements-dev.txt

# 4. Create .env file (required for SEC EDGAR)
cp .env.example .env
# Open .env and set:   SEC_USER_AGENT="Your Name your_email@asu.edu"
```

### Pull Raw Data

```bash
# Tesla (vehicle manufacturer — pull both)
python scripts/pull_sec_submissions.py --cik 0001318605
python scripts/pull_nhtsa_recalls.py --make TESLA
python scripts/build_evidence_tesla.py

# Ford (vehicle manufacturer — pull both)
python scripts/pull_sec_submissions.py --cik 0000037996
python scripts/pull_nhtsa_recalls.py --make FORD
python scripts/build_evidence_ford.py
```

### Run the Tests

```bash
pytest tests/unit -v
# Expected: 82 passed, 0 failed, 0 errors
```

### Run the Lead Agent (Terminal Demo)

```bash
python scripts/run_lead_agent.py
# Default query: "Investigate Tesla for money laundering"

python scripts/run_lead_agent.py "Investigate Ford for fraud"
# Will resolve Ford, decompose tasks, dispatch agents, print findings summary
```

### Run the Full Flask Web Demo

```bash
python app/app.py
# Open http://127.0.0.1:5000 in browser
# Type: "Investigate Tesla for money laundering"  →  click Run investigation
```

> **macOS note**: If port 5000 is busy (AirPlay Receiver conflict), run:
> `flask --app app/app.py run --port 5001`
> or disable AirPlay Receiver in System Settings → General → AirDrop & Handoff.

### What You See in the Flask App

The results page shows:
- **Entity resolved**: name + identifiers (CIK, ticker)
- **Tasks**: which tasks were generated and which agent handled each
- **Findings count**: total evidence rows by agent
- **Risk Dashboard**: scored by governance / regulatory / legal / network
- **Gaps detected**: e.g. "sanctions coverage missing", "adverse media missing"
- **Conflicts**: any cross-source contradictions found
- **Evidence Report**: full HTML report with citations and confidence per finding
- **Audit Trail**: timestamped log of every pipeline step

---

## 7. Test Results — 2026-03-15

**Command**: `pytest tests/unit -v`
**Python**: 3.10.16 | **pytest**: 7.4.4 | **Runtime**: 0.23 s

```
82 passed, 0 skipped, 0 failed, 0 errors
```

> Previously (before `.env` was created and SEC data was pulled), there was 1 skip.
> Now all 82 tests pass including the SEC cache test.

### Coverage by Module

| Module | Tests | Result |
|---|---|---|
| Lead Agent — Context Manager | 6 | ✅ All pass |
| Lead Agent — Entity Resolution | 6 | ✅ All pass |
| Lead Agent — Orchestrator | 4 | ✅ All pass |
| Lead Agent — Task Planner | 5 | ✅ All pass |
| Specialist Agents — Corporate | 5 | ✅ All pass |
| Specialist Agents — Legal | 3 | ✅ All pass |
| Specialist Agents — Social Graph | 3 | ✅ All pass |
| Knowledge Graph | 4 | ✅ All pass |
| MCP Layer — Base | 1 | ✅ All pass |
| MCP Layer — Evidence Loader | 4 | ✅ All pass |
| MCP Layer — Facade | 5 | ✅ All pass |
| MCP Layer — NHTSA Processor | 4 | ✅ All pass |
| MCP Layer — SEC Processor | 3 | ✅ All pass |
| Output — Audit Trail | 5 | ✅ All pass |
| Output — Evidence Report | 5 | ✅ All pass |
| Output — Risk Dashboard | 4 | ✅ All pass |
| Reflexion — Confidence Module | 5 | ✅ All pass |
| Reflexion — Cross-check | 5 | ✅ All pass |
| Reflexion — Gap Detection | 5 | ✅ All pass |
| **TOTAL** | **82** | **✅ 82/82** |

---

## 8. Data Inventory — What Has Been Collected

### Tesla, Inc. (`tesla_inc_cik_0001318605`)

| File | Records | Date Range | Source |
|---|---|---|---|
| `data/raw/sec/CIK0001318605.json` | 1,001 filings (recent history) | up to 2026 | SEC EDGAR |
| `data/raw/nhtsa/recalls_make_TESLA.json` | 90 recall campaigns | 2009-05-26 → 2025-10-28 | DOT DataHub |
| `data/processed/tesla/evidence_tesla.csv` | **91 rows** | 2009 → 2025 | Built from above |

Tesla evidence breakdown:
- 90 rows: NHTSA recalls → `source_type=regulator_api`, `risk_category=regulatory`, confidence=0.80
- 1 row: SEC 8-K (CFO change 2023-08-04) → `source_type=sec_filing`, `risk_category=governance`, confidence=0.95

> Note: `build_evidence_tesla.py` uses 1 hardcoded SEC seed + all NHTSA records. Tesla's SEC JSON is cached and available, but the Tesla build script has not yet been updated to extract all SEC filings (unlike the Ford script). This is a quick improvement — update `build_evidence_tesla.py` to mirror `build_evidence_ford.py`.

### Ford Motor Company (`ford_motor_cik_0000037996`)

| File | Records | Date Range | Source |
|---|---|---|---|
| `data/raw/sec/CIK0000037996.json` | 1,001 filings (recent history) | up to 2026-03-13 | SEC EDGAR |
| `data/raw/nhtsa/recalls_make_FORD.json` | 1,693 recall campaigns | 1966-10-06 → 2026-03-03 | DOT DataHub |
| `data/processed/ford/evidence_ford.csv` | **2,570 rows** | 1966 → 2026 | Built from above |

Ford evidence breakdown:
- 1,693 rows: NHTSA recalls → `source_type=regulator_api`, `risk_category=regulatory`, confidence=0.80
- 872 rows: SEC filings (8-K, 10-K, 10-Q, DEF 14A, 4/3/5) → `source_type=sec_filing`, `risk_category=governance`, confidence=0.95
- 5 rows: SEC Schedule 13G/D (significant ownership disclosures) → `source_type=sec_filing`, `risk_category=network`, confidence=0.95

### Combined Evidence Across Both Entities

| Metric | Value |
|---|---|
| Total evidence rows on disk | **2,661** (91 Tesla + 2,570 Ford) |
| Data sources integrated | **2** (SEC EDGAR, NHTSA DOT DataHub) |
| Entities in registry | **2** (Tesla, Ford) |
| Date range covered | 1966 → 2026 |
| Source types present | `sec_filing`, `regulator_api` |
| Risk categories covered | `governance`, `regulatory`, `network` |
| Risk categories with NO real data yet | `legal` (sanctions, court records), `network` from adverse media |

---

## 9. Feasibility Assessment

### Overall Verdict: Fully Achievable with One Substitution

| Proposal Feature | Verdict | Notes |
|---|---|---|
| Multi-agent swarm architecture | ✅ Done | Lead Agent + 3 specialists fully wired |
| SEC EDGAR governance data | ✅ Done | Real data for Tesla + Ford |
| NHTSA regulatory data | ✅ Done | Real data for Tesla + Ford |
| OFAC / Sanctions screening | ✅ Achievable | Free XML at treasury.gov — 1–2 days of work |
| CourtListener legal docs | ✅ Achievable | Free REST API, no auth — 2–3 days |
| GDELT adverse media | ✅ Achievable | Free API, no auth — 2–3 days |
| OpenCorporates beneficial ownership | ⚠️ Partial | Free tier is rate-limited; curated CSV viable |
| GNN / Graph Neural Network | ⚠️ Aspirational | No labeled training data; **substitute: NetworkX co-mention graph from GDELT** |
| Twitter/LinkedIn social graph | ❌ Not achievable | Paid APIs / ToS violations — **substitute with GDELT** |
| Reflexion / self-correction | ✅ Done | All three components working |
| Knowledge graph | ✅ Done | In-memory; visualization pending |
| Evidence report + audit trail | ✅ Done | HTML + Markdown + JSON audit log |
| Flask web demo | ✅ Done | Full pipeline in browser |
| Multi-entity support | ✅ Growing | Tesla + Ford; adding more is 1 command + 1 registry entry |

---

## 10. What Is Working vs What Is a Stub

### ✅ Fully Working (Real Data, Real Logic)

| Component | What Happens in a Live Run |
|---|---|
| Entity resolution | "Tesla" → `tesla_inc_cik_0001318605` with full identifiers |
| Task planner | "money laundering" → 5 targeted sub-tasks correctly assigned |
| Context manager | Stores and retrieves entity/tasks/results cleanly |
| Lead Agent orchestration | Dispatches all tasks, collects all results, returns complete context |
| MCP SEC EDGAR processor | Reads cached SEC JSON, converts filings to Evidence rows |
| MCP NHTSA processor | Reads cached NHTSA JSON, converts recalls to Evidence rows |
| Corporate Agent | Fetches real SEC + NHTSA evidence via MCP; produces governance summary |
| Reflexion — cross-check | Flags conflicting evidence across agents |
| Reflexion — gap detection | Correctly flags missing sanctions, legal, adverse media coverage |
| Reflexion — confidence | Computes weighted confidence per category (SEC=0.95, NHTSA=0.85) |
| Knowledge graph | Builds node/edge graph from all evidence |
| Evidence report | Generates formatted HTML + Markdown with citations |
| Risk dashboard | Scores governance / regulatory / legal / network with finding counts |
| Audit trail | Logs every pipeline step with timestamps |
| Flask web app | Full end-to-end pipeline rendered in browser |
| All 82 unit tests | Pass in 0.23 seconds |

### ⚠️ Stubs (Placeholder — Real Data Not Yet Integrated)

| Component | What It Currently Returns | What It Should Return |
|---|---|---|
| Legal Agent → Sanctions Screener | 1 row: `"Sanctions screening not yet integrated"` | Matched entries from OFAC SDN list / UN / EU sanctions |
| Legal Agent → PACER Analyzer | 1 row: `"PACER/legal docs not yet integrated"` | Court cases from CourtListener REST API |
| Corporate Agent → Structure Mapper | 1 row: `"Beneficial ownership not yet integrated"` | Subsidiary/ownership data from OpenCorporates or SEC 13G filings |
| Social Graph Agent → GNN Analyzer | 1 row: `"Social graph not yet integrated"` | Adverse media events from GDELT |
| Social Graph Agent → Influence Mapper | 1 row: `"Influence mapping not yet integrated"` | Co-mention network data from GDELT |

**Important**: All stubs follow the exact same `SpecialistAgent` protocol and return a valid `Evidence` object. This means the Reflexion layer, knowledge graph, and output layer all handle them gracefully — they just produce low-information results. Replacing any stub with real data requires **only editing that one stub file** — zero changes to the rest of the pipeline.

---

## 11. What Is Left and Immediate Next Steps

### Priority 1 — Critical (Must Have for Demo)

#### 1a. Fix Tesla evidence to use full SEC filings (Taljinder — 1 hour)
`build_evidence_tesla.py` currently uses only 1 hardcoded SEC seed row. The SEC data is already on disk. Update the script to mirror the Ford approach and extract all governance SEC filings.

#### 1b. OFAC Sanctions Screening (Raj + Arnab — 1–2 days)
**File to edit**: `agents/specialist_agents/legal_agent/sanctions_screener/screener.py`

Replace the stub with a real implementation:
- Source: OFAC SDN list — free XML at `https://www.treasury.gov/ofac/downloads/sdn.xml`
- Implementation: download + cache XML; parse `<sdnEntry>` elements; match entity name/aliases; return `Evidence` rows with `source_type="other"`, `risk_category="legal"`
- Add `lxml` to `requirements.txt`

Also consider: UN Consolidated List, EU Financial Sanctions.

#### 1c. CourtListener Legal Docs (Jacob + Raj — 2–3 days)
**File to edit**: `agents/specialist_agents/legal_agent/pacer_analyzer/analyzer.py`

Replace the stub:
- Source: CourtListener REST API — free, no auth needed
- Endpoint: `https://www.courtlistener.com/api/rest/v3/search/?q=Tesla&type=o&format=json`
- Implementation: search by entity name, extract case name + date + court + citation; return `Evidence` rows with `source_type="court_record"`, `risk_category="legal"`

#### 1d. GDELT Adverse Media (Taljinder + Aditya — 2–3 days)
**Files to edit**:
- `agents/specialist_agents/social_graph_agent/gnn_analyzer/analyzer.py`
- `agents/specialist_agents/social_graph_agent/influence_mapper/mapper.py`

Replace the stubs:
- Source: GDELT DOC 2.0 API — free, no auth
- Endpoint: `https://api.gdeltproject.org/api/v2/doc/doc?query=Tesla%20fraud&mode=artlist&maxrecords=50&format=json`
- Implementation: query by entity name + risk keywords; filter by negative tone; return `Evidence` rows with `source_type="news_article"`, `risk_category="network"`

#### 1e. Add more entities to registry (Taljinder — 1 day)
**File to edit**: `agents/lead_agent/entity_resolution/resolver.py`

Add at least 1–2 more companies. Good candidates:

| Company | CIK | NHTSA make | Notes |
|---|---|---|---|
| Boeing | 0000012927 | N/A | Aviation → no NHTSA; rich SEC governance |
| ExxonMobil | 0000034088 | N/A | No NHTSA; interesting for AML demo |
| General Motors | 0000040533 | CHEVROLET / GMC | Both SEC + NHTSA |

For each: add to registry, run `pull_sec_submissions.py --cik <CIK>`, create `build_evidence_<entity>.py` (copy from `build_evidence_ford.py`, change entity ID and constants).

---

### Priority 2 — Important (Should Have)

| Task | Files | Effort | Owner |
|---|---|---|---|
| Update `build_evidence_tesla.py` to extract full SEC filings | `scripts/build_evidence_tesla.py` | 30 min | Taljinder |
| OpenCorporates beneficial ownership | `corporate_agent/structure_mapper/mapper.py` | 2–3 days | Arnab, Raj |
| Knowledge graph visualization (NetworkX or D3.js) | `knowledge_graph/`, `app/templates/results.html` | 1–2 days | Aditya |
| Real vs stub labels in Flask UI | `app/templates/results.html` | Half day | Aditya, Jacob |
| Fuzzy entity matching (rapidfuzz) | `agents/lead_agent/entity_resolution/resolver.py` | 1 day | Taljinder |
| Evaluation metrics (citations/claim, coverage %, runtime) | `app/pipeline.py`, `docs/` | 1 day | All |

---

### Priority 3 — Polish

| Task | Files | Effort | Owner |
|---|---|---|---|
| One-command run script | `scripts/run_demo.sh` | Half day | Jacob |
| Deployment runbook | `docs/DEPLOYMENT.md` | 1 day | Jacob |
| Final evaluation write-up | `docs/EVALUATION.md` | 2 days | All |

---

## 12. Timeline

| Week | Target | Owner |
|---|---|---|
| Mar 15–21 (now) | Fix Tesla SEC, OFAC screening, CourtListener, GDELT, add entities | Taljinder, Raj, Arnab, Jacob |
| Mar 22–28 | OpenCorporates/structure map, KG visualization, UI labels | Aditya, Arnab, Raj |
| Mar 29 – Apr 4 | Evaluation metrics, fuzzy matching, entity resolution improvements | All |
| Apr 5–11 | Demo polish, one-command run, deployment runbook | Jacob, Aditya |
| Final weeks | Evaluation write-up, demo rehearsal, submission | All |

---

## 13. Repository Structure

```
FSE570/
│
├── .env                         ← YOUR local config (gitignored — create from .env.example)
├── .env.example                 ← Template: SEC_USER_AGENT="Name email@asu.edu"
├── .gitignore                   ← Ignores: .venv/, .env, data/raw/, data/processed/, extras/
├── Architecture-Diagram.jpeg    ← Visual architecture diagram
├── README.md                    ← Quickstart guide
├── pyproject.toml               ← Project metadata + pytest config (pythonpath: src + root)
├── requirements.txt             ← requests, python-dotenv, flask, markdown
├── requirements-dev.txt         ← + pytest
│
├── agents/                      ← ALL AGENT CODE
│   ├── lead_agent/
│   │   ├── orchestrator.py      ✅ Lead Agent: entity resolve → plan → dispatch → return context
│   │   ├── context_manager/     ✅ InvestigationContext (entity, query, tasks, results)
│   │   ├── entity_resolution/   ✅ ENTITY_REGISTRY — Tesla + Ford currently
│   │   └── task_planner/        ✅ Keyword decomposition → SubTask list
│   └── specialist_agents/
│       ├── base.py              ✅ SpecialistAgent Protocol (run → List[Evidence])
│       ├── corporate_agent/     ✅ REAL DATA — SEC + NHTSA via MCP
│       ├── legal_agent/         ⚠️ STUB — OFAC + CourtListener not integrated
│       └── social_graph_agent/  ⚠️ STUB — GDELT not integrated
│
├── app/                         ← FLASK WEB APP
│   ├── app.py                   ✅ Flask routes (GET / → form, POST / → pipeline)
│   ├── pipeline.py              ✅ Full pipeline: Lead Agent → Reflexion → KG → Report
│   └── templates/               ✅ base.html, index.html, results.html
│
├── data/                        ← GITIGNORED — generated locally by running scripts
│   ├── raw/
│   │   ├── sec/CIK*.json        Raw SEC submissions JSON (fetched by pull_sec_submissions.py)
│   │   └── nhtsa/recalls_*.json Raw NHTSA recall JSON  (fetched by pull_nhtsa_recalls.py)
│   └── processed/
│       └── <entity>/evidence_*.csv  Structured Evidence CSVs (built by build_evidence_*.py)
│
├── docs/                        ← ALL DOCUMENTATION
│   ├── PROJECT_STATUS.md        ← This file (updated 2026-03-15)
│   ├── IMPLEMENTATION_PLAN.md   Phase 1–7 plan with Mermaid diagram
│   ├── QUAD_CHART.md            Status quadrant (last updated 2026-02-28)
│   ├── schema.md                Entity + Evidence schema reference
│   ├── data_sources.md          Data sources blueprint
│   └── EVIDENCE_AS_INPUT.md     Evidence-as-canonical-input contract
│
├── knowledge_graph/             ← GRAPH BUILDER
│   ├── graph.py                 ✅ build_graph_from_evidence() → nodes + edges
│   └── types.py                 ✅ Node + Edge dataclasses
│
├── mcp_layer/                   ← DATA ACCESS LAYER (agents go through this, not connectors)
│   ├── __init__.py              ✅ Facade: get_evidence_for_entity()
│   ├── base.py                  ✅ Abstract DataSourceProcessor
│   ├── evidence_loader.py       ✅ load_evidence_from_csv()
│   ├── nhtsa_processor/         ✅ Cache-first NHTSA evidence
│   └── sec_edgar_processor/     ✅ Cache-first SEC evidence
│
├── output_layer/                ← REPORT + DASHBOARD + AUDIT
│   ├── audit_trail/             ✅ Append-only timestamped event log
│   ├── evidence_report_generator/ ✅ MD + HTML report with citations
│   └── risk_dashboard/          ✅ Risk scores by category + CLI formatter
│
├── reflexion_layer/             ← QA / SELF-CORRECTION LAYER
│   ├── confidence_module/       ✅ Source-weighted confidence aggregation
│   ├── cross_check/             ✅ Conflict detection
│   └── gap_detection/           ✅ Coverage gap identification
│
├── scripts/                     ← RUNNABLE SCRIPTS
│   ├── pull_sec_submissions.py  ✅ Fetch + cache SEC data for any CIK
│   ├── pull_nhtsa_recalls.py    ✅ Fetch + cache NHTSA data for any make
│   ├── build_evidence_tesla.py  ✅ Build evidence_tesla.csv (91 rows; 1 SEC seed + 90 NHTSA)
│   ├── build_evidence_ford.py   ✅ Build evidence_ford.csv (2,570 rows; 877 SEC + 1693 NHTSA)
│   └── run_lead_agent.py        ✅ CLI demo of Lead Agent for any query
│
├── src/osint_swarm/             ← CORE LIBRARY (schemas + connectors)
│   ├── entities.py              ✅ Entity + Evidence frozen dataclasses
│   ├── data_sources/sec_edgar.py ✅ SEC EDGAR HTTP connector
│   ├── data_sources/nhtsa.py    ✅ DOT DataHub HTTP connector
│   └── utils/io.py              ✅ JSON/CSV helpers
│
└── tests/unit/                  ← UNIT TESTS (82 tests, all pass)
    ├── agents/                  13 tests
    ├── knowledge_graph/         4 tests
    ├── mcp_layer/               17 tests
    ├── output_layer/            14 tests
    └── reflexion_layer/         15 tests + 1 in specialist_agents
```

---

## 14. Schema Reference

### Entity (frozen dataclass — `src/osint_swarm/entities.py`)

```python
entity_id:    str        # "tesla_inc_cik_0001318605"
name:         str        # "Tesla, Inc."
entity_type:  Literal["public_company", "private_company", "nonprofit", "individual", "unknown"]
country:      Optional[str]          # "US"
jurisdiction: Optional[str]          # "Delaware"
identifiers:  Dict[str, str]         # {"cik": "0001318605", "ticker": "TSLA", "make": "TESLA"}
aliases:      List[str]              # ["Tesla", "Tesla Inc", "Tesla Motors", "TSLA"]
```

### Evidence (frozen dataclass — `src/osint_swarm/entities.py`)

```python
evidence_id:   str        # deterministic slug, e.g. "ford_nhtsa_26v124000"
entity_id:     str        # links to Entity.entity_id
date:          str        # ISO date: "2026-03-03"
source_type:   Literal[   # where this evidence came from
    "sec_submissions", "sec_filing",
    "regulator_api", "regulator_report",
    "court_record", "news_article", "other"
]
risk_category: Literal[   # what kind of risk this relates to
    "governance",         # SEC filings, exec changes, board disclosures
    "regulatory",         # NHTSA recalls, regulator actions
    "legal",              # sanctions hits, court cases
    "network",            # adverse media, ownership, co-mentions
    "other"
]
summary:       str        # human-readable citable claim (truncated at 5000 chars)
source_uri:    str        # direct URL to primary source document
raw_location:  Optional[str]   # local path under data/raw/
confidence:    float      # 0.0–1.0 (sec_filing=0.95, regulator_api=0.80, news=0.60)
attributes:    Dict[str, Any]  # source-specific fields (form type, NHTSA ID, etc.)
```

### Confidence Weights (applied in `reflexion_layer/confidence_module/scorer.py`)

| Source Type | Weight |
|---|---|
| `sec_filing` | 0.95 |
| `regulator_api` | 0.85 |
| `court_record` | 0.80 |
| `news_article` | 0.60 |
| `other` | 0.50 |

---

*Generated 2026-03-15. Based on complete codebase audit, live test runs, and verified data pipeline execution.*
