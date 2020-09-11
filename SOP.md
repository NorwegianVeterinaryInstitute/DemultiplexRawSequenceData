## Data storage area:
Hostname: seqtech01.vetinst.no  
IP: 128.39.96.73
> Folder structure:  

    ./mnt/data/ 
            ├── scratch                             # MiSeq writes the Runs here; Mounted on MiSeq as Z:\
                ├── SampleSheets                    # Copy of all SampleSheets
            ├── demultiplex                         # Demultiplex data goes here; Mounted on MiSeq as Y:\  
                ├── scripts                         # scripts
                    ├── cron_job.py                 # Cron job script 
                    ├── cron_out.txt                # Cron job output
                    ├── demultiplex_script_v5.py    # Script used to demutliplex and QC the run 
                    ├── demultiplex_script_v*.py    # Old script(s)


## Procedure
* MiSeq writes as _sambauser01_ to /mnt/data/scratch; shared folder Z:\ (alias rawdata) in MiSeq
* Lab members save the _SampleSheet.csv_ file to the \<RunId\> folder in Z:\ and a copy within Z:\SampleSheets\ as \<RunId>\.csv

> Example:  

    Z:\190912_M06578_0001_000000000-CNNTP 
            ├── SampleSheets.csv                             
    Z:\SampleSheets 
            ├── 190912_M06578_0001_000000000-CNNTP.csv                            
                 
      
                
* Cron job runs every three hours and if it finds a new run, _RTAComplete.txt_ and _SampleSheet.csv_ files within the run new, it starts the demultiplexing script
* It can be manually started as below
```bash
$ python /mnt/data/demultiplex/scripts/demultiplex_script_v5.py <RunId>
```
* Produced _\<RunId\>\_demultiplex_ in /mnt/data/demultiplex; shared folder Y:\ (alias demutiplex) in MiSeq
    
## SampleSheet.csv (Scroll to see the hidden part)

| __Sample_ID__ | __Sample_Name__ | __Sample_Plate__ | __Sample_Well__ | __Index_Plate_Well__ | __I7_Index_ID__ | __index__ | __I5_Index_ID__ | __index__ | __Sample_Project__ | __Description__ |__Analysis__|
|-------------|------------|------------|-------------|------------|------------|------------|------------|-------------|------------|------------|------------|
| \<empty\>     | SampleName     |       |          |      | UDP0018      |  AGAGGCAACC    | UDP0018      | CTAATGATGG         | Listeria_20200101     |       |   X   |

## Backup
* Daily backups that lasts for a month

## To do
### Deletion protocol
* _scratch_
* _demultiplex_

### Transfer to SAGA
* rsync _demultiplex_ to SAGA?

### Rename the VM
