# Architecture Guide — Autonomous OSINT Investigation Swarm
**A plain-English walkthrough for someone new to this project**

---

## What Does This System Do?

Imagine you are a compliance analyst at a bank. Your job is to check whether a company — say, Tesla — is involved in any financial misconduct: money laundering, sanctions violations, regulatory penalties, suspicious ownership structures. To do this manually, you would spend **~2.5 hours** visiting five different websites, reading hundreds of pages, and writing a report.

This system does the same job in **under 4 seconds**.

You type a plain English question like:

```
Investigate Tesla for money laundering
```

The system automatically queries public data sources, collects hundreds of citable evidence items, scores them by confidence, cross-validates them, builds a risk profile, generates a natural-language analyst narrative using Llama 3.1, and produces a full audit-ready investigation report — all without any human involvement.

---

## The Team

Five people built this system across the full semester:

**Taljinder Singh** led data-source integration and ingestion readiness across SEC EDGAR, OFAC SDN, CourtListener, and GDELT. He built core connectors and data-prep flows, and contributed to source-quality validation used throughout agent execution.

**Arnab Mitra** co-led backend architecture and orchestration, including lead-agent flow, specialist-agent execution patterns, and output/report pipelines. He also contributed heavily to investigation-state handling, graph construction, and runtime reliability hardening.

**Raj Kumar Mahto** co-led planning/state-management components, especially task decomposition contracts and context-manager behavior, and contributed to backend integration and test alignment across multi-agent execution paths.

**Aditya Pokharna** co-led presentation and usability layers, including the Flask UI structure, tabbed results experience, risk and graph visualization surfaces, and interaction design/styling improvements for demo clarity.

**Jacob Kuriakose** co-led deployment/documentation and final-sprint platform enhancements, including cloud deployment, auto entity resolution improvements, LLM integration/prompt-contract updates, and evaluation/documentation packaging for presentation readiness.

---

## The Big Picture — How It Works in One Paragraph

When you submit a query, a **Lead Agent** reads it and figures out which company you mean (e.g., "Tesla" → Tesla, Inc., CIK 0001318605). It then breaks your request into a set of investigation tasks and hands each task to a **specialist agent**. Three specialist agents run in sequence — one for corporate filings, one for legal/sanctions, one for news. Each agent collects structured evidence from public data sources via a **MCP (Model Context Protocol) layer** that handles caching and API calls. Once all agents finish, a **Reflexion layer** checks the evidence for gaps, conflicts, and assigns confidence scores. The results are assembled into a **knowledge graph**, a **risk dashboard**, and a **full evidence report**. Finally, **Llama 3.1** reads the aggregated metrics and writes a concise natural-language analyst narrative. Everything is displayed in a **Flask web UI**.

---

## System Layers — Top to Bottom

The system is organized into 7 layers. Think of them like floors in a building — each floor talks to the ones above and below it.

For a presentation-friendly flowchart, see [`docs/ARCHITECTURE_DIAGRAM.md`](docs/ARCHITECTURE_DIAGRAM.md).

```
┌─────────────────────────────────────────────┐
│  Layer 7 — Flask Web UI  (what you see)     │
├─────────────────────────────────────────────┤
│  Layer 6½— LLM Layer     (Llama 3.1)        │
├─────────────────────────────────────────────┤
│  Layer 6 — Output Layer  (reports, scores)  │
├─────────────────────────────────────────────┤
│  Layer 5 — Reflexion     (quality control)  │
├─────────────────────────────────────────────┤
│  Layer 4 — Specialist Agents  (workers)     │
├─────────────────────────────────────────────┤
│  Layer 3 — Lead Agent    (orchestrator)     │
├─────────────────────────────────────────────┤
│  Layer 2 — MCP Layer     (data access)      │
├─────────────────────────────────────────────┤
│  Layer 1 — Core Library  (raw connectors)   │
└─────────────────────────────────────────────┘
```

---

## Layer 1 — Core Library (`src/osint_swarm/`)

This is the foundation. The data-integration track built the core raw connectors and preprocessing pipeline that feed everything else.

### The Two Core Data Types

Everything in the system is built around two Python dataclasses, designed by the backend team:

