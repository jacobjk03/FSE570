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

The system automatically queries five public data sources, collects hundreds of citable evidence items, scores them by confidence, cross-validates them, builds a risk profile, generates a natural-language analyst narrative using Llama 3.1, and produces a full audit-ready investigation report — all without any human involvement.

---

## The Team

Five people built this system across the full semester:

**Taljinder Singh** identified and integrated all five public data sources — SEC EDGAR, OFAC SDN, CourtListener, GDELT, and OpenCorporates. He built the raw HTTP connectors, designed the data preprocessing pipeline, and performed exploratory data analysis to understand the shape and quality of each source before they were wired into the agents.

**Arnab Mitra** designed and implemented the core backend — the Lead Agent orchestrator, all three specialist agents (Corporate, Legal, Social Graph), the MCP caching layer, the Reflexion layer, the Knowledge Graph builder, and the full Output layer including the evidence report generator, risk dashboard, and audit trail.

**Raj Kumar Mahto** contributed to backend development, working on the task planner and context manager that coordinate how sub-tasks are dispatched across specialist agents and how findings are accumulated in shared investigation state.

**Aditya Pokharna** built the entire Flask web UI — the query form, the five-tab results page, the risk score visualizations, the interactive knowledge graph canvas using vis-network, and all CSS styling.

**Jacob Kuriakose** led deployment and documentation, and drove the final sprint improvements: cloud deployment on Render.com, automatic entity resolution for any public company via SEC EDGAR, LLM integration using Llama 3.1, two new entity data sets (Alphabet, JPMorgan), GDELT English-language filtering, filing-type confidence scoring, NetworkX graph analysis, the loading spinner UX, and all three documentation deliverables.

---

## The Big Picture — How It Works in One Paragraph

When you submit a query, a **Lead Agent** reads it and figures out which company you mean (e.g., "Tesla" → Tesla, Inc., CIK 0001318605). It then breaks your request into a set of investigation tasks and hands each task to a **specialist agent**. Three specialist agents run in sequence — one for corporate filings, one for legal/sanctions, one for news. Each agent collects structured evidence from public data sources via a **MCP (Model Context Protocol) layer** that handles caching and API calls. Once all agents finish, a **Reflexion layer** checks the evidence for gaps, conflicts, and assigns confidence scores. The results are assembled into a **knowledge graph**, a **risk dashboard**, and a **full evidence report**. Finally, **Llama 3.1** reads the aggregated metrics and writes a concise natural-language analyst narrative. Everything is displayed in a **Flask web UI**.

---

## System Layers — Top to Bottom

The system is organized into 7 layers. Think of them like floors in a building — each floor talks to the ones above and below it.

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

This is the foundation. Taljinder built the five raw data connectors and the data preprocessing pipeline that feeds into everything else.

### The Two Core Data Types

Everything in the system is built around two Python dataclasses, designed by Arnab:

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

Taljinder identified all five sources and built the HTTP clients that pull from them:

| Connector | What it calls | Auth needed |
|---|---|---|
| `sec_edgar.py` | `https://data.sec.gov/submissions/CIK{cik}.json` | Just name + email |
| `gdelt.py` | `https://api.gdeltproject.org/api/v2/doc/doc` | None |
| `ofac.py` | Parses local `data/raw/ofac/sdn.xml` (27 MB file) | None |
| `courtlistener.py` | `https://www.courtlistener.com/api/rest/v4/search/` | None |
| `opencorporates.py` | `https://api.opencorporates.com/v0.4/companies/` | Free token |

---

## Layer 2 — MCP Layer (`mcp_layer/`)

**MCP = Model Context Protocol.** Arnab designed this standardized interface layer that sits between the agents and the raw connectors.

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

**`SecEdgarProcessor`** (Arnab + Jacob) — reads `data/raw/sec/CIK{cik}.json`, converts up to 500 SEC filings into Evidence rows. Jacob extended the processor with tiered confidence scoring by filing type:
- 8-K (material events) → **0.95**
- 10-K / 10-Q (annual reports) → **0.85**
- DEF 14A (proxy statements) → **0.80**
- Form 4 (routine insider trades) → **0.75**

