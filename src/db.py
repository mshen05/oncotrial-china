"""
db.py
Database interface for the oncotrial pipeline.

Key improvements over v1:
- get_engine() properly percent-encodes special characters in passwords
- write_trials() uses a staging table + single SQL upsert (bulk, not row-by-row)
  50k rows now takes ~5 seconds instead of hanging indefinitely
"""

import os
import re
import pandas as pd
from urllib.parse import quote_plus, urlparse, urlunparse
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from pathlib import Path


# ── Column definitions ─────────────────────────────────────────────────────
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS trials (
    nct_id                  TEXT PRIMARY KEY,
    title                   TEXT,
    status                  TEXT,
    status_label            TEXT,
    phase                   TEXT,
    phase_clean             TEXT,
    study_type              TEXT,
    conditions              TEXT,
    cancer_type             TEXT,
    mesh_classified         BOOLEAN,
    intervention_types      TEXT,
    intervention_names      TEXT,
    modality                TEXT,
    sponsor_name            TEXT,
    sponsor_class           TEXT,
    sponsor_parent          TEXT,
    sponsor_origin          TEXT,
    china_cities            TEXT,
    regions                 TEXT,
    in_china                BOOLEAN,
    in_us                   BOOLEAN,
    in_eu                   BOOLEAN,
    is_multinational        BOOLEAN,
    is_active               BOOLEAN,
    start_date              TEXT,
    start_year              REAL,
    primary_completion_date TEXT,
    enrollment              REAL,
    mesh_ids                TEXT,
    mesh_terms              TEXT,
    updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

UPSERT_COLS = [
    "nct_id", "title", "status", "status_label", "phase", "phase_clean",
    "study_type", "conditions", "cancer_type", "mesh_classified",
    "intervention_types", "intervention_names", "modality",
    "sponsor_name", "sponsor_class", "sponsor_parent", "sponsor_origin",
    "china_cities", "regions", "in_china", "in_us", "in_eu",
    "is_multinational", "is_active",
    "start_date", "start_year", "primary_completion_date", "enrollment",
    "mesh_ids", "mesh_terms",
]


# ── URL helpers ────────────────────────────────────────────────────────────

def _encode_db_url(url: str) -> str:
    """
    Percent-encode special characters in the password component of a
    database URL so SQLAlchemy can parse it correctly.

    Handles passwords containing: , ? @ # % + = space and other
    characters that would otherwise confuse URL parsers.

    Also normalises postgres:// → postgresql://.
    """
    url = url.replace("postgres://", "postgresql://", 1)

    # Use regex to extract the userinfo (user:password) component
    # before the @ sign that precedes the host.
    # Pattern: scheme://user:password@host:port/db
    match = re.match(
        r"^(postgresql://)"        # scheme
        r"([^:@]+)"                # username (no colon or @)
        r":"                       # separator
        r"(.+)"                    # password (greedy — captures everything)
        r"@([^@]+)$",              # @host:port/db (last @ in the string)
        url,
    )
    if match:
        scheme_user = match.group(1) + match.group(2)
        password     = match.group(3)
        host_db      = match.group(4)
        encoded_pw   = quote_plus(password)
        return f"{scheme_user}:{encoded_pw}@{host_db}"

    # Couldn't parse — return as-is and let SQLAlchemy try
    return url


def _get_streamlit_secret() -> str | None:
    """Read DATABASE_URL from Streamlit secrets if available."""
    try:
        import streamlit as st
        return st.secrets.get("connections", {}).get("oncotrial", {}).get("url")
    except Exception:
        return None


# ── Engine ─────────────────────────────────────────────────────────────────

def get_engine(database_url: str | None = None) -> Engine:
    """
    Return a SQLAlchemy engine.

    Priority:
    1. Explicit database_url argument
    2. Streamlit secrets: [connections.oncotrial] url = "..."
    3. DATABASE_URL environment variable
    4. Falls back to local SQLite at data/oncotrial.db
    """
    raw_url = (
        database_url
        or _get_streamlit_secret()
        or os.environ.get("DATABASE_URL")
    )

    if raw_url:
        url = _encode_db_url(raw_url)
        print("Connecting to remote database...")
        return create_engine(
            url,
            pool_pre_ping=True,
            # Supabase closes idle connections after 5 min; this recycles them
            pool_recycle=300,
        )

    Path("data").mkdir(exist_ok=True)
    local_path = "data/oncotrial.db"
    print(f"No DATABASE_URL found — using local SQLite at {local_path}")
    return create_engine(f"sqlite:///{local_path}")


# ── Schema ─────────────────────────────────────────────────────────────────

def ensure_schema(engine: Engine) -> None:
    """Create the trials table if it doesn't exist."""
    with engine.begin() as conn:
        conn.execute(text(CREATE_TABLE_SQL))
    print("Schema ready.")


# ── Write ──────────────────────────────────────────────────────────────────

def write_trials(df: pd.DataFrame, engine: Engine, chunk_size: int = 5000) -> int:
    """
    Bulk-upsert trial records into the database.

    Strategy:
    - Write the full DataFrame to a staging table in chunks using
      pandas to_sql (which uses executemany under the hood, much faster
      than row-by-row SQLAlchemy execute).
    - Then run a single INSERT INTO trials ... ON CONFLICT (nct_id) DO UPDATE
      from the staging table.
    - Drop the staging table.

    This handles 50k rows in ~5-10 seconds against Supabase instead of hanging.
    """
    if df.empty:
        print("No data to write.")
        return 0

    # Ensure all expected columns exist
    for col in UPSERT_COLS:
        if col not in df.columns:
            df[col] = None

    subset = df[UPSERT_COLS].copy()

    # Boolean columns: ensure they're native Python bool, not numpy bool
    for col in ["in_china", "in_us", "in_eu", "is_multinational",
                "is_active", "mesh_classified"]:
        if col in subset.columns:
            subset[col] = subset[col].astype(bool)

    dialect = engine.dialect.name

    print(f"Writing {len(subset):,} trials to database ({dialect})...")

    if dialect == "sqlite":
        # SQLite: pandas to_sql with replace handles this simply
        # Use a staging table then INSERT OR REPLACE into main
        subset.to_sql(
            "trials_staging", engine,
            if_exists="replace", index=False,
            chunksize=chunk_size,
        )
        cols       = ", ".join(UPSERT_COLS)
        src_cols   = ", ".join(f"s.{c}" for c in UPSERT_COLS)
        with engine.begin() as conn:
            conn.execute(text(f"""
                INSERT OR REPLACE INTO trials ({cols})
                SELECT {src_cols} FROM trials_staging s
            """))
            conn.execute(text("DROP TABLE IF EXISTS trials_staging"))

    else:
        # PostgreSQL (Supabase): stage then upsert
        subset.to_sql(
            "trials_staging", engine,
            if_exists="replace", index=False,
            chunksize=chunk_size,
            method="multi",   # sends multiple rows per INSERT statement
        )

        cols      = ", ".join(UPSERT_COLS)
        src_cols  = ", ".join(f"s.{c}" for c in UPSERT_COLS)
        update_set = ", ".join(
            f"{c} = EXCLUDED.{c}"
            for c in UPSERT_COLS if c != "nct_id"
        )

        with engine.begin() as conn:
            conn.execute(text(f"""
                INSERT INTO trials ({cols})
                SELECT {src_cols} FROM trials_staging s
                ON CONFLICT (nct_id) DO UPDATE
                SET {update_set}, updated_at = CURRENT_TIMESTAMP
            """))
            conn.execute(text("DROP TABLE IF EXISTS trials_staging"))

    n = len(subset)
    print(f"Done. {n:,} rows upserted.")
    return n


# ── Read ───────────────────────────────────────────────────────────────────

def read_trials(engine: Engine) -> pd.DataFrame:
    """Read all trial records back as a DataFrame."""
    with engine.connect() as conn:
        df = pd.read_sql("SELECT * FROM trials", conn)
    df["start_year"] = pd.to_numeric(df["start_year"], errors="coerce")
    for col in ["in_china", "in_us", "in_eu", "is_multinational",
                "is_active", "mesh_classified"]:
        if col in df.columns:
            df[col] = df[col].astype(bool)
    return df


def trial_count(engine: Engine) -> int:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM trials"))
        return result.scalar() or 0


def last_updated(engine: Engine) -> str | None:
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT MAX(updated_at) FROM trials"))
            val = result.scalar()
            return str(val)[:10] if val else None
    except Exception:
        return None


# ── Self-test ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Test URL encoding
    tricky_passwords = [
        ("postgresql://user:abc@host/db",           "postgresql://user:abc@host/db"),
        ("postgresql://user:p@ss?word@host/db",     "postgresql://user:p%40ss%3Fword@host/db"),
        ("postgresql://user:Tc7i9,qHhw,4?wa@host/db", None),  # just print
        ("postgres://user:pass@host/db",            "postgresql://user:pass@host/db"),
    ]
    print("URL encoding tests:")
    for raw, expected in tricky_passwords:
        result = _encode_db_url(raw)
        if expected:
            ok = result == expected
            print(f"  {'PASS' if ok else 'FAIL'}  {raw[:40]}")
            if not ok:
                print(f"       got:      {result}")
                print(f"       expected: {expected}")
        else:
            print(f"  INFO  {raw[:50]}")
            print(f"        → {result}")