import termcolor

from demux.loggers import demuxLogger, demuxFailureLogger

########################################################################
# deliver_files_to_VIGASP
########################################################################

def deliver_files_to_VIGASP( demux ):
    """
    Write the uploader file needed to upload the data to VIGASP and then
        upload the relevant files.
    """
    demux.n = demux.n + 1
    demuxLogger.info( f"==> {demux.n}/{demux.totalTasks} tasks: Preparing files for uploading to VIGASP started\n")


    demuxLogger.info( f"==< {demux.n}/{demux.totalTasks} tasks: Preparing files for uploading to VIGASP finished\n")