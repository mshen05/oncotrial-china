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
        border-radius: 6px;
        padding: 12px 16px;
        margin: 8px 0;
        font-size: 0.9em;
    }
    h1 { color: #1a1a2e; }
    .stPlotlyChart { border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

CLEAN_PATH = "data/clean_trials.csv"
RAW_PATH = "data/raw_trials.csv"


# ── Data loading ───────────────────────────────────────────────────────────
@st.cache_data
def load_data():
    if not Path(CLEAN_PATH).exists():
        return None
    df = pd.read_csv(CLEAN_PATH)
    df["start_year"] = pd.to_numeric(df["start_year"], errors="coerce")
    return df


def run_pipeline():
    with st.spinner("Fetching data from ClinicalTrials.gov... (this takes ~3-5 min)"):
        result = subprocess.run(
            [sys.executable, "src/fetch.py"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            st.error(f"Fetch failed:\n{result.stderr}")
            return False

    with st.spinner("Cleaning and classifying data..."):
        result = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0,'src'); from clean import clean; clean()"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            st.error(f"Clean failed:\n{result.stderr}")
            return False

    st.cache_data.clear()
    return True


# ── Sidebar ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🔬 Filters")

    df_raw = load_data()

    if df_raw is None:
        st.warning("No data yet. Click below to fetch.")
        if st.button("🚀 Fetch & Build Dataset", type="primary"):
            if run_pipeline():
                st.success("Done!")
                st.rerun()
        st.stop()

    # Year range
    min_year = int(df_raw["start_year"].min()) if not df_raw["start_year"].isna().all() else 2010
    max_year = int(df_raw["start_year"].max()) if not df_raw["start_year"].isna().all() else 2025
    year_range = st.slider("Trial Start Year", min_year, max_year, (2015, max_year))

    # Status filter
    status_options = sorted(df_raw["status"].dropna().unique())
    selected_statuses = st.multiselect("Status", status_options,
                                        default=["RECRUITING", "ACTIVE_NOT_RECRUITING",
                                                 "NOT_YET_RECRUITING", "COMPLETED"])

    # Phase filter
    phase_options = sorted(df_raw["phase_clean"].dropna().unique())
    selected_phases = st.multiselect("Phase", phase_options, default=phase_options)

    # Cancer type filter
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
df = df[df["start_year"].between(year_range[0], year_range[1], inclusive="both") |
        df["start_year"].isna()]
if selected_statuses:
    df = df[df["status"].isin(selected_statuses)]
if selected_phases:
    df = df[df["phase_clean"].isin(selected_phases)]
if selected_cancers:
    df = df[df["cancer_type"].isin(selected_cancers)]


# ── Header ─────────────────────────────────────────────────────────────────
st.title("China Oncology Clinical Trial Landscape")
st.caption(f"Based on {len(df_raw):,} trials with China locations · Source: ClinicalTrials.gov")

# ── KPI row ────────────────────────────────────────────────────────────────
col1, col2, col3, col4, col5 = st.columns(5)

active_df = df[df["is_active"] == True]
china_sponsored = df[df["sponsor_origin"] == "Chinese Biotech/Pharma"]
mnc_sponsored = df[df["sponsor_origin"] == "MNC"]

col1.metric("Total Trials (filtered)", f"{len(df):,}")
col2.metric("Active / Recruiting", f"{len(active_df):,}")
col3.metric("Chinese Sponsor", f"{len(china_sponsored):,}")
col4.metric("MNC Sponsor", f"{len(mnc_sponsored):,}")
col5.metric("Multinational Trials", f"{df['is_multinational'].sum():,}")

st.divider()

# ── Row 1: Cancer type distribution + Phase distribution ───────────────────
col_a, col_b = st.columns([3, 2])

with col_a:
    st.subheader("Trials by Cancer Type")
    cancer_counts = (
        df["cancer_type"].value_counts()
        .reset_index()
        .rename(columns={"cancer_type": "Cancer Type", "count": "Trials"})
        .head(15)
    )
    fig = px.bar(
        cancer_counts, x="Trials", y="Cancer Type",
        orientation="h",
        color="Trials",
        color_continuous_scale="Blues",
        template="plotly_white",
    )
    fig.update_layout(
        showlegend=False, coloraxis_showscale=False,
        yaxis=dict(categoryorder="total ascending"),
        margin=dict(l=10, r=10, t=10, b=10),
        height=420,
    )
    st.plotly_chart(fig, use_container_width=True)

with col_b:
    st.subheader("Phase Distribution")
    phase_counts = df["phase_clean"].value_counts().reset_index()
    phase_counts.columns = ["Phase", "Count"]
    phase_order = ["Phase 1", "Phase 1/2", "Phase 2", "Phase 2/3", "Phase 3", "Phase 4", "N/A", "Unknown"]
    phase_counts["Phase"] = pd.Categorical(phase_counts["Phase"], categories=phase_order, ordered=True)
    phase_counts = phase_counts.sort_values("Phase")

    fig2 = px.pie(
        phase_counts, names="Phase", values="Count",
        color_discrete_sequence=px.colors.sequential.Blues_r,
        template="plotly_white",
    )
    fig2.update_traces(textinfo="label+percent", pull=[0.03]*len(phase_counts))
    fig2.update_layout(
        showlegend=False,
        margin=dict(l=10, r=10, t=10, b=10),
        height=420,
    )
    st.plotly_chart(fig2, use_container_width=True)

# ── Row 2: Trends over time ────────────────────────────────────────────────
st.subheader("Trial Volume Trend (by Start Year)")

trend_col1, trend_col2 = st.columns([2, 1])

with trend_col1:
    trend = (
        df[df["start_year"].between(2010, 2025)]
        .groupby(["start_year", "sponsor_origin"])
        .size()
        .reset_index(name="count")
    )
    # Only show major categories
    major_origins = ["Chinese Biotech/Pharma", "MNC", "Academic/Hospital"]
    trend = trend[trend["sponsor_origin"].isin(major_origins)]

    fig3 = px.area(
        trend, x="start_year", y="count", color="sponsor_origin",
        template="plotly_white",
        labels={"start_year": "Year", "count": "Number of Trials", "sponsor_origin": "Sponsor Type"},
        color_discrete_map={
            "Chinese Biotech/Pharma": "#1565C0",
            "MNC": "#EF5350",
            "Academic/Hospital": "#43A047",
        }
    )
    fig3.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        height=320,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig3, use_container_width=True)

with trend_col2:
    st.subheader("Sponsor Landscape")
    origin_counts = df["sponsor_origin"].value_counts().reset_index()
    origin_counts.columns = ["Sponsor Origin", "Count"]
    fig4 = px.bar(
        origin_counts, x="Count", y="Sponsor Origin",
        orientation="h",
        color="Count",
        color_continuous_scale="Reds",
        template="plotly_white",
    )
    fig4.update_layout(
        showlegend=False, coloraxis_showscale=False,
        yaxis=dict(categoryorder="total ascending"),
        margin=dict(l=10, r=10, t=10, b=10),
        height=320,
    )
    st.plotly_chart(fig4, use_container_width=True)

# ── Row 3: Modality + Top sponsors ────────────────────────────────────────
st.divider()
col_mod, col_spon = st.columns(2)

with col_mod:
    st.subheader("Therapeutic Modality Mix")
    mod_counts = df["modality"].value_counts().reset_index().head(12)
    mod_counts.columns = ["Modality", "Count"]
    fig5 = px.bar(
        mod_counts, x="Count", y="Modality",
        orientation="h",
        color="Count",
        color_continuous_scale="Greens",
        template="plotly_white",
    )
    fig5.update_layout(
        showlegend=False, coloraxis_showscale=False,
        yaxis=dict(categoryorder="total ascending"),
        margin=dict(l=10, r=10, t=10, b=10),
        height=380,
    )
    st.plotly_chart(fig5, use_container_width=True)

with col_spon:
    st.subheader("Top 15 Sponsors")
    top_sponsors = df["sponsor_name"].value_counts().reset_index().head(15)
    top_sponsors.columns = ["Sponsor", "Trials"]

    # Color by origin
    sponsor_origin_map = (
        df.drop_duplicates("sponsor_name")
        .set_index("sponsor_name")["sponsor_origin"]
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
    top_sponsors["Color"] = top_sponsors["Origin"].map(color_map).fillna("#9E9E9E")

    fig6 = px.bar(
        top_sponsors, x="Trials", y="Sponsor",
        orientation="h",
        color="Origin",
        color_discrete_map=color_map,
        template="plotly_white",
    )
    fig6.update_layout(
        yaxis=dict(categoryorder="total ascending"),
        margin=dict(l=10, r=10, t=10, b=10),
        height=380,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=10)),
    )
    st.plotly_chart(fig6, use_container_width=True)

# ── Row 4: China cities + Multinational vs domestic ───────────────────────
st.divider()
col_city, col_multi = st.columns(2)

with col_city:
    st.subheader("Top Trial Cities in China")
    city_series = (
        df["china_cities"]
        .dropna()
        .str.split("|")
        .explode()
        .str.strip()
        .replace("", pd.NA)
        .dropna()
    )
    city_counts = city_series.value_counts().reset_index().head(15)
    city_counts.columns = ["City", "Count"]
    fig7 = px.bar(
        city_counts, x="Count", y="City",
        orientation="h",
        color="Count",
        color_continuous_scale="Purples",
        template="plotly_white",
    )
    fig7.update_layout(
        showlegend=False, coloraxis_showscale=False,
        yaxis=dict(categoryorder="total ascending"),
        margin=dict(l=10, r=10, t=10, b=10),
        height=380,
    )
    st.plotly_chart(fig7, use_container_width=True)

with col_multi:
    st.subheader("China-Only vs. Multinational Trials")

    multi_year = (
        df[df["start_year"].between(2015, 2025)]
        .groupby(["start_year", "is_multinational"])
        .size()
        .reset_index(name="count")
    )
    multi_year["type"] = multi_year["is_multinational"].map(
        {True: "Multinational", False: "China-Only"}
    )
    fig8 = px.bar(
        multi_year, x="start_year", y="count", color="type",
        barmode="stack",
        template="plotly_white",
        labels={"start_year": "Year", "count": "Trials", "type": ""},
        color_discrete_map={"Multinational": "#5C6BC0", "China-Only": "#26C6DA"},
    )
    fig8.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        height=380,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig8, use_container_width=True)

