"""
sponsor_consolidation.py

Maps sponsor name variants → canonical parent company name.

Design:
- Keys are lowercase stripped strings for fuzzy matching
- Values are canonical display names (title case, as you want them in charts)
- Organized by parent company so it's easy to audit and extend
- apply_consolidation() is the single public function used by clean.py

How matching works (in order):
  1. Exact match on normalized string (lowercase, stripped)
  2. Substring match: if the normalized sponsor name contains a known key
  3. If no match: return original name unchanged

To add a new mapping: find the right parent block and add the variant string.
To add a new parent company: copy an existing block and fill it in.
"""

import pandas as pd

# ── Lookup table ───────────────────────────────────────────────────────────
# Key: lowercase, stripped variant name (or substring to match)
# Value: canonical parent company display name

SPONSOR_MAP: dict[str, str] = {

    # ── Roche ──────────────────────────────────────────────────────────────
    "roche":                              "Roche",
    "f. hoffmann-la roche":              "Roche",
    "f.hoffmann-la roche":               "Roche",
    "hoffmann-la roche":                 "Roche",
    "hoffmann la roche":                 "Roche",
    "f hoffmann":                        "Roche",
    "genentech":                         "Roche",  # wholly owned since 2009
    "chugai":                            "Roche",  # majority-owned subsidiary
    "chugai pharmaceutical":             "Roche",
    "chugai pharma":                     "Roche",
    "chugai biopharmaceuticals":         "Roche",

    # ── AstraZeneca ────────────────────────────────────────────────────────
    "astrazeneca":                        "AstraZeneca",
    "astra zeneca":                       "AstraZeneca",
    "medimmune":                          "AstraZeneca",  # AZ subsidiary
    "medimmune llc":                      "AstraZeneca",
    "medimmune, llc":                     "AstraZeneca",
    "pearl therapeutics":                 "AstraZeneca",
    "alexion":                            "AstraZeneca",  # acquired 2021
    "alexion pharmaceuticals":            "AstraZeneca",

    # ── Bristol-Myers Squibb ───────────────────────────────────────────────
    "bristol-myers squibb":              "Bristol-Myers Squibb",
    "bristol myers squibb":              "Bristol-Myers Squibb",
    "bms":                               "Bristol-Myers Squibb",
    "celgene":                           "Bristol-Myers Squibb",  # acquired 2019
    "celgene corporation":               "Bristol-Myers Squibb",
    "celgene corp":                      "Bristol-Myers Squibb",
    "myriad genetics":                   "Bristol-Myers Squibb",  # oncology dx
    "turning point therapeutics":        "Bristol-Myers Squibb",  # acquired 2022

    # ── Merck (MSD outside US) ─────────────────────────────────────────────
    "merck sharp & dohme":              "Merck (MSD)",
    "merck sharp and dohme":            "Merck (MSD)",
    "merck sharp & dohme llc":          "Merck (MSD)",
    "merck sharp & dohme corp":         "Merck (MSD)",
    "merck & co":                        "Merck (MSD)",
    "merck & co.":                       "Merck (MSD)",
    "merck & co., inc.":                 "Merck (MSD)",
    "msd":                               "Merck (MSD)",
    "msd oncology":                      "Merck (MSD)",
    # Note: Merck KGaA is a separate German company — keep distinct
    "merck kgaa":                        "Merck KGaA",
    "emd serono":                        "Merck KGaA",  # US subsidiary of Merck KGaA
    "emd serono research & development": "Merck KGaA",
    "pfizer merck":                      "Merck KGaA",  # alliance product (bavencio)

    # ── Pfizer ─────────────────────────────────────────────────────────────
    "pfizer":                            "Pfizer",
    "wyeth":                             "Pfizer",   # acquired 2009
    "hospira":                           "Pfizer",   # acquired 2015
    "array biopharma":                   "Pfizer",   # acquired 2019
    "array biopharmaceuticals":          "Pfizer",
    "medivation":                        "Pfizer",   # acquired 2016 (enzalutamide)
    "pfizer inc":                        "Pfizer",
    "pfizer inc.":                       "Pfizer",

    # ── Novartis ───────────────────────────────────────────────────────────
    "novartis":                          "Novartis",
    "novartis pharmaceuticals":          "Novartis",
    "novartis pharma":                   "Novartis",
    "novartis ag":                       "Novartis",
    "sandoz":                            "Novartis",  # generics division
    "advanced accelerator applications": "Novartis",  # acquired 2018 (AAA/177Lu-DOTATATE)
    "aaa":                               "Novartis",

    # ── Johnson & Johnson ──────────────────────────────────────────────────
    "johnson & johnson":                 "Johnson & Johnson",
    "johnson and johnson":               "Johnson & Johnson",
    "j&j":                               "Johnson & Johnson",
    "janssen":                           "Johnson & Johnson",
    "janssen research & development":    "Johnson & Johnson",
    "janssen research and development":  "Johnson & Johnson",
    "janssen-cilag":                     "Johnson & Johnson",
    "janssen cilag":                     "Johnson & Johnson",
    "janssen pharmaceutica":             "Johnson & Johnson",
    "janssen oncology":                  "Johnson & Johnson",
    "janssen biotech":                   "Johnson & Johnson",
    "janssen biotech, inc.":             "Johnson & Johnson",
    "centocor":                          "Johnson & Johnson",

    # ── Eli Lilly ──────────────────────────────────────────────────────────
    "eli lilly":                         "Eli Lilly",
    "lilly":                             "Eli Lilly",
    "eli lilly and company":             "Eli Lilly",
    "loxo oncology":                     "Eli Lilly",  # acquired 2019
    "point biopharma":                   "Eli Lilly",  # acquired 2023

    # ── AbbVie ─────────────────────────────────────────────────────────────
    "abbvie":                            "AbbVie",
    "pharmacyclics":                     "AbbVie",   # acquired 2015 (ibrutinib)
    "pharmacyclics llc":                 "AbbVie",
    "allergan":                          "AbbVie",   # acquired 2020
    "stemcentrx":                        "AbbVie",

    # ── Amgen ──────────────────────────────────────────────────────────────
    "amgen":                             "Amgen",
    "amgen inc":                         "Amgen",
    "amgen inc.":                        "Amgen",
    "onyx pharmaceuticals":              "Amgen",    # acquired 2013 (carfilzomib)
    "five prime therapeutics":           "Amgen",    # acquired 2021

    # ── Sanofi ─────────────────────────────────────────────────────────────
    "sanofi":                            "Sanofi",
    "sanofi-aventis":                    "Sanofi",
    "sanofi aventis":                    "Sanofi",
    "sanofi genzyme":                    "Sanofi",
    "genzyme":                           "Sanofi",   # acquired 2011
    "genzyme corporation":               "Sanofi",
    "regeneron":                         "Sanofi",   # alliance partner, partly owned

    # ── GSK ────────────────────────────────────────────────────────────────
    "gsk":                               "GSK",
    "glaxosmithkline":                   "GSK",
    "glaxo smithkline":                  "GSK",
    "glaxo wellcome":                    "GSK",
    "smithkline beecham":                "GSK",
    "tesaro":                            "GSK",      # acquired 2019 (niraparib)
    "tesaro, inc.":                      "GSK",
    "sierra oncology":                   "GSK",      # acquired 2022

    # ── Boehringer Ingelheim ───────────────────────────────────────────────
    "boehringer ingelheim":              "Boehringer Ingelheim",
    "boehringer ingelheim pharmaceuticals": "Boehringer Ingelheim",
    "boehringer ingelheim international":   "Boehringer Ingelheim",

    # ── Bayer ──────────────────────────────────────────────────────────────
    "bayer":                             "Bayer",
    "bayer ag":                          "Bayer",
    "bayer healthcare":                  "Bayer",
    "bayer healthcare pharmaceuticals":  "Bayer",
    "bayer schering pharma":             "Bayer",
    "bayer pharma ag":                   "Bayer",

    # ── Takeda ─────────────────────────────────────────────────────────────
    "takeda":                            "Takeda",
    "takeda pharmaceuticals":            "Takeda",
    "takeda pharmaceutical":             "Takeda",
    "millennium pharmaceuticals":        "Takeda",   # acquired 2008 (bortezomib)
    "shire":                             "Takeda",   # acquired 2019
    "ariad pharmaceuticals":             "Takeda",   # acquired 2017

    # ── Eisai ──────────────────────────────────────────────────────────────
    "eisai":                             "Eisai",
    "eisai inc":                         "Eisai",
    "eisai inc.":                        "Eisai",
    "eisai co":                          "Eisai",

    # ── Daiichi Sankyo ─────────────────────────────────────────────────────
    "daiichi sankyo":                    "Daiichi Sankyo",
    "daiichi-sankyo":                    "Daiichi Sankyo",
    "ds pharma biomedical":              "Daiichi Sankyo",

    # ── Astellas ───────────────────────────────────────────────────────────
    "astellas":                          "Astellas",
    "astellas pharma":                   "Astellas",
    "astellas pharma inc":               "Astellas",

    # ── Ipsen ──────────────────────────────────────────────────────────────
    "ipsen":                             "Ipsen",
    "ipsen innovation":                  "Ipsen",
    "ipsen biopharmaceuticals":          "Ipsen",

    # ── Servier ────────────────────────────────────────────────────────────
    "servier":                           "Servier",
    "les laboratoires servier":          "Servier",
    "institut de recherches servier":    "Servier",
    "agios pharmaceuticals":             "Servier",  # oncology assets acquired 2021

    # ── Gilead ─────────────────────────────────────────────────────────────
    "gilead":                            "Gilead",
    "gilead sciences":                   "Gilead",
    "gilead sciences, inc.":             "Gilead",
    "kite pharma":                       "Gilead",   # acquired 2017 (CAR-T)
    "kite, a gilead company":            "Gilead",
    "immunomedics":                      "Gilead",   # acquired 2020 (sacituzumab)

    # ── Incyte ─────────────────────────────────────────────────────────────
    "incyte":                            "Incyte",
    "incyte corporation":                "Incyte",
    "incyte biosciences":                "Incyte",

    # ── Regeneron ──────────────────────────────────────────────────────────
    "regeneron":                         "Regeneron",
    "regeneron pharmaceuticals":         "Regeneron",
    "regeneron pharmaceuticals, inc.":   "Regeneron",

    # ── Exelixis ───────────────────────────────────────────────────────────
    "exelixis":                          "Exelixis",
    "exelixis, inc.":                    "Exelixis",

    # ── Iovance ────────────────────────────────────────────────────────────
    "iovance":                           "Iovance",
    "iovance biotherapeutics":           "Iovance",

    # ── Blueprint Medicines ────────────────────────────────────────────────
    "blueprint medicines":               "Blueprint Medicines",
    "blueprint medicines corporation":   "Blueprint Medicines",

    # ── Moderna ────────────────────────────────────────────────────────────
    "moderna":                           "Moderna",
    "moderna therapeutics":              "Moderna",
    "moderna, inc.":                     "Moderna",

    # ── BioNTech ───────────────────────────────────────────────────────────
    "biontech":                          "BioNTech",
    "biontech se":                       "BioNTech",

    # ── Chinese Biotech ────────────────────────────────────────────────────
    # BeiGene
    "beigene":                           "BeiGene",
    "beigene ltd":                       "BeiGene",
    "beigene, ltd.":                     "BeiGene",
    "beiging": "BeiGene",  # common typo

    # Hengrui — two common name forms
    "hengrui":                           "Hengrui Medicine",
    "jiangsu hengrui":                   "Hengrui Medicine",
    "jiangsu hengrui medicine":          "Hengrui Medicine",
    "hengrui medicine":                  "Hengrui Medicine",
    "hengrui pharmaceutical":            "Hengrui Medicine",

    # Zai Lab
    "zai lab":                           "Zai Lab",
    "zai lab (shanghai)":                "Zai Lab",
    "zai lab limited":                   "Zai Lab",

    # Legend / Nanjing Legend
    "legend biotech":                    "Legend Biotech",
    "nanjing legend biotech":            "Legend Biotech",
    "nanjing legend biotechnology":      "Legend Biotech",
    "legend biotech usa":                "Legend Biotech",

    # Innovent
    "innovent biologics":                "Innovent Biologics",
    "innovent biologics (suzhou)":       "Innovent Biologics",
    "innovent biologics co., ltd.":      "Innovent Biologics",

    # Junshi
    "junshi biosciences":                "Junshi Biosciences",
    "shanghai junshi biosciences":       "Junshi Biosciences",
    "topalliance biosciences":           "Junshi Biosciences",

    # CStone
    "cstone pharmaceuticals":            "CStone Pharmaceuticals",
    "cstone":                            "CStone Pharmaceuticals",

    # Akeso
    "akeso biotech":                     "Akeso Biotech",
    "akeso":                             "Akeso Biotech",
    "akeso, inc.":                       "Akeso Biotech",

    # Gracell (acquired by AstraZeneca 2024 — keep as Gracell for historical accuracy)
    "gracell biotechnologies":           "Gracell Biotechnologies",
    "gracell biotechnologies inc.":      "Gracell Biotechnologies",

    # CSPC
    "cspc pharmaceutical":               "CSPC Pharmaceutical",
    "cspc":                              "CSPC Pharmaceutical",
    "cspc zhongqi pharmaceutical":       "CSPC Pharmaceutical",

    # Sino Biopharmaceutical
    "sino biopharmaceutical":            "Sino Biopharmaceutical",
    "sino biopharma":                    "Sino Biopharmaceutical",
    "sino biological":                   "Sino Biopharmaceutical",

    # Alphamab
    "alphamab oncology":                 "Alphamab Oncology",
    "alphamab":                          "Alphamab Oncology",

    # Abbisko
    "abbisko therapeutics":              "Abbisko Therapeutics",

    # Luye Pharma
    "luye pharma":                       "Luye Pharma",
    "luye pharmaceutical":               "Luye Pharma",
    "luye pharma group":                 "Luye Pharma",

    # Simcere
    "simcere":                           "Simcere Pharmaceutical",
    "simcere pharmaceutical":            "Simcere Pharmaceutical",

    # Qilu
    "qilu pharmaceutical":               "Qilu Pharmaceutical",
    "qilu pharma":                       "Qilu Pharmaceutical",

    # Chia Tai Tianqing
    "chia tai tianqing":                 "Chia Tai Tianqing",
    "jiangsu chia-tai tianqing":         "Chia Tai Tianqing",
    "ct tianqing":                       "Chia Tai Tianqing",

    # Harbour Biomed
    "harbour biomed":                    "Harbour Biomed",
    "harbour biomedicines":              "Harbour Biomed",

    # Genscript / Legend (GenScript is the parent of Legend Biotech)
    "genscript":                         "GenScript",
    "genscript biotech":                 "GenScript",

    # BioAtla
    "bioatla":                           "BioAtla",
    "bioatla, llc":                      "BioAtla",
}


