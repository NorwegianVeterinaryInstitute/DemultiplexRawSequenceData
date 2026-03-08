"""
detect_new_runs.py: detect new Illumina runs that need demultiplexing.

Compares the contents of the raw data directory against the demultiplex directory
to determine which runs are new and ready for processing.
"""

import logging
import os
import termcolor

import demux.core

from demux.config  import constants

from demux.loggers import demuxLogger, demuxFailureLogger

class RawDataDirectory:
    """
    Represents the raw data directory and the runs within it.
    Scans for Illumina run directories that are ready for demultiplexing,
    i.e. contain both RTAComplete.txt and SampleSheet.csv.
    """

    def __init__( self, path: str ) -> None:
        self.path = path
        self.runs = self._scan( )

    def _scan( self ) -> list:
        """
        Scan the raw data directory for Illumina run directories.
        Returns a list of RunIDs.
        """
        runs = [ ]
        for dirName in os.listdir( self.path ):
            if constants.DEMULTIPLEX_DIR_SUFFIX in dirName:
                continue
            if any( tag in dirName for tags in [ demux.core.demux.nextSeq, demux.core.demux.miSeq ] for tag in tags ):
                runs.append( dirName )
        demuxLogger.info( termcolor.colored( f"Found {len( runs )} runs in {self.path}", color = "light_cyan", attrs = [ "reverse" ] ) )
        return runs

    def is_ready( self, runid: str ) -> bool:
        """
        Check if a run is ready for demultiplexing.
        A run is ready if both RTAComplete.txt and SampleSheet.csv are present.
        """
        run_path = os.path.join( self.path, runid )
        ready = ( demux.core.demux.rtaCompleteFile in os.listdir( run_path ) and demux.core.demux.sampleSheetFileName in os.listdir( run_path ) )
        if not ready:
            demuxLogger.warning( f"{runid}: not ready for demultiplexing, waiting for RTAComplete.txt and/or SampleSheet.csv" )
        return ready


class DemultiplexDirectory:
    """
    Represents the demultiplex directory and the runs within it.
    Scans for completed demultiplex run directories.
    """

    def __init__( self, path: str ) -> None:
        self.path = path
        self.runs = self._scan( )

    def _scan( self ) -> list:
        """
        Scan the demultiplex directory for completed run directories.
        Returns a list of RunIDs with the demultiplex suffix stripped.
        """
        runs = [ ]
        for dirName in os.listdir( self.path ):
            if constants.DEMULTIPLEX_DIR_SUFFIX not in dirName:
                continue
            if any( tag in dirName for tags in [ demux.core.demux.nextSeq,  demux.core.demux.miSeq ] for tag in tags):
                runs.append( dirName.replace( constants.DEMULTIPLEX_DIR_SUFFIX, '' ) )
        demuxLogger.info( termcolor.colored( f"Found {len(runs)} completed runs in {self.path}", color = "light_cyan", attrs = [ "reverse" ] ) )
        return runs


def detect_new_runs( rawdata: RawDataDirectory, demultiplex: DemultiplexDirectory ) -> list:
    """
    Compare rawdata and demultiplex directories to find runs that need processing.
    Returns a list of RunIDs that are in rawdata but not yet in demultiplex,
    filtered to only those that are ready for demultiplexing.
    """
    rawdata_set     = set( rawdata.runs )
    demultiplex_set = set( demultiplex.runs )

    in_rawdata_only     = rawdata_set - demultiplex_set
    in_demultiplex_only = demultiplex_set - rawdata_set

    if in_rawdata_only:
        demuxLogger.warning( termcolor.colored( f"Runs in rawdata but not yet demultiplexed: {in_rawdata_only}", color="magenta", attrs=["reverse"] ) )
    if in_demultiplex_only:
        demuxLogger.warning( termcolor.colored( f"Runs in demultiplex but deleted from rawdata: {in_demultiplex_only}", color="magenta", attrs=["reverse"] ) )

    new_runs   = [ runid for runid in rawdata.runs if runid not in demultiplex.runs]
    ready_runs = [ runid for runid in new_runs if rawdata.is_ready( runid ) ]

    demuxLogger.info( termcolor.colored( f"{len( rawdata.runs )} in rawdata, {len( demultiplex.runs )} in demultiplex, {len( ready_runs )} new runs ready.", color = "light_cyan", attrs = [ "reverse" ] ) )

    if not ready_runs:
        demuxLogger.info("No new runs to process.")

    return ready_runs