**`GdeltProcessor`** (Arnab + Jacob) — reads `data/raw/gdelt/news_{slug}.json`, converts news articles into Evidence. Relevance is scored by title content. Jacob extended it with English-language filtering to remove non-English articles from the signal:
- Entity name + risk keyword in title → **0.75** (high signal)
- Entity name only → **0.70**
- Risk keyword only → **0.55**
- Neither → **0.30** (kept but down-weighted)
- Non-English articles → **filtered out**

**`EvidenceLoader`** — an alternative path that reads pre-built CSVs from `data/processed/`.

---

## Layer 3 — Lead Agent (`agents/lead_agent/`)

The Lead Agent is the orchestrator — it receives the raw query string and coordinates everything else. Arnab designed the overall architecture; Jacob extended it with automatic entity resolution and wired in the SEC EDGAR fallback resolver.

### Sub-module 1: Entity Resolution (`resolver.py` + `sec_name_resolver.py`)

Converts a query like `"Investigate Tesla for money laundering"` into an `Entity` object.

**Step 1 — Registry lookup:** Check a hardcoded list of known entities (Tesla, Ford, Boeing, Alphabet, JPMorgan). Match by name or alias using case-insensitive substring matching. Short aliases (< 3 chars, like ticker "F") use whole-word matching to avoid false positives.

**Step 2 — Auto-resolution (Jacob, final sprint):** For any unknown company, `sec_name_resolver.py` queries the SEC EDGAR full-text search API:
```
https://efts.sec.gov/LATEST/search-index?q="Microsoft"&forms=10-K
```
Parse the response to extract the CIK and official company name. Build a temporary `Entity` object on the fly.

This means the system can investigate **any publicly traded company** — not just the 5 pre-registered ones.

### Sub-module 2: Task Planner (`planner.py`)

Raj built the task planner, which reads the query and generates a list of `SubTask` objects based on keyword detection:

| Query contains... | Tasks generated |
|---|---|
| "money laundering", "sanctions", "AML", "bribery" | 6 tasks (full AML investigation) |
| Generic investigation | 4 tasks (standard investigation) |

Example tasks for an AML query:
```
1. corporate_structure   → corporate_agent
2. beneficial_ownership  → corporate_agent
3. sanctions_screening   → legal_agent
4. litigation            → legal_agent
5. transaction_patterns  → corporate_agent
6. adverse_media         → social_graph_agent
```

### Sub-module 3: Context Manager (`context.py`)

Raj built the `InvestigationContext` object that is created and passed to every agent. It holds:
- The resolved `Entity`
- The list of `SubTask` objects
- A dictionary mapping `agent_id → List[Evidence]` (results accumulate here)

Agents can read each other's results via this shared context — for example, the legal agent can see what the corporate agent already found.

---

## Layer 4 — Specialist Agents (`agents/specialist_agents/`)

Arnab built all three specialist agents, each implementing the same protocol: `run(entity, task, context) → List[Evidence]`.

### Corporate Agent

Handles tasks: `corporate_structure`, `beneficial_ownership`, `transaction_patterns`

- **SEC filings** (tasks 1 + 3): Calls `SecEdgarProcessor` → returns up to 500 filing Evidence rows + 1 governance summary row
- **Beneficial ownership** (task 2): Calls `OpenCorporates` via `structure_mapper.py` → returns ~8 Evidence rows for officers, UBOs (ultimate beneficial owners), controlling entities, and corporate groupings

### Legal Agent

Handles tasks: `sanctions_screening`, `litigation`

- **Sanctions screening** (task 3): Parses the local OFAC SDN XML file (18,712 entries) sourced by Taljinder. Normalizes names (strips "Inc", "LLC", "Corp" suffixes), runs fuzzy matching. Returns 1 Evidence row — either a match (confidence 0.90, flagged) or clean (confidence 0.90, no match). Includes false-positive guards (e.g., "Ford" does not match "Oxford").
- **Litigation** (task 4): Calls `CourtListener` API sourced by Taljinder. Cache-first. Returns 1 summary Evidence row + up to 20 docket Evidence rows (federal court cases).

