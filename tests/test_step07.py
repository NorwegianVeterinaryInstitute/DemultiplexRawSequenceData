#!/usr/bin/env python3.11
########################################################################
#
# tests/test_step07.py
#
# Integration test harness for the IRIDA upload state machine (step07).
#
# Builds a controlled environment with known test data, runs
# deliver_files_to_VIGASP() against IRIDA project 154
# (ZZTEST_API_DO_NOT_USE), and checks the results.
#
# This is an integration test. No mocking, we test against real
# Bitwarden, real IRIDA, real files. We own the test project
# (154:ZZTEST_API_DO_NOT_USE) and can clean up after ourselves.
# Steps 01-06 are skipped; we build the state step07 expects.
#
# Prerequisites:
#   - VPN to NVI is up
#   - bw serve is running and vault is unlocked
#   - IRIDA is reachable at irida.vigasp.vetinst.no:8080
#   - test .fastq.gz files exist in tests/
#
# Usage:
#   /usr/bin/python3.11 tests/test_step07.py (from within the nvi-demux directory)
#
# https://github.com/NorwegianVeterinaryInstitute/DemultiplexRawSequenceData/issues/27
#
# Copyright: The Norwegian Veterinary Institute
# Licenced under the GNU Public License 3.0 or newer
#
########################################################################

import json
import logging
import os
import shutil
import stat
import sys
import tempfile
import time
import urllib.request

from collections import defaultdict

sys.path.insert( 0, os.path.join( os.path.dirname( __file__ ), '..' ) )
from demux.core import demux
from demux.config import constants
from demux.steps.step07_deliver_files_to_VIGASP import deliver_files_to_VIGASP

# works!

########################################################################
# test configuration
########################################################################

# IRIDA test project - DO NOT use production projects
TEST_IRIDA_PROJECT_ID:int  = 154                       # ZZTEST_API_DO_NOT_USE
TEST_SAMPLE_NAME:str       = "2024_EQA13.Strain0020"   # base name for synthetic samples
TEST_PROJECT_NAME:str      = "ZZTEST_PROJECT"
TEST_RUN_ID:str            = "999999_ZZTEST_0000_000000000-ZZZZZ"
TEST_RUN_ID_SHORT:str      = "999999_ZZTEST"
TEST_R1_FILENAME:str       = "2024_EQA13.Strain0020_R1_001.fastq.gz"
TEST_R2_FILENAME:str       = "2024_EQA13.Strain0020_R2_001.fastq.gz"
TEST_SAMPLE_COUNT:int      = 20

# seconds to wait before deleting test data from IRIDA
# IRIDA's async GzipFileProcessor/FastQC chain needs time to finish
# processing the uploaded file; deleting too fast causes StaleStateException (PR 1506)
# and FileProcessorTimeoutException (60s internal timeout)
TEST_CLEANUP_DELAY_SECONDS:int = 90

# paths to the test .fastq.gz files shipped with the repo
TESTS_DIR:str              = os.path.dirname( os.path.abspath( __file__ ) )
TEST_R1:str                = os.path.join( TESTS_DIR, TEST_R1_FILENAME )
TEST_R2:str                = os.path.join( TESTS_DIR, TEST_R2_FILENAME )


########################################################################
# setup
########################################################################