**`Entity`** — the company being investigated:
```
Entity(
    entity_id = "tesla_inc_cik_0001318605",
    name      = "Tesla, Inc.",
    entity_type = "public_company",
    identifiers = {"cik": "0001318605", "ticker": "TSLA"},
    aliases   = ["Tesla", "Tesla Inc", "TSLA"]
)
```

**`Evidence`** — a single citable finding (one row of evidence):
```
Evidence(
    evidence_id  = "tesla_sec_000123...",
    entity_id    = "tesla_inc_cik_0001318605",
    date         = "2026-03-09",
    source_type  = "sec_filing",
    risk_category = "governance",
    summary      = "SEC filing: 8-K filed on 2026-03-09",
    source_uri   = "https://www.sec.gov/Archives/...",
    confidence   = 0.95,
    attributes   = {"form": "8-K"}
)
```

Every agent in the system speaks the same language — it takes an `Entity` and returns a list of `Evidence` objects. This is the key design decision that makes the system modular.

### The Five Raw Data Connectors

The data integration workstream identified core sources and built the HTTP clients that pull from them:

| Connector | What it calls | Auth needed |
|---|---|---|
| `sec_edgar.py` | `https://data.sec.gov/submissions/CIK{cik}.json` | Just name + email |
| `gdelt.py` | `https://api.gdeltproject.org/api/v2/doc/doc` | None |
| `ofac.py` | Parses local `data/raw/ofac/sdn.xml` (27 MB file) | None |
| `courtlistener.py` | `https://www.courtlistener.com/api/rest/v4/search/` | None |

---

## Layer 2 — MCP Layer (`mcp_layer/`)

**MCP = Model Context Protocol.** The backend team designed this standardized interface layer that sits between agents and raw connectors.

**Why does this layer exist?** The specialist agents should not care whether data comes from a live API call or a local cache file. The MCP layer handles this transparently:

```
Agent asks: "Give me SEC evidence for Tesla"
        ↓
MCP Layer checks: does data/raw/sec/CIK0001318605.json exist?
    YES → read from cache (fast, ~0ms)
    NO  → call SEC EDGAR API, save to cache, return data
        ↓
Agent receives: List[Evidence]  (same either way)
```

This **cache-first** design means:
- Investigations run in ~2.7 seconds (no network latency after first pull)
- The system works offline / on Render.com with no live API calls at runtime
- Results are reproducible — same query always returns the same evidence

### The Three MCP Processors

**`SecEdgarProcessor`** (backend + platform collaboration) — reads `data/raw/sec/CIK{cik}.json`, converts up to 500 SEC filings into Evidence rows. The team extended the processor with tiered confidence scoring by filing type:
- 8-K (material events) → **0.95**
- 10-K / 10-Q (annual reports) → **0.85**
- DEF 14A (proxy statements) → **0.80**
- Form 4 (routine insider trades) → **0.75**

**`GdeltProcessor`** (backend + platform collaboration) — reads `data/raw/gdelt/news_{slug}.json`, converts news articles into Evidence. Relevance is scored by title content. The team extended it with English-language filtering to remove non-English articles from the signal:
- Entity name + risk keyword in title → **0.75** (high signal)
- Entity name only → **0.70**
- Risk keyword only → **0.55**
- Neither → **0.30** (kept but down-weighted)
- Non-English articles → **filtered out**

**`EvidenceLoader`** — an alternative path that reads pre-built CSVs from `data/processed/`.

---

## Layer 3 — Lead Agent (`agents/lead_agent/`)

The Lead Agent is the orchestrator — it receives the raw query string and coordinates everything else. The backend and platform tracks co-developed this layer, including automatic entity resolution and SEC EDGAR resolver wiring.

### Sub-module 1: Entity Resolution (`resolver.py` + `sec_name_resolver.py`)

Converts a query like `"Investigate Tesla for money laundering"` into an `Entity` object.

**Step 1 — Registry lookup:** Check a hardcoded list of known entities (Tesla, Ford, Boeing, Alphabet, JPMorgan). Match by name or alias using case-insensitive substring matching. Short aliases (< 3 chars, like ticker "F") use whole-word matching to avoid false positives.

