"""
arguments.py: argument parsing for the demultiplex script.

Parses and validates command line arguments passed to demultiplex.py.
Accepts a RunID either as a bare string or prefixed with an absolute directory path.
"""

import argparse
import os

import demux.config.constants as constants


def parse_runid( value:str ) -> str:
    """
    Parse a RunID from a string, stripping leading and trailing slashes and path components.
    Accepts formats:
        RunID
        RunID/
        /foo/bar/RunID
        /foo/bar/RunID/
    Returns the bare RunID string.
    """
    RunID = os.path.basename( value.strip( '/' ) )
    if not constants.RUNID_PATTERN.match( RunID ):
        raise argparse.ArgumentTypeError( f"'{RunID}' does not look like a valid Illumina RunID. Aborting." )
    return RunID


def _add_runid_argument( parser: argparse.ArgumentParser ) -> None:
    """
    Add the RunID positional argument to the argument parser.
    """
    parser.add_argument('RunID', type = parse_runid, help = 'Illumina RunID, optionally prefixed with an absolute directory path.' )



def parse_arguments( ) -> argparse.Namespace:
    """
    Parse command line arguments for demultiplex.py.
    Returns the bare RunID string.
    """

    parser = argparse.ArgumentParser( )
    _add_runid_argument( parser )
    #
    # ... drop in as needed
    #
    return parser.parse_args( )

