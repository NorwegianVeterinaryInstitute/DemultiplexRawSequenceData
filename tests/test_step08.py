#!/usr/bin/env python3.11
########################################################################
#
# tests/test_step08.py
#
# Integration test harness for the NIRD SSH transport and upload (step08).
#
# Copies test .fastq.gz files with .tar extension to bypass suffix checks,
# computes md5 + sha512, runs deliver_files_to_NIRD(), verifies remote
# hashes match local, then cleans up.
#
# This is an integration test. No mocking - tests against real NIRD SSH,
# real Bitwarden, real SSH config.
#
# Prerequisites:
#   - VPN to NVI is up (if required for NIRD access)
#   - bw serve is running and vault is unlocked
#   - SSH config for login.nird.sigma2.no is present and compliant
#   - known_hosts contains login.nird.sigma2.no
#   - NIRD base path exists: /nird/datalake/NS9305K/test_demultiplex
#
# Usage:
#   /usr/bin/python3.11 tests/test_step08.py (from within the nvi-demux directory)
#
# Copyright: The Norwegian Veterinary Institute
# Licenced under the GNU Public License 3.0 or newer
#
########################################################################

import hashlib
import os
import paramiko
import shutil
import stat
import sys
import tempfile
import time

sys.path.insert( 0, os.path.join( os.path.dirname( __file__ ), '..' ) )
from demux.core import demux
from demux.steps.step08_deliver_files_to_NIRD  import deliver_files_to_NIRD
from demux.steps.step08_03_setup_ssh_connection import _setup_ssh_connection
from demux.steps.step08_06_tear_down_transport  import _tear_down_transport

########################################################################
# test configuration
########################################################################

TEST_RUN_ID:str       = "999999_ZZTEST_0000_000000000-ZZZZZ"
TEST_RUN_ID_SHORT:str = "999999_ZZTEST"
TEST_PROJECT_NAME:str = "ZZTEST_PROJECT"
TESTS_DIR:str         = os.path.dirname( os.path.abspath( __file__ ) )
TEST_R1:str           = os.path.join( TESTS_DIR, "2024_EQA13.Strain0020_R1_001.fastq.gz" )
TEST_R2:str           = os.path.join( TESTS_DIR, "2024_EQA13.Strain0020_R2_001.fastq.gz" )


########################################################################
# setup
########################################################################

def _setup() -> str:
    """
    Create a temporary for_transfer directory with two test files copied
    as .tar files, plus their md5 and sha512 checksum files.

    :returns: tmp_base path
    """

    if not os.path.isfile( TEST_R1 ):
        raise FileNotFoundError( f"Test R1 not found: {TEST_R1}" )
    if not os.path.isfile( TEST_R2 ):
        raise FileNotFoundError( f"Test R2 not found: {TEST_R2}" )

    tmp_base:str = tempfile.mkdtemp( prefix = "test_step08_" )
    run_dir:str  = os.path.join( tmp_base, TEST_RUN_ID )
    os.makedirs( run_dir, mode = stat.S_IRWXU )

    demux.tarFilesToTransferList      = [ ]
    demux.absoluteFilesToTransferList = { }

    for src, label in [ ( TEST_R1, "R1" ), ( TEST_R2, "R2" ) ]:
        tar_name:str = f"{TEST_RUN_ID_SHORT}.{TEST_PROJECT_NAME}.{label}.tar"
        tar_path:str = os.path.join( run_dir, tar_name )
        shutil.copy2( src, tar_path )

        with open( tar_path, "rb" ) as fh:
            data:bytes = fh.read()
        md5sum:str    = hashlib.md5( data ).hexdigest()
        sha512sum:str = hashlib.sha512( data ).hexdigest()

        with open( f"{tar_path}.md5", "w" ) as fh:
            fh.write( f"{md5sum}  {tar_name}\n" )
        with open( f"{tar_path}.sha512", "w" ) as fh:
            fh.write( f"{sha512sum}  {tar_name}\n" )

        demux.tarFilesToTransferList.append( tar_path )

    # configure demux singleton
    demux.RunID               = TEST_RUN_ID
    demux.runIDShort          = TEST_RUN_ID_SHORT
    demux.forTransferDir      = tmp_base
    demux.n                   = 0
    demux.totalTasks          = 9
    demux.nird_access_mode    = "ssh2fa"
    demux.nird_copy_mode      = "serial"
    demux.transfer_to_nird    = True
    demux.transport           = None
    demux.transport_stack     = [ ]
    demux.hostname            = demux.nird_upload_host

    return tmp_base


