########################################################################
# fastQC
########################################################################

def fastqc( demux ):
    """
    fastQC: Run /data/bin/fastqc (which is a symlink to the real qc)
    """

    demux.n            = demux.n + 1

    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: fastQC started ==", color="yellow" ) )

    command             = demux.fastqc_bin
    argv                = [ command, '-t', str(demux.threadsToUse), *demux.newProjectFileList ]  # the * operator on a list/array "splats" (flattens) the values in the array, breaking them down to individual arguemtns

    arguments = " ".join( argv[1:] )
    text = "Command to execute:"
    demuxLogger.debug( f"{text:{demux.spacing2}}" + f"{command} {arguments}")     # exclude the first element of the array # example for filename: /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/220314_M06578.SAV-amplicon-MJH/

    try:
        # EXAMPLE: /usr/local/bin/fastqc -t 4 {demux.demultiplexRunIdDir}/{project}/*fastq.gz > demultiplexRunIdDir/demultiplex_log/04_fastqc.log
        result = subprocess.run( argv, capture_output = True, cwd = demux.demultiplexRunIdDir, check = True, encoding = demux.decodeScheme )
    except ChildProcessError as err: 
            text = [ "Caught exception!",
                     f"Command: {err.cmd}", # interpolated strings
                     f"Return code: {err.returncode}"
                     f"Process output: {err.output}",
                     f"Exiting."
                ]
            text = '\n'.join( text )
            demuxFailureLogger.critical( f"{ text }" )
            demuxLogger.critical( f"{ text }" )
            logging.shutdown( )
            sys.exit( )

    # log FastQC output
    fastQCLogFileHandle = ""
    try: 
        fastQCLogFileHandle = open( demux.fastQCLogFilePath, "x" ) # fail if file exists
        if demux.verbosity == 2:
            text = f"fastQCLogFilePath:"
            demuxLogger.debug( f"{text:{demux.spacing2}}" + demux.fastQCLogFilePath )
        fastQCLogFileHandle.write( result.stdout ) 
        fastQCLogFileHandle.close( )
    except FileNotFoundError as err:
        text = [    f"Error opening fastQCLogFilePath: {demux.fastQCLogFilePath} does not exist",
                    f"err.filename:  {err.filename}",
                    f"Exiting!"
                ]
        text = '\n'.join( text )
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: FastQC complete ==\n", color="cyan" )  )
