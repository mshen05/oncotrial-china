"""
fetch.py
Pull oncology clinical trials with China locations from ClinicalTrials.gov v2 API.
Saves raw data to data/raw_trials.csv
"""

import requests
import pandas as pd
import time
import json
from pathlib import Path

BASE_URL = "https://clinicaltrials.gov/api/v2/studies"

# Broad oncology conditions to query. We cast a wide net then filter.
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
    # MeSH annotations pre-computed by ClinicalTrials.gov
    "derivedSection.conditionBrowseModule.meshes",
]


def fetch_trials_for_condition(condition: str, page_size: int = 1000) -> list[dict]:
    """Fetch all China-location trials for a given oncology condition."""
    trials = []
    page_token = None
    page = 1

    while True:
        params = {
            "query.cond": condition,
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
            print(f"  Error fetching '{condition}' page {page}: {e}")
            break

        studies = data.get("studies", [])
        if not studies:
            break

        # Filter to studies that have at least one China location
        china_studies = []
        for s in studies:
            locations = (
                s.get("protocolSection", {})
                .get("contactsLocationsModule", {})
                .get("locations", [])
            )
            countries = [loc.get("country", "") for loc in locations]
            if "China" in countries:
                china_studies.append(s)

        trials.extend(china_studies)

        if page == 1:
            total = data.get("totalCount", "?")
            print(f"  '{condition}': {total} total trials found, filtering for China...")

        page_token = data.get("nextPageToken")
        if not page_token:
            break

        page += 1
        time.sleep(0.3)  # be polite to the API

    return trials


def parse_trial(study: dict) -> dict:
    """Flatten a nested study record into a flat dict."""
    ps = study.get("protocolSection", {})

    id_mod = ps.get("identificationModule", {})
    status_mod = ps.get("statusModule", {})
    design_mod = ps.get("designModule", {})
    cond_mod = ps.get("conditionsModule", {})
    interv_mod = ps.get("armsInterventionsModule", {})
    sponsor_mod = ps.get("sponsorCollaboratorsModule", {})
    loc_mod = ps.get("contactsLocationsModule", {})

    # MeSH IDs from ClinicalTrials.gov's own annotation
    derived = study.get("derivedSection", {})
    mesh_entries = derived.get("conditionBrowseModule", {}).get("meshes", [])
    mesh_ids = [m.get("id", "") for m in mesh_entries if m.get("id")]
    mesh_terms = [m.get("term", "") for m in mesh_entries if m.get("term")]
    mesh_ids_str = "|".join(mesh_ids)
    mesh_terms_str = "|".join(mesh_terms)

    # Phases
    phases = design_mod.get("phases", [])
    phase_str = "|".join(phases) if phases else "N/A"

    # Conditions
    conditions = cond_mod.get("conditions", [])
    conditions_str = "|".join(conditions[:5])  # cap at 5

    # Interventions — type and name
    interventions = interv_mod.get("interventions", [])
    interv_types = list({i.get("type", "") for i in interventions if i.get("type")})
    interv_names = [i.get("name", "") for i in interventions[:5]]
    interv_types_str = "|".join(interv_types)
    interv_names_str = "|".join(interv_names)

    # Sponsor
    lead_sponsor = sponsor_mod.get("leadSponsor", {})
    sponsor_name = lead_sponsor.get("name", "")
    sponsor_class = lead_sponsor.get("class", "")  # INDUSTRY, NIH, OTHER, etc.

    # Locations (China only)
    locations = loc_mod.get("locations", [])
    china_locs = [l for l in locations if l.get("country") == "China"]
    china_cities = list({l.get("city", "") for l in china_locs if l.get("city")})
    china_cities_str = "|".join(china_cities[:5])

    # Also track if this trial has non-China sites (multinational?)
    all_countries = list({l.get("country", "") for l in locations if l.get("country")})
    is_multinational = len(all_countries) > 1

    # Dates
    start_date = status_mod.get("startDateStruct", {}).get("date", "")
    start_year = start_date[:4] if start_date else ""

    primary_completion = status_mod.get("primaryCompletionDateStruct", {}).get("date", "")

    # Enrollment
    enrollment_info = design_mod.get("enrollmentInfo", {})
    enrollment = enrollment_info.get("count", None)

    return {
        "nct_id": id_mod.get("nctId", ""),
        "title": id_mod.get("briefTitle", ""),
        "status": status_mod.get("overallStatus", ""),
        "phase": phase_str,
        "study_type": design_mod.get("studyType", ""),
        "conditions": conditions_str,
        "intervention_types": interv_types_str,
        "intervention_names": interv_names_str,
        "sponsor_name": sponsor_name,
        "sponsor_class": sponsor_class,
        "china_cities": china_cities_str,
        "is_multinational": is_multinational,
        "start_date": start_date,
        "start_year": start_year,
        "primary_completion_date": primary_completion,
        "enrollment": enrollment,
        "mesh_ids": mesh_ids_str,
        "mesh_terms": mesh_terms_str,
    }


def fetch_all(output_path: str = "data/raw_trials.csv"):
    """Main entry point: fetch all oncology China trials and save to CSV."""
    all_studies = {}  # keyed by nct_id to deduplicate

    for condition in ONCOLOGY_TERMS:
        print(f"\nFetching: {condition}")
        studies = fetch_trials_for_condition(condition)
        for s in studies:
            nct_id = s.get("protocolSection", {}).get("identificationModule", {}).get("nctId", "")
            if nct_id and nct_id not in all_studies:
                all_studies[nct_id] = s
        print(f"  → {len(studies)} China trials found. Running total: {len(all_studies)}")

    print(f"\nTotal unique China oncology trials: {len(all_studies)}")

    # Parse into flat records
    records = [parse_trial(s) for s in all_studies.values()]
    df = pd.DataFrame(records)

    Path(output_path).parent.mkdir(exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Saved to {output_path}")
    return df


if __name__ == "__main__":
    df = fetch_all()
    print(df.head())
    print(f"\nShape: {df.shape}")