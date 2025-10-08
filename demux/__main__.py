# Entry point 
# (calls main(  )function in `demultiplex_script.py`
#
#########################################################################
# To run this:
#
# PYTHONPATH=/data/bin python3.11 -m demultiplex <RunID>
########################################################################


import os
import sys

# ensure the bytecode cache is stored in a unique directory for each user
# under /tmp
username = os.getenv('USER') or os.getenv('USERNAME')  # Get current username
sys.pycache_prefix = f'/tmp/pycache/{username}'



import logging
import argparse
from demultiplex import main


# TODO: setup logging properly in its own module before anything else get started
# Initialize loggers
demuxLogger = logging.getLogger( __name__ )
demuxFailureLogger = logging.getLogger( "SMTPFailureLogger" )


if __name__ == "__main__":
    if sys.hexversion < 51056112:  # Require Python 3.11 or newer
        sys.exit("Python 3.11 or newer is required to run this program.")

    parser = argparse.ArgumentParser()

    if len(sys.argv) == 1:
        sys.exit("No RunID argument present. Exiting.")

    RunID = sys.argv[1]
    RunID = RunID.rstrip('/,.')  # Be forgiving any ',' '/' or '.' during copy-paste

    main(RunID)
