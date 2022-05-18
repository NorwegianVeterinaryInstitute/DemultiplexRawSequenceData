### Transfer the demultiplexed run folder to NIRD from MiSeq VM
Log in into MiSeq VM:
```
$ ssh <USERNAME>@128.39.96.73
```
Move to demultiplexed directory:
```
$ cd //data/for_transfer
```
Rsync the compressed (tar) demultiplexed run folder and its md5sum to NIRD:
```
$ rsync -rauPW <tar> <tar.md5> \
  <NIRD_USERNAME>@login.nird.sigma2.no:/projects/NS9305K/SEQ-TECH/data_delivery/
```
Log out of MiSeq server  

------
### Check the transfer is successful in NIRD
Log in into NIRD:
```
$ ssh <USERNAME>@login.nird.sigma2.no
```
Move to the destination folder:
```
$ cd /projects/NS9305K/SEQ-TECH/data_delivery/
```
Check the md5sum for the transferred tar file:
```
$ md5sum -c <tar.md5>
```
If the output says 'OK', 
Change the persmission on the files:
```
$ chmod 444 <tar> <tar.md5>
```
Log out of NIRD

------
### Delete the transferred files in MiSeq VM
Log in into MiSeq VM:
```
$ ssh <USERNAME>@128.39.96.73
```
Move to demultiplexed directory:
```
$ cd /data/for_transfer
```
Remove the transferred tar and md5 file
```
rm <tar> <tar.md5>
```

-----
### All tasks completed!!!

<!--- Not implemented yet


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
