# prod_bioinf

## Demutliplexing a MiSeq run: Cron job takes care of this now

## Manual demultiplexing steps:
### Log into seqtech01

Run data is at /mnt/data/scratch/<RunId>  
Demultiplex data will be available here at /mnt/data/demultiplex/<RunId>

Python script is available at:  
https://github.com/NorwegianVeterinaryInstitute/prod_bioinf/blob/master/scripts/demultiplex_script_v2.py  
/mnt/data/demultiplex/scripts/demultiplex_script_v2.py  

Execute the following command:

```
python /mnt/data/demultiplex/scripts/demultiplex_script_v2.py <RunId>
```

Replace <RunId> with <RunId> in the above command. Example <RunID> looks like "190912_M06578_0001_000000000-CNNTP".
  
The script checks if the run is complete (preference of file "RTAComplete.txt"), executes bcl2fastq, renames the fastq files to include the part of the <RunId> and completed quality control using FastQC and multiQC.

Python 3.6.7  
bcl2fastq v2.19.0.316  
FastQC v0.11.8  
MultiQC v1.7  
