# FSE570 Final Week — Team Plan & Presentation Framing
**Presentation & Report Due:** ~April 23, 2026  
**Shared by:** Jacob Kuriakose

---

## Part 1 — How to Address the Proposal Gaps (Report & Presentation Framing)

These are questions the professor or evaluators may raise. Here is exactly how to answer each one.

---

### Gap 1 — "The proposal said Multi-Agent AI System but there's no LLM"

**Answer to give:**

> *"The evidence layer remains source-grounded and deterministic: every finding comes from SEC EDGAR, OFAC SDN, CourtListener, or GDELT with high citation coverage. On top of that, orchestration is now strict LLM-driven: planner, action policy, reflexion ranking, stop policy, and final analyst narrative all run through validated LLM contracts. We separate responsibilities intentionally: deterministic retrieval for facts, LLMs for adaptive reasoning and analyst-facing synthesis."*

**Why this works:** You now have genuine AI behavior across the investigation loop (not just final narration), while still preserving citation-traceable evidence integrity.

---

### Gap 2 — "Only 3 entities — where's the generality?"

**Answer to give during the demo:**
- Show the demo working on Tesla, then switch to Alphabet or JPMorgan live.
- If auto-resolution is done: type any company name and show it resolving to a CIK automatically.

> *"The system was designed to be entity-agnostic from day one. The registry was a development convenience for reproducibility during testing. This week we added Alphabet and JPMorgan, and implemented automatic entity resolution via SEC full-text search — any public company name now resolves to a CIK on the fly."*

---

### Gap 3 — "The Social Graph Agent just fetches news — where's the graph analysis?"

**Answer to give:**

> *"The SocialGraphAgent collects adverse media evidence from GDELT. We then apply network analysis on the knowledge graph — degree centrality identifies the most-connected entities, and clustering coefficients surface tightly-linked risk clusters. These metrics are surfaced in a dedicated Network Analysis panel on the results page."*

---

### Gap 4 — "How does this compare to a human analyst?"

**Answer to give (with numbers):**

| Task | Manual Analyst | Our System |
|---|---|---|
| SEC filings review | ~30 min | < 1s (cached) |
| OFAC sanctions screening | ~20 min | < 0.5s |
| Court records search | ~30 min | < 1s (cached) |
| News / adverse media | ~45 min | < 1s (cached) |
| **Total** | **~2.5 hours** | **2.9 seconds** |
| **Speedup** | — | **~3,100x** |

> *"Our system completes a full multi-source investigation in around 2.9 seconds with high citation coverage. A trained analyst performing the same investigation manually across these public sources takes approximately 2.5 hours. That is a ~3,100x reduction in investigation time — without sacrificing source traceability."*

---

### Gap 5 — "Is there a deployment guide?"

**Answer to give:** Yes. The deployment guide is available at `docs/DEPLOYMENT_RUNBOOK.md`.

---

## Part 2 — Remaining Work (All Tasks, Prioritized)

### P1 — Loading Spinner + Progress Indicator
**Owner:** Jacob | **Effort:** ~1-2 hrs  
**Why:** 2-3s blocking POST with no UI feedback looks broken during a live demo.  
**What:** Add a loading overlay/spinner on form submit in `app/templates/index.html`.  
**Status:** ✅ Done — full-page blur overlay with spinning ring, query text echo, and 5 animated pipeline step indicators. Hides automatically when results page loads.

---

### P2 — Add New Entities: Alphabet (Google) + JPMorgan
**Owner:** Jacob | **Effort:** ~2-3 hrs  
**Why:** Proves system generality. Explicitly committed to in QC2.  
**What:**
- Add `alphabet_inc_cik_0001652044` (GOOGL) and `jpmorgan_chase_cik_0000019617` (JPM) to `ENTITY_REGISTRY` in `agents/lead_agent/entity_resolution/resolver.py`
- Run all 5 pull scripts for both entities
- Cache results in `data/raw/`  
**Status:** ✅ Done — Google: 1,121 findings, 2.97s, 98% citation, 82% GDELT signal. JPMorgan: 1,119 findings, 2.87s, 98% citation, 100% GDELT signal.

