from demux.loggers import demuxLogger, demuxFailureLogger


########################################################################
# script_completion
########################################################################

def finalize( demux ):
    """
    Create the {DemultiplexDir}/{demux.DemultiplexCompleteFile} file to signal that this script has finished
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Finishing up script ==", color="green", attrs=["bold"] ) )

    try:
        file = os.path.join( demux.demultiplexRunIDdir, demux.demultiplexCompleteFile )
        pathlib.Path( file ).touch( mode=644, exist_ok=False)
    except Exception as e:  
        demuxLogger.critical( f"{file} already exists. Please delete it before running {__file__}.\n")
        sys.exit( )

    demuxLogger.debug( f"demux.demultiplexCompleteFile {file} created.")
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Finishing up script ==", color="red", attrs=["bold"] ) )