def _setup() -> str:
    """
    Create a temporary directory structure that mimics what steps 01-06
    produce, copy test .fastq.gz files into it, and configure the demux
    singleton.

    Creates TEST_SAMPLE_COUNT synthetic samples, each with their own
    R1/R2 file copies named after the synthetic sample name.

    :returns: path to the temporary base directory (for cleanup).
    """

    # verify test files exist
    if not os.path.isfile( TEST_R1 ):
        raise FileNotFoundError( f"Test R1 file not found: {TEST_R1}" )
    if not os.path.isfile( TEST_R2 ):
        raise FileNotFoundError( f"Test R2 file not found: {TEST_R2}" )

    # create temp directory layout: <base>/<runIDShort>.<project_name>/
    tmp_base:str    = tempfile.mkdtemp( prefix = "test_step07_" )
    project_dir:str = os.path.join( tmp_base, f"{TEST_RUN_ID_SHORT}.{TEST_PROJECT_NAME}" )
    os.makedirs( project_dir, mode = stat.S_IRWXU )  # rwx------ (owner only)

    # build project_samples_metadata pointing at test project 154
    demux.project_samples_metadata = defaultdict( dict )

    for i in range( 1, TEST_SAMPLE_COUNT + 1 ):
        synthetic_name:str    = f"2024_EQA13_Strain0020_T{i:02d}"
        r1_filename:str       = f"{synthetic_name}_R1_001.fastq.gz"
        r2_filename:str       = f"{synthetic_name}_R2_001.fastq.gz"

        shutil.copy2( TEST_R1, os.path.join( project_dir, r1_filename ) )
        shutil.copy2( TEST_R2, os.path.join( project_dir, r2_filename ) )

        demux.project_samples_metadata[ TEST_PROJECT_NAME ][ synthetic_name ] = {
            'upload_to_vigasp': True,
            'vigas_project_id': TEST_IRIDA_PROJECT_ID,
        }

    # configure demux singleton
    demux.RunID                    = TEST_RUN_ID
    demux.runIDShort               = TEST_RUN_ID_SHORT
    demux.demultiplexRunIDdir      = tmp_base
    demux.n                        = 0
    demux.totalTasks               = 9

    # Reset IRIDA state in case the singleton was touched by a previous run in the same process.
    # Does not happen now (script runs once and exits) but matters if we move to pytest later,
    # where multiple test functions share the same process.
    demux.irida_oauth_token          = ""
    demux.irida_samples              = [ ]
    demux.irida_verified_projects    = { }
    demux.irida_tmp_dir              = ""
    demux.irida_decompressed_map     = { }
    demux.irida_local_hashes         = { }
    demux.irida_sequencing_run_id    = 0
    demux.irida_uploaded_samples     = [ ]
    demux.irida_verification_passed  = False
    demux.irida_run_completed        = False
    demux.irida_stage_times          = { }

    return tmp_base


########################################################################
# assert
########################################################################

def _assert_results() -> bool:
    """
    Check that the state machine completed successfully.

    :returns: True if all assertions pass, False otherwise.
    """
    passed:bool = True

    if not demux.irida_verification_passed:
        print( "ASSERT FAILED: irida_verification_passed is not True" )
        passed = False

    if not demux.irida_run_completed:
        print( "ASSERT FAILED: irida_run_completed is not True" )
        passed = False

    if demux.irida_sequencing_run_id == 0:
        print( "ASSERT FAILED: irida_sequencing_run_id is still 0" )
        passed = False

    if len( demux.irida_uploaded_samples ) != TEST_SAMPLE_COUNT:
        print( f"ASSERT FAILED: expected {TEST_SAMPLE_COUNT} uploaded samples, got {len( demux.irida_uploaded_samples )}" )
        passed = False
    else:
        expected_names:set = { f"2024_EQA13_Strain0020_T{i:02d}" for i in range( 1, TEST_SAMPLE_COUNT + 1 ) }
        uploaded_names:set = { s[ 'sample_name' ] for s in demux.irida_uploaded_samples }
        missing:set        = expected_names - uploaded_names
        if missing:
            print( f"ASSERT FAILED: missing uploaded samples: {sorted( missing )}" )
            passed = False
        wrong_project:list = [ s for s in demux.irida_uploaded_samples if s[ 'project_id' ] != TEST_IRIDA_PROJECT_ID ]
        if wrong_project:
            print( f"ASSERT FAILED: samples with wrong project_id: {wrong_project}" )
            passed = False

    if not demux.irida_oauth_token:
        print( "ASSERT FAILED: irida_oauth_token is empty" )
        passed = False

    if not demux.irida_local_hashes:
        print( "ASSERT FAILED: irida_local_hashes is empty" )
        passed = False

    return passed


########################################################################
# cleanup
########################################################################

def _wait_for_irida_processing() -> None:
    """
    Wait for IRIDA's async GzipFileProcessor/FastQC chain to finish
    processing the uploaded files before deleting test data.

    Without this delay, deleting the sample while IRIDA is still
    processing causes Hibernate StaleStateException (PR 1506)
    and FileProcessorTimeoutException (60s internal timeout).
    """
    for remaining in range( TEST_CLEANUP_DELAY_SECONDS, 0, -1 ):
        print( f"\r  waiting {remaining}s for IRIDA async processing to finish...  ", end = '', flush = True )
        time.sleep( 1 )
    print( "\r  IRIDA async processing wait complete.                              " )


