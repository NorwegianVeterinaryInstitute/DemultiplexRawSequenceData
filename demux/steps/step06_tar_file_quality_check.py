import os
import sys
import tarfile
import shutil
import logging
import termcolor

from demux.loggers import demuxLogger, demuxFailureLogger

########################################################################
# tar_file_quality_check: verify tar files before upload
########################################################################

def tar_file_quality_check( demux ):
    """
    Perform a final quality check on the tar files before uploading them.
    If there are errors in the untarring or the sha512 check, halt.
    If there are no errors, go ahead with the uploading


    steps for completing this function:
        Step 1: create a /data/for_transfer/RunID/test directory
        Step 2: copy any tar file for relevant runIDShort into the test directory
        Step 3: untar files under /data/for_transfer/RunID/test
        Step 4: recalculate sha512 hash for each file
        compare result with hash file on disk
            stuff result in sql database?
        delete {demux.forTransferRunIdDir}/{demux.forTransferRunIdDirTestName} and contents
        return True/false depending on answer

    INPUT
        Input is RunID rather than demux.RunID or some other variable because we can use this method later to check the tarFile quality of any fetched tar file from archive
    """
    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Tar files quaility check started ==", color="green", attrs=["bold"] ) )

    forTransferRunIdDirTestName = os.path.join( demux.forTransferRunIdDir,demux.forTransferRunIdDirTestName )

#---- Step 1: create a /data/for_transfer/RunID/test directory -------------------------------------------------------------------------------------------

    # ensure that demux.forTransferDir (/data/for_transfer) exists
    if not os. path. isdir( demux.forTransferDir ):
        text = f"{demux.forTransferDir} does not exist! Please re-run the ansible playbook! Exiting!"
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )    

    try: 
        os.mkdir( forTransferRunIdDirTestName )
    except Exception as err:
        text = f"{demux.forTransferRunIdDir} cannot be created: { str( err ) }\nExiting!"
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )

# there is no point in making this complicated: tar files can be easily edited, they are just a simple container and any attacker can easily alter the file insitu,
# recalculate the hash and replace the hash again in situ
#
# So the only thing we can do is basically untar the file to ensure that it was packed correctly in this program,
# then delete the test_tar directory

# for file in $TARFILES; do printf '\n==== tar file: $file============================='; tar --verbose --compare --file=$file | grep -v 'Mod time differs'; done
#---- Step 2: untar all demux.tarFilesToTransferList in {demux.forTransferRunIdDir}/{demux.forTransferRunIdDirTestName} ------------------------------------------------------------
    for tarFile in demux.tarFilesToTransferList:
        try:
            text = "Now extracting tarfile:"
            demuxLogger.debug( f"{text:{demux.spacing3}}" + tarFile )
            tarFileHandle = tarfile.open( name = tarFile, mode = "r:" )     # Open a tar file under  demux.forTransferRunIdDir as project + demux.tarSuffix . example: /data/for_transfer/220603_M06578_0105_000000000-KB7MY/220603_M06578.42015-NORM-VET.tar
            tarFileHandle.extractall( path = forTransferRunIdDirTestName  )
            tarFileHandle.close( )
        except Exception as err:
            text = f"{forTransferRunIdDirTestName}/{tarFile} cannot be created: { str( err ) }\nExiting!"
            demuxFailureLogger.critical( f"{ text }" )
            demuxLogger.critical( f"{ text }" )
            logging.shutdown( )
            sys.exit( )

#---- Step 3: delete {demux.forTransferRunIdDir}/{demux.forTransferRunIdDirTestName} and contents ------------------------------------------------------------
    # clean up
    text = "Cleanup up path:"
    demuxLogger.info( f"{text:{demux.spacing2}}" + forTransferRunIdDirTestName )
    shutil.rmtree( forTransferRunIdDirTestName )


    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Tar files quaility check finished ==", color="red", attrs=["bold"] ) )