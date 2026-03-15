# Data Sources

## Integrated (Active)

### SEC EDGAR (US public company governance filings)
- **Endpoint**: `https://data.sec.gov/submissions/CIK{cik}.json`
- **Authentication**: None (free). Requires `SEC_USER_AGENT` header: `"First Last email@asu.edu"`
- **Cache**: `data/raw/sec/CIK{cik}.json`
- **Evidence type**: `sec_filing` | risk categories: `governance`, `network`
- **Confidence**: 0.95 (authoritative government data)
- **Pull script**: `python scripts/pull_sec_submissions.py --cik <CIK>`

### GDELT DOC 2.0 (Global adverse media / news events)
- **Endpoint**: `https://api.gdeltproject.org/api/v2/doc/doc`
- **Authentication**: None (completely free, no API key required)
- **Cache**: `data/raw/gdelt/news_<slug>.json`
- **Evidence type**: `news_article` | risk category: `network`
- **Confidence**: 0.60 (news articles — lower confidence reflects media noise)
- **Pull script**: `python scripts/pull_gdelt_news.py --entity-id <entity_id>`
- **Notes**: Returns news articles mentioning entity name + risk keywords (fraud, investigation, penalty, fine, violation, lawsuit, scandal, misconduct, bribery, corruption, sanction, money laundering, settlement, indictment). Covers global news continuously from 2015-present.

---

## Planned (Stubs — Not Yet Integrated)

### OFAC SDN (US Treasury sanctions list)
- **Source**: `https://www.treasury.gov/ofac/downloads/sdn.xml` (free XML)
- **Status**: Stub in `agents/specialist_agents/legal_agent/sanctions_screener/screener.py`
- **Next step**: Download + cache XML; parse `<sdnEntry>` elements; match aliases

### CourtListener / RECAP (US federal court records)
- **Source**: `https://www.courtlistener.com/api/rest/v3/` (free, 5 req/s)
- **Status**: Stub in `agents/specialist_agents/legal_agent/pacer_fetcher/fetcher.py`
- **Next step**: Query by company name; return docket entries as Evidence

### OpenCorporates (Global corporate registry / beneficial ownership)
- **Source**: `https://api.opencorporates.com/` (free tier available)
- **Status**: Stub in `agents/specialist_agents/corporate_agent/structure_mapper/mapper.py`
- **Next step**: Lookup entity by name; extract officers, parent/subsidiary relationships
