CREATE TABLE IF NOT EXISTS assistant (
  assistant_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT,
  config_yaml TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_endpoint (
  endpoint_id TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  base_url TEXT,
  auth_ref TEXT,
  chat_model TEXT NOT NULL,
  embed_model TEXT,
  created_at TEXT NOT NULL,
  metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS thread (
  thread_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  updated_at TEXT,
  title TEXT,
  tags_json TEXT,
  metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS message (
  message_id TEXT PRIMARY KEY,
  thread_id TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('user','assistant','tool','system')),
  content TEXT NOT NULL,
  content_json TEXT,
  created_at TEXT NOT NULL,
  parent_message_id TEXT,
  metadata_json TEXT,
  FOREIGN KEY(thread_id) REFERENCES thread(thread_id)
);

CREATE TABLE IF NOT EXISTS run (
  run_id TEXT PRIMARY KEY,
  thread_id TEXT NOT NULL,
  endpoint_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('queued','running','requires_action','completed','failed','cancelled')),
  started_at TEXT,
  completed_at TEXT,
  error TEXT,
  trace_id TEXT,
  metadata_json TEXT,
  FOREIGN KEY(thread_id) REFERENCES thread(thread_id),
  FOREIGN KEY(endpoint_id) REFERENCES model_endpoint(endpoint_id)
);

CREATE TABLE IF NOT EXISTS run_step (
  step_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  step_index INTEGER NOT NULL,
  step_type TEXT NOT NULL,
  status TEXT NOT NULL,
  input_json TEXT,
  output_json TEXT,
  started_at TEXT,
  completed_at TEXT,
  FOREIGN KEY(run_id) REFERENCES run(run_id)
);

CREATE TABLE IF NOT EXISTS tool_server (
  server_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  name TEXT NOT NULL,
  endpoint TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS tool_definition (
  tool_name TEXT PRIMARY KEY,
  server_id TEXT,
  schema_json TEXT NOT NULL,
  risk_level TEXT NOT NULL CHECK(risk_level IN ('low','medium','high')),
  enabled INTEGER NOT NULL DEFAULT 1,
  FOREIGN KEY(server_id) REFERENCES tool_server(server_id)
);

CREATE TABLE IF NOT EXISTS tool_call (
  tool_call_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  step_id TEXT NOT NULL,
  tool_name TEXT NOT NULL,
  arguments_json TEXT NOT NULL,
  result_json TEXT,
  status TEXT NOT NULL CHECK(status IN ('planned','running','succeeded','failed','blocked','cancelled')),
  approval_id TEXT,
  started_at TEXT,
  completed_at TEXT,
  FOREIGN KEY(run_id) REFERENCES run(run_id),
  FOREIGN KEY(step_id) REFERENCES run_step(step_id),
  FOREIGN KEY(tool_name) REFERENCES tool_definition(tool_name)
);

CREATE TABLE IF NOT EXISTS policy_rule (
  rule_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL CHECK(scope IN ('global','project','thread')),
  scope_id TEXT,
  rule_type TEXT NOT NULL,
  effect TEXT NOT NULL CHECK(effect IN ('allow','deny')),
  pattern TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approval (
  approval_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  tool_call_id TEXT NOT NULL,
  requested_at TEXT NOT NULL,
  approved_at TEXT,
  approved_by TEXT,
  decision TEXT NOT NULL CHECK(decision IN ('pending','approved','rejected')),
  rationale TEXT,
  FOREIGN KEY(run_id) REFERENCES run(run_id),
  FOREIGN KEY(tool_call_id) REFERENCES tool_call(tool_call_id)
);

CREATE TABLE IF NOT EXISTS tool_cache (
  cache_key TEXT PRIMARY KEY,
  tool_name TEXT NOT NULL,
  arguments_json TEXT NOT NULL,
  result_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  ttl_seconds INTEGER
);

CREATE TABLE IF NOT EXISTS checkpoint (
  checkpoint_id TEXT PRIMARY KEY,
  thread_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  step_id TEXT NOT NULL,
  state_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(thread_id) REFERENCES thread(thread_id),
  FOREIGN KEY(run_id) REFERENCES run(run_id),
  FOREIGN KEY(step_id) REFERENCES run_step(step_id)
);

CREATE TABLE IF NOT EXISTS memory_item (
  memory_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL CHECK(scope IN ('global','thread','project')),
  scope_id TEXT,
  key TEXT,
  value TEXT NOT NULL,
  importance REAL NOT NULL DEFAULT 0.5,
  created_at TEXT NOT NULL,
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS project (
  project_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  root_path TEXT NOT NULL,
  created_at TEXT NOT NULL,
  metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS instruction_source (
  source_id TEXT PRIMARY KEY,
  project_id TEXT,
  kind TEXT NOT NULL,
  path TEXT,
  precedence INTEGER NOT NULL,
  content TEXT NOT NULL,
  loaded_at TEXT NOT NULL,
  FOREIGN KEY(project_id) REFERENCES project(project_id)
);

CREATE TABLE IF NOT EXISTS zip_archive (
  zip_id TEXT PRIMARY KEY,
  path TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  sha256 TEXT,
  source_id TEXT NOT NULL DEFAULT '',
  package_id TEXT NOT NULL DEFAULT '',
  vault_root TEXT NOT NULL DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1,
  added_at TEXT NOT NULL,
  last_scanned_at TEXT
);

CREATE TABLE IF NOT EXISTS zip_entry (
  entry_id TEXT PRIMARY KEY,
  zip_id TEXT NOT NULL,
  package_id TEXT NOT NULL DEFAULT '',
  inner_path TEXT NOT NULL,
  size_bytes INTEGER,
  modified_at TEXT,
  crc32 TEXT,
  mime TEXT,
  entry_sha256 TEXT,
  parse_status TEXT NOT NULL DEFAULT 'pending',
  parse_error TEXT NOT NULL DEFAULT '',
  text_extracted INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(zip_id) REFERENCES zip_archive(zip_id)
);

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

CREATE TABLE IF NOT EXISTS document (
  doc_id TEXT PRIMARY KEY,
  source_uri TEXT NOT NULL,
  title TEXT,
  language TEXT,
  created_at TEXT NOT NULL,
  metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS chunk (
  chunk_id TEXT PRIMARY KEY,
  doc_id TEXT NOT NULL,
  chunk_index INTEGER NOT NULL,
  text TEXT NOT NULL,
  token_count INTEGER,
  page INTEGER,
  start_offset INTEGER,
  end_offset INTEGER,
  created_at TEXT NOT NULL,
  metadata_json TEXT,
  FOREIGN KEY(doc_id) REFERENCES document(doc_id)
);

CREATE TABLE IF NOT EXISTS chunk_vector (
  chunk_id TEXT PRIMARY KEY,
  vector_json TEXT NOT NULL,
  backend TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(chunk_id) REFERENCES chunk(chunk_id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(
  text,
  chunk_id UNINDEXED
);

CREATE TABLE IF NOT EXISTS citation (
  citation_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  source_uri TEXT NOT NULL,
  doc_id TEXT,
  chunk_id TEXT,
  page INTEGER,
  start_offset INTEGER,
  end_offset INTEGER,
  snippet TEXT,
  FOREIGN KEY(run_id) REFERENCES run(run_id)
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

CREATE TABLE IF NOT EXISTS index_snapshot (
  snapshot_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  backend TEXT NOT NULL,
  created_at TEXT NOT NULL,
  details_json TEXT
);

CREATE TABLE IF NOT EXISTS artifact (
  artifact_id TEXT PRIMARY KEY,
  thread_id TEXT NOT NULL,
  run_id TEXT,
  kind TEXT NOT NULL,
  uri TEXT NOT NULL,
  mime TEXT,
  sha256 TEXT,
  bytes INTEGER,
  created_at TEXT NOT NULL,
  metadata_json TEXT,
  FOREIGN KEY(thread_id) REFERENCES thread(thread_id),
  FOREIGN KEY(run_id) REFERENCES run(run_id)
);

CREATE TABLE IF NOT EXISTS secret (
  secret_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  cipher_text BLOB NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_run_thread_status ON run(thread_id, status);
CREATE INDEX IF NOT EXISTS idx_run_step_run_index ON run_step(run_id, step_index);
CREATE INDEX IF NOT EXISTS idx_tool_call_run_status ON tool_call(run_id, status);
CREATE INDEX IF NOT EXISTS idx_chunk_doc_index ON chunk(doc_id, chunk_index);
CREATE INDEX IF NOT EXISTS idx_citation_run ON citation(run_id);
CREATE INDEX IF NOT EXISTS idx_zip_entry_zip_inner ON zip_entry(zip_id, inner_path);
CREATE INDEX IF NOT EXISTS idx_zip_archive_source_active ON zip_archive(source_id, active);
CREATE INDEX IF NOT EXISTS idx_zip_entry_package_inner ON zip_entry(package_id, inner_path);
CREATE INDEX IF NOT EXISTS idx_citation_verification_run_status ON citation_verification(run_id, status);