# ── Public functions ───────────────────────────────────────────────────────

def normalize(name: str) -> str:
    """Lowercase and strip a sponsor name for matching."""
    return name.lower().strip() if isinstance(name, str) else ""


def consolidate(sponsor_name: str) -> str:
    """
    Return the canonical parent company name for a given sponsor string.

    Matching order:
    1. Exact match on normalized name
    2. Substring match: check if any known key is contained in the normalized name
       (catches variants like "Janssen Research & Development, LLC")
    3. No match: return original name unchanged
    """
    if not isinstance(sponsor_name, str) or not sponsor_name.strip():
        return sponsor_name

    norm = normalize(sponsor_name)

    # 1. Exact match
    if norm in SPONSOR_MAP:
        return SPONSOR_MAP[norm]

    # 2. Substring match — check all keys, prefer longer keys (more specific)
    matches = [
        (key, parent)
        for key, parent in SPONSOR_MAP.items()
        if key in norm
    ]
    if matches:
        # Pick the longest matching key (most specific)
        best_key, best_parent = max(matches, key=lambda x: len(x[0]))
        return best_parent

    # 3. No match — return as-is
    return sponsor_name


def apply_consolidation(df: "pd.DataFrame") -> "pd.DataFrame":
    """
    Add a 'sponsor_parent' column to the dataframe.
    Preserves 'sponsor_name' (original) for auditability.
    """
    import pandas as pd
    df = df.copy()
    df["sponsor_parent"] = df["sponsor_name"].apply(consolidate)
    return df


