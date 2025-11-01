# FDA Data Bridges Capstone Project
-
This project builds a pipeline for **loading FDA inspection data** from CSVs and **extracting structured observations** from PDF inspection reports into a **SQLite database**.  

The goal is to support analytics and insights on FDA inspection outcomes.

---

## 📦 Project Structure
FDA-Data-Bridges-Capstone-Project/
├─ db/
│  └─ state_demo.db                 # SQLite DB (generated, gitignored)
├─ data/
│  ├─ raw/                          # Raw PDFs (gitignored)
│  ├─ staged/
│  │  └─ inspections.csv            # Staged CSV used to seed DB
│  └─ processed/                    # Any exports/snapshots
├─ downloads/                       # PDFs fetched by pdfdownloader.py (gitignored)
├─ fda_outputs/                     # Datasets downloaded from dashboard (XLSX/CSV)
├─ src/
│  ├─ apiextract.py                 # Pull inspection records into DB (inspections)
│  ├─ datasetdownloader.py          # Scrape dashboard, get XLSX, convert to CSV
│  ├─ pdfdownloader.py              # Read dataset CSV/Excel → download PDFs → downloads/
│  ├─ extractpdf.py                 # Parse PDFs → observations table in DB
│  ├─ config.py                     # Paths, helpers
│  ├─ load_seed.py                  # Load inspections.csv seed into DB
│  ├─ schema_sqlite.sql             # DB schema (inspections, observations, etc.)
│  └─ utils_*.py                    # Helpers (HTTP, logging, etc.) if present
├─ requirements.txt
├─ .env.example
├─ .gitignore
└─ README.md




---
Pipeline Overview

Path A – Structured (Inspection metadata)

src/apiextract.py queries FDA dashboard/API → upserts inspections into db/state_demo.db.

Alternatively, seed from CSV: place data/staged/inspections.csv and run src/load_seed.py.

Path B – Unstructured (Form 483 PDFs)

src/datasetdownloader.py hits https://datadashboard.fda.gov/oii/cd/inspections.htm
, opens Download Dataset, finds links, downloads .xlsx, converts to .csv → saved in fda_outputs/.

src/pdfdownloader.py reads those datasets (Excel/CSV), scans a Download URL column, and downloads the PDFs into downloads/ (polite rate-limit).

src/extractpdf.py parses each PDF (PyMuPDF): FEI, firm name, address, city, state, zip, country; inserts a “Metadata” snapshot into observations table in db/state_demo.db.

Storage

inspections – structured metadata (seeded or via API).

observations – per-PDF structured attributes (one “Metadata” row per PDF at minimum).


## 🚀 Getting Started (From Scratch)

### 1. Install Python
Make sure you have **Python 3.12+** installed:

🗄️ Database Setup
1. Create Schema + Seed Data
We start by loading the FDA inspections.csv dataset.

Place inspections.csv into:
data/staged/inspections.csv

Then run:
python src/load_seed.py

This will:

Create db/state_demo.db

Apply schema from src/schema_sqlite.sql

Load inspection rows into the inspections table

📑 Extracting Observations from PDFs
1. Place PDF files
Drop FDA 483/inspection PDFs into:
data/raw/

2. Run Extraction
python src/extractpdf.py

This will:
Parse PDFs in data/raw/
Extract rule-based observations
Save results into data/processed/

Insert observations into db/state_demo.db

🔍 Querying Data
Open the DB:

sqlite3 db/state_demo.db
Example queries:

sql

-- State-wise recent inspections (example: Virginia)
SELECT firm_name, city, inspection_end_date, classification, fei_number
FROM inspections
WHERE state = 'Virginia'
ORDER BY inspection_end_date DESC
LIMIT 10;

-- Most recent 10 inspections
SELECT inspection_id, firm_name, state, inspection_end_date, classification
FROM inspections
ORDER BY inspection_end_date DESC
LIMIT 10;

-- Top 10 product types
SELECT product_type, COUNT(*) AS inspections_count
FROM inspections
GROUP BY product_type
ORDER BY inspections_count DESC
LIMIT 10;

-- Top 5 project areas in FY 2022
SELECT project_area, COUNT(*) AS inspections_count
FROM inspections
WHERE fiscal_year = 2022
GROUP BY project_area
ORDER BY inspections_count DESC
LIMIT 5;

-- Recent parsed PDFs (observations)
SELECT doc_type, fei_number, firm_name, city, state, zip, country, source_doc, date(extracted_at) as extracted
FROM observations
ORDER BY extracted_at DESC
LIMIT 20;


-- CSV inspections with a matching PDF by FEI
SELECT COUNT(*) AS csv_with_pdf
FROM inspections i
JOIN observations o
  ON i.fei_number = o.fei_number;

-- Sample matches
SELECT i.inspection_id, i.firm_name AS csv_firm, o.firm_name AS pdf_firm,
       i.city AS csv_city, i.state AS csv_state,
       o.city AS pdf_city, o.state AS pdf_state
FROM inspections i
JOIN observations o
  ON i.fei_number = o.fei_number
ORDER BY i.inspection_id DESC
LIMIT 10;

-- CSV without a matching PDF (by FEI)
SELECT i.fei_number, i.firm_name, i.city, i.state, i.inspection_end_date
FROM inspections i
LEFT JOIN observations o
  ON i.fei_number = o.fei_number
WHERE o.fei_number IS NULL
ORDER BY i.inspection_end_date DESC
LIMIT 15;

-- PDFs without a matching CSV (by FEI)
SELECT o.fei_number, o.firm_name, o.city, o.state, o.source_doc
FROM observations o
LEFT JOIN inspections i
  ON i.fei_number = o.fei_number
WHERE i.fei_number IS NULL
ORDER BY o.extracted_at DESC
LIMIT 15;

 db/state_demo.db and data/ are ignored in Git to keep repo clean.

src/extract_pdf_llm.py is excluded since LLM integration isn’t ready.

If you're doing in virtual environtment always activate your virtual environment before running scripts:

source .venv/bin/activate

Teammates Quickstart (TL;DR)

For Slack/Teams pin:

git clone <https://github.com/vdavalap/FDA-Data-Bridges-Capstone-Project>
cd FDA-Data-Bridges-Capstone-Project
.\venv\Scripts\Activate.ps1 
pip install -r requirements.txt
cp .env.example .env
python src/load_seed.py
python src/extractpdf.py
sqlite3 db/state_demo.db 



