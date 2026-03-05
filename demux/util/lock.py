import fcntl
import logging
import os
import sys

def setup_lock( ) -> None:
    """
    Acquire an exclusive non-blocking lock on $XDG_RUNTIME_DIR/demux/demux.lock.
    Exits cleanly if the lock cannot be acquired, indicating another instance is running.
    Requires Python 3.11 or newer; exits with an error message if the requirement is not met.
    """

    if sys.hexversion < 51056112: # Require Python 3.11 or newer
        sys.exit( "Python 3.11 or newer is required to run this program." )

    lock_fd = open( os.path.join( os.environ[ 'XDG_RUNTIME_DIR' ], 'demux', 'demux.lock' ), 'w' )
    try:
        fcntl.flock( lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB )
    except BlockingIOError:
        logging.warning( "Demux already running, exiting." )
        sys.exit( 0 )  # another instance is running, exit cleanly