def consolidation_report(df: "pd.DataFrame") -> None:
    """Print a report of how many sponsors were consolidated."""
    total = len(df)
    consolidated = (df["sponsor_name"] != df["sponsor_parent"]).sum()
    unchanged = total - consolidated
    unique_before = df["sponsor_name"].nunique()
    unique_after  = df["sponsor_parent"].nunique()

    print(f"\n── Sponsor Consolidation Report ─────────────────")
    print(f"  Trials processed:       {total:>6,}")
    print(f"  Names consolidated:     {consolidated:>6,}  ({100*consolidated/max(total,1):.1f}%)")
    print(f"  Names unchanged:        {unchanged:>6,}")
    print(f"  Unique sponsors before: {unique_before:>6,}")
    print(f"  Unique sponsors after:  {unique_after:>6,}")
    print(f"  Reduction:              {unique_before - unique_after:>6,} fewer unique entries")
    print(f"─────────────────────────────────────────────────\n")

    # Show what got consolidated
    changed = df[df["sponsor_name"] != df["sponsor_parent"]][["sponsor_name", "sponsor_parent"]]
    if len(changed) > 0:
        print("  Sample consolidations:")
        for orig, parent in changed.drop_duplicates().values[:20]:
            print(f"    '{orig}' → '{parent}'")


