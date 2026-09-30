import fcntl
import logging
import os
import sys
from typing import TextIO

_lock_fd: TextIO | None = None   # module-level: the flock lives as long as this file object stays open, i.e. until the process exits

def setup_lock( ) -> None:
    """
    Acquire an exclusive non-blocking lock on $XDG_RUNTIME_DIR/demux/demux.lock.
    Exits cleanly if the lock cannot be acquired, indicating another instance is running.
    Requires Python 3.11 or newer; exits with an error message if the requirement is not met.
    """

    if sys.hexversion < 51056112: # Require Python 3.11 or newer
        sys.exit( "Python 3.11 or newer is required to run this program." )

    global _lock_fd
    _lock_fd = open( os.path.join( os.environ[ 'XDG_RUNTIME_DIR' ], 'demux', 'demux.lock' ), 'w' )   # noqa: SIM115 - no with: the flock lives as long as this file stays open, i.e. until the process exits
    try:
        fcntl.flock( _lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB )
    except BlockingIOError:
        logging.getLogger( __name__ ).warning( "Demux already running, exiting." )
        sys.exit( 0 )  # another instance is running, exit cleanly
