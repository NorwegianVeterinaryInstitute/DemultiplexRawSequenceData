"""
logging.py: logging setup for the demultiplex script.

Initialises the logging stack for demultiplex.py, including syslog and console handlers.
Provides the setup_logging() function which must be called before any other component
that emits log messages.
"""

import logging
import logging.handlers
import sys

def setup_logging( ) -> None:
    """
    Set up basic logging for demultiplex.py.
    Initialises syslog and console handlers.
    Full logging initialisation including file and SMTP handlers is handled in main( ).
    """
    logging.basicConfig(
        level    = logging.WARNING,
        handlers = [
            logging.handlers.SysLogHandler(address = '/dev/log'),
            logging.StreamHandler()
        ]
    )
