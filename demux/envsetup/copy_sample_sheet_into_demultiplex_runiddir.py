import logging
import shutil
import sys

import termcolor

from demux.loggers import demuxFailureLogger, demuxLogger

########################################################################
# copy_sample_sheet_into_demultiplex_runiddir( demux )
########################################################################

def copy_sample_sheet_into_demultiplex_runiddir( demux ):
    """
    Copy SampleSheet.csv from {demux.sampleSheetFilePath} to {demux.demultiplexRunIDdir}
        because bcl2fastq requires the file existing before it starts demultiplexing
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Copy {demux.sampleSheetFilePath} to {demux.demultiplexRunIDdir} ==\n", color="green", attrs=["bold"] ) )

    try:
        shutil.copy2( demux.sampleSheetFilePath, demux.demultiplexRunIDdir )
    except OSError as err:
        text = [    f"Copying {demux.sampleSheetFilePath} to {demux.demultiplexRunIDdir} failed.",
                    str( err ),
                    "Exiting."
        ]
        text = '\n'.join( text )
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( 1 )

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Copy {demux.sampleSheetFilePath} to {demux.demultiplexRunIDdir} ==\n", color="red", attrs=["bold"] ) )
