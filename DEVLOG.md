# Dev Log — China Oncology Trial Landscape

A record of what was built, why decisions were made, and how to operate this project going forward.

---

## Project Overview

A Streamlit dashboard that pulls public oncology clinical trial data from ClinicalTrials.gov, classifies and cleans it, stores it in a Supabase PostgreSQL database, and visualizes the China oncology R&D landscape with comparisons to the US and EU.

**Live app:** [your-app-url.streamlit.app]  
**Data source:** ClinicalTrials.gov public API v2  
**Database:** Supabase (PostgreSQL)  
**Last full ETL run:** April 2026

---

## How to Update the Database

Do this whenever you want fresh data (e.g. monthly, or before showing the project).

### Prerequisites
- Python 3.11+
- Dependencies installed: `pip install -r requirements.txt`
- `DATABASE_URL` set to the Supabase **session pooler** connection string

### Step 1 — Set your database URL

```bash
export DATABASE_URL="postgresql://postgres.YOUR-REF:YOUR-PASSWORD@aws-0-YOUR-REGION.pooler.supabase.com:5432/postgres"
```

Use the **Session pooler** URL from Supabase → Project Settings → Database → Connection string.  
Do NOT use the Direct connection URL — it uses IPv6 and fails from most laptops and cloud hosts.

### Step 2 — Fetch from ClinicalTrials.gov

```bash
python3 src/fetch.py
```

- Queries 20 oncology conditions across China, US, and EU regions
- Deduplicates by NCT ID across regions
- Saves to `data/raw_trials.csv`
- Takes ~15–25 minutes (rate-limited to be polite to the API)
- Expect ~50,000 trials total

### Step 3 — Clean, classify, and push to database

```bash
python3 src/clean.py
```

This does everything in one command:
- Loads `data/raw_trials.csv`
- Classifies cancer type (MeSH lookup first, regex fallback)
- Classifies therapeutic modality
- Classifies sponsor origin (Chinese biotech / MNC / Academic)
- Consolidates sponsor name variants to parent companies
- Saves `data/clean_trials.csv`
- Upserts all rows to Supabase in 5,000-row chunks

Takes ~2–3 minutes. Progress prints as `Chunk 0–5,000 / 50,807` etc.

### Step 4 — Verify

```bash
python3 -c "
import sys; sys.path.insert(0,'src')
from db import get_engine, trial_count, last_updated
e = get_engine()
print(f'Rows in DB: {trial_count(e):,}')
print(f'Last updated: {last_updated(e)}')
"
```

The Streamlit app refreshes its cache every hour (`ttl=3600`), so the dashboard will show new data within 60 minutes of the ETL finishing.

---

## Architecture

```
ClinicalTrials.gov API v2
        │
        ▼
src/fetch.py          — pulls raw trial JSON, filters to China/US/EU, saves CSV
        │
        ▼
data/raw_trials.csv   — 50k rows, not committed to git
        │
        ▼
src/clean.py          — classification pipeline
  ├── src/mesh_map.py              — MeSH ID → cancer type (130+ mappings)
  ├── src/clean.py (regex)         — fallback for untagged trials
  ├── src/sponsor_consolidation.py — 200+ name → parent company mappings
  └── src/db.py                   — writes to Supabase
        │
        ▼
Supabase PostgreSQL   — single `trials` table, ~50k rows
        │
        ▼
app.py                — Streamlit dashboard, reads from DB
```

### Why no CSV in the deployed app?

Streamlit Community Cloud does not guarantee persistence of local files — they can be wiped at any time. All data lives in Supabase. The CSV files are local working files only and are gitignored.

### Why Session pooler and not Direct connection?

Streamlit Community Cloud connects via IPv4. Supabase's direct connection URL (`db.*.supabase.co:5432`) resolves to an IPv6 address from Streamlit's infrastructure, which fails with `Cannot assign requested address`. The session pooler URL (`aws-0-*.pooler.supabase.com:5432`) routes over IPv4 and works reliably.

---

## Classification Logic

### Cancer Type

1. **MeSH lookup** (`src/mesh_map.py`): ClinicalTrials.gov pre-annotates every trial with MeSH term IDs in `derivedSection.conditionBrowseModule.meshes`. We map those IDs to canonical cancer type labels. Covers 26 cancer categories, 130+ MeSH IDs.

2. **Regex fallback** (`src/clean.py`, `CANCER_TYPE_MAP`): For trials without MeSH tags, we match on the free-text `conditions` field. Priority-ordered so more specific patterns match first.

**Coverage on real data:** ~82% MeSH, ~15% regex, ~2.5% unclassified.

### Therapeutic Modality

Regex on `intervention_types` + `intervention_names`. Categories: Checkpoint Inhibitor, Small Molecule, ADC, CAR-T/Cell Therapy, Bispecific Antibody, Monoclonal Antibody, Chemotherapy, Vaccine/Oncolytic, Other Biological.

### Sponsor Origin

Regex on `sponsor_name`. Categories:
- **Chinese Biotech/Pharma** — matches known Chinese company names or Chinese geography keywords
- **MNC** — matches known global pharma company names
- **Academic/Hospital** — matches "university", "hospital", "institute", etc.
- **Other** — industry sponsors not matching above

