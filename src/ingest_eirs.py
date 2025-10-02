# src/ingest_eirs.py
import os
import argparse
from pathlib import Path
from urllib.parse import urljoin, urlparse
import csv
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from utils_http import session, can_fetch, polite_get, take_limit

load_dotenv()
BASE = os.getenv("FDA_OII_READING_ROOM", "https://www.fda.gov/about-fda/office-inspections-and-investigations/oii-foia-electronic-reading-room")
ENV_LIMIT = os.getenv("LIMIT")

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "raw" / "eir"
LOG = ROOT / "docs" / "ingest_log_eirs.csv"

KEYS = ("eir", "establishment inspection report")

def looks_like_eir(a) -> bool:
    text = (a.get_text() or "").lower()
    href = a.get("href","").lower()
    return any(k in text for k in KEYS) or any(k in href for k in KEYS)

def log_row(row: dict):
    new = not LOG.exists()
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["url","filename","status","note"])
        if new: w.writeheader()
        w.writerow(row)

def main():
    ap = argparse.ArgumentParser(description="Ingest EIR PDFs from OII Reading Room.")
    ap.add_argument("--limit", type=int, default=int(ENV_LIMIT) if ENV_LIMIT else None,
                    help="Limit number of PDFs to download (CLI overrides .env LIMIT).")
    args = ap.parse_args()

    s = session()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not can_fetch(BASE):
        print("❌ robots disallow base page"); return
    r = polite_get(s, BASE)
    soup = BeautifulSoup(r.text, "html.parser")

    # Collect all candidate links from the landing page
    links = []
    for a in soup.find_all("a", href=True):
        if looks_like_eir(a):
            href = a["href"]
            links.append(href if href.startswith("http") else urljoin(BASE, href))

    links = sorted(set(links))
    if args.limit:
        links = take_limit(links, args.limit)
    print(f"Found {len(links)} candidate EIR link(s).")

    for url in links:
        if not can_fetch(url):
            log_row({"url": url, "filename":"", "status":"skip", "note":"robots"}); continue
        try:
            r2 = polite_get(s, url, stream=True, allow_redirects=True)
            ctype = (r2.headers.get("Content-Type") or "").lower()
            if "pdf" not in ctype and not r2.url.lower().endswith(".pdf"):
                log_row({"url": url, "filename":"", "status":"skip", "note":"not-pdf"}); continue
            name = Path(urlparse(r2.url).path).name or "eir.pdf"
            if not name.lower().endswith(".pdf"): name += ".pdf"
            outp = OUT_DIR / name
            if outp.exists():
                log_row({"url": url, "filename": name, "status":"exists", "note":""}); continue
            with outp.open("wb") as f:
                for chunk in r2.iter_content(8192):
                    if chunk: f.write(chunk)
            log_row({"url": url, "filename": name, "status":"ok", "note":""})
            print(f"⬇️  {name}")
        except Exception as e:
            log_row({"url": url, "filename":"", "status":"error", "note":str(e)})
    print(f"Done. Log: {LOG}")

if __name__ == "__main__":
    main()
