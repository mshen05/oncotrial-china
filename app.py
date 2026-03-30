"""
app.py
Streamlit dashboard: China Oncology Trial Landscape
Run with: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
import subprocess
import sys
import datetime

# ── Page config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="China Oncology Trial Landscape",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .metric-card {
        background: #f8f9fa;
        border-radius: 8px;
        padding: 16px 20px;
        border-left: 4px solid #2196F3;
    }
    .insight-box {
        background: #e8f4f8;
        color: #1a1a2e;
        border-radius: 6px;
        padding: 12px 16px;
        margin: 8px 0;
        font-size: 0.9em;
        line-height: 1.6;
    }
    .insight-box strong, .insight-box b { color: #1a1a2e; }
    h1 { color: #1a1a2e; }
    .stPlotlyChart { border-radius: 8px; }
    @media (max-width: 768px) {
        .block-container { padding-left: 1rem !important; padding-right: 1rem !important; }
        h1 { font-size: 1.4rem !important; }
    }
</style>
""", unsafe_allow_html=True)

CLEAN_PATH = "data/clean_trials.csv"
RAW_PATH   = "data/raw_trials.csv"

# ── Status display labels ──────────────────────────────────────────────────
STATUS_LABELS = {
    "RECRUITING":              "Recruiting",
    "ACTIVE_NOT_RECRUITING":   "Active, not recruiting",
    "NOT_YET_RECRUITING":      "Not yet recruiting",
    "COMPLETED":               "Completed",
    "TERMINATED":              "Terminated",
    "SUSPENDED":               "Suspended",
    "WITHDRAWN":               "Withdrawn",
    "ENROLLING_BY_INVITATION": "Enrolling by invitation",
    "UNKNOWN":                 "Unknown status",
}
STATUS_LABELS_INV = {v: k for k, v in STATUS_LABELS.items()}

def label_status(raw: str) -> str:
    return STATUS_LABELS.get(str(raw).strip(), raw)

def no_data_msg(msg: str = "No data matches the current filters."):
    st.info(f"ℹ️ {msg}")


# ── Data loading ───────────────────────────────────────────────────────────
@st.cache_data
def load_data():
    if not Path(CLEAN_PATH).exists():
        return None
    df = pd.read_csv(CLEAN_PATH)
    df["start_year"]   = pd.to_numeric(df["start_year"], errors="coerce")
    df["status_label"] = df["status"].apply(label_status)
    return df


def run_pipeline(show_progress: bool = True) -> bool:
    """Run fetch + clean pipeline. Returns True on success."""
    spin = st.spinner if show_progress else _null_spinner
    with spin("Fetching data from ClinicalTrials.gov... (~3–5 min)"):
        result = subprocess.run([sys.executable, "src/fetch.py"], capture_output=True, text=True)
        if result.returncode != 0:
            st.error(f"Fetch failed:\n{result.stderr}")
            return False
    with spin("Cleaning and classifying data..."):
        result = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0,'src'); from clean import clean; clean()"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            st.error(f"Clean failed:\n{result.stderr}")
            return False
    st.cache_data.clear()
    return True


from contextlib import contextmanager
@contextmanager
def _null_spinner(msg=""):
    yield


# ── Load data — must be before sidebar so st.stop() is unconditional ───────
df_raw = load_data()

if df_raw is None:
    st.title("China Oncology Clinical Trial Landscape")

    # Auto-fetch on first load (e.g. fresh Streamlit Cloud deployment).
    # Guard with session_state so a failed fetch doesn't loop forever.
    if not st.session_state.get("auto_fetch_attempted"):
        st.session_state["auto_fetch_attempted"] = True
        st.info(
            "No local data found — fetching from ClinicalTrials.gov now. "
            "This takes 3–5 minutes on first deployment."
        )
        if run_pipeline():
            st.rerun()
        else:
            st.error(
                "Auto-fetch failed. Check that ClinicalTrials.gov is reachable, "
                "then click Retry below."
            )

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🔄 Retry fetch from ClinicalTrials.gov", type="primary"):
            st.session_state.pop("auto_fetch_attempted", None)
            st.rerun()
    with col_b:
        if st.button("🧪 Load sample data instead"):
            subprocess.run([sys.executable, "generate_sample.py"], check=True)
            st.cache_data.clear()
            st.session_state.pop("auto_fetch_attempted", None)
            st.rerun()
    st.stop()


