# src/load_seed.py
# Robust loader for FDA inspection CSV variants (semicolon/comma/etc; flexible headers)
# Loads into SQLite: db/state_demo.db -> table inspections

import csv
import sqlite3
from pathlib import Path
from datetime import datetime

import pandas as pd

# ---- Paths (inline for Sprint-1; you can switch to config.py later if you like) ----
ROOT = Path(__file__).resolve().parents[1]
DB_PATH    = ROOT / "db" / "state_demo.db"
SCHEMA_SQL = ROOT / "src" / "schema_sqlite.sql"
CSV_PATH   = ROOT / "data" / "staged" / "inspections.csv"


# ---- Helpers -----------------------------------------------------------------------

def sniff_delimiter(path: Path, sample_bytes: int = 131072) -> str:
    """Detect CSV delimiter; default to ',' if unsure."""
    with path.open("rb") as f:
        sample = f.read(sample_bytes)
    text = sample.decode("utf-8-sig", errors="replace")
    try:
        return csv.Sniffer().sniff(text, delimiters=[",", ";", "|", "\t"]).delimiter
    except Exception:
        return ","


def norm(s: str) -> str:
    """Normalize a header name: lowercase, remove non-alnum except spaces, collapse spaces."""
    import re
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9/ ]+", " ", s)     # keep slash for 'country/area'
    s = re.sub(r"\s+", " ", s).strip()
    return s


def build_column_index(columns) -> dict:
    """
    Build a lookup from normalized column name -> original name.
    If duplicates normalize the same, the first wins.
    """
    idx = {}
    for c in columns:
        n = norm(c)
        if n and n not in idx:
            idx[n] = c
    return idx


def pick(col_index: dict, candidates: list[str]) -> str | None:
    """
    Return the original column name whose normalized name matches any of the candidates.
    Candidates should be normalized keys (we'll normalize here too).
    """
    for c in candidates:
        nc = norm(c)
        if nc in col_index:
            return col_index[nc]
    return None


def clean_date(value: str) -> str | None:
    """Normalize to YYYY-MM-DD if possible; otherwise return original or None."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s  # leave as-is if unknown format


def filename_from_url(u: str) -> str | None:
    """Extract filename from URL; return None if not a usable URL."""
    if not u or not str(u).strip():
        return None
    from urllib.parse import urlparse
    from pathlib import Path as _P
    try:
        return _P(urlparse(str(u)).path).name or None
    except Exception:
        return None


# ---- Loader ------------------------------------------------------------------------

def load():
    # Ensure DB folder exists; open DB connection
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # Create/validate schema
    cur.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))
    con.commit()

    # Read CSV
    if not CSV_PATH.exists():
        print(f"⚠️  CSV not found: {CSV_PATH}. Schema created; nothing loaded.")
        con.close()
        return

    delim = sniff_delimiter(CSV_PATH)
    print(f"→ Using delimiter: {repr(delim)}  for {CSV_PATH.name}")

    try:
        df_raw = pd.read_csv(
            CSV_PATH,
            sep=delim,
            engine="python",
            dtype=str,
            encoding="utf-8-sig",
            keep_default_na=False,
            on_bad_lines="skip",
            skip_blank_lines=True,
            quotechar='"',
            skipinitialspace=True,
        )
    except pd.errors.ParserError as e:
        print(f"❌ ParserError: {e}")
        con.close()
        return

    if df_raw.empty:
        print("⚠️  CSV parsed but is empty; nothing to load.")
        con.close()
        return

    # Build header index
    col_index = build_column_index(df_raw.columns)

    # Candidate sets for multiple CSV variants
    c_inspection_id   = ["inspection id", "record id", "recordid", "id"]
    c_fei_number      = ["fei number", "fei", "fei_number"]
    c_firm_name       = ["legal name", "firm name", "name"]
    c_inspection_date = ["inspection end date", "record date", "inspection date", "date"]
    c_inspection_type = ["classification", "record type", "inspection type", "product type", "project area"]
    c_source_url      = ["download", "url", "link"]

    # Resolve actual columns present
    cols = {
        "inspection_id":   pick(col_index, c_inspection_id),
        "fei_number":      pick(col_index, c_fei_number),
        "firm_name":       pick(col_index, c_firm_name),
        "inspection_date": pick(col_index, c_inspection_date),
        "inspection_type": pick(col_index, c_inspection_type),
        "source_url":      pick(col_index, c_source_url),   # may be None in your current CSV
    }

    # Hard requirements: we need at least id + date + some name/type to make rows meaningful
    required = ["inspection_id", "fei_number", "firm_name", "inspection_date", "inspection_type"]
    missing = [k for k in required if cols[k] is None]
    if missing:
        # For your file, FEI Number / Legal Name / Inspection ID / Inspection End Date / Classification should resolve.
        raise KeyError(
            f"Missing required columns in CSV: {missing}. "
            f"Found headers: {list(df_raw.columns)}"
        )

    print("Resolved columns:")
    for k, v in cols.items():
        print(f"  {k:16} -> {v}")

    # Transform rows
    rows = []
    for _, r in df_raw.iterrows():
        # inspection_id: must be an integer-ish value
        raw_id = (r.get(cols["inspection_id"]) or "").strip()
        if not raw_id:
            continue
        try:
            inspection_id = int(raw_id)
        except Exception:
            # Sometimes 'Inspection ID' may have non-digit noise; skip those rows
            continue

        fei_number      = (r.get(cols["fei_number"]) or "").strip() or None
        firm_name       = (r.get(cols["firm_name"]) or "").strip() or None
        inspection_date = clean_date(r.get(cols["inspection_date"]))
        inspection_type = (r.get(cols["inspection_type"]) or "").strip() or None
        source_url      = (r.get(cols["source_url"]) or "").strip() or None
        source_doc      = filename_from_url(source_url)
        outcome         = inspection_type  # simple first-pass; can refine later

        rows.append((
            inspection_id, fei_number, firm_name, inspection_date,
            inspection_type, outcome, source_url or None, source_doc
        ))

    if not rows:
        print("⚠️  No valid rows to insert after parsing.")
        con.close()
        return

    # Insert
    cur.executemany(
        """
        INSERT OR REPLACE INTO inspections
          (inspection_id, fei_number, firm_name, inspection_date,
           inspection_type, outcome, source_url, source_doc)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        rows
    )
    con.commit()

    n = cur.execute("SELECT COUNT(*) FROM inspections;").fetchone()[0]
    print(f"✅ Loaded {len(rows)} row(s) from {CSV_PATH.name}. Total in DB: {n}")

    con.close()


if __name__ == "__main__":
    load()
