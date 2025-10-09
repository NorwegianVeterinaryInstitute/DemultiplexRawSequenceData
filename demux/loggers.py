#!/usr/bin/python3.11

import logging
import logging.handlers
import os
import socket
import sys
import syslog
import termcolor

from . import loggers as demux_logging # avoid naming loggers as logging cuz python might import the stdlib logging, depending on path

demuxLogger = None
demuxFailureLogger = None

########################################################################
# set_loggers( )
########################################################################

def set_loggers(main_logger, failure_logger):
    global demuxLogger, demuxFailureLogger
    demuxLogger = main_logger
    demuxFailureLogger = failure_logger


########################################################################
# setup_event_and_log_handling( )
########################################################################
def setup_event_and_log_handling( logging_level = logging.DEBUG ):
    """
    Setup the event and log handling we will be using everywhere
    Be carefu: 
        setup_event_and_log_handling() should not bump demux.n or emit "task started/finished" banners.
        This function should do one thing: wire handlers. Otherwise, you are itching for a chicken-and-egg log problem
    """
    # Initalize the logging for the script
    demux_logging.set_loggers( logging.getLogger( "demux" ), logging.getLogger( "demux.smtp.failure" ) )

    demuxLogFormatter      = logging.Formatter( "%(asctime)s %(dns)s %(filename)s %(levelname)s %(message)s", datefmt = '%Y-%m-%d %H:%M:%S', defaults = { "dns": socket.gethostname( ) } )
    demuxSyslogFormatter   = logging.Formatter( "%(levelname)s %(message)s" )

    # setup loging for console
    demuxConsoleLogHandler    = logging.StreamHandler( stream = sys.stderr )
    demuxConsoleLogHandler.setFormatter( demuxLogFormatter )

    # # setup logging for syslog
    demuxSyslogLoggerHandler       = logging.handlers.SysLogHandler( address = '/dev/log', facility = syslog.LOG_USER ) # setup the syslog logger
    demuxSyslogLoggerHandler.ident = f"{os.path.basename(__file__)} "
    demuxSyslogLoggerHandler.setFormatter( demuxSyslogFormatter )

    # # setup email notifications
    # demuxSMTPfailureLogHandler = BufferingSMTPHandler( demux.mailhost, demux.fromAddress, demux.toAddress, demux.subjectFailure )
    # demuxSMTPsuccessLogHandler = BufferingSMTPHandler( demux.mailhost, demux.fromAddress, demux.toAddress, demux.subjectSuccess )

    # Set the level early
    demuxLogger.setLevel( logging_level )

    if not any( isinstance(h, logging.StreamHandler ) for h in demuxLogger.handlers):
        demuxLogger.addHandler(demuxConsoleLogHandler )

    if not any( isinstance( h, logging.handlers.SysLogHandler ) for h in demuxLogger.handlers):
        demuxLogger.addHandler(demuxSyslogLoggerHandler)
    
    # demuxLogger.addHandler( demuxSMTPsuccessLogHandler )

    # this has to be in a separate logger because we are only logging to it when we fail
    # demuxFailureLogger.addHandler( demuxSMTPfailureLogHandler )

    # setup logging for messaging over Workplace/Teams
    # demuxHttpsLogHandler       = logging.handlers.HTTPHandler( demux.httpsHandlerHost, demux.httpsHandlerUrl, method = 'GET', secure = True, credentials = None, context = None ) # FIXME later


########################################################################
# setup_file_log_handling( )
########################################################################