### Social Graph Agent

Handles tasks: `adverse_media`, `network_analysis`

- Calls `GdeltProcessor` → returns up to 100 news article Evidence rows, relevance-scored by title content, English-language filtered.

---

## Layer 5 — Reflexion Layer (`reflexion_layer/`)

Arnab built the reflexion layer, which runs three quality checks after all agents finish:

### 1. Cross-Check (`checker.py`)
Groups all findings by `(entity_id, date)`. If two or more findings share the same entity and date but have different summaries → flags a **Conflict**.

> **Note:** 88 conflicts for Tesla is normal — companies often file multiple SEC forms (e.g., an 8-K and a Form 4) on the same day. This is expected behaviour, not an error.

### 2. Gap Detection (`detector.py`)
Checks for missing evidence:
- Did the entity fail to resolve? → Gap: "Entity not found"
- Did OFAC screening return `cache_missing=True`? → Gap: "Sanctions data unavailable"
- Did GDELT return no articles? → Gap: "Adverse media unavailable"
- Did OpenCorporates return `cache_missing=True`? → Gap: "Beneficial ownership data unavailable"

Each gap includes a `suggested_follow_up` explaining what to do next.

### 3. Confidence Scoring (`scorer.py`)
Aggregates all findings into:
- **Overall mean confidence** (e.g., 0.81 for Tesla AML)
- **Confidence by risk category** (governance, regulatory, legal, network)
- **Confidence by source type** (sec_filing, news_article, court_record, etc.)
- **Adjusted confidence** applying source reliability weights (SEC=0.95, court=0.80, news=0.60)

---

## Layer 6 — Output Layer (`output_layer/`)

Arnab built all four output modules that run after reflexion:

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

Built from the full evidence set after all agents finish. Arnab designed and built the graph structure and builder; Jacob added the NetworkX analysis module (`network_analysis.py`) and wired the results into the pipeline and UI.

**Structure:**
- One **node** per entity (the company being investigated)
- One **node** per evidence item (each finding is a node)
- **Edges** of type `has_evidence` connect the entity node to each evidence node
- **Edges** of type `same_source_type` chain evidence nodes that share the same source

**Network Analysis** (Jacob, final sprint — powered by NetworkX):
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

Jacob integrated Llama 3.1 during the final sprint to give the system a genuine generative AI component. After the output layer produces all structured metrics, **Llama 3.1-8b-instant** is called to synthesise a natural-language analyst narrative.

**What it receives** — a structured prompt containing:
- Entity name and total findings count
- Overall risk score and top 3 risk categories
- Data source breakdown (SEC, GDELT, CourtListener, OFAC, OpenCorporates)
- Adverse media signal rate (GDELT relevant/total)
- Coverage gaps and cross-check conflict count
- Citation rate

**What it produces** — a 3–4 sentence analyst-style paragraph, e.g.:
> *"Tesla, Inc. has been identified as a subject of concern based on a comprehensive OSINT investigation, yielding 1,125 findings with a high citation rate of 98.1%. The overall risk score of 0.84 indicates a moderate to high level of risk, primarily driven by governance (0.82), regulatory (0.79), and legal (0.75) concerns. Adverse media coverage suggests a significant issue, with 85% of 47 articles flagged as highly relevant."*

**Key design points:**
- The LLM sees only **aggregated metrics** — not raw evidence documents. This limits hallucination surface area.
- If `GROQ_API_KEY` is not set, the call is skipped and the card is hidden — all other features work unchanged.
- The LLM narrative is **advisory only**; every underlying fact is independently citable from primary sources.
- The deterministic `verdict_synthesis.py` still runs alongside it — the LLM narrative supplements it, not replaces it.

---

## Layer 7 — Flask Web UI (`app/`)

Aditya built the Flask web application — the query form, the five-tab results page, risk score visualizations, and the interactive knowledge graph canvas. Jacob extended it during the final sprint with the loading spinner overlay, the conflict explanation info box, and the LLM narrative card.