########################################################################
# cleanup
########################################################################

def _cleanup_local( tmp_base:str ) -> None:
    if tmp_base and os.path.isdir( tmp_base ):
        shutil.rmtree( tmp_base )
        print( f"  cleaned up local temp directory: {tmp_base}" )


def _cleanup_remote() -> None:
    """
    Open a fresh SSH connection and delete all remote test files and directory.
    Only called on successful test run. Best-effort: prints warnings on failure.
    """

    demux.transport       = None
    demux.transport_stack = [ ]

    try:
        _setup_ssh_connection( demux )
    except Exception as error:
        print( f"  WARNING: remote cleanup SSH connection failed: {error}" )
        return

    remote_dir:str = os.path.join( demux.nird_base_upload_path_ssh, TEST_RUN_ID )

    try:
        sftp:paramiko.SFTPClient = paramiko.SFTPClient.from_transport( demux.transport )
        for entry in demux.absoluteFilesToTransferList.values():
            for key in ( 'tar_file_remote', 'md5_file_remote', 'sha512_file_remote' ):
                try:
                    sftp.remove( entry[ key ] )
                    print( f"  deleted remote: {entry[ key ]}" )
                except Exception as error:
                    print( f"  WARNING: could not delete {entry[ key ]}: {error}" )
        try:
            sftp.rmdir( remote_dir )
            print( f"  deleted remote directory: {remote_dir}" )
        except Exception as error:
            print( f"  WARNING: could not delete remote directory: {error}" )
        sftp.close()
    except Exception as error:
        print( f"  WARNING: remote cleanup failed: {error}" )
    finally:
        try:
            _tear_down_transport( demux )
        except Exception:
            pass


########################################################################
# main
########################################################################

def main() -> int:

    test_start_time:float = time.time()

    print( "=" * 72 )
    print( "test_step08: NIRD SSH transport integration test" )
    print( "=" * 72 )
    print( f"  run ID:       {TEST_RUN_ID}" )
    print( f"  access mode:  {demux.nird_access_mode}" )
    print( f"  remote base:  {demux.nird_base_upload_path_ssh}" )
    print( f"  R1 source:    {TEST_R1}" )
    print( f"  R2 source:    {TEST_R2}" )
    print( )

    tmp_base:str = ""
    try:
        tmp_base = _setup()
        print( f"  temp directory: {tmp_base}" )
        print( f"  files:          {[ os.path.basename( f ) for f in demux.tarFilesToTransferList ]}" )
    except Exception as error:
        print( f"SETUP FAILED: {type( error ).__name__}: {error}" )
        return 1

    print( )
    print( "running deliver_files_to_NIRD()..." )
    print( )

    passed:bool = False
    try:
        deliver_files_to_NIRD( demux )
        passed = True
    except Exception as error:
        print( f"\nEXECUTION FAILED: {type( error ).__name__}: {error}" )

    print( )
    print( "cleanup:" )
    if passed:
        _cleanup_remote()
    else:
        print( "  remote cleanup skipped: upload failed - verify remote state manually before deleting" )
    _cleanup_local( tmp_base )

    elapsed:float = time.time() - test_start_time

    print( )
    if passed:
        print( "=" * 72 )
        print( "PASSED" )
        print( f"  total time: {elapsed:.1f}s" )
        print( "=" * 72 )
        return 0
    else:
        print( f"FAILED (total time: {elapsed:.1f}s)" )
        return 1


if __name__ == '__main__':
    sys.exit( main() )