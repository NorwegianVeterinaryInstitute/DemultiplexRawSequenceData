# DemultiplexRawSequenceData

## Branch: `26-feature-request-deliver-to-nird`

---

# 1. Branch Overview

This branch introduces deterministic, per-project delivery of demultiplexed Illumina data to NIRD with strict routing, host key validation, and transfer verification.

The core addition is explicit upload metadata per Sample_Project tar and a controlled SSH transport model built on Paramiko.

---

# 2. High-Level Workflow

The system performs the following stages:

1. Detect new completed Illumina runs
2. Demultiplex via `bcl2fastq`
3. Run QC via FastQC and MultiQC
4. Package per Sample_Project tar archives
5. Deliver to NIRD with verified transport and checksum validation

Each stage is idempotent and logs explicit outcomes.

---

# 3. System Boundaries

## Inputs

* Illumina run folder
* `RTAComplete.txt`
* `SampleSheet.csv`
* Sequencing server directory structure
* Local SSH configuration
* Known hosts file

## Outputs

Per run:

```
RunID/
    demultiplex/
    qc/
    for_transfer/
        <Sample_Project>.tar
```

Per tar:

* Exactly one Sample_Project
* Embedded metadata including:

  * `nird_upload_location`
  * checksum values
  * run identifier

---

# 4. Core Invariants

1. One tar equals one Sample_Project.
2. All samples within a Sample_Project resolve to exactly one identical `NIRD_Location`.
3. Upload routing is deterministic and stored explicitly on tar metadata.
4. Unknown SSH host keys are rejected.
5. Transfer success requires checksum verification.

If any invariant fails, execution aborts early, so the operator can intervene.

---

# 5. Stage Documentation

## 5.1 Run Detection

Purpose: Identify new completed runs.

Mechanics:

* Scan run directory root.
* Require `RTAComplete.txt`.
* Skip runs previously marked complete.
* Maintain idempotency through metadata tracking.

Failure Modes:

* Missing SampleSheet
* Partial run
* Corrupt directory

---

## 5.2 Demultiplex

Tool: `bcl2fastq`

Inputs:

* Run folder
* SampleSheet

Outputs:

* FASTQ files under `demultiplex/`

Abort Conditions:

* Non-zero exit code
* Missing expected FASTQ output

---

## 5.3 Quality Control

Tools:

* FastQC
* MultiQC

Outputs:

```
qc/fastqc/
qc/multiqc_report.html
```

Failure in QC does not invalidate demultiplexed data unless explicitly configured.

---

## 5.4 Packaging

Mechanics:

* Group samples by Sample_Project.
* Validate that all samples within group share identical `NIRD_Location`.
* Fail immediately if mismatch.
* Produce:

```
for_transfer/<Sample_Project>.tar
```

Metadata attached:

* `nird_upload_location`
* checksum values
* upload flag
* run context

The list `absoluteFilesToTransferList` must include:

```
upload_to_nird: true
```

---

# 6. NIRD Delivery Model

## 6.1 Destination Resolution

Upload base path is derived per project.

It is not a global constant.

The resolved `NIRD_Location` is attached to tar metadata and becomes the single source of truth.

All upload logic reads from tar metadata only.

---

## 6.2 Authentication Model

NIRD enforces 2FA.

The branch supports:

* SSH key authentication
* Optional agent-based authentication
* Bitwarden local API for password retrieval
* TOTP integration when required

Constraints:

* No passwords stored on disk
* Bitwarden binds to localhost only
* Secrets exist in memory only

---

## 6.3 SSH Topology

Transport chain may include ProxyJump hops.

Mechanics:

* Parse `~/.ssh/config`
* Expand ProxyJump chain explicitly
* Build transport stack per hop
* Open `direct-tcpip` channels
* Wrap channel in new Transport
* Authenticate per hop
* Maintain LIFO teardown order

No implicit inference beyond ssh config.

---

## 6.4 Host Key Policy

* Strict host key verification.
* Unknown host keys rejected.
* Mismatched keys abort execution.
* No AutoAddPolicy.

