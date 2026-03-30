# China Oncology Clinical Trial Landscape

An analytical tool that pulls public data from ClinicalTrials.gov to map the oncology R&D landscape in China — covering trial volume trends, cancer type distribution, therapeutic modalities, and the competitive dynamics between Chinese biotech and multinational sponsors.

Built as a portfolio project demonstrating biomedical data analysis, ETL design, and analytical storytelling relevant to life science consulting and healthcare intelligence.

---

## What It Does

- Fetches oncology trials with China locations from the ClinicalTrials.gov v2 API
- Classifies each trial by cancer type, therapeutic modality, and sponsor origin (Chinese biotech vs. MNC vs. academic)
- Visualizes pipeline trends, geographic distribution, phase breakdown, and sponsor landscape in an interactive Streamlit dashboard

---

## Key Questions Answered

1. Which cancer types dominate China's oncology pipeline?
2. How has Chinese biotech sponsor activity grown relative to MNCs over time?
3. Which therapeutic modalities (checkpoint inhibitor, ADC, CAR-T, small molecule) are most prevalent?
4. What share of China trials are part of global multinational studies vs. China-only?
5. Which cities and institutions concentrate trial activity?

---

## Setup

```bash
git clone <repo>
cd oncotrial-china
pip install -r requirements.txt
```

---

## Usage

### Step 1: Fetch data from ClinicalTrials.gov
```bash
python src/fetch.py
```
This pulls trials across 20 oncology conditions and filters for those with China locations. Takes ~3–5 minutes. Saves to `data/raw_trials.csv`.

### Step 2: Clean and classify
```bash
python -c "import sys; sys.path.insert(0,'src'); from clean import clean; clean()"
```
Applies cancer type normalization, modality classification, and sponsor origin labeling. Saves to `data/clean_trials.csv`.

### Step 3: Run the dashboard
```bash
streamlit run app.py
```

### Quick demo (no API call needed)
```bash
python generate_sample.py   # generates synthetic data
streamlit run app.py
```

---

## Project Structure

```
oncotrial-china/
├── app.py                  # Streamlit dashboard
├── generate_sample.py      # Synthetic data for demo
├── requirements.txt
├── src/
│   ├── fetch.py            # ClinicalTrials.gov API client + pagination
│   └── clean.py            # Normalization, classification, feature engineering
└── data/
    ├── raw_trials.csv       # Output of fetch.py
    └── clean_trials.csv     # Output of clean.py
```

---

## Data Source

All data from [ClinicalTrials.gov](https://clinicaltrials.gov) via the public REST API v2.  
No authentication required. Data updated daily by the U.S. National Library of Medicine.

---

## Design Decisions

**Why not a database?**  
For analytical purposes, flat CSV + pandas is faster to iterate on than a normalized schema. The classification logic (cancer type, modality, sponsor origin) is inherently fuzzy and benefits from being explicit Python rather than SQL constraints.

**Sponsor origin classification**  
Uses regex pattern matching against known Chinese biotech names, MNC names, and academic keywords. Imperfect but reproducible and auditable — the patterns are fully visible in `clean.py`.

**Cancer type normalization**  
Free-text conditions are mapped to canonical types using a priority-ordered regex table. This handles common synonyms (NSCLC → Lung Cancer, HCC → Liver Cancer) without requiring a full ontology.

---

## Potential Extensions

- Add WHO ICTRP data for trials not registered on ClinicalTrials.gov
- Map sponsor names to parent companies for consolidated MNC view
- Link trial drugs to target/mechanism using a public drug database
- Add China vs. US vs. EU comparison layer
