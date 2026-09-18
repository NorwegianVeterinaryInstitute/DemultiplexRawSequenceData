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

    A run directory is complete when it contains demux.demultiplexCompleteFile, which
    finalize( ) touches as the last step. A run directory without it is a run that died
    mid-way: setup_lock( ) guarantees one instance, so at scan time nothing is in progress.
    """

    def __init__( self, path: str ) -> None:
        self.path            = path
        self.runs            = [ ]                                                              # complete runs, RunID without suffix
        self.incomplete_runs = { }                                                              # RunID -> reason, for runs without the completion marker
        self.pending_deliveries = { }                                                           # RunID -> missing delivery and run markers, for complete runs, informational
        self._scan( )

    def _scan( self ) -> None:
        """
        Scan the demultiplex directory and split run directories into complete and incomplete.
        """
        for dirName in os.listdir( self.path ):
            if constants.DEMULTIPLEX_DIR_SUFFIX not in dirName:
                continue
            if not any( tag in dirName for tags in [ demux.core.demux.nextSeq, demux.core.demux.miSeq ] for tag in tags ):
                continue

            runid    = dirName.replace( constants.DEMULTIPLEX_DIR_SUFFIX, '' )
            run_path = os.path.join( self.path, dirName )
            complete = os.path.join( run_path, demux.core.demux.demultiplexCompleteFile )
            failed   = os.path.join( run_path, demux.core.demux.demultiplexFailedFile )

            if os.path.isfile( complete ):
                self.runs.append( runid )
                missing = [ marker for marker in ( demux.core.demux.vigaspDeliveryCompleteFile, demux.core.demux.nirdDeliveryCompleteFile, demux.core.demux.runCompleteFile )
                            if not os.path.isfile( os.path.join( run_path, marker ) ) ]
                if missing:
                    self.pending_deliveries[ runid ] = missing
            elif os.path.isfile( failed ):
                with open( failed, encoding = "utf-8" ) as handle:
                    first_line = handle.readline( ).strip( )
                self.incomplete_runs[ runid ] = first_line or f"{demux.core.demux.demultiplexFailedFile} present"
            else:
                self.incomplete_runs[ runid ] = f"no {demux.core.demux.demultiplexCompleteFile}, no {demux.core.demux.demultiplexFailedFile}: killed or crashed outside process_run( )"

        demuxLogger.info( termcolor.colored( f"Found {len( self.runs )} completed runs in {self.path}", color = "light_cyan", attrs = [ "reverse" ] ) )
        if self.incomplete_runs:
            demuxLogger.warning( termcolor.colored( f"Found {len( self.incomplete_runs )} incomplete runs in {self.path}", color = "magenta", attrs = [ "reverse", "bold" ] ) )


def detect_new_runs( rawdata: RawDataDirectory, demultiplex: DemultiplexDirectory ) -> list:
    """
    Compare rawdata and demultiplex directories to find runs that need processing.
    Returns a list of RunIDs that are in rawdata but not yet in demultiplex,
    filtered to only those that are ready for demultiplexing.

    Incomplete runs (a demultiplex directory without the completion marker) are
    reported loudly and excluded: they are neither "done" nor "new", and nothing
    is run on top of a half-built directory. Rerunning one is a manual step.
    """

    rawdata_set     = set( rawdata.runs )
    demultiplex_set = set( demultiplex.runs )
    incomplete_set  = set( demultiplex.incomplete_runs )

    in_rawdata_only     = rawdata_set - demultiplex_set - incomplete_set
    in_demultiplex_only = ( demultiplex_set | incomplete_set ) - rawdata_set

    if in_rawdata_only:
        demuxLogger.warning( termcolor.colored( f"Runs in rawdata but not yet demultiplexed: {in_rawdata_only}", color="magenta", attrs=["reverse"] ) )
    if in_demultiplex_only:
        demuxLogger.warning( termcolor.colored( f"Runs in demultiplex but deleted from rawdata: {in_demultiplex_only}", color="magenta", attrs=["reverse"] ) )

    for runid, reason in demultiplex.incomplete_runs.items( ):
        text = [ f"INCOMPLETE RUN: {runid}",
                 f"    reason:  {reason}",
                 f"    this run is skipped until the incomplete directory is removed:",
                 f"    rm -rvf {os.path.join( demux.core.demux.demultiplexDir, runid + constants.DEMULTIPLEX_DIR_SUFFIX )}* {os.path.join( demux.core.demux.forTransferDir, runid )}*",
               ]
        text = '\n'.join( text )
        demuxLogger.warning( termcolor.colored( text, color="magenta", attrs=["bold"] ) )

    for runid, missing in demultiplex.pending_deliveries.items( ):
        demuxLogger.debug( f"{runid}: demultiplexed, missing markers: {', '.join( missing )}" )

    new_runs   = [ runid for runid in rawdata.runs if runid not in demultiplex.runs and runid not in demultiplex.incomplete_runs ]
    ready_runs = [ runid for runid in new_runs if rawdata.is_ready( runid ) ]

    demuxLogger.info( termcolor.colored( f"{len( rawdata.runs )} in rawdata, {len( demultiplex.runs )} in demultiplex, {len( demultiplex.incomplete_runs )} incomplete, {len( ready_runs )} new runs ready.", color = "light_cyan", attrs = [ "reverse" ] ) )

    if not ready_runs:
        demuxLogger.info("No new runs to process.")

    return ready_runs
