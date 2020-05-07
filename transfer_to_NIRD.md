### Transfer the demultiplexed run folder to NIRD
Log in into MiSeq server:
```
$ ssh <USERNAME>@128.39.96.73
```
Move to demultiplexed directory:
```
$ cd /mnt/data/demultiplex
```
Rsync the compressed (tar) demultiplexed run folder and its md5sum to NIRD:
```
$ rsync -rauPW <RUN_FOLDER.tar> <RUN_FOLDER.tar.md5> \
  <NIRD_USERNAME>@login.nird.sigma2.no:/projects/NS9305K/SEQ-TECH/data_delivery/
```
Log out of MiSeq server.  

------
### Check the transfer is successful in NIRD
Log in into NIRD:
```
$ ssh <USERNAME>@128.39.96.73
```
Move to the destination folder:
```
$ cd /projects/NS9305K/SEQ-TECH/data_delivery/
```
Check the md5sum for the transferred tar file:
```
$ md5sum -c <RUN_FOLDER.tar.md5>
```
Change the persmission on the files:
```
$ chmod 444 <RUN_FOLDER.tar> <RUN_FOLDER.tar.md5>
```
Find the user's NIRD username
```
$ finger
```
Change the ownership of the files to the user
```
$ chown 
```


<!--- Not implemented yet

Filepermission to 444  
chwon to user  
finger command to find the username  
DATA NEED NOT BE DELETED  

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