# Autonomous OSINT Investigation Swarm (Capstone)

This repository is the implementation for **Autonomous OSINT Investigation Swarm** — a modular, multi-agent system for corporate/entity risk assessment.

## Architecture

![Autonomous OSINT Investigation Swarm architecture](Architecture-Diagram.jpeg)

## Quickstart

```bash
# 1. Clone and enter the repo
git clone <repo-url>
cd Repo

# 2. Create & activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up your .env (one time)
cp .env.example .env
# Open .env and replace the placeholder with your name/email

# 5. Pull raw data for an entity (Tesla example)
python scripts/pull_sec_submissions.py --cik 0001318605
python scripts/pull_gdelt_news.py --entity-id tesla_inc_cik_0001318605

# 6. Build the evidence CSV
python scripts/build_evidence.py --entity-id tesla_inc_cik_0001318605
```

**Output**: `data/processed/tesla_inc/evidence_tesla_inc.csv`
(SEC governance filings + GDELT adverse media — structured `Evidence` rows)

## Data Sources

The pipeline uses two fully public, no-auth data sources:

| Source | What it provides | Confidence |
|--------|-----------------|------------|
| **SEC EDGAR** | Governance filings (10-K, 8-K, DEF 14A) | 0.95 |
| **GDELT DOC 2.0** | Adverse media / news (fraud, investigation, penalty) | 0.60 |

See [`docs/data_sources.md`](docs/data_sources.md) for full details.

## Registered Entities

| Entity | Entity ID | CIK |
|--------|-----------|-----|
| Tesla, Inc. | `tesla_inc_cik_0001318605` | 0001318605 |
| Ford Motor Company | `ford_motor_cik_0000037996` | 0000037996 |
| The Boeing Company | `boeing_cik_0000012927` | 0000012927 |

To add a new entity, see `agents/lead_agent/entity_resolution/resolver.py`.

## Demo (Flask)

Run the web demo to investigate an entity from the browser:

```bash
python app/app.py
```

Open **http://127.0.0.1:5000**, enter a query (e.g. *Investigate Tesla for money laundering*), and click **Run investigation**. The app runs the full pipeline (Lead Agent → specialists → reflexion → knowledge graph → report) and shows entity, tasks, findings count, risk dashboard, gaps, evidence report, and audit trail. See [`app/README.md`](app/README.md) for details.

## Repo layout

- `src/osint_swarm/`: core library (schemas + connectors for SEC and GDELT)
- `agents/`: Lead Agent + specialist agents (Corporate, Legal, Social Graph)
- `mcp_layer/`: data layer (SEC EDGAR processor, GDELT processor, evidence loader)
- `reflexion_layer/`: cross-check, gap detection, confidence
- `knowledge_graph/`: graph built from evidence
- `output_layer/`: evidence report, risk dashboard, audit trail
- `app/`: Flask demo (web UI to run investigations)
- `scripts/`: runnable ingestion/build scripts
- `data/raw/`: cached raw source files (traceability)
- `data/processed/`: normalized evidence tables used by agents
- `docs/`: data sources blueprint + schemas

## Testing

From the project root (with the virtual environment activated):

```bash
pytest tests/unit -v
```

See `pyproject.toml` for pytest configuration (pythonpath includes `src` and project root).

## Documentation

- [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) — Phase-wise implementation plan (Phases 1–7).
- [`docs/schema.md`](docs/schema.md) — Entity and Evidence schema.
- [`docs/data_sources.md`](docs/data_sources.md) — Data sources blueprint.
- [`docs/EVIDENCE_AS_INPUT.md`](docs/EVIDENCE_AS_INPUT.md) — Evidence as canonical agent input.
- [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md) — Detailed project status, workflow, and next steps.

## Notes

- **Python**: 3.8+ recommended (tested with 3.13).
- **SEC EDGAR** requires a valid `User-Agent`; set `SEC_USER_AGENT` in `.env` (see `.env.example`).
- **GDELT** requires no authentication — free and fully public.
- Paywalled sources (PACER/Reuters/etc.) are treated as future extensions.
