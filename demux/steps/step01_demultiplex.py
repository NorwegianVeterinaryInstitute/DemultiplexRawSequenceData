#!/usr/bin/python3.11

import logging
import os
import resource
import subprocess
import sys
import termcolor

from demux.loggers import demuxLogger, demuxFailureLogger

########################################################################
# bcl2fastq
########################################################################

def bcl2fastq( demux ):
    """
    Use Illumina's blc2fastq linux command-line tool to demultiplex each lane into an appropriate fastq file

    bcl2fastq is available here https://emea.support.illumina.com/sequencing/sequencing_software/bcl2fastq-conversion-software/downloads.html
        and you will have to have an account with Illumina to download it.
        Account is setup automatically, but needs manual approval from representative in Illumina, which means you need a contract with Illumina
        in order to access the software.

    CAREFUL: when trying to execute this array, please break all arguments that include a space into their own array element. Otherwise it will execute as '--runfolder-dir {SequenceRunOriginDir}'
         the space will be considered part of the argument: While you will scratch your head that you are passing argument and option, subprocess.run() will report that as a single
         argument with no options

        blc2fastq accepts just *fine* absolute paths when run from the command-line
        example: /data/bin/bcl2fastq --no-lane-splitting --runfolder-dir /data/rawdata/220314_M06578_0091_000000000-DFM6K --output-dir /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex

    CAREFUL: if you run blc2fastq with only --runfolder-dir {demux.RawDataRunIDdir} , bcl2fastq will create all the files within the {demux.RawDataRunIDdir} rawdata directory

    """

    demux.n            = demux.n + 1

    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Demultiplexing started ==\n", color="green", attrs=["bold"] ) )

    # increase the file descriptor limit to 65535:
    #       241202_M06578_0219_000000000-LT29R has over 350 sampless, when executing it, bcl2fastq threw this error:
    #       bcl2fastq::common::Exception: 2024-Dec-05 22:59:50: Too many open files (24): /TeamCityBuildAgent/work/556afd631a5b66d8/src/cxx/include/io/FileBufWithReopen.hpp(48): Throw in function bcl2fastq::io::BasicFileBufWithReopen<CharT, Traits>::BasicFileBufWithReopen(std::ios_base::openmode) [with CharT = char; Traits = std::char_traits<char>; std::ios_base::openmode = std::_Ios_Openmode]
    #       Dynamic exception type: boost::exception_detail::clone_impl<bcl2fastq::common::IoError>
    #       std::exception::what: Failed to allocate a file handle
    # raising the file descriptor , seems to fix the issue
    # command line equiv: ulimit -n 65535
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    resource.setrlimit(resource.RLIMIT_NOFILE, (65535, hard))

    # get the available CPUs, and use that for --loading-threads, --processing-threads, --writing-threads
    availableCpus = os.cpu_count()
    cpuMultiplier = 2
    availableCpus = availableCpus * cpuMultiplier

    argv = [ demux.bcl2fastq_bin,
         "--loading-threads",
         f"{availableCpus}",
         "--processing-threads",
         f"{availableCpus}",
         "--writing-threads",
         f"{availableCpus}",
         "--no-lane-splitting",
         "--runfolder-dir",
        f"{demux.rawDataRunIDdir}",
         "--output-dir",
        f"{demux.demultiplexRunIDdir}"
    ]

    text = f"Command to execute:"
    demuxLogger.debug( f"{text:{demux.spacing2}}" + "ulimit -n 65535; " + " ".join( argv ) )

    try:
        # EXAMPLE: /usr/local/bin/bcl2fastq --no-lane-splitting --runfolder-dir ' + demux.rawDataRunIDdir + ' --output-dir ' + demux.demultiplexDir + ' 2> ' + demux.demultiplexDir + '/demultiplex_log/02_demultiplex.log'
        result =  subprocess.run( argv, capture_output = True, cwd = demux.rawDataRunIDdir, check = True, encoding = demux.decodeScheme )
    except ChildProcessError as err: 
        text = [    f"Caught exception!",
                    f"Command: {err.cmd}", # interpolated strings
                    f"Return code: {err.returncode}"
                    f"Process output: {err.stdout}",
                    f"Process error:  {err.stderr}",
                    f"Exiting."
                 ]
        text = '\n'.join( text )
        demuxFailureLogger.critical( text )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )

    if not result.stderr:
        demuxLogger.critical( f"result.stderr has zero lenth. exiting at {inspect.currentframe().f_code.co_name}()" )
        demuxFailureLogger.critical( f"result.stderr has zero lenth. exiting at {inspect.currentframe().f_code.co_name}()" )
        logging.shutdown( )
        sys.exit( )

    try: 
        file = open( demux.bcl2FastqLogFile, "w" )
        file.write( result.stderr )
        file.close( )
    except OSError as err:
        text = [    f"Caught exception!",
                    f"Command: {err.cmd}", # interpolated strings
                    f"Return code: {err.returncode}"
                    f"Process output: {err.stdout}",
                    f"Process error:  {err.stderr}",
                    f"Exiting."
                 ]
        text = '\n'.join( text )
        demuxFailureLogger.critical( text )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )


    if not os.path.isfile( demux.bcl2FastqLogFile ):
        demuxFailureLogger.critical( f"{demux.bcl2FastqLogFile} did not get written to disk. Exiting." )
        demuxLogger.critical( f"{demux.bcl2FastqLogFile} did not get written to disk. Exiting." )
        logging.shutdown( )
        sys.exit( )
    else:
        filesize = os.path.getsize( demux.bcl2FastqLogFile )
        text = "bcl2FastqLogFile:"
        demuxLogger.debug( f"{text:{demux.spacing2}}" + f"{demux.bcl2FastqLogFile} is {filesize} bytes.\n")

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Demultiplexing finished ==\n", color="red", attrs=["bold"] ) )
