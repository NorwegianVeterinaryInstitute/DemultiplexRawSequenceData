import termcolor

from demux.loggers import demuxLogger, demuxFailureLogger

########################################################################
# deliver_files_to_NIRD
########################################################################

def deliver_files_to_NIRD( demux ):
    """
    Make connection to NIRD and upload the data
    """
    demux.n = demux.n + 1
    demuxLogger.info( f"==> {demux.n}/{demux.totalTasks} tasks: Preparing files for archiving to NIRD started\n")


    demuxLogger.info( f"==< {demux.n}/{demux.totalTasks} tasks: Preparing files for archiving to NIRD finished\n")
