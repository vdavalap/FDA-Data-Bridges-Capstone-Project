-- src/schema_sqlite.sql
PRAGMA foreign_keys = ON;

----------------------------------------------------------------------
-- Re-create core tables (safe because we re-create the DB when needed)
----------------------------------------------------------------------

DROP TABLE IF EXISTS observations;
DROP TABLE IF EXISTS inspections;

-- =========================
-- Inspections (master)
-- =========================
CREATE TABLE IF NOT EXISTS inspections (
  inspection_id         INTEGER PRIMARY KEY,           -- from CSV "Inspection ID" or synthetic for PDFs
  fei_number            TEXT,                          -- CSV "FEI Number" / PDF header
  firm_name             TEXT,                          -- CSV "Legal Name" / PDF header

  -- Location / address fields (PDF or CSV)
  address               TEXT,                          -- from PDF when present
  city                  TEXT,                          -- CSV "City" or PDF
  state                 TEXT,                          -- CSV "State" or PDF (two-letter if possible)
  zip                   TEXT,                          -- CSV "Zip" or PDF
  country               TEXT,                          -- normalized (e.g., "United States")
  country_area          TEXT,                          -- keep original CSV "Country/Area" if you want both

  -- Dates
  inspection_date       TEXT,                          -- from PDFs (normalized yyyy-mm-dd)
  inspection_end_date   TEXT,                          -- from CSV "Inspection End Date" (yyyy-mm-dd)

  -- Types / classification
  inspection_type       TEXT,                          -- '483' | 'EIR' | 'Other'
  classification        TEXT,                          -- CSV "Classification" or PDF summary
  establishment_type    TEXT,                          -- PDF "TYPE OF ESTABLISHMENT INSPECTED" if present
  project_area          TEXT,                          -- CSV "Project Area"
  product_type          TEXT,                          -- CSV "Product Type"
  outcome               TEXT,                          -- optional future use

  -- CSV-only extras
  fiscal_year           INTEGER,                       -- CSV "Fiscal Year"
  posted_citations      INTEGER,                       -- CSV Yes/No -> 1/0

  -- Provenance
  source_url            TEXT,                          -- if coming from a link
  source_doc            TEXT,                          -- filename used for this inspection
  ingested_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Helpful indexes for common filters
CREATE INDEX IF NOT EXISTS idx_inspections_state           ON inspections(state);
CREATE INDEX IF NOT EXISTS idx_inspections_fy              ON inspections(fiscal_year);
CREATE INDEX IF NOT EXISTS idx_inspections_end_date        ON inspections(inspection_end_date);
CREATE INDEX IF NOT EXISTS idx_inspections_date            ON inspections(inspection_date);
CREATE INDEX IF NOT EXISTS idx_inspections_class           ON inspections(classification);
CREATE INDEX IF NOT EXISTS idx_inspections_fei             ON inspections(fei_number);
CREATE INDEX IF NOT EXISTS idx_inspections_firm            ON inspections(firm_name);

-- =========================
-- Observations (detail rows from 483/EIR text)
-- =========================
CREATE TABLE IF NOT EXISTS observations (
  observation_id        INTEGER PRIMARY KEY AUTOINCREMENT,
  inspection_id         INTEGER NOT NULL,               -- FK → inspections.inspection_id
  category              TEXT,                           -- e.g., Sanitation | Documentation | Aseptic | Training | Other
  severity              TEXT,                           -- Low | Medium | High (or PDF-inferred)
  is_repeat             INTEGER,                        -- 0/1 if "repeat" was detected
  text                  TEXT,                           -- observation snippet/excerpt
  source_doc            TEXT,                           -- filename of the PDF
  source_page           INTEGER,                        -- page number within PDF
  doc_type              TEXT,                           -- '483' | 'EIR'

  -- denormalized context for quick queries (optional but handy)
  fei_number            TEXT,
  firm_name             TEXT,
  inspection_date       TEXT,
  address               TEXT,
  city                  TEXT,
  state                 TEXT,
  zip                   TEXT,
  country               TEXT,
  extracted_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

  FOREIGN KEY (inspection_id) REFERENCES inspections(inspection_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_observations_inspection     ON observations(inspection_id);
CREATE INDEX IF NOT EXISTS idx_observations_category       ON observations(category);
CREATE INDEX IF NOT EXISTS idx_observations_doc            ON observations(source_doc);