---

### P3 — Automatic Entity Resolution (SEC Full-Text Search → CIK)
**Owner:** Jacob | **Effort:** ~4-6 hrs  
**Why:** Removes the registry bottleneck. Any company name typed → auto-resolves to CIK. This is the most impressive demo moment and fixes the "generality" gap completely.  
**What:**
- Query SEC EDGAR full-text search API: `https://efts.sec.gov/LATEST/search-index?q="<name>"&forms=10-K`
- Parse response to extract CIK
- Fall back to registry if search fails
- New file: `agents/lead_agent/entity_resolution/sec_name_resolver.py`  
**Status:** ✅ Done — `sec_name_resolver.py` built, wired into resolver + orchestrator. Microsoft → CIK 0000789019, 1,025 findings, 4.4s. Goldman Sachs, Apple, Amazon, Nvidia all auto-resolve correctly.

---

### P4 — Evaluation Write-up (vs Manual Workflows)
**Owner:** Jacob + whole team | **Effort:** ~3-4 hrs  
**Why:** Core proposal evaluation criterion. Needed in the final report.  
**What:** Document the speedup table above + citation rate + coverage + GDELT signal rate metrics. Add a section to the final report and one slide to the presentation.  
**Status:** ✅ Done — `docs/EVALUATION.md` written. Includes: 3,100× speedup table, per-entity metrics (5 entities), confidence methodology, reflexion quality, generality tests, strict LLM orchestration rationale, 219-test coverage breakdown.

---

### P5 — GDELT Language/Country Filtering
**Owner:** Jacob | **Effort:** ~1 hr  
**Why:** Pushes Tesla GDELT signal from 53% → ~70%+. Better KPI numbers.  
**What:** Add `sourcecountry=US&sourcelanguage=English` to GDELT API call in `src/osint_swarm/data_sources/gdelt.py`.  
**Status:** ✅ Done — `sourcelang=english` in API params; processor filters non-English from cache too. Ford: 100→75 articles (25 non-English removed). Boeing 89%, Alphabet 82%, JPMorgan 100% signal.

---

### P6 — Filing-Type Confidence Modifiers
**Owner:** Jacob | **Effort:** ~2 hrs  
**Why:** Flat 0.85 for all SEC filings is defensible but unsophisticated. Tiered scoring is more credible in the demo.  
**What:**
- 8-K (material events) → 0.95
- 10-K / 10-Q → 0.85 (unchanged)
- Form 4 (routine insider) → 0.75
- DEF 14A (proxy) → 0.80  
**Files:** `mcp_layer/sec_edgar_processor/`  
**Status:** ✅ Done — 8-K→0.95 (104 filings), 10-K→0.85 (302), DEF 14A→0.80 (178), Form 4→0.75 (416). Confidence now reflects filing materiality.

---

### P7 — UI Explanation for Cross-Check Conflicts
**Owner:** Jacob | **Effort:** ~1 hr  
**Why:** 88 conflicts for Tesla currently looks like a bug to anyone unfamiliar with SEC filing behavior.  
**What:** Add a tooltip or inline note on the results page: *"Conflicts = multiple SEC filings on the same date with different summaries. This is expected behavior, not a data error."*  
**Files:** `app/templates/results.html`  
**Status:** ✅ Done — yellow info box above conflict list explains expected SEC filing behaviour; not conditional on narrative flag.

---

### P8 — Deployment Runbook
**Owner:** Jacob | **Effort:** ~1-2 hrs  
**Why:** Required for the report's reproducibility section. Any teammate must be able to demo from a fresh clone.  
**What:** `docs/DEPLOYMENT_RUNBOOK.md` covering:
1. Clone repo
2. `pip install -r requirements.txt`
3. Set `.env` (`SEC_USER_AGENT=Your Name your@email.com` and `GROQ_API_KEY=...`)
4. Run pull scripts to populate `data/raw/`
5. `flask run` or `gunicorn app.app:app`
6. Demo walkthrough — which queries to run, what to point at  
**Status:** ✅ Done — `docs/DEPLOYMENT_RUNBOOK.md` written. Local setup (5 steps), Render.com deployment, demo query sequence (Tesla → JPMorgan → Microsoft auto-resolve), adding new entities guide, troubleshooting table, env vars reference.

