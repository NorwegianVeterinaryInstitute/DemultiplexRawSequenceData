# demux 2.0: what it does, how to use it, when to use it

Version 1.65 stopped after the tar files. Everything after that, the upload to VIGASP and the archive to NIRD, was done by hand. 2.0 does the whole chain without anyone touching it. This is a tour of what is new, written for the people who will run it, watch it or ask it for things. The line-by-line list of changes is in `Changelog.md`; the install steps are in `deployment/2.0/v2.0.md`.

## 1. Queue order and locking

Run detection works as before: the timer runs the script every 20 minutes and every run under `/data/rawdata/` with `RTAComplete.txt`, `CopyComplete.txt` and `SampleSheet.csv` and without a `<RunID>_demultiplex` folder is processed. What is new is the order and the guard rails. Runs are taken oldest first, one after the other. Only one instance can run at a time, for the whole length of the run and not only while it starts; a second one exits with `Demux already running, exiting.`

How to use it: do nothing. When the sequencer finishes and ShinyLIMS has written the SampleSheet, the run is picked up within 20 minutes.

When to run it by hand: when you do not want to wait for the tick or when you want one specific run and not every pending one. The same script does both:

    /data/bin/demultiplex.py                     # everything that is pending, oldest first
    /data/bin/demultiplex.py <RunID>             # this run only
    /data/bin/demultiplex.py <RunID1> <RunID2>   # these runs, in this order

A run that already has a `<RunID>_demultiplex` folder is refused with `File already exists! Exiting!`. A finished run cannot be overwritten by accident and it cannot be marked as failed by accident either: the script only writes a failure marker into a folder it created itself.

## 2. SampleSheet delivery columns

What it does: four columns in the `[Data]` section decide where each sample goes. ShinyLIMS fills them in.

| Column | Meaning |
|---|---|
| `Transfer_VIGAS` | `Yes`: upload the sample's FASTQ pair to VIGASP. |
| `VIGASP_ID` | The IRIDA project number the sample goes into. |
| `Transfer_NIRD` | `Yes`: archive the project's tar file on NIRD. |
| `NIRD_Location` | The NIRD directory the tar file goes under. |

Every row must carry a whole number in `VIGASP_ID` and an absolute path in `NIRD_Location`, whether or not the transfer flags are `Yes`. The pipeline is strict on purpose: a sheet that is wrong stops the run at the very beginning, before bcl2fastq, with a message naming the column and the sample. The checks:

- `Sample_ID` set, `Sample_Project` set.
- `Sample_Name` empty or equal to `Sample_ID`. A different `Sample_Name` makes bcl2fastq write per-sample subfolders, which nothing downstream expects.
- `VIGASP_ID` an integer, `NIRD_Location` an absolute path.
- Within one `Sample_Project`, the same `Transfer_NIRD` and the same `NIRD_Location` on every row. A project is one tar file; it cannot go to two places.

Controls: every project named `Control_<tag>` or `Negativ` is demultiplexed and kept in `/data/demultiplex/`, but never QC'd, tarred or delivered. A project in which no sample produced any reads is dropped with a warning instead of failing the run; its numbers remain in the MultiQC stats.

When to care: when a run stops at step 1 or 2 of 30. That is always the sheet. Fix it in ShinyLIMS, replace `SampleSheet.csv` in the run folder, remove the failed folders and let the timer take it again.

## 3. Delivery to VIGASP (IRIDA)

What it does: for every sample with `Transfer_VIGAS=Yes`, in order:

1. Fetches the IRIDA credentials from Bitwarden and checks that every `VIGASP_ID` project exists.
2. Computes the sha256 of each FASTQ.
3. Creates one IRIDA sequencing run for the whole demultiplex run.
4. Finds the sample by name in the project or creates it. Characters IRIDA does not allow in a sample name (dots, spaces, brackets and a few more) become underscores: `2024_EQA13.Strain0020` is `2024_EQA13_Strain0020` in IRIDA.
5. Uploads the R1 and R2 files as a pair, two pairs in flight, with a 60 s pause between batches so IRIDA's own processing keeps up.
6. Polls IRIDA until it reports a sha256 for every uploaded file and compares it with the local one.
7. Only when every file matches, sets the sequencing run to COMPLETE and writes `VigaspDeliveryComplete.txt`.

