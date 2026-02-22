#######################################################################
# checkRunningDirectoryStructure( )
########################################################################

def check_running_directory_structure( ):
    """
    Check if the runtime directory structure is ready for processing

    To be done: https://github.com/NorwegianVeterinaryInstitute/DemultiplexRawSequenceData/issues/121
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Check if the runtime directory structure is ready for processing ==\n", color="green", attrs=["bold"] ) )

    # init:

    #   check if sequencing run has completed, exit if not
    #       Completion of sequencing run is signaled by the existance of the file {demux.rtaCompleteFilePath} ( {demux.sequenceRunOriginDir}/{demux.rtaCompleteFile} )
    if not os.path.isfile( f"{demux.rtaCompleteFilePath}" ):
        text = f"{demux.RunID} is not finished sequencing yet!"
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )

    #   check if {demux.demultiplexDirRoot} exists
    #       exit if not
    if not os.path.exists( demux.demultiplexDirRoot ):
        text = f"{demux.demultiplexDirRoot} is not present, please use the provided ansible file to create the root directory hierarchy"
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )

    if not os.path.isdir( demux.demultiplexDirRoot ):
        text = f"{demux.demultiplexDirRoot} is not a directory! Cannot stored demultiplex data in a non-directory structure! Exiting." 
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )
    if os.path.exists( demux.demultiplexDirRoot ):
        text = f"{demux.demultiplexRunIDdir} exists. Delete the demultiplex folder before re-running the script"
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Check if the runtime directory structure is ready for processing ==\n", color="red" ) )