def _cleanup_irida() -> None:
    """
    Remove test data from IRIDA: delete uploaded samples from the test
    project and delete the sequencing run.

    Best-effort: prints warnings on failure but does not raise exceptions.
    The test has already passed or failed by this point.
    """

    if not demux.irida_oauth_token:
        print( "  IRIDA cleanup skipped: no token" )
        return

    # ---- delete samples from project ----------------------------------

    for uploaded in demux.irida_uploaded_samples:
        sample_id:int  = uploaded[ 'sample_id' ]
        project_id:int = uploaded[ 'project_id' ]
        url:str = f"{demux.irida_base_url}/{demux.irida_projects_endpoint}/{project_id}/{demux.irida_project_samples_subpath}/{sample_id}"

        request = urllib.request.Request( url, method = constants.HTTP_DELETE )
        request.add_header( constants.HTTP_HEADER_AUTHORIZATION, f'{constants.HTTP_BEARER_PREFIX} {demux.irida_oauth_token}' )

        try:
            with urllib.request.urlopen( request, timeout = demux.irida_timeout ) as response:
                pass
            print( f"  deleted sample {sample_id} from project {project_id}" )
        except Exception as error:
            print( f"  WARNING: failed to delete sample {sample_id} from project {project_id}: {error}" )

    # ---- delete sequencing run ----------------------------------------

    if demux.irida_sequencing_run_id:
        url:str = f"{demux.irida_base_url}/{demux.irida_sequencingrun_endpoint}/{demux.irida_sequencing_run_id}"

        request = urllib.request.Request( url, method = constants.HTTP_DELETE )
        request.add_header( constants.HTTP_HEADER_AUTHORIZATION, f'{constants.HTTP_BEARER_PREFIX} {demux.irida_oauth_token}' )

        try:
            with urllib.request.urlopen( request, timeout = demux.irida_timeout ) as response:
                pass
            print( f"  deleted sequencing run {demux.irida_sequencing_run_id}" )
        except Exception as error:
            print( f"  WARNING: failed to delete sequencing run {demux.irida_sequencing_run_id}: {error}" )


def _cleanup_local( tmp_base: str ) -> None:
    """
    Remove temporary directory created during setup.
    """
    if tmp_base and os.path.isdir( tmp_base ):
        shutil.rmtree( tmp_base )
        print( f"  cleaned up temp directory: {tmp_base}" )


########################################################################
# main
########################################################################

def main() -> int:

    test_start_time:float = time.time()

    print( "=" * 72 )
    print( "test_step07: IRIDA upload state machine integration test" )
    print( "=" * 72 )
    print( f"  IRIDA project:  {TEST_IRIDA_PROJECT_ID} (ZZTEST_API_DO_NOT_USE)" )
    print( f"  sample count:   {TEST_SAMPLE_COUNT}" )
    print( f"  max_in_flight:  {demux.irida_max_in_flight} workers ({demux.irida_max_in_flight * 2} files in flight)" )
    print( f"  batch stagger:  {demux.irida_upload_batch_stagger_seconds}s" )
    print( f"  R1 source:      {TEST_R1}" )
    print( f"  R2 source:      {TEST_R2}" )
    print( )

    # ---- setup --------------------------------------------------------

    tmp_base:str = ""
    try:
        tmp_base = _setup()
        print( f"  temp directory: {tmp_base}" )
    except Exception as error:
        print( f"SETUP FAILED: {type( error ).__name__}: {error}" )
        return 1

    # ---- execute ------------------------------------------------------

    print( )
    print( "running deliver_files_to_VIGASP()..." )
    print( )

    try:
        deliver_files_to_VIGASP( demux )
    except Exception as error:
        print( f"\nEXECUTION FAILED: {type( error ).__name__}: {error}" )
        print( )
        print( "IRIDA cleanup after failure:" )
        _wait_for_irida_processing()
        _cleanup_irida()
        _cleanup_local( tmp_base )
        elapsed:float = time.time() - test_start_time
        print( f"\n  total time: {elapsed:.1f}s" )
        return 1

    # ---- assert -------------------------------------------------------

    print( )
    passed:bool = _assert_results()

    # ---- cleanup ------------------------------------------------------

    print( )
    print( "IRIDA cleanup:" )
    _wait_for_irida_processing()
    _cleanup_irida()
    _cleanup_local( tmp_base )

    # ---- report -------------------------------------------------------

    elapsed:float = time.time() - test_start_time

    print( )
    if passed:
        print( "=" * 72 )
        print( "PASSED" )
        print( f"  sequencing_run_id:  {demux.irida_sequencing_run_id}" )
        print( f"  max_in_flight:      {demux.irida_max_in_flight}" )
        print( f"  batch stagger:      {demux.irida_upload_batch_stagger_seconds}s" )
        print( f"  stage times:        {demux.irida_stage_times}" )
        print( f"  uploaded_samples:   {demux.irida_uploaded_samples}" )
        print( f"  local_hashes:       {demux.irida_local_hashes}" )
        print( f"  total time:         {elapsed:.1f}s" )
        print( "=" * 72 )
        return 0
    else:
        print( f"FAILED: see assertions above (total time: {elapsed:.1f}s)" )
        return 1


if __name__ == '__main__':
    sys.exit( main( ) )