The file names in IRIDA carry the run: `260807_M09180.<Sample_ID>_S1_R1_001.fastq.gz`.

When something fails: the run stops with the IRIDA error, the sequencing run stays in UPLOADING and nothing is retried. A sample that was already uploaded before the failure is in IRIDA; running the RunID again would add a second copy to it. Delivery failures are sorted out by hand, not by a re-run.

When to skip it: `--skip-vigasp` makes and verifies everything locally and on NIRD but uploads nothing to IRIDA. Use it for a run that must not reach VIGASP or for testing.

## 4. Delivery to NIRD

What it does: for every project with `Transfer_NIRD=Yes`, the project tar file and its `.md5` and `.sha512` are copied straight into `<NIRD_Location>/` over SSH, up to five files at once. After each copy, `md5sum` and `sha512sum` run on NIRD and the results are compared with the local sums. The QC tar stays local for now.

The SSH side is taken entirely from the `seqtech` user's `~/.ssh/config`: hostname, user, port, any ProxyJump chain, strict host key checking. Two-factor login to NIRD uses a TOTP and a password fetched from Bitwarden at the moment of login; nothing is stored on disk. The log says which host it connected to and through which jump hosts:

    Connected to login.nird.sigma2.no:22 over ProxyJump <jump>

If a tar file with the same name already exists in `<NIRD_Location>/`, the run stops before anything is copied over it:

    RuntimeError: Remote file already exists: login.nird.sigma2.no:/nird/.../wgs-bacteria/<date_instrument>.<project>.tar

That is deliberate. The script never overwrites a file on NIRD. The `<NIRD_Location>/` directory itself must exist; the script does not create it.

When to skip it: `--skip-nird`. Same idea as `--skip-vigasp`.

## 5. Run state markers

What it does: the run folder `/data/demultiplex/<RunID>_demultiplex/` gets a marker file at the end of each phase:

| Marker | Written when |
|---|---|
| `DemultiplexComplete.txt` | FASTQ, QC and tar files are done and the tar files have been test-extracted. |
| `VigaspDeliveryComplete.txt` | Every sample is in IRIDA and verified. |
| `NirdDeliveryComplete.txt` | Every tar file is on NIRD and verified. |
| `RunComplete.txt` | The run is finished. |
| `DemultiplexFailed.txt` | The run stopped. First line: the reason. Below: the full traceback. |

A failure before the run folder exists (a SampleSheet error, say) still gets a folder and a `DemultiplexFailed.txt`, so a broken run is never silently retried every 20 minutes.

On every tick the script reports what it sees, in `/data/log/demultiplex.log` and on the console when run by hand:

    12 in rawdata, 9 in demultiplex, 2 incomplete, 1 new runs ready.
    INCOMPLETE RUN: 999999_M09180_9999_000000001-MDJ2D
        reason:  ValueError: Sample_Project is empty for sample 'TESTDATA_000000001_MDJ2D_0001'. Aborting.
        this run is skipped until the incomplete directory is removed:
        rm -rvf /data/demultiplex/999999_M09180_9999_000000001-MDJ2D_demultiplex* /data/for_transfer/999999_M09180_9999_000000001-MDJ2D*

A failure stops the queue: the failed run is not retried and no newer run is started until its folders are removed. Every tick reports the failed run with the command that removes it and names the runs held behind it, so a bad sheet is fixed by a person rather than retried in a loop or stepped over.

