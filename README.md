# Autonomous OSINT Investigation Swarm

A modular, multi-agent system for corporate AML and financial risk assessment. Submit a plain-English query — the system queries five public data sources, scores and cross-validates hundreds of evidence items, runs NetworkX graph analysis, generates an LLM-powered analyst narrative via Llama 3.1, and returns a full audit-ready investigation report in under 4 seconds.

**Live demo:** deployed on Render.com (auto-deploys on every push to `main`)

---

## Quickstart

```bash
git clone https://github.com/jacobjk03/FSE570.git
cd FSE570
pip install -r requirements.txt
cp .env.example .env          # set SEC_USER_AGENT (name + email — no account needed)
flask --app app.app run
```

Open **http://127.0.0.1:5000** and run a query, e.g. `Investigate Tesla for money laundering`.

All data for the 5 pre-cached entities is committed to the repo — no pull scripts needed.  
For Llama 3.1 analyst narratives, set `GROQ_API_KEY` in `.env` (free at console.groq.com).

---

## Demo Query Sequence

| Query | What it shows |
|---|---|
| `Investigate Tesla for money laundering` | 1,125 findings, 5 sources, LLM narrative, knowledge graph |
| `Investigate JPMorgan for money laundering` | 1,119 findings, 100% GDELT signal rate |
| `Investigate Microsoft for money laundering` | Auto-resolves to CIK 0000789019 — any public company works |

---

## Supported Entities

5 pre-cached entities (instant, no network calls at runtime):

| Entity | CIK | Findings | Citation Rate |
|---|---|---|---|
| Tesla, Inc. | 0001318605 | ~1,125 | 98% |
| Ford Motor Company | 0000037996 | ~1,088 | 98% |
| The Boeing Company | 0000012927 | ~1,088 | 98% |
| Alphabet Inc. (Google) | 0001652044 | ~1,121 | 98% |
| JPMorgan Chase & Co. | 0000019617 | ~1,119 | 98% |

**Any publicly traded US company** also works via automatic entity resolution — the system queries SEC EDGAR full-text search to resolve the name to a CIK on the fly.

---

## Data Sources

| Source | What it provides | Auth |
|---|---|---|
| **SEC EDGAR** | All public company filings (10-K, 8-K, Form 4, DEF 14A) | Name + email only |
| **OFAC SDN** | US Treasury sanctions list (18,712 entities) | None |
| **CourtListener** | Federal court dockets and case records | None |
| **GDELT DOC 2.0** | Global English-language adverse media | None |
| **OpenCorporates** | Corporate structure, officers, beneficial owners | Free token |

---

## Architecture

The pipeline runs 7 layers in sequence:

```
User query
    → Lead Agent (entity resolution + task planning)
    → Specialist Agents (Corporate / Legal / Social Graph)
    → MCP Layer (cache-first data access)
    → Reflexion Layer (cross-check, gap detection, confidence scoring)
    → Knowledge Graph (NetworkX analysis + vis-network visualization)
    → Output Layer (evidence report, risk dashboard, audit trail)
    → LLM Layer (Llama 3.1 analyst narrative)
    → Flask UI (5-tab results page)
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for a full plain-English walkthrough.

---

## Results Page — 5 Tabs

- **Overview** — LLM analyst narrative (Llama 3.1), deterministic verdict synthesis, key metrics
- **Analysis** — risk scores by category, source breakdown, gaps, cross-check conflicts
- **Knowledge Graph** — interactive vis-network canvas + NetworkX analysis panel (degree centrality, top-5 nodes)
- **Evidence** — full cited report, every finding with source URL (98%+ citation rate)
- **Explanation** — methodology guide, metric definitions

---

## Repo Layout

```
├── agents/                   Lead Agent + specialist agents
│   ├── lead_agent/           Entity resolution, task planner, orchestrator
│   └── specialist_agents/    CorporateAgent, LegalAgent, SocialGraphAgent
├── mcp_layer/                Cache-first data access (SEC, GDELT, OFAC, CourtListener)
├── reflexion_layer/          Cross-check, gap detection, confidence scoring
├── knowledge_graph/          Graph builder + NetworkX analysis
├── output_layer/             Evidence report, risk dashboard, audit trail, metrics
├── app/                      Flask web application
│   ├── pipeline.py           Full pipeline orchestration
│   ├── llm_narrative.py      Llama 3.1 analyst narrative (Groq API)
│   ├── verdict_synthesis.py  Deterministic rule-based verdict
│   └── templates/            Jinja2 HTML (index + results)
├── src/osint_swarm/          Core library (Entity + Evidence dataclasses, raw connectors)
├── data/raw/                 Cached API responses (committed — no pull scripts needed)
├── scripts/                  Data pull scripts for adding new entities
├── tests/unit/               219 pytest unit tests
└── docs/
    ├── ARCHITECTURE.md       Plain-English system guide
    ├── EVALUATION.md         Performance benchmarks (3,100x speedup vs manual)
    └── DEPLOYMENT_RUNBOOK.md Setup, Render deployment, demo walkthrough
```

---

## Environment Variables

| Variable | Required | Purpose |
|---|---|---|
| `SEC_USER_AGENT` | **Yes** | SEC EDGAR fair-use identifier (`First Last email@domain.com`) |
| `GROQ_API_KEY` | No | Enables Llama 3.1 analyst narrative (free at console.groq.com) |
| `OPENCORPORATES_API_TOKEN` | No | Live OpenCorporates lookups for new entities |

---

## Testing

```bash
pytest tests/unit -v    # 219 tests
```

---

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — full system walkthrough for new contributors
- [`docs/EVALUATION.md`](docs/EVALUATION.md) — 3,100x speedup benchmark, per-entity metrics, methodology
- [`docs/DEPLOYMENT_RUNBOOK.md`](docs/DEPLOYMENT_RUNBOOK.md) — local setup, Render deployment, demo guide
- [`TEAM_FINAL_PLAN.md`](TEAM_FINAL_PLAN.md) — presentation framing, gap responses, task statuses