if __name__ == "__main__":
    # Quick self-test
    cases = [
        ("Genentech",                    "Roche"),
        ("F. Hoffmann-La Roche",        "Roche"),
        ("Hoffmann-La Roche",           "Roche"),
        ("Janssen Research & Development, LLC", "Johnson & Johnson"),
        ("Merck Sharp & Dohme LLC",     "Merck (MSD)"),
        ("Merck KGaA",                  "Merck KGaA"),
        ("Jiangsu Hengrui Medicine Co., Ltd.", "Hengrui Medicine"),
        ("Nanjing Legend Biotech",      "Legend Biotech"),
        ("Celgene",                     "Bristol-Myers Squibb"),
        ("Kite Pharma",                 "Gilead"),
        ("MedImmune",                   "AstraZeneca"),
        ("Chugai Pharmaceutical",       "Roche"),
        ("Some Unknown Biotech Co.",    "Some Unknown Biotech Co."),
    ]

    print("Sponsor Consolidation Self-Test\n")
    all_pass = True
    for input_name, expected in cases:
        result = consolidate(input_name)
        ok = result == expected
        if not ok:
            all_pass = False
        print(f"  {'PASS' if ok else 'FAIL'}  '{input_name}'\n        → '{result}' (expected '{expected}')")

    print(f"\n{'All tests passed!' if all_pass else 'SOME TESTS FAILED'}")