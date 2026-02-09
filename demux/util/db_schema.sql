PRAGMA foreign_keys = ON;

CREATE TABLE runs (
  run_id TEXT PRIMARY KEY,
  started_at_ns INTEGER NOT NULL,
  ended_at_ns INTEGER,
  operator TEXT,
  host TEXT,
  software_versions_json TEXT,
  config_hash TEXT,
  input_paths_json TEXT,
  output_root TEXT,
  status TEXT NOT NULL,
  exit_code INTEGER,
  error_summary TEXT
);

CREATE TABLE barcodes (
  run_id TEXT NOT NULL,
  barcode_id TEXT NOT NULL,
  sample_id TEXT,
  kit TEXT,
  assigned_reads INTEGER,
  assigned_bases INTEGER,
  unassigned_reads INTEGER,
  yield_metrics_json TEXT,
  files_manifest_hash TEXT,
  PRIMARY KEY (run_id, barcode_id),
  FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE TABLE phases (
  run_id TEXT NOT NULL,
  phase_name TEXT NOT NULL,
  started_at_ns INTEGER NOT NULL,
  ended_at_ns INTEGER,
  duration_ns INTEGER,
  status TEXT NOT NULL,
  exit_code INTEGER,
  stdout_path TEXT,
  stderr_path TEXT,
  log_path TEXT,
  commandline_json TEXT,
  commandline_hash TEXT,
  PRIMARY KEY (run_id, phase_name),
  FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE TABLE prepared_files (
  run_id TEXT NOT NULL,
  phase_name TEXT NOT NULL,
  path TEXT NOT NULL,
  kind TEXT NOT NULL,               -- input|output|temp
  role TEXT,                        -- eg multiqc_report|raw_fastq|bcl_out
  size_bytes INTEGER,
  mtime_ns INTEGER,
  checksum_sha512 TEXT,
  remote_uri TEXT,
  upload_status TEXT,               -- pending|ok|failed
  upload_attempts INTEGER DEFAULT 0,
  PRIMARY KEY (run_id, phase_name, path),
  FOREIGN KEY (run_id, phase_name) REFERENCES phases(run_id, phase_name) ON DELETE CASCADE
);

CREATE INDEX idx_phases_run ON phases(run_id);
CREATE INDEX idx_files_run ON prepared_files(run_id);
CREATE INDEX idx_files_role ON prepared_files(role);
