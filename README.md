# FDA Data Bridges Capstone Project
-
This project builds a pipeline for **loading FDA inspection data** from CSVs and **extracting structured observations** from PDF inspection reports into a **SQLite database**.  

The goal is to support analytics and insights on FDA inspection outcomes.

---

## 📦 Project Structure

FDA-Data-Bridges-Capstone-Project/
├── db/
│ └── state_demo.db # SQLite DB (auto-created, ignored in Git)
├── data/
│ ├── raw/ # Raw PDFs (ignored in Git)
│ ├── staged/ # Staged CSVs for seeding DB
│ └── processed/ # Extracted observations JSON/CSV
├── docs/ # Documentation
├── src/ # Source code
│ ├── config.py # Configuration paths & helpers
│ ├── load_seed.py # Load inspections.csv into DB
│ ├── extractpdf.py # Rule-based PDF text extraction
│ └── schema_sqlite.sql # Database schema
│ 
├── requirements.txt # Python dependencies
├── .env.example # Example environment config
├── .gitignore # Ignore DB, venv, raw data, unfinished code
└── README.md # This file



---

## 🚀 Getting Started (From Scratch)

### 1. Install Python
Make sure you have **Python 3.12+** installed:
```bash
python3 --version
2. Create Virtual Environment
bash

python3 -m venv .venv
source .venv/bin/activate   # Linux/Mac
.venv\Scripts\activate      # Windows (PowerShell)
3. Install Dependencies
bash

pip install --upgrade pip
pip install -r requirements.txt
4. Environment Variables
Copy .env.example to .env and adjust paths if needed:

bash

cp .env.example .env
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

-- Count inspections
SELECT COUNT(*) FROM inspections;

-- Count observations
SELECT COUNT(*) FROM observations;

--State wise inspecions
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

--for pdfs
 SELECT doc_type, fei_number, firm_name, city, state, zip, country, source_doc FROM observations ORDER BY extracted_at DESC LIMIT 20;

db/state_demo.db and data/ are ignored in Git to keep repo clean.

src/extract_pdf_llm.py is excluded since LLM integration isn’t ready.

Always activate your virtual environment before running scripts:

source .venv/bin/activate

Teammates Quickstart (TL;DR)

For Slack/Teams pin:

git clone <https://github.com/vdavalap/FDA-Data-Bridges-Capstone-Project>
cd FDA-Data-Bridges-Capstone-Project
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python src/load_seed.py
python src/extractpdf.py
sqlite3 db/state_demo.db
