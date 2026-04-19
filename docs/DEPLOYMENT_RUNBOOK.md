# Deployment Runbook — Autonomous OSINT Investigation Swarm
**FSE 570 Capstone | Last updated: April 2026**

---

## Option A — Run Locally (Recommended for Demo)

### Prerequisites
- Python 3.8+ (tested on 3.12)
- Git
- A free SEC EDGAR user-agent string (your name + email — no account needed)
- A free Groq API key (`GROQ_API_KEY`) for strict LLM-only orchestration

### Step 1 — Clone the repo
```bash
git clone <your-repo-url>
cd FSE570
```

### Step 2 — Create virtual environment and install dependencies
```bash
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

### Step 3 — Configure environment
```bash
cp .env.example .env
```

Open `.env` and set:
```
SEC_USER_AGENT=Your Name your@email.com
GROQ_API_KEY=your_groq_api_key
```
> This is required by SEC EDGAR's fair-use policy. Any name + email works — it is not an API key.
> `GROQ_API_KEY` is required in the current strict LLM-only runtime (planner, policies, and final narrative).

### Step 4 — Verify cached data is present
```bash
ls data/raw/sec/          # should show CIK*.json files
ls data/raw/gdelt/        # should show news_*.json files
ls data/raw/courtlistener/ # should show dockets_*.json files
ls data/raw/ofac/         # should show sdn.xml (~27 MB)
```

All raw data is committed to the repo — no pull scripts needed for the 5 pre-cached entities.

### Step 5 — Start the Flask server
```bash
# Development server
flask --app app.app run

# OR production server (same as Render)
gunicorn app.app:app --bind 0.0.0.0:5000
```

Open `http://localhost:5000` in your browser.

---

## Option B — Deployed on Render.com (Live URL)

The app is deployed on Render.com and auto-deploys on every push to `main`.

**Deployment config:**
- **Build command:** `pip install -r requirements.txt`
- **Start command:** `gunicorn app.app:app --bind 0.0.0.0:$PORT` (from `Procfile`)
- **Environment variable:** `SEC_USER_AGENT=<name email>` (set in Render dashboard)
- **No database** — all data is file-based and committed to the repo

**To redeploy after changes:**
```bash
git add .
git commit -m "your message"
git push origin main
# Render auto-deploys within ~2 minutes
```

---

## Demo Walkthrough — What to Show

### Recommended query sequence for the presentation:

**1. Start with a pre-cached entity (fast, reliable)**
```
Investigate Tesla for money laundering
```
- Shows: 1,125 findings, multi-source evidence, risk dashboard, knowledge graph, conflict explanation

**2. Switch industry to prove generality**
```
Investigate JPMorgan for money laundering
```
- Shows: 1,119 findings, 100% GDELT signal rate, court dockets, sanctions screening

**3. Show auto entity resolution (most impressive moment)**
```
Investigate Microsoft for money laundering
```
- Shows: system auto-resolves "Microsoft" → CIK 0000789019 via SEC EDGAR, returns 1,025 findings without any manual registry entry

**4. Point out specific UI features:**
- **Overview tab** — strict sectioned LLM narrative + key metrics at a glance
- **Analysis tab** — risk scores by category (governance, regulatory, legal, network)
- **Knowledge Graph tab** — interactive network + Network Analysis panel (degree centrality, top connected nodes)
- **Evidence tab** — full cited report, every finding with source URL
- **Explanation tab** — what each metric means, methodology

---

## Adding a New Entity to the Registry (Optional)

To add a company permanently (faster than auto-resolution):

**1. Find their CIK** at `https://www.sec.gov/cgi-bin/browse-edgar`

**2. Add to registry** in `agents/lead_agent/entity_resolution/resolver.py`:
```python
Entity(
    entity_id="company_name_cik_0001234567",
    name="Company Name, Inc.",
    entity_type="public_company",
    identifiers={"cik": "0001234567", "ticker": "TICK"},
    aliases=["Company Name", "Company", "TICK"],
),
```

**3. Pull data** (~5 minutes per entity):
```bash
python scripts/pull_sec_submissions.py --cik 0001234567
python scripts/pull_courtlistener.py --entity-id company_name_cik_0001234567
python scripts/pull_gdelt_news.py --entity-id company_name_cik_0001234567
# OFAC uses the local sdn.xml — no pull needed
```

**4. Commit the cached data:**
```bash
git add data/raw/
git commit -m "feat: add <Company Name> entity and cached data"
git push origin main
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `Missing SEC user agent` error | Set `SEC_USER_AGENT` in `.env` |
| `No module named 'osint_swarm'` | Run from repo root; `src/` is in `sys.path` via app |
| GDELT returns 429 | Rate limit — wait 60s and retry, or use cached data |
| Render deployment fails | Check `SEC_USER_AGENT` is set in Render environment variables |
| Investigation returns 0 findings | Entity not in registry AND SEC EDGAR can't resolve name — check spelling |

---

## Environment Variables Reference

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `SEC_USER_AGENT` | **Yes** | — | SEC EDGAR fair-use identifier (name + email) |
| `GROQ_API_KEY` | **Yes** | — | Required for strict LLM-only planner, action policy, reflexion ranking, stop policy, and final narrative |
| `COURTLISTENER_API_TOKEN` | No | — | Higher rate limits on CourtListener API |
| `PORT` | No (Render sets it) | 5000 | Port for gunicorn (set automatically by Render) |
