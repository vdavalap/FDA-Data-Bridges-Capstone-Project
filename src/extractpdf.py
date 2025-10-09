# src/extractpdf.py
from __future__ import annotations
import re, glob, sqlite3, hashlib
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import fitz  # PyMuPDF


# ===== Paths =====
ROOT    = Path(__file__).resolve().parents[2]          # .../FDA-Data-Bridges-Capstone-Project
RAW_DIR = ROOT / "data" / "raw"
DB_PATH = ROOT / "db" / "state_demo.db"


# ===== Utilities =====
def clean(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()

def only_digits(s: Optional[str]) -> str:
    return re.sub(r"\D+", "", s or "")

def sha_int(*parts: str, mod: int = 10**9) -> int:
    h = hashlib.sha1("||".join(parts).encode("utf-8")).hexdigest()
    return int(h[:12], 16) % mod

def extract_all_text(pdf_path: Path) -> Tuple[str, List[str]]:
    doc = fitz.open(pdf_path)
    pages = []
    for i in range(doc.page_count):
        pages.append(doc.load_page(i).get_text("text"))
    doc.close()
    full = "\n".join(pages)
    return full, full.splitlines()

def drop_district_box(full_text: str) -> str:
    """
    Removing the 'DISTRICT ADDRESS AND PHONE NUMBER' block so it doesn't
    misread the firm city/state parsing.
    """
    pattern = (
        r"(DISTRICT\s+ADDRESS\s+AND\s+PHONE\s+NUMBER.*?)"
        r"(?=\n\s*\n|NAME\s+AND\s+TITLE\s+OF\s+INDIVIDUAL|FIRM\s+NAME|STREET\s+ADDRESS|CITY[, ]\s*STATE|$)"
    )
    return re.sub(pattern, "", full_text, flags=re.I | re.S)

def find_fei(full_text: str, lines: List[str]) -> Optional[str]:
    # Inline FEI patterns
    m = re.search(r"\bFEI\s*(?:NUMBER|NO\.|#)?\s*[:\-]?\s*([0-9][0-9\-\s]{5,})\b", full_text, flags=re.I)
    if m:
        d = only_digits(m.group(1))
        if 6 <= len(d) <= 12:
            return d
    # Two-line layouts (label on one line, digits on the next)
    for i, line in enumerate(lines):
        if re.search(r"\bFEI\s*(?:NUMBER|NO\.|#)?\b", line, flags=re.I):
            for j in (i + 1, i + 2):
                if j < len(lines):
                    d = only_digits(lines[j])
                    if 6 <= len(d) <= 12:
                        return d
    # Fallback: digits near 'FEI'
    for line in lines:
        if "FEI" in line.upper():
            m = re.search(r"([0-9][0-9\-\s]{5,})", line)
            if m:
                d = only_digits(m.group(1))
                if 6 <= len(d) <= 12:
                    return d
    return None

def extract_header_fields(txt: str) -> Dict[str, str]:
    out: Dict[str, str] = {}

    # Firm name / legal name
    m = re.search(r"(?:FIRM\s*NAME|LEGAL\s*NAME|NAME\s*OF\s*FIRM)\s*[:\s]*([^\n]+)", txt, flags=re.I)
    if m:
        out["firm_name"] = clean(m.group(1))

    # Street address
    m = re.search(r"(?:STREET\s*ADDRESS|ADDRESS)\s*[:\s]*([^\n]+)", txt, flags=re.I)
    if m:
        out["address"] = clean(m.group(1))

    # City, ST ZIP
    m = re.search(r"\b([A-Za-z .'\-]+),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)\b", txt)
    if m:
        out.setdefault("city",  clean(m.group(1)))
        out.setdefault("state", clean(m.group(2)))
        out.setdefault("zip",   clean(m.group(3)))
        out.setdefault("country", "United States")

    # Fallbacks if still missing
    if "city" not in out:
        m = re.search(r"\bCITY\b\s*[:\s]*([^\n]+)", txt, flags=re.I)
        if m: out["city"] = clean(m.group(1))

    if "state" not in out:
        m = re.search(r"\bSTATE\b\s*[:\s]*([A-Z]{2})(?:\s|$)", txt, flags=re.I)
        if m: out["state"] = clean(m.group(1))

    if "zip" not in out:
        m = re.search(r"\bZIP(?:\s*CODE)?\b\s*[:\s]*([0-9]{5}(?:-\d{4})?)", txt, flags=re.I)
        if m: out["zip"] = clean(m.group(1))

    if "country" not in out:
        m = re.search(r"\bCOUNTRY\b\s*[:\s]*([^\n]+)", txt, flags=re.I)
        if m: out["country"] = clean(m.group(1))

    return out


# ===== DB helpers (no new tables are created) =====
def table_columns(cur: sqlite3.Cursor, table: str) -> List[str]:
    cur.execute(f"PRAGMA table_info({table});")
    return [row[1] for row in cur.fetchall()]

def inspections_exists(cur: sqlite3.Cursor) -> bool:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='inspections';")
    return cur.fetchone() is not None

def observations_exists(cur: sqlite3.Cursor) -> bool:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='observations';")
    return cur.fetchone() is not None

def find_or_create_inspection(cur: sqlite3.Cursor, i_cols: List[str], info: Dict[str, str], source_doc: str) -> int:
    """
    Tries to find an existing inspection_id by FEI or by (firm_name, city, state).
    If none is found and 'inspections' exists, insert a minimal inspection row
    so the FK in 'observations' will be satisfied.
    """
    fei = info.get("fei_number")
    firm = info.get("firm_name")
    city = info.get("city")
    state = info.get("state")

    # 1) Match by FEI when available
    if fei and "fei_number" in i_cols:
        cur.execute("SELECT inspection_id FROM inspections WHERE fei_number = ? ORDER BY inspection_id DESC LIMIT 1;", (fei,))
        row = cur.fetchone()
        if row:
            return int(row[0])

    # 2) Fallback: match by (firm_name, city, state)
    if firm and city and state and {"firm_name","city","state"}.issubset(i_cols):
        cur.execute("""
            SELECT inspection_id
            FROM inspections
            WHERE firm_name = ? AND city = ? AND state = ?
            ORDER BY inspection_id DESC LIMIT 1;
        """, (firm, city, state))
        row = cur.fetchone()
        if row:
            return int(row[0])

    # 3) Create a minimal inspection row (only if table exists)
    #    Choose an inspection_id that is stable per (fei or firm) + source_doc
    base = fei if fei else f"{firm}|{city}|{state}"
    if not base:
        base = source_doc
    inspection_id = sha_int(base, source_doc)

    # Build insert using available columns only
    cols = ["inspection_id"]
    vals = [inspection_id]
    if "fei_number" in i_cols:      cols.append("fei_number");      vals.append(fei)
    if "firm_name" in i_cols:       cols.append("firm_name");       vals.append(firm)
    if "address" in i_cols:         cols.append("address");         vals.append(info.get("address"))
    if "city" in i_cols:            cols.append("city");            vals.append(city)
    if "state" in i_cols:           cols.append("state");           vals.append(state)
    if "zip" in i_cols:             cols.append("zip");             vals.append(info.get("zip"))
    if "country_area" in i_cols:    cols.append("country_area");    vals.append(info.get("country") or info.get("country_area"))
    elif "country" in i_cols:       cols.append("country");         vals.append(info.get("country"))
    if "source_doc" in i_cols:      cols.append("source_doc");      vals.append(source_doc)

    placeholders = ",".join("?" for _ in cols)
    cur.execute(f"INSERT OR IGNORE INTO inspections ({','.join(cols)}) VALUES ({placeholders});", vals)
    return inspection_id


def insert_observation_snapshot(cur: sqlite3.Cursor,
                                o_cols: List[str],
                                inspection_id: int,
                                info: Dict[str, str],
                                source_doc: str,
                                source_page: int = 1):
    """
    Insert a single 'Metadata' observation row summarizing the header fields.
    Adapts to whatever columns exist in 'observations' (no schema changes).
    """
    # Build a compact text payload
    text = (
        f"FEI Number: {info.get('fei_number','-')} | "
        f"Firm: {info.get('firm_name','-')} | "
        f"Address: {info.get('address','-')} | "
        f"City: {info.get('city','-')} | "
        f"State: {info.get('state','-')} | "
        f"ZIP: {info.get('zip','-')} | "
        f"Country: {info.get('country','-')}"
    )

    cols = ["inspection_id"]
    vals = [inspection_id]

    # Required-ish fields we try to set if present
    if "category"   in o_cols: cols.append("category");    vals.append("Metadata")
    if "severity"   in o_cols: cols.append("severity");    vals.append("Low")
    if "is_repeat"  in o_cols: cols.append("is_repeat");   vals.append(0)
    if "text"       in o_cols: cols.append("text");        vals.append(text)
    if "source_doc" in o_cols: cols.append("source_doc");  vals.append(source_doc)
    if "source_page"in o_cols: cols.append("source_page"); vals.append(source_page)

    # If your observations table also has these extra columns, we fill them
    if "fei_number" in o_cols:  cols.append("fei_number");  vals.append(info.get("fei_number"))
    if "firm_name"  in o_cols:  cols.append("firm_name");   vals.append(info.get("firm_name"))
    if "city"       in o_cols:  cols.append("city");        vals.append(info.get("city"))
    if "state"      in o_cols:  cols.append("state");       vals.append(info.get("state"))
    if "zip"        in o_cols:  cols.append("zip");         vals.append(info.get("zip"))
    if "country"    in o_cols:  cols.append("country");     vals.append(info.get("country"))

    placeholders = ",".join("?" for _ in cols)
    cur.execute(f"INSERT INTO observations ({','.join(cols)}) VALUES ({placeholders});", vals)


# ===== Main =====
def main():
    print(f"DB:   {DB_PATH}")
    print(f"RAW:  {RAW_DIR}")

    pdfs = sorted(glob.glob(str(RAW_DIR / "*.pdf"))) + sorted(glob.glob(str(RAW_DIR / "*.PDF")))
    if not pdfs:
        print("No PDFs found in data/raw. Add 483/EIR PDFs and re-run.")
        return

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    if not observations_exists(cur):
        con.close()
        print("ERROR: 'observations' table not found. Load your schema / seed first.")
        return

    o_cols = table_columns(cur, "observations")
    i_cols = table_columns(cur, "inspections") if inspections_exists(cur) else []

    for p in pdfs:
        pdfp = Path(p)
        full, lines = extract_all_text(pdfp)
        full = drop_district_box(full)

        # Parse header fields
        info = extract_header_fields(full)
        fei  = find_fei(full, lines)
        if fei:
            info["fei_number"] = fei

        # Find or create an inspection_id (to satisfy FK on observations)
        if i_cols:
            inspection_id = find_or_create_inspection(cur, i_cols, info, pdfp.name)
        else:
            # If 'inspections' table doesn’t exist, we cannot satisfy FK reliably.
            # Use a stable synthetic id and hope FK is not enforced; otherwise advise user to seed CSV first.
            inspection_id = sha_int(info.get("fei_number",""), pdfp.name)

        # Log
        print(
            f"• {pdfp.name:42s} | "
            f"FEI: {info.get('fei_number','-'):>6s} | "
            f"{info.get('firm_name','-')} | "
            f"{info.get('city','-')}, {info.get('state','-')} {info.get('zip','-')} | "
            f"{info.get('country','-')}"
        )

        # Insert a single metadata observation snapshot
        insert_observation_snapshot(cur, o_cols, inspection_id, info, pdfp.name)
        con.commit()

    con.close()
    print("\n✅ Done. Inserted one metadata observation per PDF into 'observations' (no new tables).")


if __name__ == "__main__":
    main()