# ── Sidebar ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🔬 Filters")

    min_year = int(df_raw["start_year"].min()) if not df_raw["start_year"].isna().all() else 2010
    max_year = int(df_raw["start_year"].max()) if not df_raw["start_year"].isna().all() else 2025
    year_range = st.slider("Trial Start Year", min_year, max_year, (2015, max_year))

    # Status — show clean display labels, map back to raw for filtering
    status_label_options = sorted(df_raw["status_label"].dropna().unique())
    default_labels = [label_status(s) for s in
                      ["RECRUITING", "ACTIVE_NOT_RECRUITING", "NOT_YET_RECRUITING", "COMPLETED"]
                      if label_status(s) in status_label_options]
    selected_status_labels = st.multiselect("Status", status_label_options, default=default_labels)
    selected_statuses = [STATUS_LABELS_INV.get(l, l) for l in selected_status_labels]

    phase_options = sorted(df_raw["phase_clean"].dropna().unique())
    selected_phases = st.multiselect("Phase", phase_options, default=phase_options)

    cancer_options = sorted(df_raw["cancer_type"].dropna().unique())
    selected_cancers = st.multiselect("Cancer Type", cancer_options, default=cancer_options)

    st.divider()
    if st.button("🔄 Refresh Data"):
        if run_pipeline():
            st.success("Refreshed!")
            st.rerun()

    st.caption("Data: ClinicalTrials.gov API v2")


# ── Apply filters ──────────────────────────────────────────────────────────
df = df_raw.copy()
df = df[df["start_year"].between(year_range[0], year_range[1], inclusive="both") | df["start_year"].isna()]
if selected_statuses:
    df = df[df["status"].isin(selected_statuses)]
if selected_phases:
    df = df[df["phase_clean"].isin(selected_phases)]
if selected_cancers:
    df = df[df["cancer_type"].isin(selected_cancers)]


# ── Header ─────────────────────────────────────────────────────────────────
st.title("China Oncology Clinical Trial Landscape")
_extracted = datetime.datetime.fromtimestamp(
    Path(CLEAN_PATH).stat().st_mtime
).strftime("%B %d, %Y")
st.caption(
    f"{len(df_raw):,} trials across China, US & EU  ·  "
    f"Source: ClinicalTrials.gov API v2  ·  "
    f"Last extracted: {_extracted}"
)

with st.expander("ℹ️ Methodology & Definitions", expanded=False):
    st.markdown("""
**Data source:** All records are fetched from the public [ClinicalTrials.gov API v2](https://clinicaltrials.gov/data-api/api).
The dataset covers interventional oncology trials with at least one registered site in China, the United States, or an EU member state.

**Cancer type classification** uses ClinicalTrials.gov's own MeSH annotations first
(`derivedSection.conditionBrowseModule.meshes`), then falls back to regex matching on free-text condition names.

**Sponsor classification:**
- *Chinese Biotech/Pharma* — lead sponsor matches known Chinese pharma companies or major Chinese geography keywords
- *MNC* — lead sponsor matches a known global pharma company
- *Academic/Hospital* — sponsor name contains "university," "hospital," "institute," or similar
- *Other* — industry sponsors not matching either pattern above

**Sponsor consolidation:** Subsidiary names are mapped to parent companies
(e.g. Genentech → Roche, Celgene → Bristol-Myers Squibb, Janssen → Johnson & Johnson).
The original reported name is preserved in the raw data table.

**Multinational trials** have registered sites in more than one country.
A single trial can appear in both the China and US counts simultaneously.

**Phase "Unknown":** Trials without a declared phase are expected — observational studies and
expanded access programs are not required to report one. This does not indicate a data quality problem.
    """)


