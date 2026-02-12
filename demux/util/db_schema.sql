# more things to expand the schema on: date of upload, nird/irida, time for each file to be uploaded to nird,
# time for each pair to be uploaded to irida adn finish processing (maybe seperate)
-- runs: run_id (PK), started_at, ended_at, operator, host, software_versions (demux, guppy/dorado, barcoder), config_hash, input_paths, output_root, status, exit_code, error_summary
-- samples/barcodes: run_id (FK), barcode_id, sample_id, kit, assigned_reads, assigned_bases, unassigned_reads, yield_metrics, files_manifest_hash
-- artifacts+provenance: run_id (FK), file_path, file_type, size_bytes, mtime_ns, checksum_sha512, remote_uri, upload_status, upload_attempts, tool_stdout/stderr_hash, log_path
-- phases: run_id (FK), phase_name (PK-part), started_at_ns, ended_at_ns, duration_ns, status, exit_code, stdout_path, stderr_path, log_path, commandline_hash
-- prepared_files: run_id (FK), phase_name (FK), path, kind (input/output/temp), size_bytes, mtime_ns, checksum_sha512, role (eg "multiqc_report", "raw_fastq"), remote_uri

--- metadata: what machine sequenced this run, by serial id

-- About that database you were talking about - I would have liked to have the unique sample lims id in it. The Sample_ID in the sample sheet isn't unique. 
-- So if I were to query the database from the shiny app for example, i would prefer to query by the unique lims id
-- If so, thats an additional column in the sample sheet.
-- we can have a view of the sample + date as primary key
-- Of course, even though unique for the sample it could be on several sequencing runs. So maybe one sample table where limsid is the primary key and separate tables for the demultiplexing runs.
-- The sequencing run also has one of those unique limsids by the way. Although there you also have the run id
 


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
