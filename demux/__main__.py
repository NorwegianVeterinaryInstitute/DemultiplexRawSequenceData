# Entry point 
# (calls main(  )function in `demultiplex.py`
#
#########################################################################
# To run this:
#
# /usr/bin/python3.11 -m demultiplex <RunID>
########################################################################


import os
import sys
import logging
import argparse

# from demultiplex import main

def parse_cli( argv = None ):
    parser = argparse.ArgumentParser( prog = "demultiplex" )
    parser.add_argument( "RunID", nargs = "+" )
    parser.add_argument("--dry-run", action = "store_true" )
    parser.add_argument("--nird",    action = "store_true" )
    parser.add_argument("--vigas",   action = "store_true" )
    return parser.parse_args( argv )


if __name__ == "__main__":
    if sys.hexversion < 0x030B0000:  # 0x030B0000 -> 03 = Python 3, 0B = 11 (hex), 00 = patch 0 -> Python 3.11.0
        sys.exit("Python 3.11 or newer is required to run this program.")

    parser = argparse.ArgumentParser( )

    if len(sys.argv) == 1:
        sys.exit("No RunID argument present. Exiting.")

    args = parse_cli( )
    for runid in args.RunID:
        demultiplex.main( RunID, args )


# I need:
# positional args (nargs='+')
# optional flags (action='store_true')
# optional values (type=, default=)
# help/usage formatting
# Core mental model:
# argparse -> define schema -> parse_args() -> get Namespace -> pass downstream.