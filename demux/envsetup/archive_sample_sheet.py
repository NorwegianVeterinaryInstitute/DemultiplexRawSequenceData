import inspect
import logging
import os
import shutil
import stat
import sys
import termcolor

from demux.loggers import demuxLogger, demuxFailureLogger


########################################################################
# archive_sample_sheet( )
########################################################################

def archive_sample_sheet( demux ):
    """

    # Request by Cathrine: Copy the SampleSheet file to /data/samplesheet automatically

    Check for validity of the filepath of the sample sheet
    then
        archive a copy
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Archive {demux.sampleSheetFilePath} to {demux.sampleSheetArchiveFilePath} ==\n", color="green", attrs=["bold"] ) )


    if not os.path.exists( demux.sampleSheetFilePath ):
        text = f"{demux.sampleSheetFilePath} does not exist! Demultiplexing cannot continue. Exiting."
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )


    if not os.path.isfile( demux.sampleSheetFilePath ):
        text = f"{demux.ampleSheetFilePath} is not a file! Exiting."
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )

    try:
        shutil.copy2( demux.sampleSheetFilePath, demux.sampleSheetArchiveFilePath )
        currentPermissions = stat.S_IMODE(os.lstat( demux.sampleSheetArchiveFilePath ).st_mode )
        os.chmod( demux.sampleSheetArchiveFilePath, stat.S_IREAD | stat.S_IWRITE | stat.S_IRGRP | stat.S_IROTH ) # Set samplesheet to "o=rw,g=r,o=r"
    except Exception as err:
        frameinfo = inspect.getframeinfo( inspect.currentframe( ) )
        text = [    f"Archiving {demux.sampleSheetFilePath} to {demux.sampleSheetArchiveFilePath} failed.",
                    str(err),
                    f" at {frameinfo.filename}:{frameinfo.lineno}."
                    "Exiting.",
        ]
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks:  Archive {demux.sampleSheetFilePath} to {demux.sampleSheetArchiveFilePath} ==\n", color="red", attrs=["bold"] ) )