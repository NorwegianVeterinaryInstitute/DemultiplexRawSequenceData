import logging
import os
import shutil
import stat
import sys
import termcolor

from demux.loggers import demuxLogger, demuxFailureLogger

########################################################################
# copy_sample_sheet_into_demultiplex_runiddir( demux )
########################################################################

def copy_sample_sheet_into_demultiplex_runiddir( demux ):
    """
    Copy SampleSheet.csv from {demux.SampleSheetFilePath} to {demux.DemultiplexRunIdDir}
        because bcl2fastq requires the file existing before it starts demultiplexing
    """
    #

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Copy {demux.sampleSheetFilePath} to {demux.demultiplexRunIDdir} ==\n", color="green", attrs=["bold"] ) )

    try:
        currentPermissions = stat.S_IMODE(os.lstat( demux.sampleSheetFilePath ).st_mode )
        # os.chmod( demux.sampleSheetFilePath, currentPermissions & ~stat.S_IEXEC  ) # demux.SampleSheetFilePath is probably +x, remnant from windows transfer, so remove execute bit
        shutil.copy2( demux.sampleSheetFilePath, demux.demultiplexRunIDdir )
    except Exception as err:
        text = [    f"Copying {demux.sampleSheetFilePath} to {demux.demultiplexRunIDdir} failed.",
                    err.tostring( ),
                    "Exiting."
        ]
        '\n'.join( text )
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Copy {demux.sampleSheetFilePath} to {demux.demultiplexRunIDdir} ==\n", color="red", attrs=["bold"] ) )
