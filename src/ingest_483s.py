# src/ingest_483s.py
import os
import argparse
from pathlib import Path
from urllib.parse import urljoin, urlparse
import csv as _csv
import pandas as pd
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from utils_http import session, can_fetch, polite_get, take_limit

load_dotenv()
DASH = os.getenv("FDA_INSPECTIONS_DASH", "https://datadashboard.fda.gov/oii/cd/inspections.htm")
ENV_LIMIT = os.getenv("LIMIT")  # optional fallback

ROOT = Path(__file__).resolve().parents[1]
CSV_OUT = ROOT / "data" / "staged" / "published_483s.csv"
PDF_DIR = ROOT / "data" / "raw" / "fda_483"
LOG = ROOT / "docs" / "ingest_log_483s.csv"

def find_483_csv_link(html: str, base_url: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        text = (a.get_text() or "").lower()
        href = a["href"]
        if "published 483s" in text or ("483" in text and href.lower().endswith(".csv")):
            return href if href.startswith("http") else urljoin(base_url, href)
    return None

def log_row(path: Path, row: dict):
    new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="", encoding="utf-8") as f:
        w = _csv.DictWriter(f, fieldnames=["url","filename","status","note"])
        if new: w.writeheader()
        w.writerow(row)

def main():
    # Parse CLI
    ap = argparse.ArgumentParser(description="Ingest Published 483s dataset and PDFs.")
    ap.add_argument("--limit", type=int, default=int(ENV_LIMIT) if ENV_LIMIT else None,
                    help="Limit number of PDFs to download (CLI overrides .env LIMIT).")
    args = ap.parse_args()

    s = session()
    r = polite_get(s, DASH)
    csv_link = find_483_csv_link(r.text, DASH)
    if not csv_link:
        print("❌ 483 CSV link not found. Update selector if dashboard changed."); return

    if not can_fetch(csv_link):
        print("❌ robots disallow CSV."); return
    resp = polite_get(s, csv_link, stream=True)
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    with CSV_OUT.open("wb") as f:
        for chunk in resp.iter_content(8192):
            if chunk: f.write(chunk)
    print(f"✅ Saved 483 list → {CSV_OUT}")

    # Load CSV and identify a URL column
    df = pd.read_csv(CSV_OUT, dtype=str, engine="python").fillna("")
    cand_cols = [c for c in df.columns if "download" in c.lower() or "url" in c.lower()]
    if not cand_cols:
        print("❌ No URL column found in 483 CSV."); return
    url_col = cand_cols[0]

    # Build list of unique URLs
    urls = []
    for u in df[url_col].astype(str):
        u2 = u.strip()
        if u2.lower().startswith(("http://","https://")):
            urls.append(u2)
    urls = sorted(set(urls))
    if args.limit:
        urls = take_limit(urls, args.limit)
    print(f"Planning to download {len(urls)} PDF(s).")

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    for url in urls:
        if not can_fetch(url):
            log_row(LOG, {"url": url, "filename":"", "status":"skip", "note":"robots"}); continue
        try:
            pr = polite_get(s, url, stream=True, allow_redirects=True)
            ctype = (pr.headers.get("Content-Type") or "").lower()
            if "pdf" not in ctype and not pr.url.lower().endswith(".pdf"):
                log_row(LOG, {"url": url, "filename":"", "status":"skip", "note":"not-pdf"}); continue
            name = Path(urlparse(pr.url).path).name or "483.pdf"
            if not name.lower().endswith(".pdf"): name += ".pdf"
            outp = PDF_DIR / name
            if outp.exists():
                log_row(LOG, {"url": url, "filename": name, "status":"exists", "note":""}); continue
            with outp.open("wb") as f:
                for chunk in pr.iter_content(8192):
                    if chunk: f.write(chunk)
            log_row(LOG, {"url": url, "filename": name, "status":"ok", "note":""})
            print(f"⬇️  {name}")
        except Exception as e:
            log_row(LOG, {"url": url, "filename":"", "status":"error", "note":str(e)})
    print(f"Done. Log: {LOG}")

if __name__ == "__main__":
    main()
