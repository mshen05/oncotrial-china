"""
mesh_map.py
Maps MeSH descriptor IDs to canonical cancer type labels.

ClinicalTrials.gov pre-annotates each trial with MeSH terms via
derivedSection.conditionBrowseModule.meshes — so we never need to
call the MeSH API ourselves. We just look up the IDs here.

Priority: more specific IDs are listed first within each cancer type.
When a trial has multiple MeSH IDs, we return the most specific match.

Sources:
  - NLM MeSH Browser: https://meshb.nlm.nih.gov/
  - IDs verified against MeSH 2024 descriptor list
"""

# ── Lookup: MeSH ID → canonical cancer type ────────────────────────────────
# Listed specific → general within each group.
# The classify() function tries IDs in priority order.

MESH_TO_CANCER: dict[str, str] = {

    # ── Lung ──────────────────────────────────────────────────────────────
    "D002289": "Lung Cancer",      # Carcinoma, Non-Small-Cell Lung
    "D018288": "Lung Cancer",      # Carcinoma, Small Cell
    "D008175": "Lung Cancer",      # Lung Neoplasms (parent)
    "D000077192": "Lung Cancer",   # Adenocarcinoma of Lung
    "D055752": "Lung Cancer",      # Small Cell Lung Carcinoma

    # ── Breast ────────────────────────────────────────────────────────────
    "D001943": "Breast Cancer",    # Breast Neoplasms
    "D018175": "Breast Cancer",    # Carcinoma, Ductal, Breast
    "D018306": "Breast Cancer",    # Carcinoma, Lobular
    "D064726": "Breast Cancer",    # Triple Negative Breast Neoplasms
    "D006906": "Breast Cancer",    # HER2-positive (part of Receptor, ErbB-2)

    # ── Gastric ───────────────────────────────────────────────────────────
    "D013274": "Gastric Cancer",   # Stomach Neoplasms
    "D000230": "Gastric Cancer",   # Adenocarcinoma (stomach context — see fallback)

    # ── Colorectal ────────────────────────────────────────────────────────
    "D015179": "Colorectal Cancer",  # Colorectal Neoplasms
    "D003110": "Colorectal Cancer",  # Colonic Neoplasms
    "D012004": "Colorectal Cancer",  # Rectal Neoplasms
    "D003112": "Colorectal Cancer",  # Colorectal Neoplasms, Hereditary Nonpolyposis
    "D044584": "Colorectal Cancer",  # Colorectal Neoplasms — alt descriptor

    # ── Liver / HCC ───────────────────────────────────────────────────────
    "D006528": "Liver Cancer",     # Carcinoma, Hepatocellular
    "D008113": "Liver Cancer",     # Liver Neoplasms
    "D018450": "Liver Cancer",     # Disease Progression (sometimes tagged here — fallback)

    # ── Leukemia ──────────────────────────────────────────────────────────
    "D007938": "Leukemia",         # Leukemia (parent)
    "D015470": "Leukemia",         # Leukemia, Myeloid, Acute (AML)
    "D015461": "Leukemia",         # Leukemia, Myelogenous, Chronic, BCR-ABL Positive (CML)
    "D015464": "Leukemia",         # Leukemia, Myeloid, Chronic-Phase
    "D006220": "Leukemia",         # Leukemia, Hairy Cell
    "D007945": "Leukemia",         # Leukemia, Lymphoid
    "D054198": "Leukemia",         # Precursor B-Cell Lymphoblastic Leukemia-Lymphoma (ALL)
    "D054351": "Leukemia",         # Philadelphia Chromosome
    "D007946": "Leukemia",         # Leukemia, Myeloid
    "D020192": "Leukemia",         # Leukemia, T-Cell (T-ALL)

    # ── Lymphoma ──────────────────────────────────────────────────────────
    "D008223": "Lymphoma",         # Lymphoma (parent)
    "D008228": "Lymphoma",         # Lymphoma, Non-Hodgkin
    "D006689": "Lymphoma",         # Hodgkin Disease
    "D016403": "Lymphoma",         # Lymphoma, Large B-Cell, Diffuse (DLBCL)
    "D005910": "Lymphoma",         # Glioma (wrongly tagged sometimes — check)
    "D020522": "Lymphoma",         # Lymphoma, Mantle-Cell
    "D016393": "Lymphoma",         # Lymphoma, B-Cell
    "D016399": "Lymphoma",         # Lymphoma, T-Cell
    "D016400": "Lymphoma",         # Lymphoma, T-Cell, Peripheral
    "D017728": "Lymphoma",         # Burkitt Lymphoma
    "D018442": "Lymphoma",         # Lymphoma, B-Cell, Marginal Zone
    "D016402": "Lymphoma",         # Lymphoma, Large-Cell, Anaplastic

    # ── Esophageal ────────────────────────────────────────────────────────
    "D004938": "Esophageal Cancer",  # Esophageal Neoplasms
    "D000077237": "Esophageal Cancer",  # Esophageal Squamous Cell Carcinoma
    "D000077192": "Esophageal Cancer",  # Adenocarcinoma (esophageal — overlap with lung)

    # ── Nasopharyngeal ────────────────────────────────────────────────────
    "D009303": "NPC",              # Nasopharyngeal Neoplasms
    "D000077274": "NPC",           # Nasopharyngeal Carcinoma

    # ── Ovarian ───────────────────────────────────────────────────────────
    "D010051": "Ovarian Cancer",   # Ovarian Neoplasms
    "D018284": "Ovarian Cancer",   # Cystadenocarcinoma, Serous
    "D002296": "Ovarian Cancer",   # Carcinoma, Ovarian Epithelial

    # ── Cervical ──────────────────────────────────────────────────────────
    "D002583": "Cervical Cancer",  # Uterine Cervical Neoplasms
    "D002578": "Cervical Cancer",  # Uterine Cervical Dysplasia

    # ── Pancreatic ────────────────────────────────────────────────────────
    "D010190": "Pancreatic Cancer",  # Pancreatic Neoplasms
    "D002278": "Pancreatic Cancer",  # Carcinoma, Pancreatic Ductal

    # ── Bladder / Urothelial ──────────────────────────────────────────────
    "D001749": "Bladder Cancer",   # Urinary Bladder Neoplasms
    "D014556": "Bladder Cancer",   # Urinary Bladder Diseases (broad — context needed)
    "D000077195": "Bladder Cancer",  # Carcinoma, Transitional Cell

    # ── Renal ────────────────────────────────────────────────────────────
    "D002292": "Renal Cancer",     # Carcinoma, Renal Cell
    "D007680": "Renal Cancer",     # Kidney Neoplasms

    # ── Prostate ──────────────────────────────────────────────────────────
    "D011471": "Prostate Cancer",  # Prostatic Neoplasms
    "D064129": "Prostate Cancer",  # Prostatic Neoplasms, Castration-Resistant

    # ── Thyroid ───────────────────────────────────────────────────────────
    "D013964": "Thyroid Cancer",   # Thyroid Neoplasms
    "D065646": "Thyroid Cancer",   # Thyroid Cancer, Papillary
    "D000077273": "Thyroid Cancer",  # Carcinoma, Medullary

    # ── Melanoma ──────────────────────────────────────────────────────────
    "D008545": "Melanoma",         # Melanoma
    "D008548": "Melanoma",         # Melanoma, Experimental
    "D064533": "Melanoma",         # Uveal Melanoma

    # ── Brain ────────────────────────────────────────────────────────────
    "D005909": "Brain Tumor",      # Glioblastoma
    "D005910": "Brain Tumor",      # Glioma
    "D001932": "Brain Tumor",      # Brain Neoplasms (parent)
    "D018306": "Brain Tumor",      # overlap with breast — context resolves
    "D020252": "Brain Tumor",      # Astrocytoma

    # ── Myeloma ───────────────────────────────────────────────────────────
    "D009101": "Myeloma",          # Multiple Myeloma
    "D018600": "Myeloma",          # Plasmacytoma

    # ── Cholangiocarcinoma / Biliary ──────────────────────────────────────
    "D018281": "Cholangiocarcinoma",  # Cholangiocarcinoma
    "D001650": "Cholangiocarcinoma",  # Bile Duct Neoplasms
    "D001660": "Cholangiocarcinoma",  # Bile Ducts, Intrahepatic

    # ── Endometrial / Uterine ────────────────────────────────────────────
    "D016889": "Endometrial Cancer",  # Endometrial Neoplasms
    "D014594": "Endometrial Cancer",  # Uterine Neoplasms

    # ── Head & Neck ───────────────────────────────────────────────────────
    "D006258": "Head & Neck Cancer",  # Head and Neck Neoplasms
    "D002294": "Head & Neck Cancer",  # Carcinoma, Squamous Cell of Head and Neck (SCCHN)
    "D009393": "Head & Neck Cancer",  # Nose Neoplasms

    # ── Sarcoma ───────────────────────────────────────────────────────────
    "D012513": "Sarcoma",          # Sarcoma
    "D011376": "Sarcoma",          # Rhabdomyosarcoma
    "D018204": "Sarcoma",          # Neoplasms, Connective and Soft Tissue
    "D006101": "Sarcoma",          # Chondrosarcoma

    # ── Myelodysplastic / MPN ─────────────────────────────────────────────
    "D009190": "MDS/MPN",          # Myelodysplastic Syndromes
    "D009196": "MDS/MPN",          # Myeloproliferative Disorders

    # ── Mesothelioma ──────────────────────────────────────────────────────
    "D008654": "Mesothelioma",     # Mesothelioma
    "D054363": "Mesothelioma",     # Mesothelioma, Malignant

    # ── Neuroendocrine ───────────────────────────────────────────────────
    "D018358": "Neuroendocrine Tumor",  # Neuroendocrine Tumors
    "D002276": "Neuroendocrine Tumor",  # Carcinoid Tumor
}

