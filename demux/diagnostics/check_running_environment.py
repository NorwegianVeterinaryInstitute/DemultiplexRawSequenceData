import logging
import shutil
import sys
import termcolor

from demux.loggers import demuxLogger, demuxFailureLogger

########################################################################
# checkRunningEnvironment( )
########################################################################

def check_running_environment( demux ):
    """
    See if the following things exist:
        - bcl2fastq ( to be moved from other section )
        - Java
        - FastQC    ( to be moved from other section )
        - MultiQC   ( to be moved from other section)
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Check the validity of the current running environment ==\n", color="green", attrs=["bold"] ) )

    # ensure Java[tm] exists
    if not shutil.which( "java"):
        text = "Java executable not detected! Exiting." 
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )

    if not any( demux.projectList ):
        text = "List projectList contains no projects/zero length! Exiting." 
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )
    elif demux.debug and len( demux.projectList ) == 1: 
        demux.projectList.append( demux.testProject )               # if debug, have at least two project names to ensure multiple paths are being created

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Check the validity of the current running environment ==\n", color="red", attrs=["bold"] ) )