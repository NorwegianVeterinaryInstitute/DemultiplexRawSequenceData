import os
import shutil

from demux.loggers import demuxLogger, demuxFailureLogger


########################################################################
# _cleanup
########################################################################

def _cleanup( demux ) -> None:
    """
    Remove the temporary directory created during the decompress step.

    This runs unconditionally after upload, regardless of whether
    verify has run yet. The decompressed .fastq files were only needed
    for local hashing; the .fastq.gz originals remain untouched.

    :param demux: demux object with irida_tmp_dir set by step07_03.

    On failure: logs a warning but does not raise. A failed cleanup
    is not a reason to abort the pipeline or mark the run as ERROR.
    The tmp directory will be cleaned on the next re-run or by
    operator intervention.
    """

    demuxLogger.info( "IRIDA cleanup: starting" )

    if not demux.irida_tmp_dir:
        demuxLogger.warning( "IRIDA cleanup: irida_tmp_dir is empty; nothing to clean" )
        return

    if not os.path.isdir( demux.irida_tmp_dir ):
        demuxLogger.warning( f"IRIDA cleanup: tmp directory does not exist: {demux.irida_tmp_dir}" )
        return

    try:
        shutil.rmtree( demux.irida_tmp_dir )
        demuxLogger.info( f"IRIDA cleanup: removed {demux.irida_tmp_dir}" )
    except OSError as error:
        demuxLogger.warning( f"IRIDA cleanup: failed to remove {demux.irida_tmp_dir}: {error}" )

    demux.irida_tmp_dir = ""

    demuxLogger.info( "IRIDA cleanup: complete" )
