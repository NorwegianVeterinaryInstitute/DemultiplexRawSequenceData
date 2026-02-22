# nvi-demux

nvi-demux is an operational demultiplexing and quality-control pipeline for Illumina MiSeq and NextSeq runs, developed for the [Norwegian Veterinary Institute](https://vetinst.no).
It converts BCL to FASTQ, runs FastQC and MultiQC and prepares structured output for upload to VIGASP (analysis) or NIRD (archiving).

# Usage

The script runs every 20 minutes, on the dot, via a systemd user timer.

## Run manually

Should you need to run it manually, log into seqtech as the seqtech user and run

```bash
/usr/local/bin/demultiplex <RunID>
```

Example:

```bash
/usr/local/bin/demultiplex 190912_M06578_0001_000000000-CNNTP
```




# demultiplex_script.py

Demutliplex a MiSEQ or NextSEQ run, perform QC using FastQC and MultiQC and deliver files either to VIGASP for analysis or NIRD for archiving

# Software requirements

    Python >= v3.11
    bcl2fastq    ( from https://emea.support.illumina.com/sequencing/sequencing_software/bcl2fastq-conversion-software/downloads.html )
    FastQC       ( https://www.bioinformatics.babraham.ac.uk/projects/fastqc/ )
    MultiQC      ( pip3 install multiqc )
    sample_sheet 
    paramiko  
    scp
    psutil   
    termcolor==3.3.0


# Usage

The software starts as a user systemd service, when the system comes up. It detects when a run is finished sequencing and begins demultiplexing.

You can manually start a run using
```bash
clear; rm -rvf /data/{demultiplex,for_transfer}/<RunID>* && /data/bin/demultiplex.py <RunID>
```

as the seqtech user.