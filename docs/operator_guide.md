# Demultiplexing on seqtech00: operator guide

For Cathrine. This covers what the demultiplexing script does with a finished sequencing run, what it needs from you, how to see where a run is and what to do when it stops. The Bitwarden part has its own guide, `unlock-bitwarden-on-seqtech00.md`.

## 1. What happens to a run

Once the MiSeq has written `RTAComplete.txt` and `CopyComplete.txt` and ShinyLIMS has written `SampleSheet.csv` into the run folder under `/data/rawdata/`, the script picks the run up on its own. It runs every 20 minutes (on the hour, 20 past and 40 past).

For each run it does the following, in this order:

1. Reads the SampleSheet and checks it. See: section 2 for more
2. Converts BCL to FASTQ with bcl2fastq.
3. Renames project folders and FASTQ files so they carry the run: project `23015-APEC_Escherichia` from run `260807_M09180_0070_000000000-MDJ2D` becomes `260807_M09180.23015-APEC_Escherichia` and its files `260807_M09180.<Sample_ID>_S1_R1_001.fastq.gz`.
4. Quality control:
   1. FastQC on every sample.
   2. MultiQC over the whole run.
5. Packs each named project into one tar file, with md5 and sha512 checksums.
6. Uploads the FASTQ pairs to VIGASP (IRIDA), one sample at a time and verifies each uploaded file against the checksum IRIDA reports back.
7. Uploads the project tar files to NIRD and verifies them with md5 and sha512 on the NIRD side. The QC tar file is not uploaded.

Runs are taken oldest first, one at a time. If a run stops with an error, everything stops: the failed run is not retried and no newer run is started until the failed one has been dealt with (sections 5 to 7). Every 20 minutes the script repeats what failed and which runs are waiting.

Where things end up:

| What | Where |
|---|---|
| FASTQ files, QC reports, logs | `/data/demultiplex/<RunID>_demultiplex/` |
| Tar files for delivery, with `.md5` and `.sha512` | `/data/for_transfer/<RunID>/` |
| Copy of the SampleSheet used | `/data/samplesheets/<RunID>.csv` |
| Log of this run | `/data/log/<RunID>.log` |
| Log of every run, appended | `/data/log/demultiplex.log` |
| VIGASP | the IRIDA project given by `VIGASP_ID`, sample by sample |
| NIRD | the directory given by `NIRD_Location`, one tar file per project (see below) |

On NIRD, each project tar file lands directly in the directory named in the SampleSheet. Today these are:

| `NIRD_Location` | What goes there |
|---|---|
| `/nird/datapeak/NS12018K/internal/illumina/wgs-bacteria/` | bacterial projects |
| `/nird/datapeak/NS12018K/internal/illumina/wgs-virus/` | viral projects |
| `/nird/datapeak/NS12018K/internal/illumina/controls/` | control projects; the SampleSheet names it, but the script never delivers controls |

The file names on NIRD are `<date_instrument>.<project>.tar` with `.md5` and `.sha512` next to each. For example:

    /nird/datapeak/NS12018K/internal/illumina/wgs-bacteria/261009_M09180.23015-APEC_Escherichia.tar
    /nird/datapeak/NS12018K/internal/illumina/wgs-bacteria/261009_M09180.23015-APEC_Escherichia.tar.md5
    /nird/datapeak/NS12018K/internal/illumina/wgs-bacteria/261009_M09180.23015-APEC_Escherichia.tar.sha512

## 2. The SampleSheet

ShinyLIMS fills in the SampleSheet. A wrong SampleSheet is the most common reason for a run to stop. These are the rules the script checks before starting any work:

