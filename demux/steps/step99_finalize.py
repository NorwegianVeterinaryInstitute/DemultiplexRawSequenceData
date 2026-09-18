import os
import pathlib
import stat
import sys
import termcolor

from demux.loggers import demuxLogger, demuxFailureLogger


########################################################################
# finalize( )
########################################################################

def finalize( demux, marker: str ):
    """
    Touch {demux.demultiplexRunIDdir}/{marker} to record that a phase of this run finished.

    markers:
        demux.demultiplexCompleteFile     demultiplexing, QC and tar files done
        demux.vigaspDeliveryCompleteFile  VIGASP delivery done
        demux.nirdDeliveryCompleteFile    NIRD delivery done

    detect_new_runs( ) treats a run directory without demux.demultiplexCompleteFile as an
    incomplete run and reports missing delivery markers. These become database fields later.
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Marking phase complete: {marker} ==", color="green", attrs=["bold"] ) )

    file = os.path.join( demux.demultiplexRunIDdir, marker )
    try:
        pathlib.Path( file ).touch( mode = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH, exist_ok = False )
    except FileExistsError:
        text = f"{file} already exists. Please delete it before running {demux.RunID}."
        demuxFailureLogger.critical( text )
        demuxLogger.critical( text )
        sys.exit( 1 )

    demuxLogger.debug( f"{file} created." )
    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Marking phase complete: {marker} ==", color="red", attrs=["bold"] ) )
