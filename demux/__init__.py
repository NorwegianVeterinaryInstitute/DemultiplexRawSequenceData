#!/usr/bin/python3.11

# demux/__init__.py

import demux.core
import demux.config

from . import loggers as demux_logging # avoid naming loggers as logging cuz python might import the stdlib logging, depending on path

# set up the logging handling

demux_logging.setup_event_and_log_handling( )