| Column | Rule |
|---|---|
| `Sample_ID` | Must be set. This becomes the sample name in IRIDA. Dots, spaces, brackets and similar characters are replaced by underscores there, because IRIDA does not allow them. |
| `Sample_Name` | Empty or exactly the same as `Sample_ID`. Anything else makes bcl2fastq put the files in the wrong place, so the run stops before that happens. |
| `Sample_Project` | Must be set. The project is what gets delivered: bcl2fastq puts the FASTQ files in a folder per project, one tar file is made per project and `Transfer_NIRD` and `NIRD_Location` are decided per project. A sample without a project has nowhere to go. |
| `Transfer_VIGAS` | `Yes` or `No`. `Yes` means the sample is uploaded to VIGASP. |
| `VIGASP_ID` | The IRIDA project number, always a whole number, even when `Transfer_VIGAS` is `No`. |
| `Transfer_NIRD` | `Yes` or `No`. Every sample in the same project must have the same value. |
| `NIRD_Location` | The full NIRD path, starting with `/nird/`, always filled in, even when `Transfer_NIRD` is `No`. Every sample in the same project must have the same path. |

Control samples (`Control_PRK`, `Control_PTK`, `Control_EBK` and so on, plus anything called `Negativ`) are demultiplexed and kept under `/data/demultiplex/`, but they are not QC'd, not packed into tar files and not uploaded anywhere, whatever their `Transfer_` columns say. ShinyLIMS sets them to `Transfer to VIGAS = No` in any case.

A project where no sample got any reads (a water control in its own project, for example) is dropped with a warning and the run carries on without it. The read counts for it are still in the MultiQC report.

If a SampleSheet is wrong, the run stops at once with a message that names the column and the sample, for example:

    VIGASP_ID 'shotgun' for sample '22-80-93-P92-419-7t' is not a valid integer. Aborting.
    Sample_Project is empty for sample 'TESTDATA_000000001_MDJ2D_0001'. Aborting.
    NIRD_Location mismatch for Sample_Project '31226-AMR_Klebsiella': ['/nird/.../wgs-bacteria', '/nird/.../wgs-virus']. Aborting.

Section 6 says what to do then.

## 3. Seeing where a run is

In addition to watching the log file (`/data/log/<RunID>.log`, e.g. `/data/log/261009_M09180_0075_000000000-MH2KV.log`), look in `/data/demultiplex/<RunID>_demultiplex/`. The script leaves a small marker file behind at the end of each phase:

| File present | Meaning |
|---|---|
| no `<RunID>_demultiplex` folder at all | Not started. Either the run is not finished on the sequencer yet or the script has not come round to it. |
| folder exists, none of the files below | Running right now or it was killed. Check the log. |
| `DemultiplexComplete.txt` | FASTQ files, QC and tar files are done. |
| `VigaspDeliveryComplete.txt` | All samples are in IRIDA and verified. |
| `NirdDeliveryComplete.txt` | All tar files are on NIRD and verified. |
| `RunComplete.txt` | Everything finished. |
| `DemultiplexFailed.txt` | The run stopped. The first line of the file says why. |

