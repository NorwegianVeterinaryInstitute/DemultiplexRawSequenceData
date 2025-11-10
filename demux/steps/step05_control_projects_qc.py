import termcolor

from demux.loggers import demuxLogger, demuxFailureLogger


########################################################################
# Water Control Negative report
########################################################################

def control_projects_qc(  demux ):
    """
    This function creeates a report if any water 1 samples are submitted for sequence ( and subsequently, analysis )

    If there are no water control samples, no report is generated.

    If there are water control samples,
        create the full report ONLY if any amplicons are found
    Otherwise
        just mention in green text that no results are detected (and move on)

    This might need to go into a qc/ or reporting/ module https://github.com/NorwegianVeterinaryInstitute/DemultiplexRawSequenceData/issues/123
    """
    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Control Project QC for non-standard proejcts started ==", color="green", attrs=["bold"] ) )

    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Control Project QC for non-standard proejcts finished ==", color="red", attrs=["bold"] ) )