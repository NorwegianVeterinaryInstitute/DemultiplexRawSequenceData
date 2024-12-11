# Entry point 
# (calls main(  )function in `demultiplex_script.py`
#
#########################################################################
# To run this:
#
# PYTHONPATH=/data/bin python3.11 -m demultiplex <RunID>
########################################################################


import sys
import logging
import argparse
from demultiplex_script import main

# Initialize loggers
demuxLogger = logging.getLogger(__name__)
demuxFailureLogger = logging.getLogger("SMTPFailureLogger")

if __name__ == "__main__":
    if sys.hexversion < 50923248:  # Require Python 3.9 or newer
        sys.exit("Python 3.9 or newer is required to run this program.")

    parser = argparse.ArgumentParser()

    if len(sys.argv) == 1:
        sys.exit("No RunID argument present. Exiting.")

    RunID = sys.argv[1]
    RunID = RunID.replace("/", "")  # Be forgiving for copy-paste issues
    RunID = RunID.replace(",", "")

    main(RunID)
