# Project Status — Autonomous OSINT Investigation Swarm

**Last updated: 2026-03-15**
**159/159 unit tests passing | 4 live data sources | 3 entities verified | Legal Agent fully live**

---

## Table of Contents

1. [What This Project Does](#1-what-this-project-does)
2. [Pipeline Architecture (Visual)](#2-pipeline-architecture-visual)
3. [Core Data Schema](#3-core-data-schema)
4. [Data Sources — Full Technical Detail](#4-data-sources)
5. [Repository Structure](#5-repository-structure)
6. [Every Component — Implementation Detail](#6-every-component)
7. [End-to-End Workflow & Commands](#7-end-to-end-workflow--commands)
8. [Entity Registry](#8-entity-registry)
9. [Live Data Inventory](#9-live-data-inventory)
10. [Environment Setup for Teammates](#10-environment-setup-for-teammates)
11. [Test Suite & Audit](#11-test-suite--audit)
12. [Hard-Coding Audit](#12-hard-coding-audit)
13. [Known Limitations (Honest)](#13-known-limitations)
14. [Design Decisions & Rationale](#14-design-decisions--rationale)
15. [Sprint History & Bug Fix Log](#15-sprint-history--bug-fix-log)
16. [Next Steps](#16-next-steps)
17. [Team Roles](#17-team-roles)

---

## 1. What This Project Does

This is a **multi-agent OSINT (Open Source Intelligence) investigation system** for **corporate risk assessment and AML (Anti-Money Laundering) screening**.

**In plain English:** You type a question like *"Investigate Tesla for money laundering"*, and the system automatically:
1. Figures out you're asking about Tesla, Inc. (CIK 0001318605)
2. Creates 6 investigation sub-tasks
3. Dispatches them to 3 specialist agents in parallel
4. Each agent queries real public data (SEC filings, OFAC sanctions list, court dockets, news)
5. Returns structured, citable evidence with confidence scores
6. A reflexion layer cross-checks for conflicts and flags gaps
7. Outputs a risk dashboard, evidence report, and audit trail

**What is "evidence"?** Every finding is a frozen Python dataclass (`Evidence`) with: entity ID, date, source type, risk category, summary, source URL, raw file location, confidence score (0.0–1.0), and extra attributes. Nothing is made up — every row traces back to a real government filing, court record, sanctions entry, or news article.

---

## 2. Pipeline Architecture (Visual)

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                  AUTONOMOUS OSINT INVESTIGATION SWARM                      ║
╚══════════════════════════════════════════════════════════════════════════════╝

    ┌──────────────────────────────────────────────────────────────┐
    │                    USER QUERY (natural language)             │
    │              "Investigate Tesla for money laundering"        │
    └───────────────────────────┬──────────────────────────────────┘
                                │
                                ▼
    ╔══════════════════════════════════════════════════════════════╗
    ║                       LEAD AGENT                            ║
    ║  ┌─────────────────┐  ┌──────────────┐  ┌───────────────┐  ║
    ║  │Entity Resolution│  │ Task Planner │  │Context Manager│  ║
    ║  │                 │  │              │  │               │  ║
    ║  │ "Tesla" → match │  │ Query has    │  │ Holds:        │  ║
    ║  │ in ENTITY_      │  │ "money       │  │  • entity     │  ║
    ║  │ REGISTRY via    │  │  laundering" │  │  • tasks[]    │  ║
    ║  │ alias lookup +  │  │ → emit 6     │  │  • findings{} │  ║
    ║  │ whole-word      │  │   sub-tasks  │  │    per agent  │  ║
    ║  │ matching        │  │              │  │               │  ║
    ║  └────────┬────────┘  └──────┬───────┘  └───────────────┘  ║
    ╚═══════════╪══════════════════╪══════════════════════════════╝
                │                  │
                │    ┌─────────────┴──────────────────────────────────────┐
                │    │  6 SubTasks dispatched to specialist agents:       │
                │    │                                                    │
                │    │  1. corporate_structure   → corporate_agent        │
                │    │  2. beneficial_ownership  → corporate_agent (stub) │
                │    │  3. sanctions_screening   → legal_agent (OFAC)     │
                │    │  4. litigation            → legal_agent (Courts)   │
                │    │  5. transaction_patterns  → corporate_agent        │
                │    │  6. adverse_media         → social_graph_agent     │
                │    └───────────────────────────────────────────────────-┘
                │
    ┌───────────┼──────────────────────────────────┐
    │           │                                  │
    ▼           ▼                                  ▼
╔═══════════════════╗ ╔════════════════════════╗ ╔═══════════════════════╗
║  CORPORATE AGENT  ║ ║     LEGAL AGENT        ║ ║  SOCIAL GRAPH AGENT   ║
║                   ║ ║                        ║ ║                       ║
║ Tasks 1,2,5       ║ ║ Tasks 3,4              ║ ║ Task 6                ║
║                   ║ ║                        ║ ║                       ║
║ ┌───────────────┐ ║ ║ ┌────────────────────┐ ║ ║ ┌───────────────────┐ ║
║ │SEC MCP Layer  │ ║ ║ │ OFAC SDN Screener  │ ║ ║ │ GDELT MCP Layer   │ ║
║ │ → 500 filings │ ║ ║ │ → 18,712 entries   │ ║ ║ │ → 100 articles    │ ║
║ │ conf=0.85     │ ║ ║ │ conf=0.90          │ ║ ║ │ conf=0.60         │ ║
║ └───────────────┘ ║ ║ └────────────────────┘ ║ ║ └───────────────────┘ ║
║ ┌───────────────┐ ║ ║ ┌────────────────────┐ ║ ╚═══════════════════════╝
║ │Structure      │ ║ ║ │ CourtListener      │ ║
║ │Mapper (stub)  │ ║ ║ │ → 20 dockets       │ ║
║ │ conf=0.0      │ ║ ║ │ conf=0.85          │ ║
║ └───────────────┘ ║ ║ └────────────────────┘ ║
╚═══════════════════╝ ╚════════════════════════╝
         │                       │                          │
         └───────────────────────┼──────────────────────────┘
                                 │
                    All Evidence rows collected
                    into InvestigationContext
                                 │
                                 ▼
    ╔══════════════════════════════════════════════════════════════╗
    ║                    REFLEXION LAYER                          ║
    ║                                                            ║
    ║  ┌──────────────┐ ┌──────────────┐ ┌────────────────────┐  ║
    ║  │ Cross-Check  │ │Gap Detection │ │ Confidence Scoring │  ║
    ║  │              │ │              │ │                    │  ║
    ║  │ Groups by    │ │ Flags:       │ │ SOURCE_RELIABILITY │  ║
    ║  │ (entity,date)│ │ • no entity  │ │  sec_filing: 0.95  │  ║
    ║  │ → flags      │ │ • empty      │ │  regulator:  0.85  │  ║
    ║  │ different    │ │   agent      │ │  court_rec:  0.80  │  ║
    ║  │ summaries    │ │ • cache miss │ │  news:       0.60  │  ║
    ║  │ as conflicts │ │ • stubs only │ │  other:      0.50  │  ║
    ║  └──────────────┘ └──────────────┘ └────────────────────┘  ║
    ╚══════════════════════════╤═══════════════════════════════════╝
                               │
                               ▼
    ╔══════════════════════════════════════════════════════════════╗
    ║                    KNOWLEDGE GRAPH                          ║
    ║                                                            ║
    ║  NetworkX in-memory graph:                                 ║
    ║    • Node per entity_id (type="entity")                    ║
    ║    • Node per evidence_id (type="evidence")                ║
    ║    • Edge: entity --[has_evidence]--> evidence              ║
    ║    • Edge: evidence --[same_source_type]--> evidence        ║
    ╚══════════════════════════╤═══════════════════════════════════╝
                               │
                               ▼
    ╔══════════════════════════════════════════════════════════════╗
    ║                      OUTPUT LAYER                          ║
    ║                                                            ║
    ║  ┌─────────────────┐ ┌──────────────┐ ┌─────────────────┐  ║
    ║  │Evidence Report  │ │Risk Dashboard│ │  Audit Trail    │  ║
    ║  │                 │ │              │ │                 │  ║
    ║  │ • Markdown      │ │ Scores by:   │ │ Timestamped    │  ║
    ║  │ • HTML          │ │  governance  │ │ JSON-lines     │  ║
    ║  │ • Per-entity    │ │  regulatory  │ │ event log      │  ║
    ║  │   sections      │ │  legal       │ │                 │  ║
    ║  │ • Cited URIs    │ │  network     │ │ Who did what,  │  ║
    ║  │                 │ │  overall     │ │ when, result   │  ║
    ║  └─────────────────┘ └──────────────┘ └─────────────────┘  ║
    ╚══════════════════════════════════════════════════════════════╝
```

**Verified live output for "Investigate Tesla for money laundering" (2026-03-15):**

```
Entity      : Tesla, Inc. (tesla_inc_cik_0001318605)
Tasks       : 6
Results     :
  corporate_agent     : 1,003 findings (500 SEC filings × 2 tasks + summary rows + 1 stub)
  legal_agent         :    22 findings (1 OFAC clean + 1 court summary + 20 dockets)
  social_graph_agent  :   100 findings (GDELT news articles)
  ─────────────────────────────────────────
  TOTAL               : 1,125 findings
Confidence  : overall=0.827 | governance=0.85 | regulatory=0.85 | legal=0.85 | network=0.60
Conflicts   : 87 (same entity/date, different summaries — normal for multi-filing days)
Gaps        : 1 (beneficial_ownership — structure_mapper stub)
```

---

## 3. Core Data Schema

All components exchange two frozen dataclasses defined in `src/osint_swarm/entities.py`:

### Entity — the investigation target

```python
@dataclass(frozen=True)
class Entity:
    entity_id: str                              # "tesla_inc_cik_0001318605"
    name: str                                   # "Tesla, Inc."
    entity_type: EntityType = "unknown"         # "public_company" | "private_company" | "individual" | ...
    country: Optional[str] = None               # reserved for future use
    jurisdiction: Optional[str] = None          # reserved for future use
    identifiers: Dict[str, str] = {}            # {"cik": "0001318605", "ticker": "TSLA"}
    aliases: List[str] = []                     # ["Tesla", "Tesla Inc", "Tesla Motors", "TSLA"]
```

**Why frozen?** Entities are passed between agents; immutability prevents accidental corruption.

### Evidence — a single, citable finding

```python
@dataclass(frozen=True)
class Evidence:
    evidence_id: str                # unique ID (e.g. "tesla_gdelt_a1b2c3d4e5f6")
    entity_id: str                  # links back to Entity
    date: str                       # ISO date "YYYY-MM-DD" (empty if unknown)
    source_type: SourceType         # "sec_filing" | "regulator_api" | "court_record" | "news_article" | ...
    risk_category: RiskCategory     # "governance" | "regulatory" | "legal" | "network" | "other"
    summary: str                    # human-readable finding (≤5000 chars)
    source_uri: str                 # URL to original source (SEC, CourtListener, GDELT)
    raw_location: Optional[str]     # path in data/raw/ for traceability
    confidence: float = 0.5         # 0.0 (no data) to 1.0 (certain)
    attributes: Dict[str, Any] = {} # extra fields: stub, screened, sdn_uid, docket_number, etc.
```

**SourceType values used by each data source:**

| Data Source | `source_type` | `risk_category` | `confidence` |
|-------------|---------------|-----------------|--------------|
| SEC EDGAR | `sec_filing` | `governance` or `regulatory` | `0.85` |
| OFAC SDN | `regulator_api` | `legal` | `0.90` (or `0.0` if cache missing) |
| CourtListener | `court_record` | `legal` | `0.85` (or `0.0` on fetch error) |
| GDELT | `news_article` | `network` | `0.60` |
| Stubs | `other` | varies | `0.0` |

---

## 4. Data Sources

### 4a. SEC EDGAR — US Government Corporate Filings

| Property | Value |
|----------|-------|
| **Source URL** | `https://data.sec.gov/submissions/CIK{cik}.json` |
| **Auth** | `SEC_USER_AGENT` env var (just `"Name email"`, NOT an API key) |
| **Connector file** | `src/osint_swarm/data_sources/sec_edgar.py` |
| **MCP Processor** | `mcp_layer/sec_edgar_processor/processor.py` |
| **Cache path** | `data/raw/sec/CIK{cik}.json` |
| **Pull script** | `python scripts/pull_sec_submissions.py --cik <CIK>` |
| **Confidence** | `0.85` |
| **Filing types parsed** | 10-K, 10-Q, 8-K, DEF 14A, SC 13G, SC 13D, Form 4 |

**How it works:**
1. `pull_sec_submissions.py` calls SEC EDGAR HTTP API with the entity's CIK → caches full JSON
2. `SecEdgarProcessor.get_evidence_for_entity()` reads the cached JSON, parses `recentFilings`, extracts form type, date, and builds an `accessionNumber`-based URL
3. Each filing becomes one `Evidence` row with `source_type="sec_filing"`, `risk_category` determined by form type (10-K/DEF 14A → `governance`, 8-K → `regulatory`)
4. Processor caps at 500 filings per call; `build_evidence.py` has no cap

**Why 0.85?** SEC filings are authoritative government-mandated disclosures, but they report *what the company says*, not independent verification.

### 4b. OFAC SDN — US Treasury Sanctions List

| Property | Value |
|----------|-------|
| **Source URL** | `https://www.treasury.gov/ofac/downloads/sdn.xml` |
| **Auth** | **None** — free public XML |
| **Connector file** | `src/osint_swarm/data_sources/ofac.py` |
| **Screener file** | `agents/specialist_agents/legal_agent/sanctions_screener/screener.py` |
| **Cache path** | `data/raw/ofac/sdn.xml` (27 MB) |
| **Pull script** | `python scripts/pull_ofac_sdn.py --stats` |
| **Confidence** | `0.90` (match or clean), `0.0` (cache missing) |
| **Entries** | 18,712 total: 9,521 entities, 7,394 individuals, 1,455 vessels, 342 aircraft |

**How it works:**
1. `pull_ofac_sdn.py` downloads the full SDN XML to `data/raw/ofac/sdn.xml` (one-time, ~30s)
2. `ofac.parse_sdn_entries()` strips XML namespaces, extracts `uid`, `firstName`, `lastName`, `sdnType`, `programList`, `akaList`, `remarks` per entry
3. `ofac.search_entries()` normalizes both query and SDN names: lowercase, strip punctuation, remove legal suffixes (Inc, LLC, Corp, Ltd, Co, Company)
4. Matching uses `_terms_match()`: exact after normalization, or whole-word substring match (≥5 chars). Query aliases shorter than 3 chars are excluded to prevent ticker false positives
5. `screener.screen()` returns: match rows (conf=0.90, `⚠ OFAC SDN MATCH`), clean row (conf=0.90, `sdn_matches=0`), or cache-missing fallback (conf=0.0)

**Why 0.90?** OFAC SDN is the definitive US government sanctions list. Not 1.0 because name-matching can have edge cases (e.g. common names).

**False-positive prevention (verified):**
- `_normalize("Ford Motor Company")` → `"ford motor"` (strips "Company" suffix)
- `_normalize("OXFORD FINANCIAL HOLDINGS")` → `"oxford financial holdings"` (strips nothing)
- `_terms_match("ford motor", "oxford financial holdings")` → **False** (5+ chars but "ford motor" is NOT a whole word inside "oxford financial holdings")
- Unit test: `test_terms_match_false_positive_oxford_vs_ford` confirms this

### 4c. CourtListener — US Federal Court Dockets

| Property | Value |
|----------|-------|
| **Source URL** | `https://www.courtlistener.com/api/rest/v4/search/` |
| **Auth** | **None** required (optional `COURTLISTENER_API_TOKEN` in `.env` for higher rate limits) |
| **Connector file** | `src/osint_swarm/data_sources/courtlistener.py` |
| **Analyzer file** | `agents/specialist_agents/legal_agent/pacer_analyzer/analyzer.py` |
| **Cache path** | `data/raw/courtlistener/dockets_<slug>.json` |
| **Pull script** | `python scripts/pull_courtlistener.py --all` |
| **Confidence** | `0.85` (found or clean), `0.0` (fetch error) |
| **Max results** | 20 per entity (configurable via `--max-results`) |

**How it works:**
1. `courtlistener.fetch_dockets()` queries the CourtListener v4 search API: `type=d`, `q="Entity Name"`, `order_by=score desc`
2. `_normalize_docket()` handles both camelCase (search results) and snake_case (dockets endpoint) field names. Relative URLs are prepended with `https://www.courtlistener.com/`
3. `pacer_analyzer.fetch()` follows a cache-first pattern: checks `data/raw/courtlistener/dockets_<slug>.json` → if missing, fetches live → caches → converts to Evidence
4. Returns 1 summary row (`court_records=N, total_found_api=M`) + 1 row per docket (case name, docket number, suit nature, cause, court, filing date, termination status)
5. Each docket's `evidence_id` is deterministic: `{entity_id}_courtlistener_{md5(docket_id)[:10]}`

**Why 0.85?** Court records are public, authoritative legal documents — same tier as SEC filings.

**Live data (2026-03-15):**

| Entity | API Total | Cached | Notable Cases |
|--------|-----------|--------|---------------|
| Tesla | 2,054 | 20 | Tremblett v. Tesla (product liability), civil rights employment suits |
| Ford | 21,885 | 20 | Product liability, employment discrimination, contract disputes |
| Boeing | 3,582 | 20 | *In re: The Boeing Company* (securities, CA9 appeal), airplane product liability |

### 4d. GDELT DOC 2.0 — Global Adverse Media

| Property | Value |
|----------|-------|
| **Source URL** | `https://api.gdeltproject.org/api/v2/doc/doc` |
| **Auth** | **None** — completely free, no registration |
| **Connector file** | `src/osint_swarm/data_sources/gdelt.py` |
| **MCP Processor** | `mcp_layer/gdelt_processor/processor.py` |
| **Cache path** | `data/raw/gdelt/news_<slug>.json` |
| **Pull script** | `python scripts/pull_gdelt_news.py --entity-id <ID>` |
| **Confidence** | `0.60` |
| **Max records** | 100 (configurable, GDELT caps at 250) |
| **Lookback** | 730 days (~2 years) |

**How it works:**
1. Builds query: `"Entity Name" (fraud OR investigation OR penalty OR fine OR violation OR lawsuit OR scandal OR misconduct OR bribery OR corruption OR sanction OR money laundering OR settlement OR indictment)`
2. Fetches JSON artlist from GDELT DOC 2.0 API (sorted by date descending)
3. Each article becomes an Evidence row with `source_type="news_article"`, `risk_category="network"`
4. `evidence_id` is deterministic from URL hash: `{entity_prefix}_gdelt_{md5(url)[:12]}`
5. Date parsed from GDELT format `"20240615T120000Z"` → `"2024-06-15"`

**Why 0.60?** News articles are noisy — see Section 13 (Known Limitations) for honest analysis.

### 4e. Not Yet Integrated

| Source | What it would provide | Status | File |
|--------|----------------------|--------|------|
| OpenCorporates | Beneficial ownership, officers, subsidiaries | **Stub** — `structure_mapper/mapper.py` | Priority 1 |

### 4f. Removed (intentionally)

- **NHTSA (vehicle safety recalls)** — removed because it is irrelevant to AML/corporate risk assessment. Zero traces in codebase (verified by `rg -il "nhtsa" --no-ignore` → 0 matches).

---

## 5. Repository Structure

```
src/osint_swarm/                     Core library (importable from anywhere via sys.path)
  data_sources/
    sec_edgar.py                     SEC EDGAR HTTP connector
    gdelt.py                         GDELT DOC 2.0 HTTP connector
    ofac.py                          OFAC SDN XML parser + name matcher
    courtlistener.py                 CourtListener REST API v4 connector
  entities.py                        Entity + Evidence dataclasses
  utils/io.py                        read_json, write_json, write_csv_dicts, ensure_parent

mcp_layer/                           Data Access Layer — agents call this, not connectors
  base.py                            DataSourceProcessor abstract base
  sec_edgar_processor/processor.py   Cached SEC JSON → List[Evidence]
  gdelt_processor/processor.py       Cached GDELT JSON → List[Evidence]
  evidence_loader/loader.py          Processed CSV → List[Evidence]
  __init__.py                        get_evidence_for_entity(), get_processor()

agents/
  lead_agent/
    entity_resolution/resolver.py    ENTITY_REGISTRY + resolve() + whole-word matching
    task_planner/planner.py          Keyword-based query decomposition → SubTasks
    task_planner/types.py            SubTask(task_type, target_agent, description)
    context_manager/manager.py       InvestigationContext: entity + tasks + findings
    orchestrator/orchestrator.py     LeadAgent.run(query) → full pipeline
  specialist_agents/
    corporate_agent/
      agent.py                       CorporateAgent: SEC MCP + structure_mapper stub
      sec_analyzer/analyzer.py       summarize_governance_red_flags()
      structure_mapper/mapper.py     **STUB** — returns confidence=0.0
    legal_agent/
      agent.py                       LegalAgent: OFAC screener + CourtListener fetcher
      sanctions_screener/screener.py **LIVE** — OFAC SDN screening
      pacer_analyzer/analyzer.py     **LIVE** — CourtListener dockets
    social_graph_agent/
      agent.py                       SocialGraphAgent: GDELT via MCP
      gnn_analyzer/analyzer.py       DEAD CODE — no longer called
      influence_mapper/mapper.py     DEAD CODE — no longer called

reflexion_layer/
  cross_check/checker.py             Finds conflicting claims (same entity+date)
  gap_detection/detector.py          Flags missing data (empty agents, stubs, cache)
  confidence_module/scorer.py        Source-weighted confidence aggregation

knowledge_graph/
  graph.py                           NetworkX-style graph builder (nodes + edges)
  types.py                           Node, Edge dataclasses

output_layer/
  evidence_report_generator/         Markdown + HTML evidence reports
  risk_dashboard/dashboard.py        CLI risk score summary per category
  audit_trail/trail.py               Timestamped JSON-lines event log

app/
  app.py                             Flask web demo — routes
  pipeline.py                        Calls LeadAgent end-to-end (generic, no hard-coding)

scripts/                             All generic — take --entity-id or --cik params
  pull_sec_submissions.py            SEC data → data/raw/sec/
  pull_gdelt_news.py                 GDELT data → data/raw/gdelt/
  pull_ofac_sdn.py                   OFAC SDN XML → data/raw/ofac/sdn.xml
  pull_courtlistener.py              Court dockets → data/raw/courtlistener/
  build_evidence.py                  Generic: SEC+GDELT raw → processed CSV
  build_evidence_tesla.py            Thin wrapper → build_evidence.py
  build_evidence_ford.py             Thin wrapper → build_evidence.py
  run_lead_agent.py                  Run full pipeline from CLI

data/                                NOT committed to git (see .gitignore)
  raw/sec/                           Cached SEC JSON
  raw/gdelt/                         Cached GDELT JSON
  raw/ofac/sdn.xml                   OFAC SDN XML (27 MB)
  raw/courtlistener/                 Cached docket JSON per entity
  processed/                         Evidence CSVs per entity

tests/unit/                          159 unit tests (pytest)
  agents/lead_agent/                 16 tests
  agents/specialist_agents/          27 tests (OFAC screener, CourtListener, legal agent, corporate, social)
  data_sources/                      57 tests (OFAC connector, CourtListener connector)
  mcp_layer/                         16 tests
  reflexion_layer/                   16 tests
  knowledge_graph/                   4 tests
  output_layer/                      16 tests
  schemas/                           8 tests
```

---

## 6. Every Component — Implementation Detail

### 6a. Lead Agent

**File:** `agents/lead_agent/orchestrator.py`
**Class:** `LeadAgent(data_root, agent_stubs)`

The orchestrator runs the full pipeline:

```python
def run(self, query: str) -> InvestigationContext:
    context.set_query(query)
    entity = resolve_one(query)       # Step 1: entity resolution
    context.set_entity(entity)
    tasks = decompose(query, entity)  # Step 2: task decomposition
    context.set_tasks(tasks)
    for task in tasks:                # Step 3: dispatch to agents
        stub = self._stubs.get(task.target_agent)
        findings = stub(entity, task, context)
        context.add_agent_results(task.target_agent, findings)
    return context
```

**Entity Resolution** (`resolver.py`):
- Uses `ENTITY_REGISTRY` — a list of `Entity` objects with names and aliases
- `resolve(query)` normalizes query to lowercase, then checks each entity's name and aliases
- Short aliases (<3 chars like ticker "F") require whole-word matching via `\b` regex to prevent false positives (e.g. "F" in "fraud")
- Bug found & fixed: Ford's ticker "F" was matching the letter 'f' in "Investigate unknown company XYZ for fraud", incorrectly resolving to Ford. Fix: `_word_in_text()` function + `_MIN_SUBSTR_LEN = 3`

**Task Planner** (`planner.py`):
- Keywords checked (case-insensitive): `money laundering`, `aml`, `sanctions`, `ofac`, `beneficial owner`, `pep`, etc.
- AML query → 6 tasks: `corporate_structure`, `beneficial_ownership`, `sanctions_screening`, `litigation`, `transaction_patterns`, `adverse_media`
- Generic query → 4 tasks: `sec_filings`, `sanctions_screening`, `litigation`, `adverse_media`

### 6b. Corporate Agent

**File:** `agents/specialist_agents/corporate_agent/agent.py`
**Class:** `CorporateAgent(data_root)`

| Task Type | What Happens | Source |
|-----------|-------------|--------|
| `corporate_structure` | Calls `SecEdgarProcessor` via MCP → returns SEC filings + 1 governance summary | SEC EDGAR |
| `transaction_patterns` | Same as above (SEC filings analyzed for patterns) | SEC EDGAR |
| `beneficial_ownership` | Calls `structure_mapper.run_stub()` → 1 placeholder (conf=0.0, stub=True) | **STUB** |

**SEC Analyzer** (`sec_analyzer/analyzer.py`):
- `summarize_governance_red_flags(evidence, entity_id)` counts SEC filings by type:
  - 8-K filings with "restatement" in summary → governance red flags
  - Returns 1 summary Evidence row with `source_type="sec_filing"`, `risk_category="governance"`

### 6c. Legal Agent

**File:** `agents/specialist_agents/legal_agent/agent.py`
**Class:** `LegalAgent(data_root)`

| Task Type | What Happens | Source |
|-----------|-------------|--------|
| `sanctions_screening` | Calls `ofac_screen(entity, task, ctx, data_root)` | OFAC SDN XML |
| `litigation` | Calls `court_fetch(entity, task, ctx, data_root)` | CourtListener API |
| `regulatory_actions` | Same as litigation (routed to CourtListener) | CourtListener API |

**OFAC Screener** (`screener.py`):
- Returns match rows, clean rows, or cache-missing fallback (see Section 4b)
- All results have `attributes={"stub": False}`
- `run_stub()` alias maintained for backward compatibility

**CourtListener Analyzer** (`pacer_analyzer/analyzer.py`):
- Cache-first: tries `data/raw/courtlistener/dockets_<slug>.json`
- If no cache: fetches live from API → caches result → converts
- If network error: returns fallback Evidence (conf=0.0, `fetch_error=True`, helpful message)
- Returns: 1 summary row + N docket rows (default 20)

### 6d. Social Graph Agent

**File:** `agents/specialist_agents/social_graph_agent/agent.py`
**Class:** `SocialGraphAgent(data_root)`

| Task Type | What Happens | Source |
|-----------|-------------|--------|
| `adverse_media` | Calls `GdeltProcessor.get_evidence_for_entity()` | GDELT DOC 2.0 |
| `network_analysis` | Same as adverse_media | GDELT DOC 2.0 |

- Dead code: `gnn_analyzer/` and `influence_mapper/` still exist but are never called. Safe to delete later.

### 6e. MCP Layer

**File:** `mcp_layer/__init__.py`

The MCP (Message/Content Provider) layer is a facade between agents and raw data connectors:

```python
def get_evidence_for_entity(entity, sources=("sec_edgar", "gdelt"), data_root=None):
    for source_id in sources:
        processor = get_processor(source_id, data_root)  # SecEdgarProcessor or GdeltProcessor
        evidence.extend(processor.get_evidence_for_entity(entity))
    return evidence
```

**Why this layer exists:** Agents never import from `src/osint_swarm/data_sources/` directly. This allows swapping data sources without changing agent code.

### 6f. Reflexion Layer

**Cross-Check** (`checker.py`):
- Groups all findings by `(entity_id, date)`
- If 2+ findings share the same entity+date but have different summaries → `Conflict(dimension="summary_consistency", ...)`
- Tesla shows 87 conflicts (normal — multiple SEC filings on the same date)

**Gap Detection** (`detector.py`):
- Checks 4 things: (1) no entity resolved, (2) legal agent empty or no real screening, (3) social_graph empty, (4) corporate structure_mapper stub present
- `_legal_has_real_screening()` → True if any result has `screened=True` AND `confidence > 0`
- Cache-missing fallback (OFAC or CourtListener) triggers a gap with instructions to run the pull script

**Confidence Scoring** (`scorer.py`):
- `aggregate_confidence(findings)` → overall mean + breakdown by `risk_category` and `source_type`
- `adjusted_confidence(findings)` → multiplies each `evidence.confidence` by `SOURCE_RELIABILITY[source_type]`
- Source reliability weights: `sec_filing=0.95`, `regulator_api=0.85`, `court_record=0.80`, `news_article=0.60`, `other=0.50`

### 6g. Knowledge Graph

**File:** `knowledge_graph/graph.py`
- `build_graph_from_evidence(findings)` → `(List[Node], List[Edge])`
- One Node per unique `entity_id` (type="entity") and one per unique `evidence_id` (type="evidence")
- Edges: `entity --[has_evidence]--> evidence` and optional `evidence --[same_source_type]--> evidence`

### 6h. Output Layer

| Component | File | What it does |
|-----------|------|-------------|
| Evidence Report | `evidence_report_generator/generator.py` | Markdown and HTML reports with cited evidence |
| Risk Dashboard | `risk_dashboard/dashboard.py` | CLI summary: mean confidence per risk_category |
| Audit Trail | `audit_trail/trail.py` | Timestamped JSON-lines event log |

---

## 7. End-to-End Workflow & Commands

### Initial setup (run once per machine)

```bash
python -m venv .venv
source .venv/bin/activate        # macOS/Linux
pip install -r requirements.txt

# Set up .env (see Section 10 for teammates)
cp .env.example .env
# Edit .env → set SEC_USER_AGENT="Your Name your_email@asu.edu"
```

### Pull raw data

```bash
# OFAC SDN list — run ONCE, covers ALL entities (~30 seconds)
python scripts/pull_ofac_sdn.py --stats

# CourtListener — optional pre-fetch (auto-fetches if not cached)
python scripts/pull_courtlistener.py --all

# SEC EDGAR — one call per entity
python scripts/pull_sec_submissions.py --cik 0001318605    # Tesla
python scripts/pull_sec_submissions.py --cik 0000037996    # Ford
python scripts/pull_sec_submissions.py --cik 0000012927    # Boeing

# GDELT — one call per entity (NO auth needed)
python scripts/pull_gdelt_news.py --entity-id tesla_inc_cik_0001318605
python scripts/pull_gdelt_news.py --entity-id ford_motor_cik_0000037996
python scripts/pull_gdelt_news.py --entity-id boeing_cik_0000012927
```

### Build evidence CSVs (optional — for offline analysis)

```bash
python scripts/build_evidence.py --entity-id tesla_inc_cik_0001318605
python scripts/build_evidence.py --entity-id ford_motor_cik_0000037996
python scripts/build_evidence.py --entity-id boeing_cik_0000012927
```

### Run investigations

```bash
# CLI
python scripts/run_lead_agent.py "Investigate Tesla for money laundering"
python scripts/run_lead_agent.py "Investigate Ford for fraud"
python scripts/run_lead_agent.py "Investigate Boeing for violations"
python scripts/run_lead_agent.py "Investigate unknown company XYZ"  # gracefully returns empty

# Flask web demo
python app/app.py    # open http://127.0.0.1:5000
```

> **macOS port 5000 conflict:** System Preferences → General → AirDrop & Handoff → turn off AirPlay Receiver. Or edit `app/app.py` to use `port=5001`.

### Run tests

```bash
pytest tests/unit -v         # 159 tests, all passing
pytest tests/unit -q         # quick summary
```

---

## 8. Entity Registry

Defined in `agents/lead_agent/entity_resolution/resolver.py`:

| Entity | entity_id | CIK | Ticker | Aliases | Data |
|--------|-----------|-----|--------|---------|------|
| Tesla, Inc. | `tesla_inc_cik_0001318605` | 0001318605 | TSLA | Tesla, Tesla Inc, Tesla Motors, TSLA | SEC ✅ GDELT ✅ OFAC ✅ Courts ✅ |
| Ford Motor Company | `ford_motor_cik_0000037996` | 0000037996 | F | Ford, Ford Motor, Ford Motor Co, Ford Motor Company | SEC ✅ GDELT ✅ OFAC ✅ Courts ✅ |
| The Boeing Company | `boeing_cik_0000012927` | 0000012927 | BA | Boeing, Boeing Company, The Boeing Company, BA | SEC ✅ GDELT ✅ OFAC ✅ Courts ✅ |

**To add a new entity:**
1. Find CIK at [EDGAR company search](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany)
2. Add `Entity(...)` to `ENTITY_REGISTRY` in `resolver.py`
3. Pull data: `pull_sec_submissions.py --cik`, `pull_gdelt_news.py --entity-id`, `pull_courtlistener.py --entity-id` (OFAC is entity-agnostic — one file covers all)
4. Build CSV: `python scripts/build_evidence.py --entity-id <id>`

---

## 9. Live Data Inventory

*All counts verified live on 2026-03-15.*

### Raw data (in `data/raw/` — excluded from git)

| File | Type | Size/Count |
|------|------|-----------|
| `sec/CIK0001318605.json` | SEC filings (Tesla) | ~675 filings |
| `sec/CIK0000037996.json` | SEC filings (Ford) | ~894 filings |
| `sec/CIK0000012927.json` | SEC filings (Boeing) | ~838 filings |
| `gdelt/news_tesla.json` | GDELT articles | 100 articles |
| `gdelt/news_ford_motor_company.json` | GDELT articles | 100 articles |
| `gdelt/news_the_boeing_company.json` | GDELT articles | 62 articles |
| `ofac/sdn.xml` | OFAC SDN list | 27 MB, 18,712 entries |
| `courtlistener/dockets_tesla.json` | Court dockets | 20 cached (2,054 total) |
| `courtlistener/dockets_ford_motor_company.json` | Court dockets | 20 cached (21,885 total) |
| `courtlistener/dockets_the_boeing_company.json` | Court dockets | 20 cached (3,582 total) |

### Processed evidence CSVs (in `data/processed/`)

| File | SEC rows | GDELT rows | Total | Date range |
|------|----------|------------|-------|------------|
| `tesla/evidence_tesla.csv` | 675 | 100 | **775** | 2018-02-14 → 2026-03-15 |
| `ford_motor_company/evidence_ford_motor_company.csv` | 894 | 100 | **994** | 2019-03-04 → 2026-03-15 |
| `the_boeing_company/evidence_the_boeing_company.csv` | 838 | 62 | **900** | 2019-02-14 → 2026-03-08 |

### Live pipeline output (verified 2026-03-15)

| Query | Tasks | Corporate | Legal | Social | **Total** | Gaps |
|-------|-------|-----------|-------|--------|-----------|------|
| Tesla (AML) | 6 | 1,003 | 22 | 100 | **1,125** | 1 (beneficial_ownership) |
| Ford (fraud) | 4 | 501 | 22 | 100 | **623** | 0 |
| Boeing (violations) | 4 | 501 | 22 | 62 | **585** | 0 |
| Unknown XYZ | 0 | — | — | — | **0** | (entity_resolution) |

---

## 10. Environment Setup for Teammates

**`SEC_USER_AGENT` is NOT an API key.** The SEC EDGAR API is free and public. They just require you to identify yourself in the HTTP headers per their [fair access policy](https://www.sec.gov/os/accessing-edgar-data).

**Copy-paste instructions for teammates:**

> 1. `cp .env.example .env`
> 2. Open `.env`, find `SEC_USER_AGENT="Your Name your_email@asu.edu"`
> 3. Replace: `SEC_USER_AGENT="Raj Mahto raj.mahto@asu.edu"`
> 4. Save. Do NOT commit to git (`.env` is in `.gitignore`)
>
> That's it. GDELT, OFAC, and CourtListener need nothing at all.

**Optional:** For higher CourtListener rate limits, add `COURTLISTENER_API_TOKEN=<token>` (free account at courtlistener.com). Not required for the demo.

---

## 11. Test Suite & Audit

### Test suite summary

**Date: 2026-03-15 | Result: 159/159 passing | 0 skipped | 0 failures**

| Test Group | Count | What it tests |
|------------|-------|---------------|
| `agents/lead_agent/` | 16 | Entity resolution, task planner (6 tasks for AML), orchestrator, context manager |
| `agents/specialist_agents/` | 27 | Corporate agent, legal agent (OFAC + CourtListener), social graph agent, sanctions screener, pacer analyzer |
| `data_sources/` | 57 | OFAC XML parsing, name matching, false-positive prevention, CourtListener field normalization, cache, API mocking |
| `mcp_layer/` | 16 | SEC processor, GDELT processor, evidence loader, facade |
| `reflexion_layer/` | 16 | Cross-check, gap detection (OFAC cache miss, CourtListener error, social empty, stubs), confidence scoring |
| `knowledge_graph/` | 4 | Graph builder, node/edge correctness |
| `output_layer/` | 16 | Evidence report (Markdown/HTML), risk dashboard, audit trail |
| `schemas/` | 8 | Entity/Evidence creation, serialization |

### Test quality (honest assessment)

- **No fake tests.** No `assert True`. No `@pytest.mark.skip`. No `xfail`.
- OFAC tests use a hand-crafted 5-entry SDN XML with realistic structure (akaList, programList, remarks). Tests cover: exact match, case-insensitive, alias match, false-positive prevention (Oxford≠Ford, Stanford≠Ford), duplicate deduplication, empty XML, malformed XML.
- CourtListener tests use `unittest.mock.patch` to mock `requests.get` — zero real network calls in tests. Covers: field normalization (camelCase/snake_case), cache write+read round-trip, max_results truncation, network timeout, HTTP 429 error.
- `test_corporate_agent_sec_task_uses_mcp_when_cache_exists` uses `pytest.skip("no SEC cache")` as a guard — it does NOT skip on this machine because `data/raw/sec/` exists.

### Verification checks

| Claim | Status | Method |
|-------|--------|--------|
| NHTSA completely removed | ✅ | `rg -il "nhtsa" --no-ignore` → 0 matches |
| Tesla CSV: 775 rows | ✅ | `wc -l evidence_tesla.csv` → 776 (1 header) |
| Ford CSV: 994 rows | ✅ | `wc -l` → 995 |
| Boeing CSV: 900 rows | ✅ | `wc -l` → 901 |
| Tesla pipeline: 1,125 findings | ✅ | Live run of `run_lead_agent.py` |
| Ford pipeline: 623 findings | ✅ | Live run |
| Boeing pipeline: 585 findings | ✅ | Live run |
| Unknown entity → 0 findings | ✅ | Live run |
| OFAC SDN: 18,712 entries | ✅ | `pull_ofac_sdn.py --stats` |
| Tesla/Ford/Boeing OFAC clean | ✅ | `sdn_matches=0, screened=True, confidence=0.90` |
| OFAC false-positive prevention | ✅ | `search_entries("Ford Motor Company")` ≠ "OXFORD" |
| CourtListener: Tesla 2,054 | ✅ | Live API response |
| CourtListener: Ford 21,885 | ✅ | Live API response |
| CourtListener: Boeing 3,582 | ✅ | Live API response |
| CourtListener cache-first | ✅ | Second run uses cache, no network call (test verified) |
| Task planner: 6 tasks for AML | ✅ | Includes `litigation` alongside `sanctions_screening` |
| No hard-coded entity names in agent/connector code | ✅ | Grep for Tesla/Ford/Boeing in agents/mcp/src → only in docstrings |

---

## 12. Hard-Coding Audit

### Fully generic (✅)

| Component | Why it's generic |
|-----------|-----------------|
| `build_evidence.py` | Takes `--entity-id` — works for any registered entity |
| `pull_gdelt_news.py` | Takes `--entity-id` |
| `pull_sec_submissions.py` | Takes `--cik` |
| `pull_ofac_sdn.py` | Downloads full SDN list — covers ALL entities |
| `pull_courtlistener.py` | Takes `--entity-id` or `--all` |
| `SecEdgarProcessor` | Uses `entity.identifiers["cik"]` dynamically |
| `GdeltProcessor` | Uses `entity.name` dynamically |
| `ofac.search_entries()` | Accepts any `entity_name` + `aliases` |
| `courtlistener.fetch_dockets()` | Accepts any `entity_name` |
| Flask `app/pipeline.py` | Calls `LeadAgent(query)` — no entity hard-coded |
| `ENTITY_REGISTRY` | Declarative config — add any entity by editing one file |

### Fixed constants (✅ intentional, by design)

| Constant | Value | Location | Reason |
|----------|-------|----------|--------|
| SEC confidence | `0.85` | `sec_edgar_processor`, `build_evidence.py` | Authoritative gov filings |
| GDELT confidence | `0.60` | `gdelt_processor` | News articles are noisy |
| OFAC confidence | `0.90` | `screener.py` | Definitive sanctions list |
| CourtListener confidence | `0.85` | `courtlistener.py`, `analyzer.py` | Authoritative court records |
| CourtListener max_results | `20` | `courtlistener.py` | Demo-appropriate; configurable |
| GDELT max records | `100` | `gdelt.py` | Balance coverage vs. size |
| GDELT risk keywords | Fixed list | `gdelt.py` | AML domain constants |
| SEC max_filings cap | `500` | `sec_edgar_processor` | Prevents memory issues |
| Source reliability weights | 0.50–0.95 | `confidence_module/scorer.py` | Domain calibration |
| `_MIN_SUBSTR_LEN` | `3` | `resolver.py` | Prevents ticker false positives |

### Dead code (cleanup opportunity)

| File | Status | Risk |
|------|--------|------|
| `social_graph_agent/gnn_analyzer/analyzer.py` | Dead — never called | None (harmless) |
| `social_graph_agent/influence_mapper/mapper.py` | Dead — never called | None (harmless) |

### Remaining stubs

| File | Returns | When will it be replaced |
|------|---------|-------------------------|
| `corporate_agent/structure_mapper/mapper.py` | 1 Evidence (conf=0.0, stub=True) | When OpenCorporates is integrated |

---

## 13. Known Limitations (Honest)

### GDELT data quality (noise)

Tested for Tesla: **76/100 articles lack explicit risk keywords in the title**. Examples: "The Kia EV6 Is The Most American Car On Sale", investor alerts for unrelated companies.

**Why it's acceptable:**
1. Confidence `0.60` already reflects this — lower than SEC (0.85) and OFAC (0.90)
2. GDELT matches on article body, not just titles — round-up articles with "Tesla Legal Woes" are legitimate adverse media
3. Reflexion layer accounts for these weights
4. This is the realistic behavior of a real OSINT tool

**Future fix:** Filter by entity name appearing in the title, or use `sourcecountry=US` + `language=English` GDELT params.

### SEC filing cap

`SecEdgarProcessor` caps at 500 filings. Pre-built CSVs (`build_evidence.py`) have no cap and contain 675/894/838 rows. Cap prevents memory issues when agents call the processor multiple times.

### CourtListener returns 20 dockets out of thousands

Tesla has 2,054 dockets; we cache 20 by relevance score. Sufficient for demo. Increase via `--max-results` if needed (max 50 per API page without pagination).

### Cross-check "conflicts" are expected

Tesla shows 87 "conflicts" — these are same-date SEC filings with different summaries (e.g. two 8-K filings on the same day for different material events). This is correct behavior, not a bug.

### Beneficial ownership is still a stub

`structure_mapper/mapper.py` returns a single placeholder Evidence row. Gap detection correctly flags this. Will be replaced by OpenCorporates integration.

---

## 14. Design Decisions & Rationale

### Why GDELT instead of Twitter/LinkedIn?

The project proposal mentioned Twitter and LinkedIn for social graph analysis. We replaced them with GDELT because:
- Twitter API requires paid access ($100+/month for research tier)
- LinkedIn has no public API for scraping and actively blocks automation
- GDELT is free, public, indexes 100+ languages, and covers the same use case (adverse media monitoring)
- GDELT's risk keyword query maps directly to AML screening requirements

### Why CourtListener instead of PACER?

PACER charges $0.10/page — prohibitive for a capstone project. CourtListener (Free Law Project) mirrors PACER content for free via a REST API. Same underlying data.

### Why OFAC SDN as a local XML file?

The OFAC SDN list is 27 MB of XML (~18,712 entries). Downloading once and searching locally is faster and more reliable than hitting a web API on every run. The screener operates purely on the cached file — zero network calls after initial download.

### Why frozen dataclasses for Entity and Evidence?

Entities and Evidence are passed between agents, stored in context, and used by the reflexion layer. Immutability (`frozen=True`) prevents any agent from accidentally mutating shared state — a critical property in a multi-agent system.

### Why confidence=0.0 for stubs instead of omitting them?

Stubs return `confidence=0.0` and `attributes={"stub": True}` so that:
1. The gap detector can distinguish "this source was checked and had no data" from "this source was never checked"
2. The output layer can show "data not available" rather than silently omitting a category
3. Analysts see the gap and know what's missing

### Why slug-based cache filenames?

Cache files use slugified entity names (e.g. `news_tesla.json`, `dockets_ford_motor_company.json`) rather than entity IDs. This makes the `data/raw/` directory human-readable for debugging.

---

## 15. Sprint History & Bug Fix Log

### Sprint 1 — Foundation (pre-2026-03-15)
- Built core architecture: `Entity` + `Evidence` dataclasses, MCP layer, lead agent orchestrator
- Implemented SEC EDGAR connector + processor
- Implemented NHTSA recall connector (later removed)
- Created entity registry with Tesla
- Built reflexion layer (cross-check, gap detection, confidence module)
- Built output layer (evidence report, risk dashboard, audit trail)
- Built knowledge graph
- Built Flask web demo
- 83 unit tests

### Sprint 2 — NHTSA→GDELT Migration + Ford/Boeing (2026-03-15)
- **Removed NHTSA entirely** — irrelevant to AML/corporate risk
- **Added GDELT DOC 2.0** — adverse media connector + processor
- Added Ford Motor Company and Boeing to entity registry
- Created generic `build_evidence.py` (replaced entity-specific hard-coding)
- Fixed entity resolution false positive: Ford ticker "F" matching "fraud"
- Fixed SEC confidence inconsistency (0.95 in build_evidence.py vs 0.85 in processor → standardized to 0.85)
- Tests: 83 → 83 (replaced NHTSA tests with GDELT tests)

### Sprint 3 — OFAC Sanctions Screening (2026-03-15)
- **New:** `src/osint_swarm/data_sources/ofac.py` — XML parser + name matcher
- **New:** `agents/specialist_agents/legal_agent/sanctions_screener/screener.py` — replaced stub
- **New:** `scripts/pull_ofac_sdn.py`
- Updated gap detection to handle OFAC cache-missing vs. real screening
- Tests: 83 → 119

### Sprint 4 — CourtListener Court Records (2026-03-15)
- **New:** `src/osint_swarm/data_sources/courtlistener.py` — REST API connector
- **New:** `agents/specialist_agents/legal_agent/pacer_analyzer/analyzer.py` — replaced stub
- **New:** `scripts/pull_courtlistener.py`
- Updated task planner to emit `litigation` task (5 → 6 tasks for AML queries)
- Updated gap detection for CourtListener fetch errors
- Tests: 119 → 159

### Bug Fix Log

| Bug | Root Cause | Fix | Sprint |
|-----|-----------|-----|--------|
| `SEC_USER_AGENT` not set → HTTP 403 | Missing `.env` file | Created `.env`, updated `.env.example` with clear instructions | 1 |
| Flask port 5000 blocked on macOS | AirPlay Receiver uses port 5000 | Documented workaround (disable AirPlay or use port 5001) | 1 |
| Ford ticker "F" matches "fraud" | Substring matching too aggressive | Added `_word_in_text()` + `_MIN_SUBSTR_LEN = 3` | 2 |
| SEC confidence 0.95 vs 0.85 | `build_evidence.py` used 0.95, processor used 0.85 | Standardized both to 0.85 | 2 |
| `build_evidence_tesla.py` only had 1 hard-coded row | Script was not parsing full SEC JSON | Refactored into generic `build_evidence.py` | 2 |
| GDELT cache filename mismatch in tests | `_slug_for_entity("Tesla, Inc.")` → `"tesla"` not `"tesla_inc"` | Fixed test fixtures to use correct slug | 2 |
| `reg_count` undefined in SEC analyzer | Variable removed when NHTSA was deleted | Removed reference from `summarize_governance_red_flags` | 2 |
| OFAC alias "BRT" excluded by length check | Post-normalization length <4, but original alias was "BRT CORP" | Changed to check original alias length, not post-normalized | 3 |
| CourtListener camelCase vs snake_case | v4 search uses camelCase, dockets use snake_case | `_get_field()` tries both variants | 4 |
| Task planner missing `litigation` task | Task was defined in `LEGAL_TASK_TYPES` but never emitted | Added to both AML and default task paths | 4 |

---

## 16. Next Steps

### Priority 1 — Must have before final demo

#### 1a. OpenCorporates Beneficial Ownership

**File:** `agents/specialist_agents/corporate_agent/structure_mapper/mapper.py`

Replace `run_stub()` with real OpenCorporates integration:
```python
# Source: https://api.opencorporates.com/v0.4/companies/search?q=<name> (free tier)
# Extract officers, directors, parent/subsidiary relationships
# Return Evidence with source_type="other", risk_category="network", confidence=0.75
```

### Priority 2 — Polish and evaluation

| Task | Description | Owner |
|------|------------|-------|
| GDELT noise filtering | Filter articles where entity name appears in title | Taljinder |
| Flask UI improvements | SEC/GDELT/Court counts separately, clickable links, entity dropdown | Aditya |
| Evaluation metrics | Citation rate, coverage by risk_category, runtime per query | Taljinder |
| Dead code cleanup | Delete `gnn_analyzer/` and `influence_mapper/` (no longer called) | Anyone |

### Priority 3 — Demo prep

| Task | Description | Owner |
|------|------------|-------|
| Demo rehearsal | End-to-end walkthrough with all data sources | All |

---

## 17. Team Roles

| Role | Owner |
|------|-------|
| Data gathering & preprocessing | Taljinder |
| Backend / agent development | Arnab, Raj |
| Frontend & visualization | Aditya |
| Deployment & documentation | Jacob |

**Sprint allocation:**

| Task | Owner | Status |
|------|-------|--------|
| ~~OFAC SDN integration~~ | ~~Raj + Arnab~~ | ✅ Done |
| ~~CourtListener integration~~ | ~~Jacob + Raj~~ | ✅ Done |
| OpenCorporates | Arnab | Next |
| Flask UI polish | Aditya | Pending |
| GDELT noise filter | Taljinder | Pending |
| Evaluation metrics | Taljinder | Pending |
| Demo rehearsal | All | Pending |
