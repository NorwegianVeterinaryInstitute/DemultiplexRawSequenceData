# MiSeq data access

## Data storage area:

Hostname: seqtech01.vetinst.no  
IP: 128.39.96.73

> Folder structure:  

    ./mnt/data/ 
            ├── scratch                       # MiSeq writes the Runs here  
            ├── demultiplex                   # Demultiplex data is written here  
                ├── demultiplex_script.py    # Script used to demutliplex and QC the run   

## Read/Write access

* _scratch_ should have read/write access in MiSeq
* _scratch_ should have read access to lab users, Bjørn, XXXX
* _scratch_ should have write access to Arvind, Jeevan, XXXX
* _scratch_ should have read/write access to Rachid, IT_XXXX  
* 
* _demultiplex_ should have read/write access to MiSeq
* _demultiplex_ should have read/write access to lab users, Bjørn, XXXX
* _demultiplex_ should have write access to Arvind, Jeevan, XXXX
* _demultiplex_ should have read access to Vet Inst users who have provided the samples for sequencing
* _demultiplex_ should have read/write access to Rachid, IT_XXXX
  
## Backup
* Backup for _scratch_
* Backup for _demultiplex_
  
## Procedure
* How and where will the lab users, Bjørn, XXXX will access _demultiplex_ for run QC?
  
## Questions
* Arvind and Jeevan are using root**** for login ID. This should be changed to a personal one.
* How(Who) are(is) we going to transfer the data from _demultiplex_ to SAGA?
* How and when will the data be deleted from _scratch_?
* How and when will the data be deleted from _demultiplex_?
