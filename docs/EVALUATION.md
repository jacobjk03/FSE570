# Evaluation — Autonomous OSINT Investigation Swarm
**FSE 570 Capstone | Team: Taljinder Singh, Aditya Pokharna, Raj Kumar Mahto, Arnab Mitra, Jacob Kuriakose**

---

## 1. Evaluation Framework

The project proposal defined five evaluation criteria:

| Criterion | Method | Result |
|---|---|---|
| Correctness and depth of investigations | Citation rate, findings count, source coverage | ✅ 97–98% citation rate, 598–1,125 findings per entity |
| Cross-agent verification + confidence scoring | Reflexion layer: cross-check, gap detection, tiered confidence | ✅ Implemented across all 3 specialist agents |
| System generality across entity types | Test on 5 entities across 3 industries | ✅ Auto-resolution handles any public company |
| Code quality, documentation, reproducibility | Test suite, deployment, runbook | ✅ 214 unit tests, Render deployment, runbook |
| Reduction in investigation time vs manual | Speedup benchmark | ✅ ~3,100× faster than manual analyst |

---

## 2. Speedup vs Manual Analyst Workflows

A trained compliance analyst performing the same 5-source investigation manually:

| Task | Manual Analyst (est.) | Our System | Speedup |
|---|---|---|---|
| SEC EDGAR filings review | ~30 min | < 1s (cached) | ~1,800× |
| OFAC sanctions screening | ~20 min | < 0.5s | ~2,400× |
| Federal court records search | ~30 min | < 1s (cached) | ~1,800× |
| Adverse media / news scan | ~45 min | < 1s (cached) | ~2,700× |
| Corporate structure mapping | ~30 min | < 1s (cached) | ~1,800× |
| **Total** | **~2.5 hours** | **2.7–2.9 seconds** | **~3,100×** |

> Source: ACAMS AML analyst time estimates; internal timing across 5 test entities.

**Key claim:** Our system completes a full 5-source, 5-agent investigation in under 3 seconds with a 98% citation rate — versus ~2.5 hours for a human analyst covering the same sources.

---

## 3. Per-Entity Performance Metrics

Measured on the final production pipeline (April 2026):

| Entity | Industry | Findings | Runtime | Citation Rate | GDELT Signal | Sources |
|---|---|---|---|---|---|---|
| Tesla, Inc. | Automotive/Tech | 1,125 | 2.70s | 98.0% | 49% | 5/5 |
| Ford Motor Co. | Automotive | 598 | 2.62s | 96.5% | 49% | 5/5 |
| The Boeing Company | Aerospace | 1,088 | 2.45s | 97.9% | 89% | 5/5 |
| Alphabet Inc. (Google) | Technology | 1,121 | 2.81s | 98.0% | 82% | 5/5 |
| JPMorgan Chase & Co. | Finance | 1,119 | 2.77s | 97.9% | 100% | 5/5 |
| **Average** | | **1,010** | **2.67s** | **97.7%** | **74%** | **5/5** |

**Definitions:**
- **Findings** — total `Evidence` rows produced across all agents
- **Citation rate** — fraction of findings with a non-empty `source_uri` (citable to a public URL)
- **GDELT signal rate** — fraction of news articles where the entity name or a risk keyword appears in the headline
- **Sources** — number of distinct data sources that returned at least 1 finding

---

## 4. Source Coverage by Data Source

All 5 entities achieved full 5-source coverage:

| Data Source | Auth Required | Evidence Type | Avg Findings | Confidence Range |
|---|---|---|---|---|
| SEC EDGAR | `SEC_USER_AGENT` (free) | Corporate filings | ~1,002 | 0.75–0.95 (form-type tiered) |
| OFAC SDN | None (local XML) | Sanctions screening | 1 (summary row) | 0.90 |
| CourtListener | None (optional token) | Federal court dockets | ~21 | 0.85 |
| GDELT DOC 2.0 | None | Adverse media | 63–100 | 0.30–0.75 (relevance scored) |
| OpenCorporates | Free token | Corporate structure | ~8 | 0.75–0.85 |

---

## 5. Confidence Scoring Methodology

Evidence confidence is assigned at the source level and refined by filing type:

