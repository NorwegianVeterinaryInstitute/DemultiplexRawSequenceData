from demux.loggers import demuxLogger, demuxFailureLogger

########################################################################
# Perform a sha512 comparision
########################################################################

def sha512FileQualityCheck(  ):
    """
    re-perform (quietly) the sha512 calculation and compare that with the result on file for the specific file.
    https://github.com/NorwegianVeterinaryInstitute/DemultiplexRawSequenceData/issues/124
    """
    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: sha512 files check started ==", color="green", attrs=["bold"] ) )

    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: sha512 files check finished ==", color="red", attrs=["bold"] ) )