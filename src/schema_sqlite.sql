-- src/schema_sqlite.sql
PRAGMA foreign_keys = ON;

-- Drop-and-create (safe because we recreate the DB file each run)
DROP TABLE IF EXISTS inspections;

CREATE TABLE IF NOT EXISTS inspections (
  inspection_id        INTEGER PRIMARY KEY,      -- from "Inspection ID"
  fei_number           TEXT,                     -- "FEI Number"
  firm_name            TEXT,                     -- "Legal Name"
  city                 TEXT,                     -- "City"
  state                TEXT,                     -- "State"
  zip                  TEXT,                     -- "Zip"
  country_area         TEXT,                     -- "Country/Area"
  fiscal_year          INTEGER,                  -- "Fiscal Year"
  posted_citations     INTEGER,                  -- Yes/No -> 1/0
  inspection_end_date  TEXT,                     -- normalized yyyy-mm-dd
  classification       TEXT,                     -- "Classification"
  project_area         TEXT,                     -- "Project Area"
  product_type         TEXT,                     -- "Product Type"
  source_url           TEXT,                     -- optional (may be NULL)
  source_doc           TEXT,                     -- filename parsed from URL
  outcome              TEXT,                     -- optional/future
  ingested_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- helpful indexes
CREATE INDEX IF NOT EXISTS idx_inspections_state        ON inspections(state);
CREATE INDEX IF NOT EXISTS idx_inspections_fy           ON inspections(fiscal_year);
CREATE INDEX IF NOT EXISTS idx_inspections_end_date     ON inspections(inspection_end_date);
CREATE INDEX IF NOT EXISTS idx_inspections_class        ON inspections(classification);
CREATE INDEX IF NOT EXISTS idx_inspections_fei          ON inspections(fei_number);
