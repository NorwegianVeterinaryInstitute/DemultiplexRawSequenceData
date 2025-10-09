#!/usr/bin/python3.11

# demux/__init__.py

import demux.core
import logging as py_logging
from . import loggers as demux_logging # avoid naming loggers as logging cuz python might import the stdlib logging, depending on path

# demuxLogger = logging.getLogger("demux")
# demuxFailureLogger = logging.getLogger("demux.failure")
# these need replacing with above once we are stable
# demuxLogger = py_logging.getLogger( "__main__" )
# demuxFailureLogger = py_logging.getLogger( "SMTPFailureLogger" )

demux_logging.set_loggers( py_logging.getLogger( "__main__" ), py_logging.getLogger( "SMTPFailureLogger" ) )
demux_logging.setup_event_and_log_handling( )