**Step 2 — Auto-resolution (final sprint enhancement):** For any unknown company, `sec_name_resolver.py` queries the SEC EDGAR full-text search API:
```
https://efts.sec.gov/LATEST/search-index?q="Microsoft"&forms=10-K
```
Parse the response to extract the CIK and official company name. Build a temporary `Entity` object on the fly.

This means the system can investigate **any publicly traded company** — not just the 5 pre-registered ones.

### Sub-module 2: Task Planner (`task_planner/llm_planner.py`)

The planner is now **LLM-guided and strict-schema validated**. It receives the query, resolved entity, and the runtime tool map, then returns structured `SubTask` objects.

Current planner behavior:
- Produces a bounded plan (typically 3–5 tasks, max 2 rounds)
- Uses only runtime-available tools per agent
- Rejects malformed JSON/invalid fields and retries with repair prompts
- Raises typed errors on repeated contract failure (no deterministic fallback)

Typical AML-oriented plan lanes:
```
1. corporate_structure  → corporate_agent (sec_edgar)
2. sanctions_screening  → legal_agent (ofac)
3. litigation           → legal_agent (courtlistener)
4. adverse_media        → social_graph_agent (gdelt)
```

### Sub-module 3: Context Manager (`context.py`)

The team built the `InvestigationContext` object that is created and passed to every agent. It holds:
- The resolved `Entity`
- The list of `SubTask` objects
- A dictionary mapping `agent_id → List[Evidence]` (results accumulate here)

Agents can read each other's results via this shared context — for example, the legal agent can see what the corporate agent already found.

### Sub-module 4: LLM Policy Stack (strict mode)

After planning, execution is governed by LLM policies with strict JSON contracts:
- **Action policy** (`agents/lead_agent/action_policy.py`) chooses the next tool per specialist agent.
- **Reflexion ranking policy** (`reflexion_layer/action_reflexion.py`) ranks follow-up actions.
- **Stop policy** (`agents/lead_agent/orchestrator.py`) decides whether to continue another round.

Each policy includes retry-with-repair prompts and typed error handling. If contracts are repeatedly violated, the run fails explicitly rather than falling back to deterministic shortcuts.

---

## Layer 4 — Specialist Agents (`agents/specialist_agents/`)

The backend team implemented all three specialist agents, each using the same protocol: `run(entity, task, context) → List[Evidence]`.

### Corporate Agent

Handles tasks: `corporate_structure`, `sec_filings`, `transaction_patterns`

- **SEC filings** (tasks 1 + 3): Calls `SecEdgarProcessor` → returns up to 500 filing Evidence rows + 1 governance summary row
- **Corporate structure**: Uses SEC/governance disclosures to build structured corporate risk context.

### Legal Agent

Handles tasks: `sanctions_screening`, `litigation`

- **Sanctions screening** (task 3): Parses the local OFAC SDN XML file (18,712 entries) from the data-integration pipeline. Normalizes names (strips "Inc", "LLC", "Corp" suffixes), runs fuzzy matching. Returns 1 Evidence row — either a match (confidence 0.90, flagged) or clean (confidence 0.90, no match). Includes false-positive guards (e.g., "Ford" does not match "Oxford").
- **Litigation** (task 4): Calls `CourtListener` API from the integrated data-source layer. Cache-first. Returns 1 summary Evidence row + up to 20 docket Evidence rows (federal court cases).

### Social Graph Agent

Handles tasks: `adverse_media`, `network_analysis`

- Calls `GdeltProcessor` → returns up to 100 news article Evidence rows, relevance-scored by title content, English-language filtered.

---

## Layer 5 — Reflexion Layer (`reflexion_layer/`)

The backend team built the reflexion layer, which runs three quality checks after all agents finish:

### 1. Cross-Check (`checker.py`)
Groups all findings by `(entity_id, date)`. If two or more findings share the same entity and date but have different summaries → flags a **Conflict**.

> **Note:** 88 conflicts for Tesla is normal — companies often file multiple SEC forms (e.g., an 8-K and a Form 4) on the same day. This is expected behaviour, not an error.

### 2. Gap Detection (`detector.py`)
Checks for missing evidence:
- Did the entity fail to resolve? → Gap: "Entity not found"
- Did OFAC screening return `cache_missing=True`? → Gap: "Sanctions data unavailable"
- Did GDELT return no articles? → Gap: "Adverse media unavailable"

