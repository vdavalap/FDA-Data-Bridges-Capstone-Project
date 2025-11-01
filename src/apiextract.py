from __future__ import annotations
import os
import json
import time
import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import requests
from dotenv import load_dotenv, find_dotenv

# ========= Load Environment =========
def load_env():
    """Robust .env loader that works from src/ or repo root."""
    repo_root = Path(__file__).resolve().parents[1]
    env_path = repo_root / ".env"
    if env_path.is_file():
        load_dotenv(dotenv_path=env_path)
    else:
        found = find_dotenv(usecwd=True)
        if found:
            load_dotenv(found)
        else:
            print("[WARN] No .env file found, relying on OS environment variables.")

load_env()

AUTH_USER = os.getenv("FDA_DD_API_USER")
AUTH_KEY = os.getenv("FDA_DD_API_KEY")

if not AUTH_USER or not AUTH_KEY:
    raise RuntimeError("Missing FDA_DD_API_USER or FDA_DD_API_KEY. Add them to .env")

# ========= Paths =========
ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "ires"
DB_PATH = ROOT / "db" / "state_demo.db"

RAW_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

BASE_API = "https://api-datadashboard.fda.gov/v1"

# ========= Helpers =========
def today_folder() -> Path:
    folder = RAW_DIR / datetime.now(timezone.utc).strftime("%Y%m%d")
    folder.mkdir(parents=True, exist_ok=True)
    return folder

def http_post(endpoint: str, body: Dict, retries: int = 3) -> Dict:
    """POST request with retries to FDA Dashboard API."""
    url = f"{BASE_API}/{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "Authorization-User": AUTH_USER,
        "Authorization-Key": AUTH_KEY
    }

    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=60)
            data = resp.json()
            if data.get("statuscode") == 400:
                return data
            else:
                print(f"[Attempt {attempt}] Status {data.get('statuscode')} - retrying...")
                time.sleep(attempt * 2)
        except Exception as e:
            print(f"[Attempt {attempt}] Error: {e}")
            time.sleep(attempt * 2)
    raise RuntimeError("No response from FDA API after retries.")

def save_raw(endpoint: str, data: Dict):
    out_dir = today_folder() / endpoint
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    file_path = out_dir / f"{endpoint}_{ts}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return file_path

# ========= Database =========
def ensure_table(cur: sqlite3.Cursor):
    cur.execute("""
    CREATE TABLE IF NOT EXISTS inspections (
        inspection_id INTEGER PRIMARY KEY,
        fei_number TEXT,
        firm_name TEXT,
        city TEXT,
        state TEXT,
        zip TEXT,
        country TEXT,
        inspection_end_date TEXT,
        classification TEXT,
        project_area TEXT,
        product_type TEXT,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

def upsert(cur: sqlite3.Cursor, record: Dict):
    cur.execute("""
    INSERT INTO inspections (inspection_id, fei_number, firm_name, city, state, zip, country, 
                             inspection_end_date, classification, project_area, product_type)
    VALUES (:inspection_id, :fei_number, :firm_name, :city, :state, :zip, :country, 
            :inspection_end_date, :classification, :project_area, :product_type)
    ON CONFLICT(inspection_id) DO UPDATE SET
        fei_number=excluded.fei_number,
        firm_name=excluded.firm_name,
        classification=excluded.classification
    """, record)

# ========= Data Fetcher =========
def fetch_endpoint(endpoint: str, date_from: Optional[str], date_to: Optional[str]):
    filters = {}
    if date_from:
        filters["InspectionEndDateFrom"] = [date_from]
    if date_to:
        filters["InspectionEndDateTo"] = [date_to]

    payload = {
        "start": 1,
        "rows": 1000,
        "sort": "InspectionEndDate",
        "sortorder": "DESC",
        "filters": filters,
        "columns": [],
        "returntotalcount": True
    }

    data = http_post(endpoint, payload)
    save_raw(endpoint, data)
    results = data.get("result", [])
    if not results:
        print("⚠️ No records found.")
        return

    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        ensure_table(cur)
        for row in results:
            rec = {
                "inspection_id": row.get("InspectionID"),
                "fei_number": row.get("FEINumber"),
                "firm_name": row.get("LegalName"),
                "city": row.get("City"),
                "state": row.get("State"),
                "zip": row.get("ZipCode"),
                "country": row.get("CountryArea"),
                "inspection_end_date": row.get("InspectionEndDate"),
                "classification": row.get("Classification"),
                "project_area": row.get("ProjectArea"),
                "product_type": row.get("ProductType"),
            }
            upsert(cur, rec)
        con.commit()
    print(f"✅ Inserted {len(results)} records into {DB_PATH}")

# ========= CLI =========
def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--endpoint", default="inspections_classifications",
                   choices=["inspections_classifications", "inspections_citations", "inspections_eirs", "inspections_observations"])
    p.add_argument("--from", dest="date_from", help="YYYY-MM-DD", default=None)
    p.add_argument("--to", dest="date_to", help="YYYY-MM-DD", default=None)
    return p.parse_args()

def main():
    args = parse_args()
    print(f"📂 Saving raw data to: {today_folder()}")
    print(f"🗄️  Database: {DB_PATH}")
    fetch_endpoint(args.endpoint, args.date_from, args.date_to)

if __name__ == "__main__":
    main()
