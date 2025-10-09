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
import logging
import argparse

from demultiplex import main

if __name__ == "__main__":
    if sys.hexversion < 51056112:  # Require Python 3.11 or newer
        sys.exit("Python 3.11 or newer is required to run this program.")

    parser = argparse.ArgumentParser()

    if len(sys.argv) == 1:
        sys.exit("No RunID argument present. Exiting.")

    RunID = sys.argv[1]
    demultiplex.main(RunID)
