## demultiplex_script.py

Demutliplex a MiSEQ or NextSEQ run, perform QC using FastQC and MultiQC and deliver files either to VIGASP for analysis or NIRD for archiving

Replace <RunId> with relevant run id. Example <RunID>: "190912_M06578_0001_000000000-CNNTP". RunID breaks down like this (date +%y%m%d/yymmdd_MACHINE-SERIAL-NUMBER_AUTOINCREASING-NUMBER-OF-RUN_000000000-FlowcellID-used-for-this-run . 

    Note: don't bother with enforcing ISO dates for the directory name. It is an Illumina standard and they do not care.

Software requirements

    Python > v3.6
    bcl2fastq ( from https://emea.support.illumina.com/sequencing/sequencing_software/bcl2fastq-conversion-software/downloads.html )
    FastQC    ( https://www.bioinformatics.babraham.ac.uk/projects/fastqc/ )
    MultiQC   ( pip3 install multiqc )


## Directory structure on seqtech01.vetinst.no

    /data/
          ├── bin                                 # Contains the cron job and demultiplexing scripts
              ├── cron_job.py                     # launch script, gets launched by cron every 30 minutes, checks if there are new runs, then either executes demultiplexing_script.py or exists
              ├── demultiplex_script.py           # the script that does all the heavy lifting
          ├── rawdata                             # MiSeq writes the Runs here; Mounted on MiSeq as Z:\
          ├── SampleSheets                        # Copy of all SampleSheets, named as the {RunID}.csv
          ├── demultiplex                         # Demultiplex data goes here
          ├── for_transfer                        # The procesed data to be transfered goes here; Mounted on MiSeq as Y:\
          ├── Logs                                # Keep the full logs for individual runs as RunID.log


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

### Non-Automated Transfer of demultiplexed run folder from seqtch01.vetinst.no to NIRD 

For now, archiving to NIRD is done by hand, after a lab technician reviews the QC results. The transfer is done this way (replace relevant bits)

```
[sambauser@seqtech01 ~]$ /usr/bin/rsync --progress --info=progress2 --no-inc-recursive -arvpe ssh  /data/for_transfer/<RunID>.*  NIRDUSERNAME@nird.sigma2.no@/nird/projects/NS9305K/SEQ-TECH/data_delivery
```
TODO: decide account which we will use to automate the "Transfer To NIRD" process

### How to create the md5 checksum of a file
```
sambauser@seqtech01 ~]$ /usr/bin/md5sum /path/to/file
```

### How to create the sha512 checksum of a file
```
sambauser@seqtech01 ~]$ /usr/bin/sha512sum /path/to/file
```

md5 is not considered a secure hash any more, too many collisions https://stackoverflow.com/questions/2117732/reasons-why-sha512-is-superior-to-md5

> Thirdly, similar to messages, you can also generate different files that hash to the same value so using MD5 as a file checksum is 'broken'.


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

# Notifications

WRITE MORE ABOUT SYSLOG & WORKPLACE NOTIFICATIONS 

Should expand more on this about:

- what notifications happen
- where to
- when