### Sponsor Consolidation

`src/sponsor_consolidation.py` maps subsidiary and variant names to parent companies. Matching: exact first, then longest-substring. Examples: Genentech → Roche, Celgene → Bristol-Myers Squibb, Janssen → Johnson & Johnson, Nanjing Legend Biotech → Legend Biotech.

---

## Database Schema

Single table `trials` in Supabase. Primary key is `nct_id`. Upsert on conflict so re-running the ETL is always safe — existing rows are updated, new rows are inserted.

Key columns:

| Column | Description |
|---|---|
| `nct_id` | Primary key, ClinicalTrials.gov identifier |
| `cancer_type` | Canonical cancer type label |
| `mesh_classified` | Boolean — was MeSH used (vs regex fallback) |
| `phase_clean` | Normalized phase (Phase 1, Phase 2, etc.) |
| `modality` | Therapeutic modality classification |
| `sponsor_name` | Original sponsor name from API |
| `sponsor_parent` | Consolidated parent company name |
| `sponsor_origin` | Chinese Biotech/Pharma / MNC / Academic / Other |
| `in_china` / `in_us` / `in_eu` | Boolean region flags |
| `is_multinational` | True if trial has sites in >1 country |
| `regions` | Pipe-separated region list, e.g. `"China\|US"` |
| `updated_at` | Timestamp of last ETL write |

---

## Key Files

| File | Purpose |
|---|---|
| `app.py` | Streamlit dashboard — two tabs: China Overview, Regional Comparison |
| `src/fetch.py` | ClinicalTrials.gov API client, pagination, region filtering |
| `src/clean.py` | Full classification pipeline, writes CSV + DB |
| `src/db.py` | SQLAlchemy engine, schema, bulk upsert, read helpers |
| `src/mesh_map.py` | MeSH ID → cancer type lookup table |
| `src/sponsor_consolidation.py` | Sponsor name → parent company lookup table |
| `generate_sample.py` | Generates synthetic data for local UI testing without fetching |
| `.streamlit/secrets.toml.example` | Template — copy to `secrets.toml` and fill in DB URL |

---

## Environment Setup (fresh machine)

```bash
git clone https://github.com/YOUR-USERNAME/oncotrial-china
cd oncotrial-china
pip install -r requirements.txt

# For local dev with sample data (no DB needed):
python3 generate_sample.py
streamlit run app.py

# For full ETL against real DB:
export DATABASE_URL="your-session-pooler-url"
python3 src/fetch.py
python3 src/clean.py
streamlit run app.py
```

---

## Streamlit Cloud Deployment

- **Repo:** github.com/YOUR-USERNAME/oncotrial-china
- **Main file:** `app.py`
- **Secrets** (Settings → Secrets):
  ```toml
  [connections.oncotrial]
  url = "postgresql://postgres.YOUR-REF:YOUR-PASSWORD@aws-0-YOUR-REGION.pooler.supabase.com:5432/postgres"
  ```

To redeploy after code changes: push to `main`, Streamlit Cloud auto-deploys.  
To update data only: run the ETL locally, no redeployment needed.

---

## Known Issues / Things to Improve

- **Sponsor classification coverage is ~33%** — about a third of sponsors fall into "Other / Unknown" because they don't match the MNC or Chinese biotech patterns. The regex in `clean.py` (`CHINESE_BIOTECH_PATTERNS`, `MNC_PATTERNS`) can be extended. After a fresh fetch, run `df[df['sponsor_origin']=='Other / Unknown']['sponsor_name'].value_counts().head(30)` to find the biggest gaps.

- **Cancer type regex has some false positives** — the "Other Cancer" catch-all regex is broad. Trials with generic words like "carcinoma" in their condition string can get miscategorized. The MeSH-first approach mostly fixes this for well-annotated trials, but the 2.5% unclassified pool is worth reviewing occasionally.

- **EU fetch is slow** — the EU region loops across 17 countries individually because the API only accepts one location filter at a time. This makes the EU portion take ~2x longer than China or US. Could be parallelized with `concurrent.futures` if fetch time becomes a problem.

- **No scheduled refresh** — data only updates when the ETL is run manually. A GitHub Action with a monthly cron job running the ETL would keep the dashboard current automatically. Not set up yet because it requires storing the DB password as a GitHub secret.

---

## Changelog

### April 2026 — v1.0 Initial Build
- Built full ETL pipeline: fetch → clean → DB
- Streamlit dashboard with China Overview and Regional Comparison tabs
- MeSH-based cancer type classification (82% coverage)
- Sponsor consolidation: 200+ name → parent mappings
- Deployed to Streamlit Community Cloud backed by Supabase

### Connection issues resolved during initial deployment
- First attempt used direct Supabase URL → IPv6 failure on Streamlit Cloud
- Fixed by switching to Session pooler URL
- Staging table bulk upsert added to avoid Supabase 8s statement timeout
- Password URL-encoding added for special characters (`,`, `?`) in password