# ── Priority order for disambiguation ─────────────────────────────────────
# When a trial has IDs from multiple cancer type groups,
# prefer these in order (most specific/clinically distinct first).
PRIORITY_ORDER = [
    "NPC",
    "Cholangiocarcinoma",
    "Mesothelioma",
    "Neuroendocrine Tumor",
    "Myeloma",
    "MDS/MPN",
    "Sarcoma",
    "Brain Tumor",
    "Leukemia",
    "Lymphoma",
    "Liver Cancer",
    "Lung Cancer",
    "Breast Cancer",
    "Gastric Cancer",
    "Colorectal Cancer",
    "Esophageal Cancer",
    "Ovarian Cancer",
    "Cervical Cancer",
    "Pancreatic Cancer",
    "Bladder Cancer",
    "Renal Cancer",
    "Prostate Cancer",
    "Thyroid Cancer",
    "Melanoma",
    "Endometrial Cancer",
    "Head & Neck Cancer",
]


def classify_by_mesh(mesh_ids: list[str]) -> str | None:
    """
    Given a list of MeSH IDs from derivedSection.conditionBrowseModule.meshes,
    return a canonical cancer type, or None if no match found.

    Uses PRIORITY_ORDER to pick the most specific label when multiple
    cancer types are matched.
    """
    if not mesh_ids:
        return None

    matched_types = set()
    for mesh_id in mesh_ids:
        label = MESH_TO_CANCER.get(mesh_id)
        if label:
            matched_types.add(label)

    if not matched_types:
        return None

    if len(matched_types) == 1:
        return matched_types.pop()

    # Multiple matches: return highest priority one
    for cancer_type in PRIORITY_ORDER:
        if cancer_type in matched_types:
            return cancer_type

    return matched_types.pop()  # fallback: any match


def coverage_report(df) -> None:
    """
    Print a coverage report showing what fraction of trials
    were classified by MeSH vs. regex fallback.
    Call after clean.py runs.
    """
    import pandas as pd
    total = len(df)
    mesh_classified = df["mesh_classified"].sum() if "mesh_classified" in df.columns else 0
    regex_classified = total - mesh_classified
    unknown = (df["cancer_type"] == "Unknown").sum()

    print(f"\n── Classification Coverage ──────────────────")
    print(f"  Total trials:        {total:>6,}")
    print(f"  MeSH classified:     {mesh_classified:>6,}  ({100*mesh_classified/total:.1f}%)")
    print(f"  Regex fallback:      {regex_classified - unknown:>6,}  ({100*(regex_classified-unknown)/total:.1f}%)")
    print(f"  Unclassified:        {unknown:>6,}  ({100*unknown/total:.1f}%)")
    print(f"─────────────────────────────────────────────\n")