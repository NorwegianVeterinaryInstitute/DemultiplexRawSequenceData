## demultiplex_script.py

Demutliplex a MiSEQ or NextSEQ run, perform QC using FastQC and MultiQC and deliver files either to VIGASP for analysis or NIRD for archiving

Replace <RunId> with relevant run id. Example <RunID>: "190912_M06578_0001_000000000-CNNTP". RunID breaks down like this (date +%y%m%d/yymmdd_MACHINE-SERIAL-NUMBER_AUTOINCREASING-NUMBER-OF-RUN_000000000-FlowcellID-used-for-this-run . 

    Note: don't bother with enforcing ISO dates for the directory name. It is an Illumina standard and they do not care.

Software requirements

    Python > v3.9
    bcl2fastq ( from https://emea.support.illumina.com/sequencing/sequencing_software/bcl2fastq-conversion-software/downloads.html )
    FastQC    ( https://www.bioinformatics.babraham.ac.uk/projects/fastqc/ )
    MultiQC   ( pip3 install multiqc )


## Directory structure on seqtech00

	├── bin															binaries and symlinks of binaries live here
	├── clarity 													exported Illumina Clarity directory
	│   ├── gls_events	
	│   ├── logs 													clarity logs go here
	│   ├── miseq													miseq-clarity stopover directory
	│   │   └── M06578												per serial number
	│   │   	└── samplesheets									samplesheets for this serial number gohere
	│   └── nextseq													nextseq-clarity stopover directory
	│   	└── NB552450											per serial number
	│   		└── samplesheets									samplesheets for this serial number gohere
	├── demultiplex													demultiplexed data directory
	├── for_transfer												data ready to be transfered over to NIRD or VIGASP
	├── logs														all demultiplexing logs go here
	├── rawdata														raw data directory, sequencers write here
	│   ├── bad_runs												runs which are bad, or rejected
	│   └── control_runs											water/other control runs
	└── samplesheets												cummulative backups of all samplesheets
	├── M06578 -> /data/clarity/miseq/M06578/samplesheets/			symlinmk to sample sheets for convinience
	└── NB552450 -> /data/clarity/nextseq/NB552450/samplesheets/	symlinmk to sample sheets for convinience


## Procedure
* MiSeq writes as MiSEQ- to /data/scratch; shared folder Z:\ (alias rawdata) in MiSeq
* Lab members modify an existing  _SampleSheet.csv_ file to include the new project data, then save the new file to the \<RunId\> folder in Z:\ and a copy within Z:\SampleSheets\ as \<RunId\>\SampleSheet.csv

> Example:

    Z:\190912_M06578_0001_000000000-CNNTP
            ├── SampleSheets.csv
    Z:\SampleSheets
            ├── 190912_M06578_0001_000000000-CNNTP.csv

* Cron job runs every 30 minutes if it finds a new run, _RTAComplete.txt_ and _SampleSheet.csv_ files within the run new, it starts the demultiplexing script
* It can be manually started as below
```bash
/usr/bin/python3.11 /data/bin/demultiplex_script.py \<RunID\>
```

as the relevant user.
