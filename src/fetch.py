"""
fetch.py
Pull oncology clinical trials from ClinicalTrials.gov v2 API.
Fetches three regional pools (China, US, EU), deduplicates globally,
and tags each trial with all regions where it has sites.

Saves to data/raw_trials.csv
"""

import requests
import pandas as pd
import time
from pathlib import Path

BASE_URL = "https://clinicaltrials.gov/api/v2/studies"

ONCOLOGY_TERMS = [
    "lung cancer",
    "breast cancer",
    "gastric cancer",
    "colorectal cancer",
    "hepatocellular carcinoma",
    "leukemia",
    "lymphoma",
    "esophageal cancer",
    "nasopharyngeal carcinoma",
    "ovarian cancer",
    "cervical cancer",
    "pancreatic cancer",
    "bladder cancer",
    "renal cell carcinoma",
    "melanoma",
    "glioma",
    "myeloma",
    "prostate cancer",
    "thyroid cancer",
    "cholangiocarcinoma",
]

# ── Region definitions ─────────────────────────────────────────────────────
REGION_COUNTRIES: dict[str, set[str]] = {
    "China": {"China"},
    "US": {"United States"},
    "EU": {
        "Germany", "France", "Italy", "Spain", "Netherlands",
        "Belgium", "Sweden", "Denmark", "Austria", "Finland",
        "Poland", "Czech Republic", "Hungary", "Portugal",
        "Greece", "Romania", "Switzerland",
    },
}

FIELDS = [
    "protocolSection.identificationModule.nctId",
    "protocolSection.identificationModule.briefTitle",
    "protocolSection.statusModule.overallStatus",
    "protocolSection.statusModule.startDateStruct",
    "protocolSection.statusModule.primaryCompletionDateStruct",
    "protocolSection.designModule.phases",
    "protocolSection.designModule.studyType",
    "protocolSection.designModule.enrollmentInfo",
    "protocolSection.conditionsModule.conditions",
    "protocolSection.armsInterventionsModule.interventions",
    "protocolSection.sponsorCollaboratorsModule.leadSponsor",
    "protocolSection.sponsorCollaboratorsModule.collaborators",
    "protocolSection.contactsLocationsModule.locations",
    "derivedSection.conditionBrowseModule.meshes",
]


def _get_study_countries(study: dict) -> set[str]:
    locations = (
        study.get("protocolSection", {})
        .get("contactsLocationsModule", {})
        .get("locations", [])
    )
    return {loc.get("country", "") for loc in locations if loc.get("country")}


def _study_regions(countries: set[str]) -> list[str]:
    regions = []
    for region, country_set in REGION_COUNTRIES.items():
        if countries & country_set:
            regions.append(region)
    return sorted(regions)


