-- ai3 wave-a offline vault schema extension

CREATE TABLE IF NOT EXISTS vault_source (
  source_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  priority TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  metadata_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vault_package (
  package_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  zip_relpath TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  language TEXT,
  license TEXT,
  metadata_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(source_id) REFERENCES vault_source(source_id)
);

CREATE TABLE IF NOT EXISTS citation_verification (
  verification_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  citation_id TEXT NOT NULL,
  status TEXT NOT NULL,
  reason TEXT NOT NULL,
  verified_at TEXT NOT NULL,
  details_json TEXT,
  FOREIGN KEY(run_id) REFERENCES run(run_id),
  FOREIGN KEY(citation_id) REFERENCES citation(citation_id)
);
