"""
clean.py
Takes raw_trials.csv, applies classification logic, outputs clean_trials.csv.

Key transformations:
- Normalize cancer type from free-text conditions
- Classify intervention modality (small molecule, biologic, cell therapy, etc.)
- Classify sponsor as Chinese vs MNC vs Academic
- Flag active trials (recruiting or active)
"""

import pandas as pd
import re
from pathlib import Path
from mesh_map import classify_by_mesh, coverage_report
from sponsor_consolidation import apply_consolidation, consolidation_report

# ── Cancer type normalization ──────────────────────────────────────────────
# Maps keywords in 'conditions' text to a canonical cancer type.
# Order matters: more specific patterns first.
CANCER_TYPE_MAP = [
    ("Lung Cancer",         r"lung|nsclc|sclc|non.small.cell|small.cell lung"),
    ("Breast Cancer",       r"breast"),
    ("Gastric Cancer",      r"gastric|stomach"),
    ("Colorectal Cancer",   r"colorect|colon|rectal|rectum"),
    ("Liver Cancer",        r"hepatocell|liver cancer|hcc|hepatoma"),
    ("Leukemia",            r"leukemia|leukemia|aml|cll|cml|all\b"),
    ("Lymphoma",            r"lymphoma|dlbcl|hodgkin|nhl"),
    ("Esophageal Cancer",   r"esophag|oesophag"),
    ("NPC",                 r"nasopharyn"),
    ("Ovarian Cancer",      r"ovarian|ovary"),
    ("Cervical Cancer",     r"cervical|cervix"),
    ("Pancreatic Cancer",   r"pancreatic|pancreas"),
    ("Bladder Cancer",      r"bladder|urothelial"),
    ("Renal Cancer",        r"renal.cell|kidney cancer|rcc\b"),
    ("Prostate Cancer",     r"prostate"),
    ("Thyroid Cancer",      r"thyroid"),
    ("Melanoma",            r"melanoma"),
    ("Brain Tumor",         r"glioma|glioblastoma|gbm|brain tumor|brain cancer"),
    ("Myeloma",             r"myeloma"),
    ("Cholangiocarcinoma",  r"cholangiocarc|bile duct|biliary tract"),
    ("Other Cancer",        r"cancer|carcinoma|tumor|tumour|neoplasm|sarcoma|malignant"),
]

# ── Intervention modality classification ───────────────────────────────────
MODALITY_MAP = [
    ("CAR-T / Cell Therapy",    r"car.t|car t|cell therapy|adoptive|tils?\b|tcr.t"),
    ("Bispecific Antibody",     r"bispecific"),
    ("ADC",                     r"\badc\b|antibody.drug conjugate|drug.conjugate"),
    ("Checkpoint Inhibitor",    r"pd.1|pd.l1|ctla.4|pdl1|nivolumab|pembrolizumab|sintilimab|tislelizumab|camrelizumab|atezolizumab|durvalumab"),
    ("Monoclonal Antibody",     r"mab\b|monoclonal antibody|cetuximab|trastuzumab|bevacizumab|rituximab"),
    ("Small Molecule",          r"inhibitor|kinase|tyrosine|small molecule|gefitinib|erlotinib|osimertinib|imatinib|sunitinib"),
    ("Vaccine / Oncolytic",     r"vaccine|oncolytic|mrna"),
    ("Radiotherapy",            r"radiation|radiotherapy|radio"),
    ("Chemotherapy",            r"chemotherapy|cisplatin|carboplatin|oxaliplatin|paclitaxel|docetaxel|gemcitabine|5.fu|capecitabine"),
    ("Other Biological",        r"biologic|biotherapy|cytokine|interferon|interleukin"),
]

# ── Sponsor origin classification ──────────────────────────────────────────
# Chinese pharma / biotech keywords
CHINESE_SPONSOR_KEYWORDS = [
    r"zymeworks|biontech",  # false positive exceptions — skip this line actually
]

CHINESE_BIOTECH_PATTERNS = r"""
    jiangsu|zhejiang|beijing|shanghai|guangzhou|shenzhen|
    hengrui|junshi|beigene|zymeworks china|innovent|cstone|
    betta|kineta|abbisko|agenus china|alphamab|
    akeso|zan|genscript|sino biopharmaceutical|
    luye|shandong|chengdu|wuhan|nanjing|fudan|
    hutchison|cspc|lepu|mindray|siemens china|
    chia tai tianqing|hisun|yida|simcere|
    qilu|huadong|sunbio|sunshine|nanjing legend|
    legend biotech|gracell|harbour biomed|
    mabspace|zai lab|eden biologics|kineta|
    tianjin|sichuan|guangdong|yunnan|hunan|
    taizhou|hangzhou|suzhou|wuxi|xi.an|chongqing
"""

MNC_PATTERNS = r"""
    pfizer|roche|novartis|astrazeneca|bristol.myers|bms\b|merck|
    eli lilly|lilly\b|sanofi|gsk|glaxo|johnson|j&j|janssen|
    abbvie|amgen|gilead|biogen|regeneron|moderna|biontech|
    boehringer|ingelheim|bayer|takeda|eisai|daiichi|otsuka|
    astellas|novo nordisk|shire|alexion|servier|ipsen|
    celgene|incyte|exelixis|blueprint|iovance|athenex|
    medimmune|imclone|genentech|chugai
"""

