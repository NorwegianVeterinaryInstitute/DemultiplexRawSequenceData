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
#   /usr/bin/python3.11 tests/test_step07.py
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
import urllib.request

from collections import defaultdict

sys.path.insert( 0, os.path.join( os.path.dirname( __file__ ), '..' ) )
from demux.core import demux
from demux.config import constants
from demux.steps.step07_deliver_files_to_VIGASP import deliver_files_to_VIGASP


########################################################################
# test configuration
########################################################################

# IRIDA test project - DO NOT use production projects
TEST_IRIDA_PROJECT_ID:int  = 154                       # ZZTEST_API_DO_NOT_USE
TEST_SAMPLE_NAME:str       = "2024_EQA13.Strain0020"   # must be a substring of the .fastq.gz filenames
TEST_PROJECT_NAME:str      = "ZZTEST_PROJECT"
TEST_RUN_ID:str            = "999999_ZZTEST_0000_000000000-ZZZZZ"
TEST_RUN_ID_SHORT:str      = "999999_ZZTEST"
TEST_R1_FILENAME:str       = "2024_EQA13.Strain0020_R1_001.fastq.gz"
TEST_R2_FILENAME:str       = "2024_EQA13.Strain0020_R2_001.fastq.gz"

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

    # copy test files into the project directory
    shutil.copy2( TEST_R1, project_dir )
    shutil.copy2( TEST_R2, project_dir )

    # configure demux singleton
    demux.RunID                    = TEST_RUN_ID
    demux.runIDShort               = TEST_RUN_ID_SHORT
    demux.demultiplexRunIDdir      = tmp_base
    demux.n                        = 0
    demux.totalTasks               = 9

    # build project_samples_metadata pointing at test project 154
    demux.project_samples_metadata = defaultdict( dict )
    demux.project_samples_metadata[ TEST_PROJECT_NAME ][ TEST_SAMPLE_NAME ] = {
        'upload_to_vigasp': True,
        'vigas_project_id': TEST_IRIDA_PROJECT_ID,
        # mentioned here for completion sake
        # 'transfer_to_nird': False,
        # 'nird_location':    '/nird/projects/NS9305K/SEQ-TECH/data_delivery'
    }

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

    if len( demux.irida_uploaded_samples ) != 1:
        print( f"ASSERT FAILED: expected 1 uploaded sample, got {len( demux.irida_uploaded_samples )}" )
        passed = False
    else:
        uploaded:dict = demux.irida_uploaded_samples[ 0 ]
        if uploaded[ 'sample_name' ] != TEST_SAMPLE_NAME:
            print( f"ASSERT FAILED: expected sample_name '{TEST_SAMPLE_NAME}', got '{uploaded[ 'sample_name' ]}'" )
            passed = False
        if uploaded[ 'project_id' ] != TEST_IRIDA_PROJECT_ID:
            print( f"ASSERT FAILED: expected project_id {TEST_IRIDA_PROJECT_ID}, got {uploaded[ 'project_id' ]}" )
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

    print( "=" * 72 )
    print( "test_step07: IRIDA upload state machine integration test" )
    print( "=" * 72 )
    print( f"  IRIDA project:  {TEST_IRIDA_PROJECT_ID} (ZZTEST_API_DO_NOT_USE)" )
    print( f"  sample name:    {TEST_SAMPLE_NAME}" )
    print( f"  R1:             {TEST_R1}" )
    print( f"  R2:             {TEST_R2}" )
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
        _cleanup_irida()
        _cleanup_local( tmp_base )
        return 1

    # ---- assert -------------------------------------------------------

    print( )
    passed:bool = _assert_results()

    # ---- cleanup ------------------------------------------------------

    print( )
    print( "IRIDA cleanup:" )
    _cleanup_irida()
    _cleanup_local( tmp_base )

    # ---- report -------------------------------------------------------

    print( )
    if passed:
        print( "=" * 72 )
        print( "PASSED" )
        print( f"  sequencing_run_id:  {demux.irida_sequencing_run_id}" )
        print( f"  uploaded_samples:   {demux.irida_uploaded_samples}" )
        print( f"  local_hashes:       {demux.irida_local_hashes}" )
        print( "=" * 72 )
        return 0
    else:
        print( "FAILED: see assertions above" )
        return 1


if __name__ == '__main__':
    sys.exit( main( ) )