### `pipeline.py` — The Orchestrator
Runs the complete investigation when a query is submitted. Calls all layers in order and assembles a single `result` dictionary with ~25 keys that the template uses to render the page.

### `llm_narrative.py` — LLM Analyst Narrative (Jacob)
Calls **Llama 3.1-8b-instant** with a structured prompt of the investigation metrics. Returns a 3–4 sentence natural-language analyst narrative displayed as the "AI Analyst Narrative" card on the Overview tab. Gracefully returns `None` if no API key is configured.

### `verdict_synthesis.py` — The Deterministic Analyst Verdict (Arnab)
Generates a structured "analyst summary" from the result metrics using deterministic rules. Classifies the investigation into tiers:
- `substantial_public_record` — many findings across multiple sources
- `partial_coverage` — some sources missing
- `limited_evidence` — few findings

Always includes a caveat that no automated system can issue a legal verdict.

### `graph_viz.py` — Knowledge Graph Serializer (Aditya)
Converts the knowledge graph into JSON format for **vis-network** (a JavaScript library). Samples up to 72 evidence nodes for browser performance. Color-codes by source type:
- Blue → SEC filings
- Amber → News articles
- Purple → Court records
- Red → Sanctions

### Templates — The UI (Aditya + Jacob)

**`index.html`** — the query form with:
- Entity dropdown (pre-registered entities)
- Query template selector
- Free-text input
- Loading spinner overlay (Jacob — shows during the 2-3s investigation)

**`results.html`** — five-tab results page:
- **Overview** — LLM narrative card, verdict synthesis, key metrics
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
Lead Agent (Arnab + Jacob)
  ├── Entity Resolution: "Tesla" → Entity(cik="0001318605")
  ├── Task Planner: detects "money laundering" → 6 SubTasks  [Raj]
  └── Context created
        │
        ▼
Specialist Agents (Arnab)
  ├── CorporateAgent × 3 tasks
  │     ├── SecEdgarProcessor → 500 SEC filings + 1 governance summary (cached)  [Taljinder data]
  │     └── StructureMapper  → 8 OpenCorporates rows (officers, UBOs)  [Taljinder data]
  ├── LegalAgent × 2 tasks
  │     ├── OFACScreener     → 1 sanctions result (local XML, 18,712 entries)  [Taljinder data]
  │     └── CourtFetch       → 1 summary + 20 docket rows (cached)  [Taljinder data]
  └── SocialGraphAgent × 1 task
        └── GdeltProcessor   → 100 news articles (cached, English-filtered)  [Taljinder data]
        │
        ▼
~1,125 total Evidence rows collected
        │
        ▼
Reflexion Layer (Arnab)
  ├── Cross-check:   88 conflicts (expected — same-day SEC filings)
  ├── Gap detection: 0 gaps (all 5 sources returned data)
  └── Confidence:    overall = 0.81
        │
        ▼
Knowledge Graph (Arnab + Jacob)
  └── 625 nodes, 2,259 edges — NetworkX analysis computes centrality metrics
        │
        ▼
Output Layer (Arnab)
  ├── Markdown + HTML evidence report (98% citation rate)
  ├── Risk dashboard (scores by category)
  ├── Evaluation metrics (runtime, coverage, signal rate)
  └── Audit trail (timestamped JSON-lines)
        │
        ▼
Verdict Synthesis + LLM Narrative
  ├── Deterministic analyst-style summary — rule-based  [Arnab]
  └── Llama 3.1 natural-language narrative (~0.5s)  [Jacob]
        │
        ▼
Flask renders results.html  [Aditya + Jacob]
  └── 5-tab page with graph, evidence, risk scores, AI narrative card
        │
        ▼
