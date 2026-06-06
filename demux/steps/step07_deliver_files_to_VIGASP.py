########################################################################
#
# step07_deliver_files_to_VIGASP.py
#
# Upload demultiplexed FASTQ pairs to IRIDA/VIGASP.
#
# State machine (see irida_uploader_state_machine_v6.png):
#
#     PREFLIGHT -> CHECK PROJECTS -> HASH ->
#     CREATE RUN -> UPLOAD -> VERIFY -> COMPLETE
#
# Any failure transitions to ERROR: notify operator, do NOT PATCH
# the sequencing run to COMPLETE.
#
# https://github.com/NorwegianVeterinaryInstitute/DemultiplexRawSequenceData/issues/27
#
# Copyright: The Norwegian Veterinary Institute
# Licenced under the GNU Public License 3.0 or newer
#
########################################################################
import termcolor
from demux.loggers import demuxLogger, demuxFailureLogger
from demux.steps.step07_01_preflight       import _preflight
from demux.steps.step07_02_check_projects  import _check_projects
from demux.steps.step07_04_hash            import _hash
from demux.steps.step07_05_create_run      import _create_run
from demux.steps.step07_06_upload          import _upload
from demux.steps.step07_08_verify          import _verify
from demux.steps.step07_09_complete        import _complete


########################################################################
# deliver_files_to_VIGASP
########################################################################

def deliver_files_to_VIGASP( demux ):
    """
    Upload demultiplexed FASTQ pairs to IRIDA/VIGASP.

    Runs the IRIDA upload state machine. Each sub-step is a separate
    module under demux/steps/step07_*.py.

    :param demux: demux object (pipeline singleton or test context).
    :raises Exception: any sub-step failure propagates to the caller.
    """
    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Uploading files to VIGASP/IRIDA started\n", color = "green", attrs = [ "bold" ] ) )

    try:
        _preflight(      demux )
        _check_projects( demux )
        _hash(           demux )
        _create_run(     demux )
        _upload(         demux )
        _verify(         demux )
        _complete(       demux )

    except Exception as error:
        # ERROR state: notify operator, do not PATCH
        demuxLogger.critical( f"IRIDA upload ERROR: {type( error ).__name__}: {error}" )
        demuxFailureLogger.critical( f"IRIDA upload ERROR for run {demux.RunID}: {type( error ).__name__}: {error}" )
        raise

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Uploading files to VIGASP/IRIDA finished\n", color = "red", attrs = [ "bold" ] ) )