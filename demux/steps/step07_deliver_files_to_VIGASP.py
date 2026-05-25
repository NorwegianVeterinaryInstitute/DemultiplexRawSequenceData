#!/usr/bin/env -S -- /usr/bin/python3.11 -X pycache_prefix=/tmp/demultiplex

########################################################################
#
# step07_deliver_files_to_VIGASP.py
#
# Upload demultiplexed FASTQ pairs to IRIDA/VIGASP.
#
# Two execution modes:
#
#   1. Pipeline mode (called from demultiplex.py):
#       deliver_files_to_VIGASP( demux )
#
#   2. Standalone mode (operator invocation):
#       python3.11 -m demux.steps.step07_deliver_files_to_VIGASP run <RunID>
#       python3.11 -m demux.steps.step07_deliver_files_to_VIGASP manifest <path/to/manifest.json>
#
# Standalone mode bootstraps a minimal context object that exposes the
# same attributes the sub-steps expect, without importing the full
# demux class or running the entire pipeline.
#
# https://github.com/NorwegianVeterinaryInstitute/DemultiplexRawSequenceData/issues/27
#
# Copyright: The Norwegian Veterinary Institute
# Licenced under the GNU Public License 3.0 or newer
#
########################################################################

import argparse
import json
import logging
import os
import sys
import termcolor

from collections import defaultdict

from demux.loggers import demuxLogger, demuxFailureLogger

from demux.steps.step07_01_preflight       import _preflight
from demux.steps.step07_02_check_projects  import _check_projects
from demux.steps.step07_03_decompress      import _decompress
from demux.steps.step07_04_hash            import _hash
from demux.steps.step07_05_create_run      import _create_run
from demux.steps.step07_06_upload          import _upload
from demux.steps.step07_07_cleanup         import _cleanup
from demux.steps.step07_08_verify          import _verify
from demux.steps.step07_09_complete        import _complete


########################################################################
# Pipeline entry point
########################################################################

