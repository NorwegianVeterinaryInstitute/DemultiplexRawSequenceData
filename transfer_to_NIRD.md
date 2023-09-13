### Transfer files from the for_transfer folder to NIRD 
Map samba-share, if not mapped already:
```
\\10.10.71.10\for_transfer
```
Log onto NIRD in WinSCP (hostname: nird.login-lmd.sigma2) and cd to:
```
/nird/projects/NS9305K/SEQ-TECH/data_delivery
```
In WinSCP, copy the compressed (tar) demultiplexed run folder and its md5sum to NIRD.

Alternatively, using rsync
```
$ rsync -rauPW <tar> <tar.md5> \
  <NIRD_USERNAME>@nird.login-lmd.sigma2.no:/projects/NS9305K/SEQ-TECH/data_delivery/
```


------
### Check that the transfer is successful in NIRD
Log into NIRD:
```
$ ssh <USERNAME>@nird.login-lmd.sigma2.no
```
Move to the destination folder:
```
$ cd /projects/NS9305K/SEQ-TECH/data_delivery/
```
Check the md5sum for the transferred tar file:
```
$ md5sum -c <RunID>.tar.md5
```
If the output says 'OK', 
Change the persmission on the files:
```
$ chmod 444 <RunID>*
```
Create a README-file:

```
nano README_<RunID-Run#>
example README_230509_M06578_0145

alternatively,
open a README from a similar run using nano, make modifications and save using the new name
```

------
### Delete the transferred files in the for_transfer folder

Navigate to the samba-share and delete the transferred files

-----

### Send email to contact person
Template below: 
-----
Hei! 

< n samples > ble sekvensert i run #< Run# >  og sekvensdata ligger i følgende .tar-fil: 

RunID.x.tar                          

på NIRD: /projects/NS9305K/SEQ-TECH/data_delivery/

Vennligst kopier (ikke flytt) data over i egen folder på NIRD. 

README-fil for dette run ligger på NIRD og heter: README_< RunID >_< Run# >

Information on data storage:
The data from the sequencer will be kept on an in-house server for 3 months before deletion. During that time it will be possible to re-demultiplex the files in case some error with the indexes are discovered. The fastq files will be kept on the same in-house server for 1 month before deletion, in case some error in the transfer to NIRD or other locations are discovered. It is the user's own responsibility to check that their data delivered to them seems to be ok within this timeframe.


-----
### All tasks completed!!!