Each gap includes a `suggested_follow_up` explaining what to do next.

### 3. Confidence Scoring (`scorer.py`)
Aggregates all findings into:
- **Overall mean confidence** (e.g., 0.81 for Tesla AML)
- **Confidence by risk category** (governance, regulatory, legal, network)
- **Confidence by source type** (sec_filing, news_article, court_record, etc.)
- **Adjusted confidence** applying source reliability weights (SEC=0.95, court=0.80, news=0.60)

---

## Layer 6 — Output Layer (`output_layer/`)

The backend and reporting tracks built all four output modules that run after reflexion:

### Evidence Report Generator
Produces a full **Markdown + HTML report** with every finding organized by risk category. Every finding includes its date, confidence score, and a clickable source URL. Citation rate target: > 97%.

### Risk Dashboard
Computes **mean confidence per risk category**:
```
governance:  0.83
regulatory:  0.85
legal:       0.90
network:     0.62
overall:     0.81
```

### Audit Trail
Records timestamped events throughout the pipeline as JSON-lines:
```json
{"event": "query_received",    "timestamp": "2026-04-16T10:00:00", "query": "Investigate Tesla..."}
{"event": "pipeline_completed","timestamp": "2026-04-16T10:00:03", "entity_resolved": true}
```

### Evaluation Metrics
Computes system performance numbers: citation rate, coverage by category and data source, GDELT signal rate, confidence distribution, runtime.

---

## Knowledge Graph (`knowledge_graph/`)

Built from the full evidence set after all agents finish. The graph structure/builder and NetworkX analysis module (`network_analysis.py`) were developed collaboratively across backend and platform tracks, then wired into pipeline and UI.

**Structure:**
- One **node** per entity (the company being investigated)
- One **node** per evidence item (each finding is a node)
- **Edges** of type `has_evidence` connect the entity node to each evidence node
- **Edges** of type `same_source_type` chain evidence nodes that share the same source

**Network Analysis** (final sprint enhancement — powered by NetworkX):
- **Degree centrality** — which evidence nodes have the most connections
- **Connected components** — are there isolated subgraphs?
- **Average degree** — how densely connected is the graph?
- **Network density** — ratio of actual to possible edges
- **Top 5 most-connected evidence nodes** — the recurring risk signals

**Example for Tesla AML investigation:**
- 625 nodes (1 entity + 624 evidence)
- Connected components: 1 (fully connected)
- Average degree: 3.98
- Hub entity: Tesla Inc (624 direct connections)

---

## Layer 6½ — LLM Narrative Layer (`app/llm_narrative.py`)

The team integrated Llama 3.1 during the final sprint to add a strong generative analysis layer. After the output layer produces structured metrics, **Llama 3.1-8b-instant** synthesizes the analyst narrative.

**What it receives** — a structured prompt containing:
- Entity name and total findings count
- Overall risk score and top 3 risk categories
- Data source breakdown (SEC, GDELT, CourtListener, OFAC)
- Adverse media signal rate (GDELT relevant/total)
- Coverage gaps and cross-check conflict count
- Citation rate

**What it produces** — a strict five-section, bullet-formatted narrative:
- `Assessment`
- `EvidenceBasis`
- `WhyThisAssessment`
- `ConfidenceAndLimits`
- `NextActions`

Each section is validated for bullet structure and plain-language metric explanations (citation rate, overall risk score, conflicts, coverage gaps), including a “What this means for you” line.

**Key design points:**
- The LLM sees only **aggregated metrics** — not raw evidence documents. This limits hallucination surface area.
- `GROQ_API_KEY` is required in strict LLM-only mode; missing key results in explicit pipeline failure.
- The LLM narrative is **advisory only**; every underlying fact is independently citable from primary sources.
- The LLM narrative is the final synthesis layer and must satisfy a strict section contract.

---

## Layer 7 — Flask Web UI (`app/`)

The frontend and platform tracks built the Flask web application — query form, five-tab results page, risk visualizations, and interactive knowledge-graph canvas — then extended it in final sprint with loading-state and narrative UX improvements.

### `pipeline.py` — The Orchestrator
Runs the complete investigation when a query is submitted. Calls all layers in order and assembles a single `result` dictionary with ~25 keys that the template uses to render the page.

