#!/usr/bin/env python3
import os
import json
import time
import random
import sqlite3
import argparse
from pathlib import Path
from typing import Dict, Iterable, List, Optional
import requests

# ----------------------------
# Optional .env (falls back to OS env)
# ----------------------------
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except Exception:
    pass

# ----------------------------
# Config / Paths
# ----------------------------
ROOT    = Path(__file__).resolve().parents[1]       # .../src -> repo root
RAW_DIR = ROOT / "data" / "raw" / "ires"
DB_PATH = ROOT / "db" / "state_demo.db"

RAW_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

BASE_API = os.getenv("FDA_DD_BASE_API", "https://www.accessdata.fda.gov/ires/api")

AUTH_USER = os.getenv("FDA_DD_API_USER")
AUTH_KEY  = os.getenv("FDA_DD_API_KEY")

SESSION = requests.Session()
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101 Firefox/125.0",
]

def today_bucket() -> Path:
    p = RAW_DIR / time.strftime("%Y%m%d")
    p.mkdir(parents=True, exist_ok=True)
    return p

def jitter(seconds: float) -> float:
    """±15% jitter."""
    return max(1.0, seconds * random.uniform(0.85, 1.15))

# ----------------------------
# DB schema (citations)
# ----------------------------
def ensure_tables(cur: sqlite3.Cursor):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS inspections_citations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ObservationNumber TEXT,
            InspectionID TEXT,
            Citation TEXT,
            ShortDescription TEXT,
            LongDescription TEXT,
            FEINumber TEXT,
            LegalName TEXT,
            City TEXT,
            State TEXT,
            ZipCode TEXT,
            CountryArea TEXT,
            InspectionEndDate TEXT,
            ProductType TEXT,
            ProjectArea TEXT,
            source TEXT DEFAULT 'ires',
            ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Avoid hard duplicates
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_citations_observation
        ON inspections_citations (ObservationNumber, InspectionID)
    """)

def insert_citation(cur: sqlite3.Cursor, row: Dict):
    cur.execute("""
        INSERT OR IGNORE INTO inspections_citations
        (ObservationNumber, InspectionID, Citation, ShortDescription, LongDescription,
         FEINumber, LegalName, City, State, ZipCode, CountryArea,
         InspectionEndDate, ProductType, ProjectArea)
        VALUES
        (:ObservationNumber, :InspectionID, :Citation, :ShortDescription, :LongDescription,
         :FEINumber, :LegalName, :City, :State, :ZipCode, :CountryArea,
         :InspectionEndDate, :ProductType, :ProjectArea)
    """, row)

# ----------------------------
# HTTP with long backoff
# ----------------------------
def api_post(endpoint: str, payload: Dict, max_retries: int = 8) -> Dict:
    """
    Robust POST with exponential backoff on WAF/HTML/403/429 and network hiccups.
    """
    if not AUTH_USER or not AUTH_KEY:
        raise RuntimeError("Missing FDA_DD_API_USER or FDA_DD_API_KEY in environment/.env")

    url = f"{BASE_API}/{endpoint}"

    # exponential base (seconds)
    base_wait = 30.0

    for attempt in range(1, max_retries + 1):
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://www.accessdata.fda.gov",
            "Referer": "https://www.accessdata.fda.gov/",
            "Connection": "keep-alive",
            "Content-Type": "application/json",
            "Authorization-User": AUTH_USER,
            "Authorization-Key": AUTH_KEY,
        }

        try:
            resp = SESSION.post(url, headers=headers, json=payload, timeout=60)

            # WAF sometimes sends HTML placeholder (title TBD)
            ctype = resp.headers.get("Content-Type", "")
            if "text/html" in ctype:
                wait = jitter(base_wait * (2 ** (attempt - 1)))
                print(f"⚠️  HTML (WAF) attempt {attempt}/{max_retries}. Sleeping {int(wait)}s...")
                time.sleep(wait)
                continue

            # Friendly throttling codes
            if resp.status_code in (403, 408, 409, 412, 429, 500, 502, 503, 504):
                wait = jitter(base_wait * (2 ** (attempt - 1)))
                print(f"⏳ {resp.status_code} attempt {attempt}/{max_retries}. Sleeping {int(wait)}s...")
                time.sleep(wait)
                continue

            if resp.status_code == 200:
                return resp.json()

            # Other unexpected cases: raise
            raise RuntimeError(f"Unexpected {resp.status_code}: {resp.text[:200]}")

        except requests.RequestException as e:
            wait = jitter(base_wait * (2 ** (attempt - 1)))
            print(f"🌐 Network error attempt {attempt}/{max_retries}: {e}. Sleeping {int(wait)}s...")
            time.sleep(wait)

    raise RuntimeError(f"Failed after {max_retries} retries for {endpoint}")

# ----------------------------
# Paging (resumable)
# ----------------------------
def paged_fetch(endpoint: str, date_from: str, date_to: str, rows_per_page: int = 250) -> Iterable[Dict]:
    """
    Iterate over API pages; yields each row.
    Saves raw JSON per page (for audit/replay) to data/raw/ires/YYYYMMDD.
    """
    outdir = today_bucket()
    page = 1
    total = 0

    while True:
        payload = {
            "filters": {"date_from": date_from, "date_to": date_to},
            "page": page,
            "rows_per_page": rows_per_page
        }

        data = api_post(endpoint, payload)
        result = data.get("result") or []
        resultcount = data.get("resultcount")
        totalcount = data.get("totalcount")

        # Save raw
        with open(outdir / f"{endpoint}_p{page:05d}.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        if not result:
            print(f"Page {page}: 0 rows → done.")
            break

        print(f"Page {page}: {len(result)} rows (resultcount={resultcount}, totalcount={totalcount})")
        for row in result:
            yield row
            total += 1

        page += 1
        # polite tiny pause between pages
        time.sleep(jitter(1.5))

# ----------------------------
# Runner
# ----------------------------
def run_inspections_citations(date_from: str, date_to: str) -> int:
    """
    Pull inspections_citations and upsert into DB.
    """
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    ensure_tables(cur)

    inserted = 0
    for row in paged_fetch("inspections_citations", date_from, date_to):
        insert_citation(cur, row)
        inserted += 1
        if inserted % 500 == 0:
            con.commit()
    con.commit()
    con.close()
    return inserted

# ----------------------------
# CLI
# ----------------------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="iRES API harvester with long backoff")
    p.add_argument("--endpoint", choices=["inspections_citations"], default="inspections_citations")
    p.add_argument("--from", dest="date_from", required=True, help="YYYY-MM-DD")
    p.add_argument("--to", dest="date_to", required=True, help="YYYY-MM-DD")
    return p.parse_args()

def main() -> None:
    args = parse_args()
    print(f"DB:   {DB_PATH}")
    print(f"RAW:  {RAW_DIR}")

    if args.endpoint == "inspections_citations":
        total = run_inspections_citations(args.date_from, args.date_to)
        print(f"✅ Done. Inserted {total} citation rows.")
    else:
        print("Unknown endpoint flag.")

if __name__ == "__main__":
    main()
