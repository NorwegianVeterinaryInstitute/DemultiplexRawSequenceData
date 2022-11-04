## demultiplex_script.py

Demutliplex a MiSEQ or NextSEQ run, perform QC using FastQC and MultiQC and deliver files either to VIGASP for analysis or NIRD for archiving

Replace <RunId> with relevant run id. Example <RunID>: "190912_M06578_0001_000000000-CNNTP". RunID breaks down like this (date +%y%m%d/yymmdd_MACHINE-SERIAL-NUMBER_AUTOINCREASING-NUMBER-OF-RUN_10-digit-number-assigned-by-machine_CHECKSUM . 

    Note: don't bother with enforcing ISO dates of the directory name. It is an Illumina standard and they do not care.

Software requirements

    Python > v3.6
    bcl2fastq ( from https://emea.support.illumina.com/sequencing/sequencing_software/bcl2fastq-conversion-software/downloads.html )
    FastQC    ( https://www.bioinformatics.babraham.ac.uk/projects/fastqc/ )
    MultiQC   ( pip3 install multiqc )

or newer

## Directory structure on seqtech01.vetinst.no

    /data/
          ├── bin                                 # Contains the cron job and demultiplexing scripts
              ├── cron_job.py
              ├── demultiplex_script.py
          ├── rawdata                             # MiSeq writes the Runs here; Mounted on MiSeq as Z:\
              ├── SampleSheets                    # Copy of all SampleSheets
          ├── demultiplex                         # Demultiplex data goes here
          ├── for_transfer                        # The procesed data to be trnasfered goes here; Mounted on MiSeq as Y:\


## Procedure
* MiSeq writes as _sambauser01_ to /data/scratch; shared folder Z:\ (alias rawdata) in MiSeq
* Lab members modify an existing  _SampleSheet.csv_ file to include the new project data, then save the new file to the \<RunId\> folder in Z:\ and a copy within Z:\SampleSheets\ as \<RunId\>\SampleSheet.csv

> Example:

    Z:\190912_M06578_0001_000000000-CNNTP
            ├── SampleSheets.csv
    Z:\SampleSheets
            ├── 190912_M06578_0001_000000000-CNNTP.csv

* Cron job runs every 30 minutes if it finds a new run, _RTAComplete.txt_ and _SampleSheet.csv_ files within the run new, it starts the demultiplexing script
* It can be manually started as below
```bash
[sambauser01@seqtech01 bin (master)]$ clear; rm -rf /data/demultiplexing/\<RunID\> ; /usr/bin/python3 /data/bin/demultiplex_script.py \<RunID\>
```

## Things we need to think about

### Backups
* Backups, lack of, discuss

### Deletion protocol

* _scratch_
* _demultiplex_

### Automated Transfer to VIGASP

TBD
TODO: decide account which we will use to automate the "Transfer To VIGASP" process


### Automated Transfer to SAGA

TBD
TODO: decide account which we will use to automate the "Transfer To SAGA" process

### Automated Transfer the demultiplexed run folder from seqtch01.vetinst.no to NIRD 

For now, archiving to NIRD is done by hand, after a lab technician reviews the QC results. The transfer is done this way (replace relevant bits)
```
$ rsync --progress --info=progress2 --no-inc-recursive -arvpe ssh  sambauser01@seqtech:/data/for_transfer/<RunID>/  NIRDUSERNAME@nird.sigma2.no@/nird/projects/NS9305K/SEQ-TECH/data_delivery
```
TODO: decide account which we will use to automate the "Transfer To NIRD" process

## Regarding SampleSheet.csv:

The structure of SampleSheet.csv is owned by Illimina. The good part is that it has been set this way to be backwards compatible with any sequencer, so, while you can *build* on it, you can also trust that your SampleSheet.csv will be parsed by older sequencers from 2 decades ago. For more information:
```
https://support-docs.illumina.com/APP/AppBCLConvert_v1_3/Content/APP/SampleSheets_swBCL_swBS_appBCL.htm
```

To see what a SampleSheet.cvs looks like, you can go here
```
https://github.com/brwnj/bcl2fastq/blob/master/data/SampleSheet.csv
```

In this script, the essential part for NVI is that we are using Python's native slicing and indexing to grab the values of [Sample_Project] to use during demultiplexing.