def fetch_for_condition_and_region(
    condition: str,
    filter_countries: set[str],
    page_size: int = 1000,
) -> list[dict]:
    trials = []

    for country in filter_countries:
        page_token = None
        page = 1

        while True:
            params = {
                "query.cond": condition,
                "query.locn": country,
                "filter.overallStatus": "RECRUITING,ACTIVE_NOT_RECRUITING,COMPLETED,NOT_YET_RECRUITING",
                "pageSize": page_size,
                "format": "json",
                "countTotal": "true",
                "fields": ",".join(FIELDS),
            }
            if page_token:
                params["pageToken"] = page_token

            try:
                resp = requests.get(BASE_URL, params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                print(f"    Error ({country}, '{condition}', page {page}): {e}")
                break

            studies = data.get("studies", [])
            if not studies:
                break

            matched = [
                s for s in studies
                if _get_study_countries(s) & filter_countries
            ]
            trials.extend(matched)

            if page == 1 and len(filter_countries) == 1:
                total = data.get("totalCount", "?")
                print(f"    '{condition}' in {country}: {total} total, {len(matched)} matched")

            page_token = data.get("nextPageToken")
            if not page_token:
                break
            page += 1
            time.sleep(0.3)

    return trials


def parse_trial(study: dict, all_countries: set[str]) -> dict:
    ps = study.get("protocolSection", {})

    id_mod      = ps.get("identificationModule", {})
    status_mod  = ps.get("statusModule", {})
    design_mod  = ps.get("designModule", {})
    cond_mod    = ps.get("conditionsModule", {})
    interv_mod  = ps.get("armsInterventionsModule", {})
    sponsor_mod = ps.get("sponsorCollaboratorsModule", {})
    loc_mod     = ps.get("contactsLocationsModule", {})

    derived = study.get("derivedSection", {})
    mesh_entries   = derived.get("conditionBrowseModule", {}).get("meshes", [])
    mesh_ids_str   = "|".join(m.get("id", "")   for m in mesh_entries if m.get("id"))
    mesh_terms_str = "|".join(m.get("term", "") for m in mesh_entries if m.get("term"))

    phases    = design_mod.get("phases", [])
    phase_str = "|".join(phases) if phases else "N/A"

    conditions     = cond_mod.get("conditions", [])
    conditions_str = "|".join(conditions[:5])

    interventions = interv_mod.get("interventions", [])
    interv_types  = list({i.get("type", "") for i in interventions if i.get("type")})
    interv_names  = [i.get("name", "") for i in interventions[:5]]

    lead_sponsor  = sponsor_mod.get("leadSponsor", {})
    sponsor_name  = lead_sponsor.get("name", "")
    sponsor_class = lead_sponsor.get("class", "")

    locations    = loc_mod.get("locations", [])
    china_locs   = [l for l in locations if l.get("country") == "China"]
    china_cities = list({l.get("city", "") for l in china_locs if l.get("city")})

    regions     = _study_regions(all_countries)
    regions_str = "|".join(regions)

    start_date         = status_mod.get("startDateStruct", {}).get("date", "")
    start_year         = start_date[:4] if start_date else ""
    primary_completion = status_mod.get("primaryCompletionDateStruct", {}).get("date", "")
    enrollment         = design_mod.get("enrollmentInfo", {}).get("count", None)

    return {
        "nct_id":                  id_mod.get("nctId", ""),
        "title":                   id_mod.get("briefTitle", ""),
        "status":                  status_mod.get("overallStatus", ""),
        "phase":                   phase_str,
        "study_type":              design_mod.get("studyType", ""),
        "conditions":              conditions_str,
        "intervention_types":      "|".join(interv_types),
        "intervention_names":      "|".join(interv_names),
        "sponsor_name":            sponsor_name,
        "sponsor_class":           sponsor_class,
        "china_cities":            "|".join(china_cities[:5]),
        "regions":                 regions_str,
        "in_china":                "China" in regions,
        "in_us":                   "US"    in regions,
        "in_eu":                   "EU"    in regions,
        "is_multinational":        len(all_countries) > 1,
        "start_date":              start_date,
        "start_year":              start_year,
        "primary_completion_date": primary_completion,
        "enrollment":              enrollment,
        "mesh_ids":                mesh_ids_str,
        "mesh_terms":              mesh_terms_str,
    }


def fetch_all(output_path: str = "data/raw_trials.csv"):
    """
    Fetch oncology trials for China, US, and EU.
    Deduplicates globally — each NCT ID appears once,
    tagged with all regions where it has sites.
    """
    all_studies: dict[str, dict] = {}

    for region_name, country_set in REGION_COUNTRIES.items():
        print(f"\n{'='*50}")
        print(f"  Region: {region_name}")
        print(f"{'='*50}")

        for condition in ONCOLOGY_TERMS:
            print(f"\n  Condition: {condition}")
            studies = fetch_for_condition_and_region(condition, country_set)
            new = 0
            for s in studies:
                nct_id = (
                    s.get("protocolSection", {})
                    .get("identificationModule", {})
                    .get("nctId", "")
                )
                if nct_id and nct_id not in all_studies:
                    all_studies[nct_id] = s
                    new += 1
            print(f"    → {len(studies)} found, {new} new. Total: {len(all_studies)}")

    print(f"\nTotal unique trials: {len(all_studies)}")

    records = []
    for study in all_studies.values():
        countries = _get_study_countries(study)
        records.append(parse_trial(study, countries))

    df = pd.DataFrame(records)

    print(f"\n── Region coverage ──────────────────────────")
    print(f"  China: {df['in_china'].sum():,}")
    print(f"  US:    {df['in_us'].sum():,}")
    print(f"  EU:    {df['in_eu'].sum():,}")
    print(f"  China+US overlap: {(df['in_china'] & df['in_us']).sum():,}")
    print(f"─────────────────────────────────────────────")

    Path(output_path).parent.mkdir(exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Saved to {output_path}")
    return df


if __name__ == "__main__":
    df = fetch_all()
    print(f"\nShape: {df.shape}")