### `llm_narrative.py` — LLM Analyst Narrative
Calls **Llama 3.1-8b-instant** with a structured prompt of investigation metrics. Returns a strict sectioned bullet narrative displayed as the "AI Analyst Narrative" card on the Overview tab. In strict mode, missing API key raises an explicit pipeline error.

### `graph_viz.py` — Knowledge Graph Serializer
Converts the knowledge graph into JSON format for **vis-network** (a JavaScript library). Samples up to 72 evidence nodes for browser performance. Color-codes by source type:
- Blue → SEC filings
- Amber → News articles
- Purple → Court records
- Red → Sanctions

### Templates — The UI

**`index.html`** — the query form with:
- Entity dropdown (pre-registered entities)
- Query template selector
- Free-text input
- Loading spinner overlay (shows during the 2-3s investigation)

**`results.html`** — five-tab results page:
- **Overview** — LLM narrative card (sectioned bullets), key metrics
- **Analysis** — risk scores, source breakdown, gaps, conflicts
- **Knowledge Graph** — interactive vis-network canvas + NetworkX analysis panel
- **Evidence** — full cited report (HTML)
- **Explanation** — methodology guide and metric definitions

---

## End-to-End Flow: "Investigate Tesla for money laundering"

```
User submits query
        │
        ▼
Flask POST /  →  run_investigation("Investigate Tesla for money laundering")
        │
        ▼
Lead Agent (backend + platform team)
  ├── Entity Resolution: "Tesla" → Entity(cik="0001318605")
  ├── LLM Planner: builds bounded structured plan (typically 3-5 SubTasks)
  └── Context created
        │
        ▼
Specialist Agents (backend team)
  ├── CorporateAgent (SEC lane)
  │     ├── SecEdgarProcessor → 500 SEC filings + 1 governance summary (cached)  [integrated data pipeline]
  ├── LegalAgent (sanctions + litigation lane)
  │     ├── OFACScreener     → 1 sanctions result (local XML, 18,712 entries)  [integrated data pipeline]
  │     └── CourtFetch       → 1 summary + 20 docket rows (cached)  [integrated data pipeline]
  └── SocialGraphAgent × 1 task
        └── GdeltProcessor   → 100 news articles (cached, English-filtered)  [integrated data pipeline]
        │
        ▼
~1,125 total Evidence rows collected
        │
        ▼
Reflexion Layer (backend team)
  ├── Cross-check:   88 conflicts (expected — same-day SEC filings)
  ├── Gap detection: 0 gaps (all active sources returned data)
  └── Confidence:    overall = 0.81
        │
        ▼
Knowledge Graph (graph + backend team)
  └── 625 nodes, 2,259 edges — NetworkX analysis computes centrality metrics
        │
        ▼
Output Layer (backend + reporting team)
  ├── Markdown + HTML evidence report (98% citation rate)
  ├── Risk dashboard (scores by category)
  ├── Evaluation metrics (runtime, coverage, signal rate)
  └── Audit trail (timestamped JSON-lines)
        │
        ▼
Final LLM Narrative
  └── Llama 3.1 strict sectioned narrative (~0.5s)  [team integrated]
        │
        ▼
Flask renders results.html  [frontend + platform tracks]
  └── 5-tab page with graph, evidence, risk scores, AI narrative card
        │
        ▼
Total runtime: ~3.2 seconds
```

---

## Data Sources at a Glance

Core runtime sources were identified, evaluated, and integrated by the data-source workstream:

| Source | What it provides | Cost | Coverage |
|---|---|---|---|
| **SEC EDGAR** | All public company filings (10-K, 8-K, Form 4, etc.) | Free | All US public companies |
| **OFAC SDN** | US Treasury sanctions list (18,712 entities) | Free | Global sanctioned entities |
| **CourtListener** | Federal court dockets and case records | Free | US federal courts |
| **GDELT DOC 2.0** | Global news articles (adverse media) | Free | Global English-language news |

---

## Key Design Decisions (and Why)

**1. LLM at the synthesis layer only — not the evidence layer**
Every evidence row is sourced directly from a public API. No language model generates or paraphrases evidence content, giving 97–98% citation rate with zero hallucination in the evidence layer. The team integrated Llama 3.1 at the synthesis stage so it interprets structured metrics into human-readable prose without touching raw evidence.

