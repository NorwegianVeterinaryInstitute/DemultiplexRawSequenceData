# Branch Documentation

## `27-feature-request-deliver-to-vigasp`

---

# Purpose

Upload demultiplexed paired-end FASTQ files to VIGASP (IRIDA 23.01.3) directly over the IRIDA REST API, verify every file after upload and mark the IRIDA sequencing run COMPLETE only when every file has been verified.

This replaces the PHAC irida-uploader for the demux pipeline. It does not change demultiplexing, QC or NIRD delivery.

---

# Why not the PHAC irida-uploader

Findings from reading the irida-uploader source, April 2026:

* A sample is marked uploaded as soon as the POST returns without error. There is no checksum verification (`core/api_handler.py`, lines 215-226).
* The status file `irida_uploader_status.info` silently turns ERROR into PARTIAL when a run ID exists.
* A shared `properties_dict` is mutated during upload; the parser hides this with `deepcopy` instead of isolating the write.

`v2.0` uses the same OAuth2 token method and the same REST endpoints, and adds post-upload verification against IRIDA's own `uploadSha256`.

---

# State Machine

See `docs/irida_uploader_state_machine_v6.png`.

```
PREFLIGHT -> CHECK PROJECTS -> HASH -> CREATE RUN -> UPLOAD -> VERIFY -> COMPLETE
```

Any failure goes to ERROR: the error is logged to the console and the failure log, the exception propagates and the sequencing run is NOT patched to COMPLETE. It stays in UPLOADING.

Entry point: `demux/steps/step07_deliver_files_to_VIGASP.py`. Wall time per stage is recorded in `demux.irida_stage_times`.

---

# Steps

## 1. Preflight (`step07_01_preflight.py`)

1. Probe `bw serve`; abort if it is unreachable or the vault is locked.
2. Fetch the IRIDA Bitwarden item by UUID (`irida_bw_item_uuid`). Username and password come from the login fields; `client_id` and `token` (the OAuth2 client secret) come from the notes field. UUID lookup is mandatory: name matching in Bitwarden is fuzzy and unreliable.
3. Acquire an OAuth2 bearer token (password grant) from IRIDA.
4. Collect every sample with `Transfer_VIGAS=Yes` from the SampleSheet. The IRIDA project is the `VIGASP_ID` column.
5. Resolve R1 and R2 `.fastq.gz` for each sample under `<demultiplexRunIDdir>/<runIDShort>.<Sample_Project>/` and verify both exist.

## 2. Check projects (`step07_02_check_projects.py`)

`GET /api/projects/{id}` for each unique `VIGASP_ID`. Any HTTP error aborts before anything is created in IRIDA.

## 3. Hash (`step07_03_hash.py`)

SHA-256 of every `.fastq.gz`, in parallel on all cores (`ProcessPoolExecutor`). The compressed files are hashed because IRIDA computes `uploadSha256` on the bytes it receives, before its own decompression.

## 4. Create run (`step07_04_create_run.py`)

`POST /api/sequencingrun` with `layoutType=PAIRED_END` and `sequencerType=directory`. IRIDA sets `uploadStatus=UPLOADING` on creation.

## 5. Upload (`step07_05_upload.py`)

For each sample:

1. Sanitize the name: IRIDA rejects `.?()[]/ =+<>:;"',*^|&`, which are replaced with `_`.
2. `GET /api/projects/{id}/samples`; if a sample with that name exists, its ID is used; otherwise `POST /api/projects/{id}/samples` creates it.
3. `POST /api/samples/{id}/pairs` with R1, R2 and `parameters1`/`parameters2` = `{"miseqRunId": <run id>, "layoutType": "PAIRED_END"}`.

Pacing: `irida_max_in_flight` pairs are uploaded in parallel; after each batch completes, the pipeline waits `irida_upload_batch_stagger_seconds` before the next batch, so IRIDA's asynchronous GzipFileProcessor and FastQC chain can drain.

The sample list call is retried under load: timeout `irida_list_timeout`, up to `irida_list_retries` attempts, backoff `irida_list_retry_backoff` seconds doubled after each attempt.

## 6. Verify (`step07_06_verify.py`)

For each uploaded sample, poll `GET /api/samples/{id}/sequenceFiles` until IRIDA has populated `uploadSha256` for R1 and R2, then compare with the local hashes. `uploadSha256` is computed asynchronously by IRIDA after the upload.

A mismatch, or a hash still empty after `irida_verify_max_poll_attempts`, fails the run. IRIDA itself does not verify uploads; this step is the only integrity check.

## 7. Complete (`step07_07_complete.py`)

`PATCH /api/sequencingrun/{id}` with `uploadStatus=COMPLETE`, only if verification passed. The run is never patched to ERROR: that PATCH has no side effects in IRIDA (it only updates a database field), so leaving the run in UPLOADING is the clearer signal.

---

# Configuration (`demux/core.py`)

| Setting | Default | Meaning |
|---|---|---|
| `irida_base_url` | `http://irida.vigasp.vetinst.no:8080/irida-23.01.3` | IRIDA instance |
| `irida_bw_item_uuid` | Bitwarden item UUID | IRIDA credentials item |
| `irida_timeout` | 60 s | metadata calls |
| `irida_list_timeout` | 180 s | project sample list |
| `irida_list_retries` | 6 | sample list attempts |
| `irida_list_retry_backoff` | 120 s | doubled per attempt |
| `irida_max_in_flight` | 2 | pairs uploaded in parallel |
| `irida_upload_batch_stagger_seconds` | 60 s | wait between batches |
| `irida_verify_max_poll_attempts` | 10 | polls for `uploadSha256` |
| `irida_verify_poll_interval_seconds` | 5 s | between polls |
| `irida_layout_type` | `PAIRED_END` | only layout supported |
| `irida_sequencer_type` | `directory` | IRIDA never implemented instrument types |

---

# Failure Classes

* Bitwarden unreachable or vault locked: abort in preflight, nothing sent to IRIDA.
* Credential field empty: abort in preflight.
* R1 or R2 missing: abort in preflight.
* IRIDA project inaccessible: abort before the sequencing run is created.
* Sample creation or pair upload fails: run left in UPLOADING, operator notified.
* Hash mismatch or `uploadSha256` never populated: run left in UPLOADING, operator notified.

---

# Known Limitations

* If a sample with the same name already exists in the target project, the pair is added to that sample. Test runs use `TESTDATA_<counter>_<NNNN>` names to avoid this (see #211).
* Deleting a sample in IRIDA leaves its analysis submissions behind; the Analyses tab then shows entries that open an error page. This is an IRIDA bug; see the analysis in #211.

---

# Operational Impact

* Credentials live only in Bitwarden and are read at run time; no IRIDA password is stored on disk.
* The vault must be unlocked after a reboot of seqtech00; see `docs/unlock-bitwarden-on-seqtech00.md`.
* `--skip-vigasp` runs the pipeline without this step.

---

# Testing

Integration test against IRIDA project 154 (#27). Production validation plan: #211.