def setup_file_log_handling( demux ):
    """
    Setup the file event and log handling
    """

    demux.n = demux.n + 1

    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Setup the file event and log handling ==\n", color="green", attrs=["bold"] ) )

    # make sure that the /data/log directory exists.
    if not os.path.isdir( demux.logDirPath ) :
        text = [    "Trying to setup demux.logDirPath failed. Reason:\n",
                    "The parts of demux.logDirPath have the following values:\n",
                    f"demux.dataRootDirPath:\t\t\t{demux.dataRootDirPath}\n",
                    f"demux.logDirName:\t\t\t{demux.logDirName}\n",
                    f"demux.logDirPath:\t\t\t\t{demux.logDirPath}\n"
        ]
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )

    # # set up logging for /data/log/{demux.RunID}.log
    try: 
        demuxFileLogHandler   = logging.FileHandler( demux.demuxRunLogFilePath, mode = 'w', encoding = demux.decodeScheme )
    except Exception as err:
        text = [    "Trying to setup demuxFileLogHandler failed. Reason:\n",
                    str(err),
                    "The parts of demux.demuxRunLogFilePath have the following values:\n",
                    f"demux.demuxRunLogFilePath:\t\t\t{demux.demuxRunLogFilePath}\n",
                    f"demux.RunID + demux.logSuffix:\t\t{demux.RunID} + {demux.logSuffix}\n",
                    f"demux.logDirPath:\t\t\t\t{demux.logDirPath}\n"
        ]
        demuxFailureLogger.critical( *text  )
        demuxLogger.critical( *text )
        logging.shutdown( )
        sys.exit( )

    demuxLogFormatter      = logging.Formatter( "%(asctime)s %(dns)s %(filename)s %(levelname)s %(message)s", datefmt = '%Y-%m-%d %H:%M:%S', defaults = { "dns": socket.gethostname( ) } )
    demuxFileLogHandler.setFormatter( demuxLogFormatter )
    demuxLogger.setLevel( demux.loggingLevel )

    # set up cummulative logging in /data/log/demultiplex.log
    try:
        demuxFileCumulativeLogHandler   = logging.FileHandler( demux.demuxCumulativeLogFilePath, mode = 'a', encoding = demux.decodeScheme )
    except Exception as err:
        text = [    "Trying to setup demuxFileCumulativeLogHandler failed. Reason:\n",
                    str(err),
                    "The parts of demux.demuxRunLogFilePath have the following values:\n",
                    f"demux.demuxCumulativeLogFilePath:\t\t\t{demux.demuxCumulativeLogFilePath}\n",
                    f"demux.logDirPath:\t\t\t\t\t{demux.logDirPath}\n",
                    f"demux.demultiplexLogDirName:\t\t\t{demux.demultiplexLogDirName}\n",
        ]
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )

    demuxFileCumulativeLogHandler.setFormatter( demuxLogFormatter )

    # setup logging for /data/bin/demultiplex/demux.RunID/demultiplex_log/00_script.log
    try:
        demuxScriptLogHandler   = logging.FileHandler( demux.demultiplexScriptLogFilePath, mode = 'w', encoding = demux.decodeScheme )
    except Exception as err:
        text = [    "Trying to setup demuxScriptLogHandler failed. Reason:\n",
                    str(err),
                    "The parts of demux.DemultiplexScriptLogFilePath have the following values:\n",
                    f"demux.demultiplexScriptLogFilePath:\t\t\t{demux.demultiplexScriptLogFilePath}\n",
                    f"demux.demultiplexLogDirPath\t\t\t\t{demux.demultiplexLogDirPath}\n",
                    f"demux.scriptRunLogFileName:\t\t\t\t{demux.scriptRunLogFileName}\n",
                    f"demux.demultiplexRunIdDir:\t\t\t\t{demux.demultiplexRunIdDir}\n",
                    f"demux.demultiplexLogDirName:\t\t\t\t{demux.demultiplexLogDirName}\n",
                    f"demux.demultiplexDir:\t\t\t\t\t{demux.demultiplexDir}\n",
                    f"RunID + demux.demultiplexDirSuffix:\t{demux.RunID} + {demux.demultiplexDirSuffix}\n",
                    "Exiting.",
        ]
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )

    demuxScriptLogHandler.setFormatter( demuxLogFormatter )

    demuxLogger.addHandler( demuxScriptLogHandler )
    demuxLogger.addHandler( demuxFileLogHandler )
    demuxLogger.addHandler( demuxFileCumulativeLogHandler )

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Setup the file event and log handling ==\n", color="red", attrs=["bold"] ) )
