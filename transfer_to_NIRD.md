### Transfer the demultiplexed run folder to NIRD
Log in into MiSeq server:
```
$ ssh <USERNAME>@128.39.96.73
```
Move to demultiplexed directory:
```
$ cd /mnt/data/demultiplex
```
Rsync the demultiplexed run folder to NIRD:
```
$ rsync -rauPW <RUN_FOLDER> <NIRD_USERNAME>@login.nird.sigma2.no:/projects/NS9305K/SEQ-TECH/data_delivery/
```
Log out of MiSeq server.  

------
### Check the transfer is successful in NIRD
Log in into NIRD:
```
$ ssh <USERNAME>@128.39.96.73
```
Move to the transferred folder:
```
$ cd /projects/NS9305K/datasets/wgs/<RUN_FOLDER>
```
md5sum check has not been implemented yet. This will happen before end of April.  

<!--- Not implemented yet
Check md5sum:
```
$ md5sum -c md5sum.txt > md5sum.check
```
Check if the number of lines in md5sum files match
```
$ wc -l md5sum.txt md5sum.check
```
Check if all the lines in md5sum.check contains 'OK'  
'-v' option in grep outputs lines that does NOT contain the search term ('OK' in this search)  
Following command should produce NO output (should return '$ ')
```
$ grep -v 'OK' md5sum.check
```
Delete the 'md5sum.check' file:
```
$ rm md5sum.check
```
--->