Operator must manually resolve mismatches in known_hosts.

---

## 6.5 Transfer Mechanics

Transport supports:

* SCP

SFTP will replace SCP on a later date.

Per tar:

1. Ensure remote directory exists.
2. Transfer tar.
3. Compute checksum locally.
4. Validate remote checksum.
5. Confirm byte size match.

Success requires:

* Matching checksum
* No channel or transport errors

---

# 7. Paramiko Transport Lifecycle

Sequence:

1. Resolve proxyjump chain.
2. Create base Transport.
3. Authenticate.
4. Open channel.
5. Wrap next Transport if needed.
6. Perform file transfer.
7. Close channels.
8. Close transports in reverse order.

---

# 8. Error Taxonomy

## 8.1 Authentication Failures

* Key not accepted
* Agent missing key
* TOTP rejected
* Bitwarden timeout

## 8.2 Transport Failures

* DNS resolution failure
* TCP connect failure
* SSH banner failure
* Host key mismatch

## 8.3 Channel Failures

* `Secsh channel open FAILED`
* EOFError
* Remote command exit non-zero

## 8.4 Data Path Failures

* Remote disk full
* Quota exceeded
* Short write
* Timeout
* Socket reset

## 8.5 Post-Upload Verification Failures

* Checksum mismatch
* Missing remote file
* Size mismatch

All failure classes log explicit context including:

* RunID
* Sample_Project
* remote path
* transport hop

---

# 9. Concurrency Model

Parallel uploads use `ThreadPoolExecutor`.

Risks:

* Channel exhaustion
* Jump host limits
* Remote SSH max sessions
* Transient EOF

Transport isolation per thread is required.

No shared global Transport state.

---

# 10. Configuration Reference

Config parameters include:

* Run root path
* Demultiplex output path
* QC output path
* Transfer directory path
* Bitwarden base URL
* Bitwarden port
* SSH timeout values
* Retry counts
* NIRD base path
* Logging verbosity

Precedence:

1. Explicit config file
2. Environment variables
3. Hardcoded defaults

SSH topology derives strictly from `~/.ssh/config`.

---

# 11. Security Model

## Secret Exposure Points

* In-memory password retrieval
* Agent-held private keys
* TOTP tokens
* Process logs if misconfigured

## Explicitly Prevented

* Passwords on disk
* Blind host key acceptance
* Implicit routing
* Undocumented upload destinations

---

# 12. Logging and Audit

Each tar logs:

* Resolved NIRD destination
* Upload start time
* Upload completion
* Checksum values
* Verification result

Logs allow correlation between:

* RunID
* Sample_Project
* NIRD path
* transport hop

---

# 13. Developer Structure

## Module Responsibilities

* Run detection
* Demultiplex orchestration
* QC orchestration
* Tar packaging
* Metadata attachment
* SSH resolution
* Transport construction
* Upload execution
* Verification
* Error classification

Each module has single-stage responsibility.

---

# 14. Adding New Delivery Targets

Mechanics require:

* New routing metadata key
* Explicit invariant definition
* Dedicated upload implementation
* Explicit checksum policy

No implicit reuse of NIRD routing logic.

---

# 15. Operator Runbook

## Symptom: Channel open failed

Likely:

* Jump host unreachable
* ProxyJump misconfiguration
* Remote MaxSessions exceeded

## Symptom: EOFError

Likely:

* Channel closed by server
* Remote quota exceeded
* Transport reset

## Symptom: Host key mismatch

Cause:

* Remote host key changed
* Man-in-the-middle possibility

Action:

* Manual verification required

## Symptom: Checksum mismatch

Cause:

* Partial transfer
* Remote write truncation

Abort and retry after investigation.

---

# 16. Explicit Guarantees of This Branch

* Deterministic per-project upload routing.
* Strict host key validation.
* No credentials written to disk.
* Transfer verification mandatory.
* Early invariant failure detection.
* Explicit transport lifecycle management.

End.
