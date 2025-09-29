# State-Only Inspection Demo (Sprint 2)

Scope: **State regulators only** (no MOUs/FOIA).  
Demo: load small CSVs, parse 1 PDF page with an LLM → observations, run two queries.

## Quick start
1) `python -m venv .venv && source .venv/bin/activate`  (Windows: `.\.venv\Scripts\activate`)
2) `pip install -r requirements.txt`
3) `cp .env.example .env` and add your real `OPENAI_API_KEY`
4) Seed data → `python src/load_seed.py`
5) Put one PDF in `data/raw/` (e.g., `sample_483.pdf`)
6) Extract observations → `python src/extract_pdf_llm.py`
7) Run demo queries → `python src/run_demo_queries.py`

## Automation
- Scheduled download via GitHub Actions: `.github/workflows/ingest.yml`
- Configure FDA URLs in `src/download_fda.py` (edit the URL list)
