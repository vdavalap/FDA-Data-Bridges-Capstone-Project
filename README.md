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
│ ├── schema_sqlite.sql # Database schema
│ └── query_cli.py # CLI for running SQL queries
├── requirements.txt # Python dependencies
├── .env.example # Example environment config
├── .gitignore # Ignore DB, venv, raw data, unfinished code
└── README.md # This file

yaml
Copy code

---

## 🚀 Getting Started (From Scratch)

### 1. Install Python
Make sure you have **Python 3.12+** installed:
```bash
python3 --version
2. Create Virtual Environment
bash
Copy code
python3 -m venv .venv
source .venv/bin/activate   # Linux/Mac
.venv\Scripts\activate      # Windows (PowerShell)
3. Install Dependencies
bash
Copy code
pip install --upgrade pip
pip install -r requirements.txt
4. Environment Variables
Copy .env.example to .env and adjust paths if needed:

bash
Copy code
cp .env.example .env
🗄️ Database Setup
1. Create Schema + Seed Data
We start by loading the FDA inspections.csv dataset.

Place inspections.csv into:

bash
Copy code
data/staged/inspections.csv
Then run:

bash
Copy code
python src/load_seed.py
This will:

Create db/state_demo.db

Apply schema from src/schema_sqlite.sql

Load inspection rows into the inspections table

📑 Extracting Observations from PDFs
1. Place PDF files
Drop FDA 483/inspection PDFs into:

bash
Copy code
data/raw/
2. Run Extraction
bash
Copy code
python src/extractpdf.py
This will:

Parse PDFs in data/raw/

Extract rule-based observations

Save results into data/processed/

Insert observations into db/state_demo.db

🔍 Querying Data
Open the DB:

bash
Copy code
sqlite3 db/state_demo.db
Example queries:

sql
Copy code
-- Count inspections
SELECT COUNT(*) FROM inspections;

-- Count observations
SELECT COUNT(*) FROM observations;

-- View recent observations
SELECT observation_id, inspection_id, category, severity, source_doc, source_page
FROM observations
ORDER BY observation_id DESC
LIMIT 10;
📊 Minimal Helpful Indexes
Indexes speed up lookups:

sql
Copy code
CREATE INDEX IF NOT EXISTS idx_inspections_date
  ON inspections(inspection_date);

CREATE INDEX IF NOT EXISTS idx_observations_doc
  ON observations(source_doc, source_page);
✅ Requirements File
requirements.txt includes:

nginx
Copy code
pandas
sqlite-utils
pdfplumber
python-dotenv
⚠️ Notes
db/state_demo.db and data/ are ignored in Git to keep repo clean.

src/extract_pdf_llm.py is excluded since LLM integration isn’t ready.

Always activate your virtual environment before running scripts:

bash
Copy code
source .venv/bin/activate
👥 Teammate Quickstart (TL;DR)
For Slack/Teams pin:

bash
Copy code
git clone <repo-url>
cd FDA-Data-Bridges-Capstone-Project
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python src/load_seed.py
python src/extractpdf.py
sqlite3 db/state_demo.db