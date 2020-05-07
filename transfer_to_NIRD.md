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
If the output says 'OK', All done!

------
Log in into MiSeq server:
```
$ ssh <USERNAME>@128.39.96.73
```
Move to demultiplexed directory:
```
$ cd /mnt/data/demultiplex
```
Remove the transferred tar and md5 file
```
rm <RUN_FOLDER.tar> <RUN_FOLDER.tar.md5>
```

<!--- Not implemented yet

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
DATA NEED NOT BE DELETED  
--->