# ── Comparison tab helper ──────────────────────────────────────────────────
def _compare_content(df: pd.DataFrame):
    if "in_china" not in df.columns:
        st.info("Re-run the data pipeline to enable regional comparison.")
        return

    china_df = df[df["in_china"] == True]
    us_df    = df[df["in_us"]    == True]
    eu_df    = df[df["in_eu"]    == True]

    if len(us_df) == 0 and len(eu_df) == 0:
        st.info("No US or EU trials in current dataset. Run `python generate_sample.py` to regenerate.")
        return

    st.subheader("Regional Comparison: China vs US vs EU")
    st.caption("Trials are not mutually exclusive — a multinational trial appears in every region where it has sites.")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("China trials", f"{len(china_df):,}")
    c2.metric("US trials",    f"{len(us_df):,}")
    c3.metric("EU trials",    f"{len(eu_df):,}")
    overlap = int((df["in_china"] & df["in_us"]).sum())
    c4.metric("China + US overlap", f"{overlap:,}",
              help="Trials with sites in both China and the United States")

    st.divider()
    st.subheader("Trial Volume by Region (2015-2025)")

    rows = []
    for region, sub in [("China", china_df), ("US", us_df), ("EU", eu_df)]:
        t = (
            sub[sub["start_year"].between(2015, 2025)]
            .groupby("start_year").size().reset_index(name="count")
        )
        t["region"] = region
        rows.append(t)
    trend_df = pd.concat(rows, ignore_index=True)

    if trend_df.empty:
        no_data_msg()
    else:
        fig_trend = px.line(
            trend_df, x="start_year", y="count", color="region", markers=True,
            template="plotly_white",
            labels={"start_year": "Year", "count": "Trials", "region": "Region"},
            color_discrete_map={"China": "#1565C0", "US": "#C62828", "EU": "#2E7D32"},
        )
        fig_trend.update_layout(
            height=320, margin=dict(l=10, r=10, t=10, b=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig_trend, use_container_width=True)

    st.divider()
    col_phase, col_cancer = st.columns(2)

    with col_phase:
        st.subheader("Phase Mix by Region")
        phase_order = ["Phase 1", "Phase 1/2", "Phase 2", "Phase 2/3",
                       "Phase 3", "Phase 4", "N/A", "Unknown"]
        phase_rows = []
        for region, sub in [("China", china_df), ("US", us_df), ("EU", eu_df)]:
            counts = sub["phase_clean"].value_counts(normalize=True).mul(100).round(1)
            for phase, pct in counts.items():
                phase_rows.append({"Region": region, "Phase": phase, "Pct": pct})
        phase_df = pd.DataFrame(phase_rows)
        phase_df = phase_df[phase_df["Phase"].isin(phase_order)]
        if phase_df.empty:
            no_data_msg()
        else:
            phase_df["Phase"] = pd.Categorical(phase_df["Phase"], categories=phase_order, ordered=True)
            phase_df = phase_df.sort_values("Phase")
            fig_phase = px.bar(
                phase_df, x="Region", y="Pct", color="Phase", barmode="stack",
                template="plotly_white", labels={"Pct": "% of Trials"},
                color_discrete_sequence=px.colors.sequential.Blues_r,
            )
            fig_phase.update_layout(
                height=380, margin=dict(l=10, r=10, t=10, b=10),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=10)),
                yaxis=dict(ticksuffix="%"),
            )
            st.plotly_chart(fig_phase, use_container_width=True)

    with col_cancer:
        st.subheader("Cancer Type Focus by Region")
        top_cancers = df["cancer_type"].value_counts().head(10).index.tolist()
        heat_rows = []
        region_totals = {"China": max(len(china_df), 1), "US": max(len(us_df), 1), "EU": max(len(eu_df), 1)}
        for region, sub in [("China", china_df), ("US", us_df), ("EU", eu_df)]:
            counts = sub[sub["cancer_type"].isin(top_cancers)]["cancer_type"].value_counts()
            for cancer in top_cancers:
                pct = round(100 * counts.get(cancer, 0) / region_totals[region], 1)
                heat_rows.append({"Cancer Type": cancer, "Region": region, "Pct": pct})
        heat_df = pd.DataFrame(heat_rows)
        if heat_df.empty:
            no_data_msg()
        else:
            pivot = heat_df.pivot(index="Cancer Type", columns="Region", values="Pct").fillna(0)
            pivot = pivot.sort_values("China", ascending=False)
            fig_heat = px.imshow(
                pivot, text_auto=".1f", color_continuous_scale="Blues",
                template="plotly_white", labels={"color": "% of Region Trials"}, aspect="auto",
            )
            fig_heat.update_layout(
                height=380, margin=dict(l=10, r=10, t=20, b=10), coloraxis_showscale=False,
            )
            fig_heat.update_traces(texttemplate="%{z:.1f}%")
            st.plotly_chart(fig_heat, use_container_width=True)

    st.divider()
    st.subheader("Therapeutic Modality Mix by Region")
    top_modalities = df["modality"].value_counts().head(8).index.tolist()
    mod_rows = []
    for region, sub in [("China", china_df), ("US", us_df), ("EU", eu_df)]:
        total = max(len(sub), 1)
        counts = sub[sub["modality"].isin(top_modalities)]["modality"].value_counts()
        for mod in top_modalities:
            mod_rows.append({"Modality": mod, "Region": region,
                             "Pct": round(100 * counts.get(mod, 0) / total, 1)})
    mod_df = pd.DataFrame(mod_rows)
    if mod_df.empty:
        no_data_msg()
    else:
        fig_mod = px.bar(
            mod_df, x="Pct", y="Modality", color="Region", barmode="group", orientation="h",
            template="plotly_white", labels={"Pct": "% of Region Trials"},
            color_discrete_map={"China": "#1565C0", "US": "#C62828", "EU": "#2E7D32"},
        )
        fig_mod.update_layout(
            height=380, margin=dict(l=10, r=10, t=10, b=10),
            xaxis=dict(ticksuffix="%"),
            yaxis=dict(categoryorder="total ascending"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig_mod, use_container_width=True)

    st.divider()
    st.subheader("Regional Observations")
    china_p3 = round(100 * (china_df["phase_clean"] == "Phase 3").sum() / max(len(china_df), 1))
    us_p3    = round(100 * (us_df["phase_clean"]    == "Phase 3").sum() / max(len(us_df), 1))
    eu_p3    = round(100 * (eu_df["phase_clean"]    == "Phase 3").sum() / max(len(eu_df), 1))
    china_top = china_df["cancer_type"].value_counts().index[0] if len(china_df) else "N/A"
    us_top    = us_df["cancer_type"].value_counts().index[0]    if len(us_df)    else "N/A"

    for obs in [
        f"**Pipeline maturity:** Phase 3 trials make up {china_p3}% of China's pipeline vs. "
        f"{us_p3}% (US) and {eu_p3}% (EU), reflecting differences in pipeline maturity and regulatory strategy.",
        f"**Cancer focus divergence:** China's pipeline skews toward {china_top}, while the US emphasizes "
        f"{us_top} — driven partly by differences in disease burden and commercial market priorities.",
        f"**Overlap as globalization signal:** {overlap:,} trials appear in both China and the US "
        f"({round(100*overlap/max(len(china_df),1))}% of China's pipeline) — a proxy for how integrated "
        "Chinese biotech has become in global development programs.",
    ]:
        st.markdown(f"<div class='insight-box'>• {obs}</div>", unsafe_allow_html=True)


# ── Tabs ───────────────────────────────────────────────────────────────────
tab_overview, tab_compare = st.tabs(["🇨🇳 China Overview", "🌍 Regional Comparison"])

with tab_overview:
    # Empty-state guard
    if len(df) == 0:
        st.warning("No trials match the current filters. Try broadening your selection.")
        st.stop()

    # ── KPI row ────────────────────────────────────────────────────────────
    col1, col2, col3, col4, col5 = st.columns(5)
    active_df       = df[df["is_active"] == True]
    china_sponsored = df[df["sponsor_origin"] == "Chinese Biotech/Pharma"]
    mnc_sponsored   = df[df["sponsor_origin"] == "MNC"]

    col1.metric("Total Trials (filtered)", f"{len(df):,}")
    col2.metric("Active / Recruiting",     f"{len(active_df):,}")
    col3.metric("Chinese Sponsor",         f"{len(china_sponsored):,}",
                help="Lead sponsor classified as a Chinese biotech or pharma company")
    col4.metric("MNC Sponsor",             f"{len(mnc_sponsored):,}",
                help="Lead sponsor classified as a multinational pharma company")
    col5.metric("Multinational Trials",    f"{df['is_multinational'].sum():,}",
                help="Trials with registered sites in more than one country")

    st.divider()

    # ── Row 1: Cancer type + Phase ─────────────────────────────────────────
    col_a, col_b = st.columns([3, 2])

    with col_a:
        st.subheader("Trials by Cancer Type")
        cancer_counts = (
            df["cancer_type"].value_counts().reset_index()
            .rename(columns={"cancer_type": "Cancer Type", "count": "Trials"})
            .head(15)
        )
        if cancer_counts.empty:
            no_data_msg()
        else:
            fig = px.bar(
                cancer_counts, x="Trials", y="Cancer Type", orientation="h",
                color="Trials", color_continuous_scale="Blues", template="plotly_white",
            )
            fig.update_layout(
                showlegend=False, coloraxis_showscale=False,
                yaxis=dict(categoryorder="total ascending"),
                margin=dict(l=10, r=10, t=10, b=10), height=420,
            )
            st.plotly_chart(fig, use_container_width=True)

    with col_b:
        st.subheader("Phase Distribution")
        phase_counts = df["phase_clean"].value_counts().reset_index()
        phase_counts.columns = ["Phase", "Count"]
        phase_order = ["Phase 1", "Phase 1/2", "Phase 2", "Phase 2/3",
                       "Phase 3", "Phase 4", "N/A", "Unknown"]
        phase_counts["Phase"] = pd.Categorical(
            phase_counts["Phase"], categories=phase_order, ordered=True
        )
        phase_counts = phase_counts.sort_values("Phase")
        if phase_counts.empty:
            no_data_msg()
        else:
            fig2 = px.pie(
                phase_counts, names="Phase", values="Count",
                color_discrete_sequence=px.colors.sequential.Blues_r,
                template="plotly_white",
            )
            fig2.update_traces(textinfo="label+percent", pull=[0.03]*len(phase_counts))
            fig2.update_layout(
                showlegend=False, margin=dict(l=10, r=10, t=10, b=10), height=420,
            )
            st.plotly_chart(fig2, use_container_width=True)
            unknown_pct = round(100 * (df["phase_clean"] == "Unknown").sum() / max(len(df), 1))
            if unknown_pct > 15:
                st.caption(
                    f"ℹ️ {unknown_pct}% of trials report no phase. Expected — observational studies "
                    "and expanded access programs are not required to declare a phase on registration."
                )

    # ── Row 2: Trend + Sponsor landscape ──────────────────────────────────
    st.subheader("Trial Volume Trend (by Start Year)")
    trend_col1, trend_col2 = st.columns([2, 1])

    with trend_col1:
        trend = (
            df[df["start_year"].between(2010, 2025)]
            .groupby(["start_year", "sponsor_origin"]).size().reset_index(name="count")
        )
        major_origins = ["Chinese Biotech/Pharma", "MNC", "Academic/Hospital"]
        trend = trend[trend["sponsor_origin"].isin(major_origins)]
        if trend.empty:
            no_data_msg()
        else:
            fig3 = px.area(
                trend, x="start_year", y="count", color="sponsor_origin",
                template="plotly_white",
                labels={"start_year": "Year", "count": "Number of Trials",
                        "sponsor_origin": "Sponsor Type"},
                color_discrete_map={
                    "Chinese Biotech/Pharma": "#1565C0",
                    "MNC": "#EF5350",
                    "Academic/Hospital": "#43A047",
                },
            )
            fig3.update_layout(
                margin=dict(l=10, r=10, t=10, b=10), height=320,
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
            )
            st.plotly_chart(fig3, use_container_width=True)

    with trend_col2:
        st.subheader("Sponsor Landscape")
        origin_counts = df["sponsor_origin"].value_counts().reset_index()
        origin_counts.columns = ["Sponsor Origin", "Count"]
        if origin_counts.empty:
            no_data_msg()
        else:
            fig4 = px.bar(
                origin_counts, x="Count", y="Sponsor Origin", orientation="h",
                color="Count", color_continuous_scale="Reds", template="plotly_white",
            )
            fig4.update_layout(
                showlegend=False, coloraxis_showscale=False,
                yaxis=dict(categoryorder="total ascending"),
                margin=dict(l=10, r=10, t=10, b=10), height=320,
            )
            st.plotly_chart(fig4, use_container_width=True)

    # ── Row 3: Modality + Top sponsors ────────────────────────────────────
    st.divider()
    col_mod, col_spon = st.columns(2)

    with col_mod:
        st.subheader("Therapeutic Modality Mix")
        mod_counts = df["modality"].value_counts().reset_index().head(12)
        mod_counts.columns = ["Modality", "Count"]
        if mod_counts.empty:
            no_data_msg()
        else:
            fig5 = px.bar(
                mod_counts, x="Count", y="Modality", orientation="h",
                color="Count", color_continuous_scale="Greens", template="plotly_white",
            )
            fig5.update_layout(
                showlegend=False, coloraxis_showscale=False,
                yaxis=dict(categoryorder="total ascending"),
                margin=dict(l=10, r=10, t=10, b=10), height=380,
            )
            st.plotly_chart(fig5, use_container_width=True)

    with col_spon:
        st.subheader("Top 15 Sponsors")
        _spon_col    = "sponsor_parent" if "sponsor_parent" in df.columns else "sponsor_name"
        top_sponsors = df[_spon_col].value_counts().reset_index().head(15)
        top_sponsors.columns = ["Sponsor", "Trials"]
        if top_sponsors.empty:
            no_data_msg()
        else:
            sponsor_origin_map = (
                df.groupby(_spon_col)["sponsor_origin"]
                .agg(lambda x: x.value_counts().index[0])
                .to_dict()
            )
            top_sponsors["Origin"] = top_sponsors["Sponsor"].map(sponsor_origin_map)
            color_map = {
                "Chinese Biotech/Pharma": "#1565C0",
                "MNC": "#EF5350",
                "Academic/Hospital": "#43A047",
                "Other Industry": "#FF9800",
                "Other / Unknown": "#9E9E9E",
            }
            fig6 = px.bar(
                top_sponsors, x="Trials", y="Sponsor", orientation="h",
                color="Origin", color_discrete_map=color_map, template="plotly_white",
            )
            fig6.update_layout(
                yaxis=dict(categoryorder="total ascending"),
                margin=dict(l=10, r=10, t=10, b=10), height=380,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=10)),
            )
            st.plotly_chart(fig6, use_container_width=True)

    # ── Row 4: Cities + Multinational ─────────────────────────────────────
    st.divider()
    col_city, col_multi = st.columns(2)

    with col_city:
        st.subheader("Top Trial Cities in China")
        city_series = (
            df["china_cities"].dropna().str.split("|").explode()
            .str.strip().replace("", pd.NA).dropna()
        )
        city_counts = city_series.value_counts().reset_index().head(15)
        city_counts.columns = ["City", "Count"]
        if city_counts.empty:
            no_data_msg()
        else:
            fig7 = px.bar(
                city_counts, x="Count", y="City", orientation="h",
                color="Count", color_continuous_scale="Purples", template="plotly_white",
            )
            fig7.update_layout(
                showlegend=False, coloraxis_showscale=False,
                yaxis=dict(categoryorder="total ascending"),
                margin=dict(l=10, r=10, t=10, b=10), height=380,
            )
            st.plotly_chart(fig7, use_container_width=True)

    with col_multi:
        st.subheader("China-Only vs. Multinational Trials")
        multi_year = (
            df[df["start_year"].between(2015, 2025)]
            .groupby(["start_year", "is_multinational"]).size().reset_index(name="count")
        )
        multi_year["type"] = multi_year["is_multinational"].map(
            {True: "Multinational", False: "China-Only"}
        )
        if multi_year.empty:
            no_data_msg()
        else:
            fig8 = px.bar(
                multi_year, x="start_year", y="count", color="type", barmode="stack",
                template="plotly_white",
                labels={"start_year": "Year", "count": "Trials", "type": ""},
                color_discrete_map={"Multinational": "#5C6BC0", "China-Only": "#26C6DA"},
            )
            fig8.update_layout(
                margin=dict(l=10, r=10, t=10, b=10), height=380,
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
            )
            st.plotly_chart(fig8, use_container_width=True)

    # ── Key Observations ───────────────────────────────────────────────────
    st.divider()
    st.subheader("Key Observations")

    cn_pct       = round(100 * len(china_sponsored) / max(len(df), 1))
    mnc_pct      = round(100 * len(mnc_sponsored)   / max(len(df), 1))
    top_cancer   = df["cancer_type"].value_counts().index[0] if len(df) > 0 else "N/A"
    top_modality = df["modality"].value_counts().index[0]    if len(df) > 0 else "N/A"
    china_recent = df[(df["start_year"] >= 2020) & (df["sponsor_origin"] == "Chinese Biotech/Pharma")]
    mnc_recent   = df[(df["start_year"] >= 2020) & (df["sponsor_origin"] == "MNC")]

    for insight in [
        f"**Pipeline concentration:** {top_cancer} dominates, reflecting China's high disease burden "
        "and established clinical infrastructure in this indication.",
        f"**Sponsor shift:** Chinese biotech/pharma accounts for {cn_pct}% of trials vs. MNCs at {mnc_pct}%, "
        f"suggesting growing domestic R&D capability — especially post-2020 ({len(china_recent):,} Chinese "
        f"vs {len(mnc_recent):,} MNC trial initiations).",
        f"**Modality trend:** {top_modality} is the leading therapeutic class, consistent with the global "
        "push toward targeted and immuno-oncology approaches.",
        f"**Globalization:** {df['is_multinational'].sum():,} ({round(100*df['is_multinational'].mean())}%) "
        "trials include non-China sites, indicating increasing international collaboration.",
    ]:
        st.markdown(f"<div class='insight-box'>• {insight}</div>", unsafe_allow_html=True)

    # ── Raw data table ─────────────────────────────────────────────────────
    st.divider()
    with st.expander("📋 Browse Raw Data"):
        display_cols = [c for c in
                        ["nct_id", "title", "cancer_type", "phase_clean", "modality",
                         "sponsor_name", "sponsor_parent", "sponsor_origin",
                         "status_label", "start_year", "is_multinational", "china_cities"]
                        if c in df.columns]
        col_labels = {
            "nct_id": "NCT ID", "title": "Title", "cancer_type": "Cancer Type",
            "phase_clean": "Phase", "modality": "Modality",
            "sponsor_name": "Sponsor (original)", "sponsor_parent": "Sponsor (consolidated)",
            "sponsor_origin": "Sponsor Origin", "status_label": "Status",
            "start_year": "Start Year", "is_multinational": "Multinational",
            "china_cities": "China Cities",
        }
        st.dataframe(
            df[display_cols].rename(columns=col_labels),
            use_container_width=True, height=400,
        )
        st.download_button(
            "⬇️ Download CSV", df.to_csv(index=False),
            file_name="china_oncology_trials.csv", mime="text/csv",
        )

with tab_compare:
    _compare_content(df)