def deliver_files_to_VIGASP( demux ):
    """
    Upload demultiplexed FASTQ pairs to IRIDA/VIGASP.

    State machine (see irida_uploader_state_machine_v6.png):

        PREFLIGHT -> CHECK PROJECTS -> DECOMPRESS -> HASH ->
        CREATE RUN -> UPLOAD -> CLEANUP -> VERIFY -> COMPLETE

    Any failure transitions to ERROR: notify operator, do NOT PATCH
    the sequencing run to COMPLETE. Cleanup runs unconditionally
    (even on error) so decompressed temp files do not accumulate.

    Accepts either the full demux class singleton (pipeline mode) or
    a _StandaloneContext instance (standalone mode). The sub-steps do
    not care which; they read and write the same attribute names.
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Uploading files to VIGASP/IRIDA started\n", color = "green", attrs = [ "bold" ] ) )

    try:
        _preflight(      demux )
        _check_projects( demux )
        _decompress(     demux )
        _hash(           demux )
        _create_run(     demux )
        _upload(         demux )
        _cleanup(        demux )
        _verify(         demux )
        _complete(       demux )

    except Exception as error:
        # ERROR state: notify operator, do not PATCH
        demuxLogger.critical( f"IRIDA upload ERROR: {type( error ).__name__}: {error}" )
        demuxFailureLogger.critical( f"IRIDA upload ERROR for run {demux.RunID}: {type( error ).__name__}: {error}" )

        # cleanup runs unconditionally so tmp/ does not accumulate
        try:
            _cleanup( demux )
        except Exception as cleanup_error:
            demuxLogger.warning( f"IRIDA cleanup during error handling also failed: {cleanup_error}" )

        raise

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Uploading files to VIGASP/IRIDA finished\n", color = "red", attrs = [ "bold" ] ) )


########################################################################
# Standalone context
########################################################################

class _StandaloneContext:
    """
    Minimal demux-compatible object for standalone execution.

    Exposes exactly the attributes the step07 sub-steps read and write.
    Does not import demux.core; does not touch /data/rawdata or
    /data/demultiplex beyond reading the samplesheet and the .fastq.gz
    files that already exist there.
    """

    def __init__( self ):
        self.n                        = 0
        self.totalTasks               = 9
        self.RunID                    = ""
        self.runIDShort               = ""
        self.demultiplexRunIDdir      = ""
        self.rawDataRunIDdir          = ""
        self.project_samples_metadata = defaultdict( dict )
        self.projectList              = [ ]
        self.newProjectNameList       = [ ]


def _build_context_from_runid( RunID: str ) -> _StandaloneContext:
    """
    Reads the samplesheet from /data/rawdata/<RunID>/SampleSheet.csv
    (or SampleSheet-with-path-names.csv if present), builds
    project_samples_metadata the same way core.py does, and points
    demultiplexRunIDdir at the existing demultiplex output directory.

    Requires that demultiplexing has already been run (steps 01-06).
    """
    from sample_sheet import SampleSheet
    import demux.config.constants as constants

    ctx = _StandaloneContext()
    ctx.RunID = RunID
    ctx.runIDShort = '_'.join( RunID.split( '_' )[ 0:2 ] )

    ctx.rawDataRunIDdir     = os.path.join( constants.DATA_ROOT_DIR, constants.RAW_DATA_DIR_NAME, RunID )
    ctx.demultiplexRunIDdir = os.path.join( constants.DATA_ROOT_DIR, constants.DEMULTIPLEX_DIR_NAME, RunID + constants.DEMULTIPLEX_DIR_SUFFIX )

    if not os.path.isdir( ctx.demultiplexRunIDdir ):
        raise FileNotFoundError( f"Demultiplex directory does not exist: {ctx.demultiplexRunIDdir}\nRun the pipeline (steps 01-06) first, or use 'manifest' mode." )

    # samplesheet
    samplesheet_path = os.path.join( ctx.rawDataRunIDdir, 'SampleSheet.csv' )
    samplesheet_with_paths = os.path.join( ctx.rawDataRunIDdir, 'SampleSheet-with-path-names.csv' )
    if os.path.isfile( samplesheet_with_paths ):
        samplesheet_path = samplesheet_with_paths

    if not os.path.isfile( samplesheet_path ):
        raise FileNotFoundError( f"SampleSheet not found: {samplesheet_path}" )

    sample_sheet = SampleSheet( samplesheet_path )

    # project list
    ctx.projectList = list( dict.fromkeys( sample_obj.Sample_Project for sample_obj in sample_sheet.samples ) )
    ctx.newProjectNameList = [ f"{ctx.runIDShort}.{p}" for p in ctx.projectList ]

    # build project_samples_metadata (same structure as core.py _build_project_sample_metadata)
    for sample in sample_sheet.samples:
        ctx.project_samples_metadata[ sample.Sample_Project ][ sample.Sample_ID ] = {
            'transfer_to_vigas': bool( sample.Transfer_VIGAS.lower() == "yes" ),
            'vigas_project_id':  int( sample.VIGASP_ID ),
            'transfer_to_nird':  bool( sample.Transfer_NIRD.lower() == "yes" ),
            'nird_location':     str( sample.NIRD_Location ),
        }

    return ctx


def _build_context_from_manifest( manifest_path: str ) -> _StandaloneContext:
    """
    Build a standalone context from a pre-built JSON manifest.

    Manifest format:
        {
            "RunID": "230415_M01234_1234_000000000-ABCDE",
            "demultiplex_dir": "/data/demultiplex/230415_M01234_1234_000000000-ABCDE_demultiplex",
            "samples": [
                { "sample_name": "MySample", "project_id": 150, "r1": "/path/to/R1.fastq.gz", "r2": "/path/to/R2.fastq.gz" }
            ]
        }

    The manifest bypasses samplesheet parsing entirely. Use this when
    re-uploading a specific subset of samples or when the samplesheet
    is not available.

    Preflight detects that irida_samples is already set and skips the
    samplesheet walk + R1/R2 discovery.
    """
    with open( manifest_path, 'r' ) as fh:
        manifest = json.load( fh )

    ctx = _StandaloneContext()
    ctx.RunID               = manifest[ 'RunID' ]
    ctx.runIDShort          = '_'.join( ctx.RunID.split( '_' )[ 0:2 ] )
    ctx.demultiplexRunIDdir = manifest[ 'demultiplex_dir' ]

    if not os.path.isdir( ctx.demultiplexRunIDdir ):
        raise FileNotFoundError( f"Demultiplex directory does not exist: {ctx.demultiplexRunIDdir}" )

    # pre-load irida_samples; preflight will detect this and skip R1/R2 discovery
    ctx.irida_samples = manifest[ 'samples' ]

    # derive project list from unique project_ids (for logging only)
    project_ids = set()
    for sample in ctx.irida_samples:
        project_ids.add( sample[ 'project_id' ] )
    ctx.projectList = [ str( pid ) for pid in sorted( project_ids ) ]

    return ctx


########################################################################
# Standalone argument parsing
########################################################################

def _parse_standalone_args( argv = None ):
    parser = argparse.ArgumentParser( prog = 'step07_deliver_files_to_VIGASP', description = 'Upload demultiplexed FASTQ pairs to IRIDA/VIGASP (standalone mode).' )

    subparsers = parser.add_subparsers( dest = 'subcommand', required = True )

    run_parser = subparsers.add_parser( 'run', help = 'Upload from a completed pipeline run.' )
    run_parser.add_argument( 'RunID', type = str, help = 'Illumina RunID (e.g. 230415_M01234_1234_000000000-ABCDE)' )
    run_parser.add_argument( '--dry-run', action = 'store_true', help = 'Print what would be uploaded without uploading.' )

    manifest_parser = subparsers.add_parser( 'manifest', help = 'Upload from a JSON manifest file.' )
    manifest_parser.add_argument( 'manifest_path', type = str, help = 'Path to the JSON manifest file.' )
    manifest_parser.add_argument( '--dry-run', action = 'store_true', help = 'Print what would be uploaded without uploading.' )

    return parser.parse_args( argv )


########################################################################
# Standalone main
########################################################################

def _standalone_main( argv = None ):
    """
    Standalone entry point. Bootstraps a minimal context and runs the
    same state machine as the pipeline.
    """

    logging.basicConfig( level = logging.DEBUG, format = '%(asctime)s %(name)s %(levelname)s %(message)s', stream = sys.stderr )

    args = _parse_standalone_args( argv )

    if args.subcommand == 'run':
        ctx = _build_context_from_runid( args.RunID )
    elif args.subcommand == 'manifest':
        ctx = _build_context_from_manifest( args.manifest_path )
    else:
        raise ValueError( f"Unknown subcommand: {args.subcommand}" )

    dry_run = getattr( args, 'dry_run', False )

    if dry_run:
        demuxLogger.info( "DRY RUN: would upload the following:" )
        demuxLogger.info( f"  RunID: {ctx.RunID}" )
        demuxLogger.info( f"  demultiplex_dir: {ctx.demultiplexRunIDdir}" )
        if hasattr( ctx, 'irida_samples' ):
            for sample in ctx.irida_samples:
                demuxLogger.info( f"  {sample[ 'sample_name' ]} -> project {sample[ 'project_id' ]}: {sample[ 'r1' ]}, {sample[ 'r2' ]}" )
        else:
            for project, samples in ctx.project_samples_metadata.items():
                for sample_id, meta in samples.items():
                    if meta[ 'transfer_to_vigas' ]:
                        demuxLogger.info( f"  {sample_id} -> IRIDA project {meta[ 'vigas_project_id' ]}" )
        return 0

    deliver_files_to_VIGASP( ctx )
    return 0


if __name__ == '__main__':
    sys.exit( _standalone_main() )
