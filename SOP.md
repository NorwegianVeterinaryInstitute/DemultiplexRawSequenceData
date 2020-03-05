# MiSeq data access

## Data storage area:

Hostname: seqtech01.vetinst.no  
IP: 128.39.96.73

> Folder structure:  

    ./mnt/data/ 
            ├── scratch                       # MiSeq writes the Runs here; Mounted on MiSeq as Z:\
                ├── SampleSheets              # Copy of all SampleSheets
            ├── demultiplex                   # Demultiplex data goes here; Mounted on MiSeq as Y:\
                ├── demultiplex_script_v2.py  # Script used to demutliplex and QC the run   
                ├── scripts                    # Contains the cron job and cron job output files. Also old scripts

## Procedure

* MiSeq writes as _sambauser01_ to /mnt/data/scratch; shared folder Z:\
* Lab members save the _SampleSheet.csv_ file to the \<RunId\> folder in Z:\ and a copy within Z:\SampleSheets\ as \<RunId>\_SampleSheet.csv
* Cron job runs every three hours and if it finds a new run, _RTAComplete.txt_ and _SampleSheet.csv_ files within the run new, it starts the demultiplexing script
* It can be manually started as below
```bash
$ python /mnt/data/demultiplex_script_v2.py <RunId>
```
* Produced _\<RunId\>\_demultiplex_ in /mnt/data/demultiplex; shared folder Y:\
    
## SampleSheet.csv

| __Sample_ID__ | __Sample_Name__ | __Sample_Plate__ | __Sample_Well__ | __Index_Plate_Well__ | __I7_Index_ID__ | __index__ | __I5_Index_ID__ | __index__ | __Sample_Project__ | __Description__ |
|-------------|------------|------------|-------------|------------|------------|------------|------------|-------------|------------|------------|
| \<empty\>     | SampleName     |       |          |      | UDP0018      |  AGAGGCAACC    | UDP0018      | CTAATGATGG         | Listeria_20200101     |       |

## Backup
* Daily backups that lasts for a month

## To do
### Deletion protocol
* _scratch_
* _demultiplex_

### Transfer to SAGA
* rsync _demultiplex_ to SAGA?
