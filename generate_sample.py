"""
generate_sample.py
Creates a realistic sample dataset so you can test the dashboard
before running the full API fetch.
Run: python generate_sample.py
"""

import pandas as pd
import numpy as np
from pathlib import Path

np.random.seed(42)
N = 800

cancer_types = [
    "Lung Cancer", "Breast Cancer", "Gastric Cancer", "Colorectal Cancer",
    "Liver Cancer", "Leukemia", "Lymphoma", "Esophageal Cancer",
    "NPC", "Ovarian Cancer", "Pancreatic Cancer", "Myeloma",
    "Bladder Cancer", "Renal Cancer", "Cholangiocarcinoma",
]
cancer_weights_raw = [0.22, 0.14, 0.10, 0.09, 0.08, 0.06, 0.05, 0.04,
                  0.04, 0.03, 0.03, 0.03, 0.03, 0.02, 0.02]
cancer_weights = [w/sum(cancer_weights_raw) for w in cancer_weights_raw]

phases = ["Phase 1", "Phase 1/2", "Phase 2", "Phase 2/3", "Phase 3", "Phase 4", "N/A"]
phase_weights = [0.20, 0.15, 0.28, 0.10, 0.18, 0.04, 0.05]

modalities = [
    "Checkpoint Inhibitor", "Small Molecule", "Monoclonal Antibody",
    "CAR-T / Cell Therapy", "ADC", "Chemotherapy", "Bispecific Antibody",
    "Vaccine / Oncolytic", "Other Biological", "Drug (Unclassified)",
]
modality_weights = [0.22, 0.20, 0.15, 0.10, 0.10, 0.08, 0.06, 0.03, 0.04, 0.02]

sponsor_origins = ["Chinese Biotech/Pharma", "MNC", "Academic/Hospital", "Other Industry"]
sponsor_origin_weights = [0.48, 0.28, 0.18, 0.06]

chinese_sponsors = [
    "BeiGene", "Innovent Biologics", "Junshi Biosciences", "Hengrui Medicine",
    "Zai Lab", "CStone Pharmaceuticals", "Akeso Biotech", "Legend Biotech",
    "Gracell Biotechnologies", "Alphamab Oncology", "Abbisko Therapeutics",
    "Nanjing Legend Biotech", "Sino Biopharmaceutical", "CSPC Pharmaceutical",
    "Jiangsu Hengrui",
]
mnc_sponsors = [
    "AstraZeneca", "Roche", "Bristol-Myers Squibb", "Merck Sharp & Dohme",
    "Pfizer", "Novartis", "Eli Lilly", "Johnson & Johnson", "Sanofi",
    "Boehringer Ingelheim",
]
academic_sponsors = [
    "Fudan University", "Peking University Cancer Hospital",
    "Sun Yat-sen University Cancer Center", "Chinese Academy of Medical Sciences",
    "Zhongshan Hospital", "West China Hospital",
]

cities = [
    "Beijing", "Shanghai", "Guangzhou", "Chengdu", "Wuhan", "Nanjing",
    "Hangzhou", "Xi'an", "Shenzhen", "Tianjin", "Chongqing", "Suzhou",
]
city_weights = [0.18, 0.20, 0.10, 0.07, 0.08, 0.07, 0.07, 0.05, 0.06, 0.05, 0.04, 0.03]

statuses = ["RECRUITING", "ACTIVE_NOT_RECRUITING", "COMPLETED", "NOT_YET_RECRUITING", "TERMINATED"]
status_weights = [0.30, 0.15, 0.40, 0.10, 0.05]

start_years = list(range(2010, 2026))
# Weight more recent years more heavily
year_weights = [0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.07, 0.08,
                0.08, 0.09, 0.09, 0.10, 0.08, 0.08, 0.07, 0.09]
year_weights = [w/sum(year_weights) for w in year_weights]

rows = []
for i in range(N):
    origin = np.random.choice(sponsor_origins, p=sponsor_origin_weights)
    if origin == "Chinese Biotech/Pharma":
        sponsor = np.random.choice(chinese_sponsors)
    elif origin == "MNC":
        sponsor = np.random.choice(mnc_sponsors)
    elif origin == "Academic/Hospital":
        sponsor = np.random.choice(academic_sponsors)
    else:
        sponsor = "Other Pharma Co."

    cancer = np.random.choice(cancer_types, p=cancer_weights)
    year = np.random.choice(start_years, p=year_weights)
    status = np.random.choice(statuses, p=status_weights)
    n_cities = np.random.choice([1, 2, 3, 4], p=[0.4, 0.3, 0.2, 0.1])
    selected_cities = "|".join(np.random.choice(cities, size=n_cities, replace=False,
                                                 p=city_weights).tolist())


    # Region assignment — weighted to reflect real landscape
    # China: all trials (this is China-focused), US: ~60%, EU: ~45%
    # MNCs more likely to be in all regions; Chinese biotech mostly China-only
    in_china = True
    in_us    = bool(np.random.random() < (0.65 if origin == "MNC" else 0.20))
    in_eu    = bool(np.random.random() < (0.50 if origin == "MNC" else 0.10))
    region_list = ["China"]
    if in_us: region_list.append("US")
    if in_eu: region_list.append("EU")
    regions_str = "|".join(sorted(region_list))

    rows.append({
        "nct_id": f"NCT{10000000 + i}",
        "title": f"A Study of {cancer} Treatment",
        "status": status,
        "phase": np.random.choice(phases, p=phase_weights),
        "phase_clean": np.random.choice(phases, p=phase_weights),
        "study_type": "INTERVENTIONAL",
        "conditions": cancer.lower(),
        "cancer_type": cancer,
        "intervention_types": "DRUG",
        "intervention_names": "sample drug",
        "modality": np.random.choice(modalities, p=modality_weights),
        "sponsor_name": sponsor,
        "sponsor_class": "INDUSTRY" if origin in ["Chinese Biotech/Pharma", "MNC"] else "OTHER",
        "sponsor_origin": origin,
        "china_cities": selected_cities,
        "is_multinational": in_us or in_eu,
        "in_china": in_china,
        "in_us": in_us,
        "in_eu": in_eu,
        "regions": regions_str,
        "start_date": f"{year}-01-01",
        "start_year": year,
        "primary_completion_date": f"{year + 3}-01-01",
        "enrollment": int(np.random.lognormal(5, 1)),
        "is_active": status in ["RECRUITING", "ACTIVE_NOT_RECRUITING", "NOT_YET_RECRUITING"],
    })

df = pd.DataFrame(rows)
Path("data").mkdir(exist_ok=True)
df.to_csv("data/clean_trials.csv", index=False)
print(f"Generated {len(df)} sample trials → data/clean_trials.csv")
print(df["cancer_type"].value_counts().head(5))