ACADEMIC_PATTERNS = r"""
    university|hospital|institute|cancer center|
    medical college|school of medicine|clinical trial group|
    cooperative group|alliance|ecog|rtog|swog
"""


def classify_cancer_type_regex(conditions_str: str) -> str:
    """Regex fallback — used only when MeSH lookup fails."""
    if not isinstance(conditions_str, str):
        return "Unknown"
    text = conditions_str.lower()
    for label, pattern in CANCER_TYPE_MAP:
        if re.search(pattern, text, re.IGNORECASE | re.VERBOSE):
            return label
    return "Unknown"


def classify_cancer_type(mesh_ids_str: str, conditions_str: str) -> tuple[str, bool]:
    """
    Returns (cancer_type, mesh_classified).
    Tries MeSH lookup first, falls back to regex on free-text conditions.
    """
    # Step 1: MeSH lookup
    if isinstance(mesh_ids_str, str) and mesh_ids_str.strip():
        ids = [i.strip() for i in mesh_ids_str.split("|") if i.strip()]
        result = classify_by_mesh(ids)
        if result:
            return result, True

    # Step 2: regex fallback on free-text conditions
    return classify_cancer_type_regex(conditions_str), False


def classify_modality(interv_types: str, interv_names: str) -> str:
    combined = f"{interv_types} {interv_names}".lower()
    for label, pattern in MODALITY_MAP:
        if re.search(pattern, combined, re.IGNORECASE | re.VERBOSE):
            return label
    # Fall back to raw intervention type
    if "DRUG" in str(interv_types).upper():
        return "Drug (Unclassified)"
    if "BIOLOGICAL" in str(interv_types).upper():
        return "Biological (Unclassified)"
    if "PROCEDURE" in str(interv_types).upper():
        return "Procedure"
    return "Other"


def classify_sponsor_origin(sponsor_name: str, sponsor_class: str) -> str:
    if not isinstance(sponsor_name, str):
        return "Unknown"
    name_lower = sponsor_name.lower()

    if re.search(MNC_PATTERNS, name_lower, re.IGNORECASE | re.VERBOSE):
        return "MNC"

    if re.search(CHINESE_BIOTECH_PATTERNS, name_lower, re.IGNORECASE | re.VERBOSE):
        return "Chinese Biotech/Pharma"

    if re.search(ACADEMIC_PATTERNS, name_lower, re.IGNORECASE | re.VERBOSE):
        return "Academic/Hospital"

    if sponsor_class == "INDUSTRY":
        return "Other Industry"

    return "Other / Unknown"


def clean(input_path: str = "data/raw_trials.csv",
          output_path: str = "data/clean_trials.csv") -> pd.DataFrame:

    df = pd.read_csv(input_path)
    print(f"Loaded {len(df)} trials")

    # Drop rows with no NCT ID or status
    df = df.dropna(subset=["nct_id", "status"])

    # Normalize cancer type — MeSH first, regex fallback
    mesh_col = df["mesh_ids"] if "mesh_ids" in df.columns else pd.Series([""] * len(df))
    results = [
        classify_cancer_type(m, c)
        for m, c in zip(mesh_col, df["conditions"])
    ]
    df["cancer_type"] = [r[0] for r in results]
    df["mesh_classified"] = [r[1] for r in results]

    # Classify modality
    df["modality"] = df.apply(
        lambda r: classify_modality(
            r.get("intervention_types", ""),
            r.get("intervention_names", "")
        ), axis=1
    )

    # Classify sponsor origin
    df["sponsor_origin"] = df.apply(
        lambda r: classify_sponsor_origin(
            r.get("sponsor_name", ""),
            r.get("sponsor_class", "")
        ), axis=1
    )

    # Active flag
    active_statuses = {"RECRUITING", "ACTIVE_NOT_RECRUITING", "NOT_YET_RECRUITING"}
    df["is_active"] = df["status"].isin(active_statuses)

    # Start year as int
    df["start_year"] = pd.to_numeric(df["start_year"], errors="coerce")

    # Phase normalization
    df["phase_clean"] = df["phase"].apply(normalize_phase)

    print(f"Cleaned: {len(df)} trials")
    print(f"Cancer types: {df['cancer_type'].value_counts().head(10).to_dict()}")
    print(f"Sponsor origin: {df['sponsor_origin'].value_counts().to_dict()}")

    df.to_csv(output_path, index=False)
    # Sponsor consolidation
    df = apply_consolidation(df)
    consolidation_report(df)

    print(f"Saved to {output_path}")
    coverage_report(df)
    return df


def normalize_phase(phase_str: str) -> str:
    if not isinstance(phase_str, str):
        return "Unknown"
    if "PHASE3" in phase_str or "PHASE_3" in phase_str:
        if "PHASE2" in phase_str:
            return "Phase 2/3"
        return "Phase 3"
    if "PHASE2" in phase_str or "PHASE_2" in phase_str:
        if "PHASE1" in phase_str:
            return "Phase 1/2"
        return "Phase 2"
    if "PHASE1" in phase_str or "PHASE_1" in phase_str:
        return "Phase 1"
    if "PHASE4" in phase_str or "PHASE_4" in phase_str:
        return "Phase 4"
    if "NA" in phase_str or phase_str == "N/A":
        return "N/A"
    return "Unknown"


if __name__ == "__main__":
    clean()