---

### P9 — Network / Graph Analysis on Knowledge Graph
**Owner:** Jacob | **Effort:** ~2-3 hrs  
**Why:** Proposal promised "graph-based analysis to identify anomalous patterns." Right now the graph is only visualized, never analyzed. Adding real metrics turns this into a genuine claim.  
**What:**
- Use `networkx` to compute: degree centrality, clustering coefficient, most-connected nodes
- Surface results as a "Network Analysis" panel on the results page
- Highlight top 5 most-connected entities in the graph visualization  
**Files:** `knowledge_graph/network_analysis.py` (new), `app/pipeline.py`, `app/templates/results.html`, `requirements.txt`  
**Status:** ✅ Done — NetworkX module built, wired into pipeline, Network Analysis card live on results page. Tesla: 1 component, avg degree 3.98, hub entity Tesla Inc (624 connections).

---

### P10 — LLM Integration (Llama 3.1 via Groq)
**Owner:** Jacob | **Effort:** ~2 hrs  
**Why:** This is a DS capstone — evaluators expect a genuine AI/ML component. We moved from rule-only orchestration to strict LLM-driven planning/policies/synthesis to make the Multi-Agent AI System claim technically accurate.  
**What:**
- Planner/Policy/Synthesis stack now LLM-driven with strict contracts:
  - planner (`llm_planner.py`)
  - action policy (`action_policy.py`)
  - reflexion ranking (`action_reflexion.py`)
  - stop policy (`orchestrator.py`)
  - final narrative (`llm_narrative.py`)
- Narrative contract now enforces sectioned bullet output with plain-language metric explanations.
- `GROQ_API_KEY` required for strict mode in local and deployed runtime.  
**Files:** `agents/lead_agent/task_planner/llm_planner.py`, `agents/lead_agent/action_policy.py`, `reflexion_layer/action_reflexion.py`, `agents/lead_agent/orchestrator.py`, `app/llm_narrative.py`, `app/pipeline.py`, `app/templates/results.html`, `.env.example`  
**Status:** ✅ Done — strict LLM-only orchestration and narrative validated in runtime + tests.

---

## Day-by-Day Schedule

| Day | Tasks |
|---|---|
| **Thu Apr 17** | P1 (spinner) + P5 (GDELT filter) + P7 (conflict UI) |
| **Fri Apr 18** | P2 (new entities: Alphabet + JPMorgan) |
| **Sat Apr 19** | P3 (auto entity resolution) — Part 1: SEC resolver |
| **Sun Apr 20** | P3 (auto entity resolution) — Part 2: wire into pipeline + test |
| **Mon Apr 21** | P6 (filing modifiers) + P9 (graph analysis) + P8 (runbook) |
| **Tue Apr 22** | P4 (evaluation write-up) + full demo rehearsal |
| **Wed Apr 23** | Final presentation |

---

## Final KPI Targets for Presentation

| Metric | Current | Target |
|---|---|---|
| Entities supported | 3 | ✅ 5+ |
| Auto entity resolution | ❌ | ✅ Any public company |
| GDELT signal rate (Tesla) | 53% | ✅ 70%+ |
| Loading UX | ❌ Blocking | ✅ Spinner |
| Graph analysis metrics | ❌ None | ✅ Centrality + clustering |
| Speedup vs manual | ❌ Not documented | ✅ ~3,100x |
| Deployment runbook | ❌ Missing | ✅ `docs/DEPLOYMENT_RUNBOOK.md` |
| LLM component | ❌ None | ✅ Llama 3.1 via Groq (planner + policies + narrative) |
| Tests passing | 214/214 | ✅ 219/219 |
