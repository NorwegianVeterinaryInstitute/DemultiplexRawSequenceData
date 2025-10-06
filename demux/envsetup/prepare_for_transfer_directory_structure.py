#!/usr/bin/python3.11

import logging
import os
import stat
import sys
import termcolor

########################################################################
# prepareForTransferDirectoryStructure
########################################################################

def prepareForTransferDirectoryStructure( demux ):
    """
    create /data/for_transfer/RunID and any required subdirectories
    """

    demux.n            = demux.n + 1
    demuxLogger        = logging.getLogger("demuxLogger")        # logging to output
    demuxFailureLogger = logging.getLogger("demuxFailureLogger") # logging to email

    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Create delivery directory structure under {demux.forTransferRunIdDir} started ==", color="green", attrs=["bold"] ) )

    # ensure that demux.forTransferDir (/data/for_transfer) exists
    if not os.path.isdir( demux.forTransferDir ):
        text = f"{demux.forTransferDir} does not exist! Please re-run the ansible playbook! Exiting!"
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )

    try:
        os.mkdir( demux.forTransferRunIdDir )       # try to create the demux.forTransferRunIdDir directory ( /data/for_transfer/220603_M06578_0105_000000000-KB7MY )
        os.chmod( demux.forTransferRunIdDir, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH ) # rwxrwxr-x / 775 / read-write-execute owner, read-write-execute group, read-execute others
    except Exception as err:
        text = f"{demux.forTransferRunIdDir} cannot be created: { str( err ) }\nExiting!"
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks:  Create delivery directory structure under {demux.forTransferRunIdDir} ==\n", color="red", attrs=["bold"] ) )