# ── Key Insights ───────────────────────────────────────────────────────────
st.divider()
st.subheader("Key Observations")

total_active = len(active_df)
cn_pct = round(100 * len(china_sponsored) / max(len(df), 1))
mnc_pct = round(100 * len(mnc_sponsored) / max(len(df), 1))

top_cancer = df["cancer_type"].value_counts().index[0] if len(df) > 0 else "N/A"
top_modality = df["modality"].value_counts().index[0] if len(df) > 0 else "N/A"

china_recent = df[(df["start_year"] >= 2020) & (df["sponsor_origin"] == "Chinese Biotech/Pharma")]
mnc_recent = df[(df["start_year"] >= 2020) & (df["sponsor_origin"] == "MNC")]

insights = [
    f"**Pipeline concentration:** {top_cancer} dominates, reflecting China's high disease burden and established clinical infrastructure in this indication.",
    f"**Sponsor shift:** Chinese biotech/pharma accounts for {cn_pct}% of trials vs. MNCs at {mnc_pct}%, suggesting growing domestic R&D capability — especially in post-2020 trial initiations ({len(china_recent):,} Chinese vs {len(mnc_recent):,} MNC).",
    f"**Modality trend:** {top_modality} is the leading therapeutic class, consistent with the global push toward targeted and immuno-oncology approaches.",
    f"**Globalization:** {df['is_multinational'].sum():,} ({round(100*df['is_multinational'].mean())}%) trials include non-China sites, indicating increasing international collaboration.",
]

for insight in insights:
    st.markdown(f"<div class='insight-box'>• {insight}</div>", unsafe_allow_html=True)

# ── Raw data table ─────────────────────────────────────────────────────────
st.divider()
with st.expander("📋 Browse Raw Data"):
    display_cols = ["nct_id", "title", "cancer_type", "phase_clean", "modality",
                    "sponsor_name", "sponsor_origin", "status", "start_year",
                    "is_multinational", "china_cities"]
    st.dataframe(
        df[display_cols].rename(columns={
            "nct_id": "NCT ID", "title": "Title",
            "cancer_type": "Cancer Type", "phase_clean": "Phase",
            "modality": "Modality", "sponsor_name": "Sponsor",
            "sponsor_origin": "Sponsor Origin", "status": "Status",
            "start_year": "Start Year", "is_multinational": "Multinational",
            "china_cities": "China Cities",
        }),
        use_container_width=True,
        height=400,
    )
    st.download_button(
        "⬇️ Download CSV",
        df.to_csv(index=False),
        file_name="china_oncology_trials.csv",
        mime="text/csv",
    )