**2. Cache-first data access**
The team established a cache-first data path with source-ingestion leadership from the data integration track. Investigations replay from cache instantly. This makes results reproducible, eliminates API failures during demos, and enables cloud deployment without live API dependencies at runtime.

**3. Frozen dataclasses for Entity and Evidence**
Both core types are immutable. An agent cannot accidentally modify another agent's data. This prevents subtle bugs in the shared `InvestigationContext`.

**4. Confidence = 0.0 for missing data (not silent omission)**
When a cache file is missing or an API fails, the system returns an Evidence row with `confidence=0.0` and `cache_missing=True` instead of silently returning nothing. This lets the gap detector surface the issue explicitly rather than hiding it.

**5. LLM-first synthesis with strict validation**
The final synthesis is generated in `llm_narrative.py` using Llama 3.1 and validated against required sections, bullets, and plain-language metric definitions. This keeps final output readable while enforcing a strict contract.

**6. Cloud deployment with zero runtime dependencies**
The deployment/documentation track shipped Render.com deployment with Gunicorn. Because all cached data is committed to the repo, the live deployment requires no external API calls at runtime — the investigation runs entirely from local files.

---

## File Structure

```
FSE570/
├── src/osint_swarm/          Core library — team-owned
│   ├── entities.py           Entity + Evidence dataclasses
│   ├── data_sources/         Raw HTTP connectors (one per source)
│   └── utils/io.py           JSON/CSV read-write helpers
│
├── agents/
│   ├── lead_agent/           Orchestrator — shared backend/platform ownership
│   │   ├── orchestrator.py   LeadAgent.run(query) → InvestigationContext
│   │   ├── entity_resolution/ Registry + SEC auto-resolver (team contribution)
│   │   ├── task_planner/     LLM-guided bounded planning (team contribution)
│   │   └── context_manager/  Shared investigation state (team contribution)
│   └── specialist_agents/    CorporateAgent, LegalAgent, SocialGraphAgent — team-owned
│
├── mcp_layer/                Cache-first data access + confidence/relevance processing (shared ownership)
├── reflexion_layer/          Cross-check, gap detection, confidence — shared ownership
├── knowledge_graph/          Graph builder + NetworkX analysis — shared ownership
├── output_layer/             Reports, dashboard, audit trail, metrics — shared ownership
│
├── app/                      Flask web application
│   ├── app.py                Route handler
│   ├── pipeline.py           Full pipeline orchestration
│   ├── graph_viz.py          vis-network JSON serializer — frontend/graph track
│   ├── llm_narrative.py      LLM synthesis (Llama 3.1) — LLM/platform track
│   └── templates/            Jinja2 HTML — frontend track
│
├── scripts/                  Data pull scripts — data integration track
├── tests/unit/               219 pytest unit tests
├── data/raw/                 Cached API responses (committed to repo)
├── docs/                     Documentation — team maintained
│   ├── ARCHITECTURE.md       This file
│   ├── EVALUATION.md         Performance metrics + benchmarks
│   └── DEPLOYMENT_RUNBOOK.md Setup + demo guide
│
├── requirements.txt          Python dependencies
├── Procfile                  Render.com deployment — deployment track
└── .env.example              Environment variable template
```

---

## Technology Stack

| Component | Technology | Why |
|---|---|---|
| Language | Python 3.8+ | Data science ecosystem, fast iteration |
| Web framework | Flask 3.0 | Lightweight, easy to deploy |
| Production server | Gunicorn | Standard WSGI for cloud deployment |
| LLM | Llama 3.1-8b-instant | Free, fast (~0.5s), open-weight — analyst narrative synthesis |
| Graph analysis | NetworkX 3.3 | Industry-standard graph algorithms |
| Graph visualization | vis-network (JS CDN) | Interactive browser-based network viz |
| Frontend | Jinja2 templates + vanilla JS | No build step, zero JS framework overhead |
| Deployment | Render.com | Free tier, auto-deploy on git push |
| Testing | pytest | 219 unit tests across all layers |
| Data storage | File-based JSON/XML/CSV | No database needed — cache-first design |
