# src/ingest_inspections.py
from pathlib import Path
from urllib.parse import urljoin
import pandas as pd
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import os

from utils_http import session, can_fetch, polite_get

load_dotenv()
DASH_URL = os.getenv("FDA_INSPECTIONS_DASH", "https://datadashboard.fda.gov/oii/cd/inspections.htm")

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "staged" / "inspections.csv"

def find_csv_link(html: str, page_url: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        text = (a.get_text() or "").strip().lower()
        href = a["href"]
        if "entire dataset" in text or href.lower().endswith(".csv"):
            return href if href.startswith("http") else urljoin(page_url, href)
    return None

def main():
    s = session()
    if not can_fetch(DASH_URL):
        print("❌ robots.txt disallows dashboard fetch."); return
    r = polite_get(s, DASH_URL)
    csv_link = find_csv_link(r.text, DASH_URL)
    if not csv_link:
        print("❌ CSV link not found. The dashboard markup may have changed."); return
    if not can_fetch(csv_link):
        print("❌ robots.txt disallows dataset CSV."); return

    OUT.parent.mkdir(parents=True, exist_ok=True)
    resp = polite_get(s, csv_link, stream=True)
    with OUT.open("wb") as f:
        for chunk in resp.iter_content(8192):
            if chunk: f.write(chunk)
    print(f"✅ Saved inspections dataset → {OUT}")

    # Quick sanity
    try:
        df = pd.read_csv(OUT, dtype=str, engine="python")
        print(f"Rows: {len(df)}  Columns: {list(df.columns)[:10]} ...")
    except Exception as e:
        print("⚠️ CSV parse check failed:", e)

if __name__ == "__main__":
    main()
