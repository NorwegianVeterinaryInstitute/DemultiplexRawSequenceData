# MiSeq data access

## Data storage area:

Hostname: seqtech01.vetinst.no  
IP: 128.39.96.73

> Folder structure:  

    ./mnt/data/ 
            ├── scratch                       # MiSeq writes the Runs here; Mounted on MiSeq as Z:\
            ├── demultiplex                   # Demultiplex data goes here; Mounted on MiSeq as Y:\
                ├── demultiplex_script_v2.py  # Script used to demutliplex and QC the run   

## Read/Write access

* MiSeq writes as _sambauser01_ to /mnt/data/scratch; shared folder Z:\
* Lab members login to seqtech01.vetinst.no from MiSeq using Putty and personal credentials
* Execute python script _demultiplex_script_v2.py_ as below
```bash
$ python /mnt/data/demultiplex_script_v2.py <RunName>
```
* Produced _\<RunName\>\_demultiplex_ in /mnt/data/demultiplex; shared folder Y:\
    
## To do
* Backup for _scratch_ and _demultiplex_
* Create users in the VM and check the script.
* How(Who) are(is) we going to transfer the data from _demultiplex_ to SAGA?
* How and when will the data be deleted from _scratch_?
* How and when will the data be deleted from _demultiplex_?