# src/load_seed.py
import sqlite3
import csv
from pathlib import Path
from datetime import datetime
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB   = ROOT / "db" / "state_demo.db"
DDL  = ROOT / "src" / "schema_sqlite.sql"
CSV  = ROOT / "data" / "staged" / "inspections.csv"

def sniff_delimiter(path: Path, sample_bytes: int = 65536) -> str:
    with path.open("rb") as f:
        text = f.read(sample_bytes).decode("utf-8-sig", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(text, delimiters=[",",";","\t","|"])
        return dialect.delimiter
    except Exception:
        return ";"  # your file uses semicolons

def yes_no_to_int(v):
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in ("yes","y","true","1"): return 1
    if s in ("no","n","false","0",""): return 0
    return None

def to_date(s):
    if s is None: return None
    s = str(s).strip()
    if not s: return None
    for fmt in ("%m/%d/%Y","%Y-%m-%d","%m-%d-%Y","%d-%m-%Y"):
        try: return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError: pass
    return s

def resolve_required(df: pd.DataFrame, wanted: dict[str, list[str]]) -> dict[str,str]:
    norm = {c.lower().strip(): c for c in df.columns}
    picked = {}
    for target, candidates in wanted.items():
        found = None
        for cand in candidates:
            key = cand.lower().strip()
            if key in norm:
                found = norm[key]; break
        if not found:
            raise KeyError(
                f"Missing required column for '{target}'. "
                f"Tried: {candidates}. Found headers: {list(df.columns)}"
            )
        picked[target] = found
    return picked

def resolve_optional(df: pd.DataFrame, wanted_opt: dict[str, list[str]]) -> dict[str,str]:
    norm = {c.lower().strip(): c for c in df.columns}
    picked = {}
    for target, candidates in wanted_opt.items():
        for cand in candidates:
            key = cand.lower().strip()
            if key in norm:
                picked[target] = norm[key]; break
    return picked

def load():
    if not CSV.exists():
        raise FileNotFoundError(f"{CSV} not found. Put your file in data/staged and retry.")

    delim = sniff_delimiter(CSV)
    print(f"→ Using delimiter: {repr(delim)}")

    df = pd.read_csv(
        CSV, dtype=str, sep=delim, engine="python", encoding="utf-8-sig", keep_default_na=False
    )

    # REQUIRED columns (must be present)
    required = {
        "inspection_id":       ["Inspection ID","inspection id","record id"],
        "fei_number":          ["FEI Number","fei number"],
        "firm_name":           ["Legal Name","legal name"],
        "city":                ["City"],
        "state":               ["State"],
        "zip":                 ["Zip","Postal Code"],
        "country_area":        ["Country/Area","Country"],
        "fiscal_year":         ["Fiscal Year","FY"],
        "posted_citations":    ["Posted Citations"],
        "inspection_end_date": ["Inspection End Date","Record Date","Inspection Date"],
        "classification":      ["Classification"],
        "project_area":        ["Project Area"],
        "product_type":        ["Product Type"],
    }
    # OPTIONAL columns (map if present; otherwise ignore silently)
    optional = {
        "source_url": ["Download","URL","Link"]
    }

    cols = resolve_required(df, required)
    cols.update(resolve_optional(df, optional))

    print("Resolved columns:")
    for k, v in cols.items():
        print(f"  {k:<20} <- {v}")

    # Create DB/schema
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.executescript(DDL.read_text(encoding="utf-8"))
    con.commit()

    rows = []
    for _, r in df.iterrows():
        raw_id = str(r[cols["inspection_id"]]).strip()
        if not raw_id.isdigit():
            continue
        inspection_id = int(raw_id)

        fei_number   = r[cols["fei_number"]].strip() or None
        firm_name    = r[cols["firm_name"]].strip() or None
        city         = r[cols["city"]].strip() or None
        state        = r[cols["state"]].strip() or None
        zip_code     = r[cols["zip"]].strip() or None
        country_area = r[cols["country_area"]].strip() or None

        fy_raw      = r[cols["fiscal_year"]].strip()
        fiscal_year = int(fy_raw) if fy_raw.isdigit() else None

        posted      = yes_no_to_int(r[cols["posted_citations"]])
        end_date    = to_date(r[cols["inspection_end_date"]])
        classif     = r[cols["classification"]].strip() or None
        project     = r[cols["project_area"]].strip() or None
        product     = r[cols["product_type"]].strip() or None

        src_url = None
        src_doc = None
        if "source_url" in cols:
            src_url = r[cols["source_url"]].strip() or None
            src_doc = Path(src_url).name if src_url else None

        rows.append((
            inspection_id, fei_number, firm_name, city, state, zip_code, country_area,
            fiscal_year, posted, end_date, classif, project, product, src_url, src_doc
        ))

    cur.executemany("""
        INSERT OR REPLACE INTO inspections
        (inspection_id, fei_number, firm_name, city, state, zip, country_area,
         fiscal_year, posted_citations, inspection_end_date, classification,
         project_area, product_type, source_url, source_doc)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, rows)

    con.commit()
    n = cur.execute("SELECT COUNT(*) FROM inspections;").fetchone()[0]
    print(f"✅ Loaded {n} rows into inspections")
    con.close()

if __name__ == "__main__":
    load()
