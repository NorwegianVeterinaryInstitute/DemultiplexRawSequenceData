# Changelog: v1.65 (2026-03-05) -> v2.0 (2026-09-18)

## Delivery to VIGASP (IRIDA) *new*
- Full IRIDA upload state machine in step07: preflight and credentials from Bitwarden, project check, sequencing run creation, sample find-or-create, paired-end upload, sha256 verification against IRIDA's uploadSha256, run marked COMPLETE (#27).
- Parallel uploads bounded by irida_max_in_flight with a stagger between batches; benchmark harness and integration test against project 154; production defaults from the NREC benchmark, stagger raised to 60 s then 240 s for MiSeq file sizes.
- Per-sample Transfer_VIGAS and VIGASP_ID read from the SampleSheet; the development override to project 154 removed (#205).
- Retry with backoff on the IRIDA project sample list call under analysis load (#210).

## Delivery to NIRD *new*
- SSH transport: ProxyJump chain, host key verification, agent and private key auth, 2FA via Bitwarden TOTP; auth method now declared per hop from nird_access_mode, no hardcoded hostnames or Bitwarden item names (#212).
- Per-project NIRD_Location from the SampleSheet, per-project remote directories, Transfer_NIRD=No honoured, QC tar no longer sent (#205).
- Bounded parallel upload, integration test harness (test_step08.py).

## Run handling *new*
- Detection of new runs by comparing rawdata against demultiplex (#34, #122); SampleSheet-with-path-names.csv preferred when present (#195).
- Incomplete run detection: phase markers DemultiplexComplete, VigaspDeliveryComplete, NirdDeliveryComplete, RunComplete; DemultiplexFailed with the traceback; incomplete runs reported with the reason and the rm command, never re-run silently (#174).
- Control projects: Control_ prefix agreed with the lab; a project with no fastq.gz is a warning, dropped from QC, tar and delivery, kept in the MultiQC stats (#43, #49, #50, #202).
- Guard against SampleSheets older than 251110_M09180_0048 that lack the delivery columns (#179, partial).

## Command line *new*
- Subcommand parser with run, validate, clean and the future daemon commands; demultiplex.py <RunID> shorthand.
- --skip-vigasp and --skip-nird wired; --skip-qc-tarball renamed.
- Tab completion for subcommands, flags and RunIDs from /data/rawdata (argcomplete).
- Rerun hint reproduces the full command line.

## Fixes *new*
- step03: FastQC and MultiQC failures caught and logged with stdout and stderr instead of a raw traceback; exit 1 (#213).
- Bitwarden lookups report the HTTP error and the item searched.
- Duplicate console logging removed; IRIDA credentials moved from constants to Bitwarden at runtime.

## Tooling *new*
- scripts/make_test_run.py: clone a real run into an incrementing fake run with unique TESTDATA sample names in the real projects.
- scripts/delete_test_pairs.py: remove test-run pairs from IRIDA by file name prefix, dry run by default.
- Hash file tests for checksum.py; v2.0 deployment guide.
