import os
import re
import sqlite3
import pathlib
from typing import List, Tuple

import fitz  # PyMuPDF
from pdf2image import convert_from_path
import pytesseract
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "db" / "state_demo.db"
RAW_DIR = ROOT / "data" / "raw"

# ---------- simple heuristics ----------
OBS_PATTERNS = [
    r"\bObservation[s]?:?\b",
    r"\bWe observed\b",
    r"\bviolat(?:e|ion|ions)\b",
    r"\bdeficien(?:t|cies)\b",
    r"\bfailure to\b",
]
OBS_RE = re.compile("|".join(OBS_PATTERNS), flags=re.IGNORECASE)

REPEAT_RE = re.compile(r"\brepeat\b", re.IGNORECASE)
SEVERITY_HIGH_RE = re.compile(r"\bmajor\b|\bcritical\b|\bsignificant\b", re.IGNORECASE)
SEVERITY_LOW_RE  = re.compile(r"\bminor\b|\bnote\b", re.IGNORECASE)

CATEGORY_MAP = [
    (re.compile(r"\bsanitation|clean|sanitary", re.IGNORECASE), "Sanitation"),
    (re.compile(r"\btraining|qualified personnel", re.IGNORECASE), "Training"),
    (re.compile(r"\bdocument|record|SOP", re.IGNORECASE), "Documentation"),
    (re.compile(r"\baseptic|steril|contamination\b", re.IGNORECASE), "Aseptic"),
]

def guess_category(text: str) -> str:
    for rx, name in CATEGORY_MAP:
        if rx.search(text):
            return name
    return "Other"

def guess_severity(text: str) -> str:
    if SEVERITY_HIGH_RE.search(text): return "High"
    if SEVERITY_LOW_RE.search(text):  return "Low"
    return "Medium"

def needs_ocr(text: str, min_chars: int = 120) -> bool:
    return len(text.strip()) < min_chars

# ---------- OCR helpers ----------
def ocr_page(pdf_path: pathlib.Path, page_index: int) -> str:
    """
    Render a single page to image and OCR it.
    page_index is 0-based.
    """
    # convert_from_path returns PIL Images for the given pages
    images = convert_from_path(
        str(pdf_path),
        first_page=page_index + 1,
        last_page=page_index + 1,
        dpi=300
    )
    if not images:
        return ""
    img: Image.Image = images[0]
    txt = pytesseract.image_to_string(img)
    return txt or ""

# ---------- core extraction ----------
def extract_observations_from_text(text: str) -> List[str]:
    """
    Minimal rule: keep paragraphs/sentences that appear to mention
    observation-ish content. You can make this smarter later.
    """
    chunks = re.split(r"(?<=[\.\n])\s+", text)
    results = []
    for c in chunks:
        c2 = c.strip()
        if len(c2) < 30:
            continue
        if OBS_RE.search(c2):
            results.append(c2)
    return results

def extract_pdf(pdf_path: pathlib.Path) -> List[Tuple[str, str, bool, int, str]]:
    """
    Returns a list of tuples: (category, severity, is_repeat, page_num, text)
    """
    out = []
    doc = fitz.open(pdf_path)
    for i, page in enumerate(doc, start=1):
        page_text = page.get_text("text") or ""
        if needs_ocr(page_text):
            ocr_txt = ocr_page(pdf_path, i - 1)
            raw_text = ocr_txt
        else:
            raw_text = page_text

        observations = extract_observations_from_text(raw_text)
        for obs in observations:
            category = guess_category(obs)
            severity = guess_severity(obs)
            is_repeat = bool(REPEAT_RE.search(obs))
            out.append((category, severity, is_repeat, i, obs))
    doc.close()
    return out

# ---------- DB insert ----------
def insert_observations(db: pathlib.Path, inspection_id: int, pdf_file: pathlib.Path, rows: List[Tuple[str, str, bool, int, str]]):
    con = sqlite3.connect(db)
    cur = con.cursor()
    for category, severity, is_repeat, page_num, text in rows:
        cur.execute(
            """
            INSERT INTO observations
            (inspection_id, category, severity, is_repeat, text, source_doc, source_page)
            VALUES (?,?,?,?,?,?,?)
            """,
            (
                inspection_id,
                category,
                severity,
                1 if is_repeat else 0,
                text[:4000],            # truncate for safety
                pdf_file.name,
                page_num,
            )
        )
    con.commit()
    con.close()

def main():
    # For demo: attach to *first* inspection already in DB
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    row = cur.execute("SELECT inspection_id FROM inspections ORDER BY inspection_id LIMIT 1").fetchone()
    con.close()
    if not row:
        print("❌ No inspections found. Load CSV first with: python3 src/load_seed.py")
        return
    inspection_id = row[0]

    # Process all PDFs in data/raw
    pdfs = sorted(RAW_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"❌ No PDFs in {RAW_DIR}")
        return

    total = 0
    for pdf in pdfs:
        obs = extract_pdf(pdf)
        if obs:
            insert_observations(DB_PATH, inspection_id, pdf, obs)
            total += len(obs)
            print(f"✅ {pdf.name}: saved {len(obs)} observations")
        else:
            print(f"⚠️ {pdf.name}: no observations detected (possibly needs better rules)")

    if total == 0:
        print("⚠️ No observations saved. Check OCR install and rules.")
    else:
        print(f"🎯 Done. Inserted {total} observation(s).")

if __name__ == "__main__":
    main()
