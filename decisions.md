# Design Decisions — OncoTrial China Landscape

A running log of design choices, rationale, and tradeoffs made during development.
Update status to `revised` or `dropped` rather than deleting — the record of what you tried is useful.

---

## Decision 1 — Drop the API/database layer entirely

**Area:** Scope  
**Date:** 2025-03-01  
**Status:** kept

**Decision:** Build as a pure analytics project (Streamlit + pandas) rather than a PostgreSQL-backed REST API.

**Rationale:** Target audience is life science consulting, not data engineering. A polished analytical deliverable maps better to what consulting interviewers value than a normalized schema and API routes.

**Alternatives considered:** Full PostgreSQL + FastAPI stack with normalized tables for studies, conditions, interventions, sponsors, locations.

**Tradeoff / risk:** Loses "backend engineering" signal — acceptable given the target role. If pivoting toward digital health or health tech startups, revisit.

---

## Decision 2 — Use ClinicalTrials.gov MeSH annotations instead of calling the NLM MeSH API

**Area:** Classification  
**Date:** 2025-03-15  
**Status:** kept

**Decision:** Pull `derivedSection.conditionBrowseModule.meshes` from CT.gov directly rather than hitting the NLM MeSH API separately.

**Rationale:** CT.gov pre-annotates every trial with MeSH terms. Fetching them from the same API response gives structured IDs with zero additional API calls, no auth, and lower latency.

**Alternatives considered:** Call NLM MeSH API per trial; rely on regex-only matching against free-text condition strings.

**Tradeoff / risk:** Coverage is ~80–90%. Regex fallback still needed for trials without MeSH annotation. The `mesh_classified` boolean column tracks which method was used.

---

## Decision 3 — Store cancer type normalization as a priority-ordered regex table in `clean.py`

**Area:** Classification  
**Date:** 2025-03-10  
**Status:** kept

**Decision:** Regex lookup table in Python rather than a third-party ontology library or database constraint.

**Rationale:** Transparent and auditable — patterns are visible and editable without touching a database or installing NLP dependencies. Easy to extend when real data reveals gaps.

**Alternatives considered:** Full MeSH ontology traversal; MetaMap NLP pipeline; manual CSV lookup table.

**Tradeoff / risk:** Regex is brittle on novel synonyms. Mitigated by MeSH lookup running first; regex only fires as fallback.

---

## Decision 4 — Fetch three regional pools (China, US, EU) and tag globally rather than fetching all trials

**Area:** API / Fetch  
**Date:** 2025-03-22  
**Status:** kept

**Decision:** Run targeted fetches for China, US, and EU country sets. Deduplicate globally. Tag each trial with boolean `in_china`, `in_us`, `in_eu` flags.

**Rationale:** Fetching globally without a location filter would produce ~10× more rows with no gain for the comparison question. Targeted fetches keep the dataset manageable while still supporting China vs. US vs. EU analysis.

**Alternatives considered:** Fetch globally (no location filter), tag everything client-side by looping location arrays.

**Tradeoff / risk:** EU fetch loops 17 countries × 20 conditions — roughly 3× slower than the original China-only run. Can narrow to DE/FR/IT/ES if speed is a problem (covers ~70% of EU trial activity).

---

## Decision 5 — Use Streamlit over a React frontend

**Area:** Dashboard / UI  
**Date:** 2025-03-01  
**Status:** kept

**Decision:** Streamlit for the dashboard, not a React/Next.js app.

**Rationale:** Streamlit lets a Python-first analyst build a credible interactive dashboard without context-switching into JavaScript. The audience (consulting interviewers, not engineering hiring managers) won't penalize the tech choice.

**Alternatives considered:** React + Recharts; Dash by Plotly; static HTML export.

**Tradeoff / risk:** Streamlit apps aren't trivially deployable to production. For a portfolio piece this is fine — Streamlit Cloud handles free hosting.

---

<!-- TEMPLATE — copy and fill in for new decisions

## Decision N — [short title]

**Area:** Data / ETL | Classification | API / Fetch | Dashboard / UI | Schema / Data model | Scope | Other  
**Date:** YYYY-MM-DD  
**Status:** kept | revised | dropped

**Decision:** [one sentence]

**Rationale:** [why]

**Alternatives considered:** [what else was on the table]

**Tradeoff / risk:** [what you're accepting by making this choice]

---
-->