Total runtime: ~3.2 seconds
```

---

## Data Sources at a Glance

All five sources were identified, evaluated, and integrated by Taljinder:

| Source | What it provides | Cost | Coverage |
|---|---|---|---|
| **SEC EDGAR** | All public company filings (10-K, 8-K, Form 4, etc.) | Free | All US public companies |
| **OFAC SDN** | US Treasury sanctions list (18,712 entities) | Free | Global sanctioned entities |
| **CourtListener** | Federal court dockets and case records | Free | US federal courts |
| **GDELT DOC 2.0** | Global news articles (adverse media) | Free | Global English-language news |
| **OpenCorporates** | Corporate structure, officers, beneficial owners | Free tier | Global company registry |

---

## Key Design Decisions (and Why)

**1. LLM at the synthesis layer only — not the evidence layer**
Every evidence row is sourced directly from a public API. No language model generates or paraphrases evidence content, giving 97–98% citation rate with zero hallucination in the evidence layer. Jacob integrated Llama 3.1 only at the final synthesis stage, where it interprets structured numbers into human-readable prose without touching raw evidence.

**2. Cache-first data access**
Taljinder pulled all raw data once; it is committed to the repo. Investigations replay from cache instantly. This makes results reproducible, eliminates API failures during demos, and enables cloud deployment without live API dependencies at runtime.

**3. Frozen dataclasses for Entity and Evidence**
Both core types are immutable (Arnab). An agent cannot accidentally modify another agent's data. This prevents subtle bugs in the shared `InvestigationContext`.

**4. Confidence = 0.0 for missing data (not silent omission)**
When a cache file is missing or an API fails, the system returns an Evidence row with `confidence=0.0` and `cache_missing=True` instead of silently returning nothing. This lets Arnab's gap detector surface the issue explicitly rather than hiding it.

**5. Two-layer synthesis: deterministic + LLM**
Arnab's deterministic `verdict_synthesis.py` uses rule-based logic — same inputs always produce the same output, fully auditable. Jacob's `llm_narrative.py` uses Llama 3.1 to write a fluent natural-language summary. Both appear on the Overview tab, giving the user both machine-reproducible structure and human-readable interpretation.

**6. Cloud deployment with zero runtime dependencies**
Jacob deployed the system on Render.com using Gunicorn. Because all cached data is committed to the repo, the live deployment requires no external API calls at runtime — the investigation runs entirely from local files.

---

## File Structure

```
FSE570/
├── src/osint_swarm/          Core library — Taljinder + Arnab
│   ├── entities.py           Entity + Evidence dataclasses
│   ├── data_sources/         Raw HTTP connectors (one per source)
│   └── utils/io.py           JSON/CSV read-write helpers
│
├── agents/
│   ├── lead_agent/           Orchestrator — Arnab + Jacob
│   │   ├── orchestrator.py   LeadAgent.run(query) → InvestigationContext
│   │   ├── entity_resolution/ Registry + SEC auto-resolver (Jacob)
│   │   ├── task_planner/     Keyword-based task decomposition (Raj)
│   │   └── context_manager/  Shared investigation state (Raj)
│   └── specialist_agents/    CorporateAgent, LegalAgent, SocialGraphAgent — Arnab
│
├── mcp_layer/                Cache-first data access (Arnab); confidence + GDELT filter extensions (Jacob)
├── reflexion_layer/          Cross-check, gap detection, confidence — Arnab
├── knowledge_graph/          Graph builder (Arnab) + NetworkX analysis (Jacob)
├── output_layer/             Reports, dashboard, audit trail, metrics — Arnab
│
├── app/                      Flask web application
│   ├── app.py                Route handler
│   ├── pipeline.py           Full pipeline orchestration
│   ├── graph_viz.py          vis-network JSON serializer — Aditya
│   ├── verdict_synthesis.py  Deterministic analyst verdict — Arnab
│   ├── llm_narrative.py      LLM synthesis (Llama 3.1) — Jacob
│   └── templates/            Jinja2 HTML — Aditya + Jacob
│
├── scripts/                  Data pull scripts — Taljinder
├── tests/unit/               219 pytest unit tests
├── data/raw/                 Cached API responses (committed to repo)
├── docs/                     Documentation — Jacob
│   ├── ARCHITECTURE.md       This file
│   ├── EVALUATION.md         Performance metrics + benchmarks
│   └── DEPLOYMENT_RUNBOOK.md Setup + demo guide
│
├── requirements.txt          Python dependencies
├── Procfile                  Render.com deployment — Jacob
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
