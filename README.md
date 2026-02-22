# nvi-demux

nvi-demux is an operational demultiplexing and quality-control pipeline for Illumina MiSeq and NextSeq runs, developed for the [Norwegian Veterinary Institute](https://vetinst.no).
It converts BCL to FASTQ, runs FastQC and MultiQC and prepares structured output for upload to VIGASP (analysis) or NIRD (archiving).

# Usage

The script runs every 20 minutes, on the dot, via a systemd user timer.

## Run manually

Should you need to run it manually, log into seqtech as the seqtech user and run

```bash
/usr/local/bin/demultiplex.py <RunID>
```
<RunID> is the Illumina run directory name under /data/rawdata/ you need to demultiplex.

Example:

```bash
/usr/local/bin/demultiplex.py 190912_M06578_0001_000000000-CNNTP
```