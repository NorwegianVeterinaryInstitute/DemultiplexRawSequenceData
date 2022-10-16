This is the old prod_bioinf repo

Demutliplexing a MiSeq run: Cron job takes care of this now

Manual demultiplexing steps:
    Log into seqtech01
    Run data is at /mnt/data/scratch/<RunId>
    Demultiplex data will be available here at /mnt/data/demultiplex/<RunId>
    Python script is available at:
    https://github.com/NorwegianVeterinaryInstitute/prod_bioinf/blob/master/scripts/demultiplex_script_v5.py
    Execute the following command:

    python /mnt/data/demultiplex/scripts/demultiplex_script_v5.py <RunId>

    Replace <RunId> with <RunId> in the above command. Example <RunID> looks like "190912_M06578_0001_000000000-CNNTP".
    The script checks if the run is complete (preference of file "RTAComplete.txt"), executes bcl2fastq, renames the fastq files to include the part of the <RunId> and completed quality control using FastQC and multiQC.

Software requirements

    Python 3.6.7

    bcl2fastq ( from https://emea.support.illumina.com/sequencing/sequencing_software/bcl2fastq-conversion-software/downloads.html )

    FastQC v0.11.8

    MultiQC v1.7

    md5deep

or newer



## Data storage area:
Hostname: seqtech01.vetinst.no
IP: 128.39.96.73
> Folder structure:

    /data/
          ├── bin                                 # Contains the cron job and demultiplexing scripts
              ├── cron_job.py
              ├── current_demultiplex_script.py
          ├── scratch                             # MiSeq writes the Runs here; Mounted on MiSeq as Z:\
              ├── SampleSheets                    # Copy of all SampleSheets
          ├── demultiplex                         # Demultiplex data goes here; Mounted on MiSeq as Y:\              ├── scripts                         # scripts
                  ├── cron_job.py                 # Cron job script
                  ├── cron_out.txt                # Cron job output
                  ├── demultiplex_script_v5.py    # Script used to demutliplex and QC the run
                  ├── demultiplex_script_v*.py    # Old script(s)


## Procedure
* MiSeq writes as _sambauser01_ to /data/scratch; shared folder Z:\ (alias rawdata) in MiSeq
* Lab members save the _SampleSheet.csv_ file to the \<RunId\> folder in Z:\ and a copy within Z:\SampleSheets\ as \<RunId>\.csv

> Example:

    Z:\190912_M06578_0001_000000000-CNNTP
            ├── SampleSheets.csv
    Z:\SampleSheets
            ├── 190912_M06578_0001_000000000-CNNTP.csv

* Cron job runs every 30 minutes if it finds a new run, _RTAComplete.txt_ and _SampleSheet.csv_ files within the run new, it starts the demultiplexing script
* It can be manually started as below
```bash
$ python /data/demultiplex/scripts/current_demultiplex_script.py <RunId>
```
* Produced _\<RunId\>\_demultiplex_ in /data/demultiplex; shared folder Y:\ (alias demutiplex) in MiSeq

## SampleSheet.csv (Scroll to see the hidden part)

| __Sample_ID__ | __Sample_Name__ | __Sample_Plate__ | __Sample_Well__ | __Index_Plate_Well__ | __I7_Index_ID__ | __index__ | __I5_Index_ID__ | __index__ | __Sample_Project__ | __Description__ |__Analysis__|
|-------------|------------|------------|-------------|------------|------------|------------|------------|-------------|------------|------------|------------|
| \<empty\>     | SampleName     |       |          |      | UDP0018      |  AGAGGCAACC    | UDP0018      | CTAATGATGG         | Listeria_20200101     |       |   X   |


## To do
### Backup
* Daily backups that lasts for a month

### Deletion protocol
* _scratch_
* _demultiplex_

### Transfer to SAGA
* rsync _demultiplex_ to SAGA?

### Rename the VM



### Transfer the demultiplexed run folder to NIRD from MiSeq VM
Log in into MiSeq VM:
```
$ ssh <USERNAME>@128.39.96.73
```
Move to demultiplexed directory:
```
$ cd /mnt/data/demultiplex/<RUN_FOLDER>
```
Log out of MiSeq server
### Transfer the QC.zip file to your computer
```
$ cd Desktop
$ rsync -rauPW <USERNAME>@128.39.96.73:/mnt/data/demultiplex/<RUN_FOLDER>/QC .
```



### Transfer the demultiplexed run folder to NIRD from MiSeq VM
Log in into MiSeq VM:
```
$ ssh <USERNAME>@128.39.96.73
```
Move to demultiplexed directory:
```
$ cd //data/for_transfer
```
Rsync the compressed (tar) demultiplexed run folder and its md5sum to NIRD:
```
$ rsync -rauPW <tar> <tar.md5> \
  <NIRD_USERNAME>@login.nird.sigma2.no:/projects/NS9305K/SEQ-TECH/data_delivery/
```
Log out of MiSeq server
------
### Check the transfer is successful in NIRD
Log in into NIRD:
```
$ ssh <USERNAME>@login.nird.sigma2.no
```
Move to the destination folder:
```
$ cd /projects/NS9305K/SEQ-TECH/data_delivery/
```
Check the md5sum for the transferred tar file:
```
$ md5sum -c <tar.md5>
```
If the output says 'OK',Change the persmission on the files:
```
$ chmod 444 <tar> <tar.md5>
```
Log out of NIRD

------
### Delete the transferred files in MiSeq VM
Log in into MiSeq VM:
```
$ ssh <USERNAME>@128.39.96.73
```
Move to demultiplexed directory:
```
$ cd /data/for_transfer
```
Remove the transferred tar and md5 file
```
rm <tar> <tar.md5>
```

-----
### All tasks completed!!!

<!--- Not implemented yet


Find the user's NIRD username
```
$ finger
```
Change the ownership of the files to the user
```
$ chown```
DATA NEED NOT BE DELETED--->
### Transfer the demultiplexed run folder to NIRD from MiSeq VM
Log in into MiSeq VM:
```
$ ssh <USERNAME>@128.39.96.73
```
Move to demultiplexed directory:
```
$ cd //data/for_transfer
```
Rsync the compressed (tar) demultiplexed run folder and its md5sum to NIRD:
```
$ rsync -rauPW <tar> <tar.md5> \
  <NIRD_USERNAME>@login.nird.sigma2.no:/projects/NS9305K/SEQ-TECH/data_delivery/
```
Log out of MiSeq server
How to transfer over an ssh proxy:
1. setup the bastion host in  your ssh config

Host blastion
   Hostname mybastionhostname
   User bogon

2. Set up the remote and use the ProxyJump ssh option, and point it to the bastion:

Host remote
   Hostname remote.server.yes.no
   User boton
   ProxyJump blastion
scp -rv remote:/path/to/copy/from /path/to/copy/to/local

works with rsync!
rsync --progress --info=progress2 --no-inc-recursive -avpe ssh  seqtech:/data/scratch/220308_NB552450_0006_AHJ5F5AFX3 /mnt/downloads/seqtech/

if you got ssh keys setup, this will be a trip.


https://www.acagroup.be/en/blog/jump-hosts-file-transferring/
https://serverfault.com/questions/219013/showing-total-progress-in-rsync-is-it-possible



------
### Check the transfer is successful in NIRD
Log in into NIRD:
```
$ ssh <USERNAME>@login.nird.sigma2.no
```
Move to the destination folder:
```
$ cd /projects/NS9305K/SEQ-TECH/data_delivery/
```
Check the md5sum for the transferred tar file:
```
$ md5sum -c <tar.md5>
```
If the output says 'OK',Change the persmission on the files:
```
$ chmod 444 <tar> <tar.md5>
```
Log out of NIRD

------
### Delete the transferred files in MiSeq VM
Log in into MiSeq VM:
```
$ ssh <USERNAME>@128.39.96.73
```
Move to demultiplexed directory:
```
$ cd /data/for_transfer
```
Remove the transferred tar and md5 file
```
rm <tar> <tar.md5>
```

-----
### All tasks completed!!!

<!--- Not implemented yet


Find the user's NIRD username
```
$ finger
```
Change the ownership of the files to the user
```
$ chown```
DATA NEED NOT BE DELETED--->