The quickest check from PuTTY, logged in as `seqtech`:

    ls /data/demultiplex/<RunID>_demultiplex/*.txt

To watch a run that is ongoing, follow its log:

    tail -f /data/log/<RunID>.log

Press Ctrl-C to stop watching; that does not stop the run.

## 4. What the script will not do on its own

It never deletes anything, never retries a failed run and never re-uploads. When something goes wrong it stops, writes down why and waits for a person. That is on purpose: a run that is half uploaded or uploaded twice is harder to sort out than a run that stopped.

It also refuses to run on a RunID that already has a `<RunID>_demultiplex` folder:

    File already exists! Exiting!

That protects finished runs from being overwritten by accident.

## 5. When a run stops

Read the first line of the failure marker:

    head -1 /data/demultiplex/<RunID>_demultiplex/DemultiplexFailed.txt

The script also prints the same thing every 20 minutes in `/data/log/demultiplex.log`, as `INCOMPLETE RUN: <RunID>`, together with the command that removes the half-done folders.

## 6. What you can fix yourself

### SampleSheet errors

Messages that mention `Sample_ID`, `Sample_Name`, `Sample_Project`, `VIGASP_ID`, `NIRD_Location`, `Transfer_VIGAS` or `Transfer_NIRD` mean the SampleSheet broke one of the rules in section 2. These runs stop before anything was made or uploaded, so they are safe to run again.

1. Fix the SampleSheet in ShinyLIMS and put the corrected `SampleSheet.csv` into `/data/rawdata/<RunID>/`.
2. Remove the failed folders. The exact command is in the `INCOMPLETE RUN` message; it looks like this:

       rm -rvf /data/demultiplex/<RunID>_demultiplex* /data/for_transfer/<RunID>*

3. Wait for the next 20 minute tick or start it by hand (section 8).

### Bitwarden locked after a reboot

After seqtech00 has rebooted the vault is locked and the script cannot fetch its credentials. Unlock it as described in `unlock-bitwarden-on-seqtech00.md`; the script picks the run up again by itself if it had not started it yet.

## 7. When to contact demultiplexing support

When the first line of `DemultiplexFailed.txt` mentions any of these:

- IRIDA or VIGASP
- NIRD, SSH or ssh2fa
- Bitwarden, `bw` or the vault
- a timeout
- a hash or checksum mismatch
- `File already exists` on NIRD
- a Python traceback

A run that got as far as uploading may already have sample files in IRIDA, and running it again adds a second copy of every pair to the same samples. Do not remove the folders and do not run the RunID again; send the first lines of `DemultiplexFailed.txt` and the RunID.

## 8. Running by hand

Log in to seqtech00 with PuTTY as `seqtech` (same as in the Bitwarden guide).

Process one run now, without waiting for the timer:

    /data/bin/demultiplex.py <RunID>

Several runs, one after the other:

    /data/bin/demultiplex.py <RunID1> <RunID2>

Everything that is new:

    /data/bin/demultiplex.py

This is what the timer does, as well.

You can demultiplex a run and skip the delivery to VIGASP, to NIRD or to both. The script does not deliver a skipped run later; to deliver it, remove its folders and run the script again without the flag.

    /data/bin/demultiplex.py <RunID> --skip-vigasp
    /data/bin/demultiplex.py <RunID> --skip-nird
    /data/bin/demultiplex.py <RunID> --skip-vigasp --skip-nird

Pressing the Tab key completes RunIDs and options. Type the start of a RunID and press Tab:

    /data/bin/demultiplex.py 2610<Tab>
    /data/bin/demultiplex.py 261009_M09180_0075_000000000-MH2KV

With more than one match, press Tab twice to see them all. The same works for the flags:

    /data/bin/demultiplex.py 261009_M09180_0075_000000000-MH2KV --skip-<Tab><Tab>
    --skip-nird    --skip-vigasp

Only one copy of the script can run at a time. If the timer is already running one, the copy you started exits immediately with `Demux already running, exiting.` That is normal. Wait for the running one to finish and start yours again.

Running by hand does not change anything else: the same checks apply, the same files and markers are written and the timer keeps running in the background.

## 9. Things not to do

- Do not change `SampleSheet.csv` in `/data/rawdata/` once the run has started. The script keeps the copy it used in `/data/samplesheets/`; later changes do not reach a run already in progress. If the SampleSheet was wrong and the run went through, the run has to be done over: delete the local data under `/data/demultiplex/` and `/data/for_transfer/`, the tar files on NIRD and the samples in VIGASP, then fix the sheet and run again.
- Do not delete or rename anything under `/data/demultiplex/`, `/data/for_transfer/` or on NIRD by hand, other than the `rm` the script tells you to run for a failed run.
- Do not run a delivered run again. Once `VigaspDeliveryComplete.txt` or `NirdDeliveryComplete.txt` exists, a second run adds duplicate files to the samples in IRIDA and stops on NIRD because the tar files are already there.
- Do not make copies of run folders inside `/data/rawdata/`. A copy with `RTAComplete.txt`, `CopyComplete.txt` and `SampleSheet.csv` in it looks like a new run.
