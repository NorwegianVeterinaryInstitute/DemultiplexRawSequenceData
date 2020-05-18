### Transfer the demultiplexed run folder to NIRD from MiSeq VM
Log in into MiSeq VM:
```
$ ssh <USERNAME>@128.39.96.73
```
Move to demultiplexed directory:
```
$ cd /mnt/data/demultiplex/<RUN_FOLDER>
```
Create QC.zip
```
$ zip -r <RUN_FOLDER>_QC.zip QC
```
Log out of MiSeq server  

### Transfer the QC.zip file to your computer
```
$ rsync -rauPW <USERNAME>@128.39.96.73:/mnt/data/demultiplex/<RUN_FOLDER>/<RUN_FOLDER>_QC.zip .
```
