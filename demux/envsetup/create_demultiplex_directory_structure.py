#!/usr/bin/python3.11

import logging
import os
import stat
import sys
import termcolor

from demux.loggers import demuxLogger, demuxFailureLogger


########################################################################
# createDirectory
########################################################################

def create_demultiplex_directory_structure( demux ):
    """
    If the Demultiplexing directory or any relevant directory does not exist, create it
        demux.RunIDShort format is in the pattern of (date +%y%m%d)_SEQUENCERSERIALNUMBER Example: 220314_M06578
        {demultiplexDirRoot} == "/data/demultiplex" # default

        {demultiplexDirRoot}/{demux.RunID}_{demultiplexDirSuffix}/
        {demultiplexDirRoot}/{demux.RunID}_{demultiplexDirSuffix}/projectList[0]
        {demultiplexDirRoot}/{demux.RunID}_{demultiplexDirSuffix}/projectList[1]
        .
        .
        .
        {demultiplexDirRoot}{demux.RunID}_{demultiplexDirSuffix}/projectList[ len( projectList ) -1 ]
        {demultiplexDirRoot}{demux.RunID}_{demultiplexDirSuffix}/{demultiplexLogDir}
        {demultiplexDirRoot}{demux.RunID}_{demultiplexDirSuffix}/{demux.RunIDShort}{demux.qcSuffix}
        {demultiplexDirRoot}{demux.RunID}_{demultiplexDirSuffix}/Reports      # created by bcl2fastq
        {demultiplexDirRoot}{demux.RunID}_{demultiplexDirSuffix}/Stats        # created by bcl2fastq
    """

    demux.n = demux.n + 1

    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Create directory structure started ==", color="green", attrs=["bold"] ) )

    text = "demultiplexRunIdDir:"
    demuxLogger.debug( f"{text:{demux.spacing2}}" + demux.demultiplexRunIdDir )
    text = "demultiplexRunIdDir/demultiplexLogDir:"
    demuxLogger.debug( f"{text:{demux.spacing2}}" + demux.demultiplexLogDirPath )
    text = "demultiplexRunIdDir/demuxQCDirectory:"
    demuxLogger.debug( f"{text:{demux.spacing2}}" + demux.demuxQCDirectoryFullPath )

    # using absolute path names here
    try:

        # The following 3 lines have to be in this order
        os.mkdir( demux.demultiplexRunIdDir )       # root directory for run
        os.mkdir( demux.demultiplexLogDirPath )     # log directory  for run
        os.mkdir( demux.demuxQCDirectoryFullPath )  # QC directory   for run

        os.chmod( demux.demultiplexRunIdDir,            stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH ) # rwxrwxr-x / 775 / read-write-execute owner, read-write-execute group, read-execute others
        os.chmod( demux.demultiplexLogDirPath,          stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH ) # rwxrwxr-x / 775 / read-write-execute owner, read-write-execute group, read-execute others
        os.chmod( demux.demuxQCDirectoryFullPath,       stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH ) # rwxrwxr-x / 775 / read-write-execute owner, read-write-execute group, read-execute others

    except FileExistsError as err:
        demuxFailureLogger.critical( f"File already exists! Exiting!\n{err}" )
        demuxLogger.critical( f"File already exists! Exiting!\n{err}" )
        logging.shutdown( )
        sys.exit( )
    except FileNotFoundError as err:
        demuxFailureLogger.critical( f"A component of the passed path is missing! Exiting!\n{err}" )
        demuxLogger.critical( f"A component of the passed path is missing! Exiting!\n{err}" )
        logging.shutdown( )
        sys.exit( )


    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Create directory structure finished ==\n", color="red", attrs=["bold"] ) )
