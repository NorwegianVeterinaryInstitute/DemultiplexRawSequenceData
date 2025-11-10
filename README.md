## demultiplex_script.py

Demutliplex a MiSEQ or NextSEQ run, perform QC using FastQC and MultiQC and deliver files either to VIGASP for analysis or NIRD for archiving

<RunID> is an Illumina designated string, used as the root folder for the specified sequence, e.g. "190912_M06578_0001_000000000-CNNTP". 

RunID breaks down like this (date +%y%m%d/yymmdd_MACHINE-SERIAL-NUMBER_AUTOINCREASING-NUMBER-OF-RUN_000000000-FlowcellID-used-for-this-run . 

    Note: don't bother with enforcing ISO dates for the directory name. It is an Illumina standard and they do not care.

Software requirements

    Python > v3.11
    bcl2fastq ( from https://emea.support.illumina.com/sequencing/sequencing_software/bcl2fastq-conversion-software/downloads.html )
    FastQC    ( https://www.bioinformatics.babraham.ac.uk/projects/fastqc/ )
    MultiQC   ( pip3 install multiqc )


## Directory structure on seqtech00

    ├── bin                                                         binaries and symlinks of binaries live here
    ├── clarity                                                     exported Illumina Clarity directory
    │   ├── gls_events  
    │   ├── logs                                                    clarity logs go here
    │   ├── miseq                                                   miseq-clarity stopover directory
    │   │   ├── M06578                                              per serial number
    │   │   │   └── samplesheets                                    samplesheets for this serial number go here
    │   │   └── M09180                                              other serial number
    │   │       └── samplesheets                                    samplesheets for other serial number go here
    │   └── nextseq                                                 nextseq-clarity stopover directory
    │       └── NB552450                                            per serial number
    │           └── samplesheets                                    samplesheets for this serial number gohere
    ├── demultiplex                                                 demultiplexed data directory
    ├── for_transfer                                                data ready to be transfered over to NIRD or VIGASP
    ├── logs                                                        all demultiplexing logs go here
    ├── rawdata                                                     raw data directory, sequencers write here
    │   ├── bad_runs                                                runs which are bad, or rejected
    │   └── control_runs                                            water/other control runs
    └── samplesheets                                                cummulative backups of all samplesheets

## Procedure
* MiSeq/NextSeq instrument writes as MiSEQ-serialID/NextSeq-serialID to /data/rawdata; shared folder Z:\ (alias rawdata) in MiSeq/NextSeq
* Lab members use template made by @magnulei to generate a new SampleSheet.csv, then save the new file to the Z:\<RunId\> folder

> Example:

    Z:\rawdata\190912_M06578_0001_000000000-CNNTP
                     ├── SampleSheets.csv

* Cron job runs every 15 minutes if it finds a new run, _RTAComplete.txt_ and _SampleSheet.csv_ files within the run new, it starts the demultiplexing script
* It can be manually started as below
```bash
clear; rm -rvf /data/{demultiplex,for_transfer}/<RunID>* && /data/bin/demultiplex.py <RunID>
```

as the relevant user.