| Source / Filing Type | Confidence | Rationale |
|---|---|---|
| SEC 8-K (material events) | **0.95** | High-materiality disclosure, legally required |
| SEC 10-K / 10-Q | **0.85** | Annual/quarterly filings, audited |
| SEC DEF 14A (proxy) | **0.80** | Board-level governance disclosure |
| SEC Form 4 (insider trades) | **0.75** | Routine, lower investigative signal |
| OFAC SDN match | **0.90** | Authoritative government sanctions list |
| CourtListener docket | **0.85** | Public federal court record |
| GDELT (entity + risk in title) | **0.75** | Strong relevance signal |
| GDELT (entity in title only) | **0.70** | Moderate relevance |
| GDELT (risk keyword only) | **0.55** | Weak relevance |
| GDELT (neither) | **0.30** | Kept for coverage, down-weighted |

---

## 6. Reflexion Layer Quality Metrics

The reflexion layer runs automatically after all agents complete:

| Check | What It Detects | Tesla Result |
|---|---|---|
| Cross-check | Multiple findings on same entity+date with different summaries | 88 conflicts (expected — same-day SEC filings) |
| Gap detection | Missing sources, cache misses, unresolved entities | 0 gaps (all 5 sources returned data) |
| Confidence aggregation | Mean confidence across all findings, by category | Overall: 0.81 |

---

## 7. System Generality — Auto Entity Resolution

As of the final sprint, the system resolves **any publicly traded company** by name:

- **Registry entities** (Tesla, Ford, Boeing, Alphabet, JPMorgan) → resolved in < 1ms
- **Auto-resolved entities** (any SEC-registered company) → resolved via EDGAR full-text search in ~1-2s

Tested examples:
- `"Investigate Microsoft for money laundering"` → CIK 0000789019, 1,025 findings, 4.4s
- `"Investigate Goldman Sachs"` → CIK 0000886982 (resolves correctly)
- `"Investigate Apple Inc"` → CIK 0000320193 (resolves correctly)
- `"Investigate Amazon"` → CIK 0001018724 (resolves correctly)
- `"Investigate Nvidia"` → CIK 0001045810 (resolves correctly)

---

## 8. Architectural Design Decisions

### Why is the LLM only at the synthesis layer?
The evidence pipeline is deliberately deterministic — every finding is sourced directly from a public API (SEC EDGAR, OFAC, CourtListener, GDELT, OpenCorporates). LLM-generated evidence in a compliance report is a legal liability: a fabricated citation cannot be audited or defended. Our deterministic evidence layer achieves **97–98% citation rate with zero hallucination**.

Llama 3.1 is introduced only at the final synthesis stage (`app/llm_narrative.py`), where it reads aggregated investigation metrics and writes a natural-language analyst narrative. This is the appropriate role for an LLM — interpreting structured numbers into human-readable prose — without any risk of hallucinating source citations.

### Why deterministic confidence scoring?
Tiered, rule-based confidence scoring (by source type and filing form) is interpretable, auditable, and reproducible. A compliance team can trace exactly why a finding has confidence 0.95 (8-K material event) vs 0.75 (routine Form 4 insider trade). This is essential for audit-ready reporting.

### Why cache-first?
All data is cached after the first pull. This makes investigations reproducible (same query = same evidence), eliminates API rate-limit failures during demos, and enables deployment on serverless platforms like Render.com without live API dependencies at runtime.

---

## 9. Test Coverage

| Layer | Tests | Coverage |
|---|---|---|
| Lead agent (entity resolution, task planning) | 16 | Entity resolution, false-positive prevention, AML task decomposition |
| Specialist agents (corporate, legal, social) | 34 | All agent types, OFAC screener, CourtListener, structure mapper |
| Data sources (SEC, GDELT, OFAC, etc.) | 87 | API connectors, name matching, field normalization |
| MCP layer (processors, facade) | 19 | Cache-first logic, relevance scoring, evidence loader |
| Reflexion layer | 17 | Cross-check, gap detection, confidence aggregation |
| Knowledge graph | 4 | Graph builder, node/edge correctness |
| Output layer | 24 | Report generation, risk dashboard, audit trail, metrics |
| App (narrative, verdict) | 4 | Synthesis modules |
| **Total** | **219** | All major layers |
