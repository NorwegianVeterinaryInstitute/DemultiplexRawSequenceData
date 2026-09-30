
# demux/__init__.py

from . import (
    core as core,  # redundant alias = explicit re-export; loads demux.core first, before loggers
)
from . import (
    loggers as demux_logging,  # avoid naming loggers as logging cuz python might import the stdlib logging, depending on path
)

# set up the logging handling

demux_logging.setup_event_and_log_handling( )