What it does not yet record: which step a run is in while it runs. A folder without any marker is either in progress or dead; the log tells which. Per-step state is planned (#238).

## 6. Logs

| File | Contents |
|---|---|
| `/data/log/<RunID>.log` | Everything the script did for this run, step by step, numbered `n/30 tasks`. |
| `/data/log/demultiplex.log` | The same, for every run, appended. |
| `/data/demultiplex/<RunID>_demultiplex/demultiplex_log/` | `00_script.log` plus the raw bcl2fastq, FastQC and MultiQC output. |
| `journalctl --user -u demux.service` | What systemd saw, mostly the same as the console. |

Every failure is logged once, at CRITICAL, with the step that raised it. Tracebacks are printed in full on purpose.

## 7. Command line

`demultiplex.py` has subcommands now. The ones that work:

| Form | Does |
|---|---|
| `demultiplex.py` | Scan and process everything pending. |
| `demultiplex.py <RunID> ...` | Process these runs. Shorthand for `run`. |
| `demultiplex.py run <RunID> ... [--skip-vigasp] [--skip-nird]` | The same, spelled out. |
| `demultiplex.py --version` | Print the version. |
| `demultiplex.py --help`, `demultiplex.py run --help` | Help. |

Tab completion works for subcommands, flags and RunIDs (it lists `/data/rawdata/`) once the argcomplete hook is in the shell.

Everything else on the command line is parsed but refused:

    error: --dry-run: not yet implemented.
    error: validate: not yet implemented.

That covers `--dry-run`, `--force`, `--only-vigasp`, `--only-nird`, `--note`, `--config`, `-v` and the `--skip-*` flags other than the two above as well as all subcommands other than `run`. They are in the help because they are planned; refusing them is safer than running the full pipeline with an option silently ignored, which is what `--dry-run` would otherwise have done.

## 8. Credentials

Nothing secret is in the code or in a config file. The IRIDA client id, client secret and user, the NIRD user, password and TOTP seed, all live in Bitwarden, served locally by `bw serve` on seqtech00 and fetched by hostname at the moment they are needed.

The price is that the vault is locked after every reboot of seqtech00. `bw-serve.service` sends a mail when that happens. Unlocking takes two minutes and is written up for the lab in `unlock-bitwarden-on-seqtech00.md`; `vault_status.sh` answers in one line whether anything needs doing:

    /usr/local/bin/vault_status.sh
    Vault is UNLOCKED. Everything is ready.

## 9. Test runs

`scripts/make_test_run.py <real RunID>` clones a real run into `/data/rawdata/999999_M09180_9999_<counter>-<flowcell>` and rewrites its SampleSheet so every sample is called `TESTDATA_<counter>_<flowcell>_<NNNN>`. Projects, flags and NIRD paths stay as they were, so the fake run exercises the real IRIDA projects and the real NIRD directories with data that is unmistakably test data. The `999999_` prefix is how everything downstream recognises it.

    scripts/make_test_run.py 260807_M09180_0070_000000000-MDJ2D
    /data/bin/demultiplex.py 999999_M09180_9999_000000003-MDJ2D

Cleaning up afterwards:

- `scripts/delete_test_pairs.py 999999_M09180 <project id> ...` removes the test pairs from IRIDA by file name prefix. Dry run unless `--delete` is given.
- `scripts/remove_nird_test_directory.sh <RunID>` removes one test run directory from NIRD; with the flat layout the test tar files are removed by hand with `rm -rvf <NIRD_Location>/999999_*`.

Removing a delivered run from NIRD through the pipeline itself is planned and will be limited to `999999_` runs at first.

## 10. What was tested

The validation runs are documented in #211. The last full test run, `999999_M09180_9999_000000005-MDJ2D` on seqtech00 with no skip flags: 44 of 44 samples uploaded to IRIDA and verified, sequencing run set to COMPLETE, 8 of 8 project tar files on NIRD and verified, all four markers written. VIGASP side confirmed by Jeevan.

The first production run, `261009_M09180_0075_000000000-MH2KV` on 11 October 2026, was picked up by the timer at 19:40 and finished at 20:46: 46 of 46 pairs to IRIDA, 10 of 10 project tar files to NIRD, all verified, nobody at the keyboard. Cathrine watched it.

## 11. Not in 2.0

- No retries, no resume and no automatic cleanup. A failed run stops and waits.
- No `--dry-run`, no `--only-vigasp` or `--only-nird`, no partial re-delivery. A run that failed during delivery is sorted out by hand.
- No per-step state while a run is in progress (#238).
- No mail or Teams notification from the pipeline itself; the information is in the markers and the logs.
- IRIDA is reached over plain HTTP inside the NVI network until the NREC contract allows otherwise (#225).
- Removal of delivered data from NIRD is not automated.
- Runs sequenced before the SampleSheet got the delivery columns (before November 2025) cannot be processed by 2.0 as they are (#179).
