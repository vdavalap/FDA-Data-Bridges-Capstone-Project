-- SQLite schema for our Sprint-1 demo.
-- We only create what we truly use today: the `inspections` table.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS inspections (
  -- FDA inspection record identifier (from “Record ID”)
  inspection_id   INTEGER PRIMARY KEY,

  -- FEI number and firm name let us link to firm entities later (Sprint-2+)
  fei_number      TEXT,
  firm_name       TEXT,

  -- Normalized as TEXT (YYYY-MM-DD) for simplicity; can convert to DATE later
  inspection_date TEXT,

  -- As provided by source (e.g., “Classification” or other type labels)
  inspection_type TEXT,

  -- Our simple derived label (for now we just mirror inspection_type)
  outcome         TEXT,

  -- Where the record came from (if any)
  source_url      TEXT,
  source_doc      TEXT,

  -- Loader time
  ingested_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_inspections_id ON inspections (inspection_id);
CREATE INDEX IF NOT EXISTS idx_inspections_fei ON inspections (fei_number);
CREATE INDEX IF NOT EXISTS idx_inspections_date ON inspections (inspection_date);
