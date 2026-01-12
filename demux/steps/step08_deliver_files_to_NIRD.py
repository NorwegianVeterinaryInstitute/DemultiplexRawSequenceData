import hashlib
import json
import os
import paramiko
import psutil
import shutil
import socket
import subprocess
import sys
import termcolor
import urllib.request

from typing import Tuple

from paramiko                 import SSHClient, SSHConfig, AutoAddPolicy, RejectPolicy, Transport, SSHException
from paramiko.ssh_exception   import AuthenticationException
from scp                      import SCPClient

from concurrent.futures       import ThreadPoolExecutor

from demux.util.ssh_transport import _setup_ssh_connection, _ensure_remote_run_directory_ssh, _auth_transport_2fa

from demux.config             import constants
from demux.loggers            import demuxLogger, demuxFailureLogger


def _upload_tar_via_scp( demux, ssh_client, scp_client, file_entry ) -> None:
    """
    Upload a single local tar file to its remote path via an existing SCP session.

    Asserts that the remote target does not already exist, then performs a single
    SCP put operation. Does not perform verification by hashing the uploaded files.

    Returns None on success.

    Raises RuntimeError if remote file exists.
    """

    demuxLogger.info( f"Transferring: {file_entry[ 'tar_file_local' ]}" )

    stdin, stdout, stderr = ssh_client.exec_command( f"/usr/bin/test -f -- {shlex.quote( file_entry[ 'tar_file_remote' ] )}" )
    if stdout.channel.recv_exit_status( ) == 0:
        message  = f"RuntimeError: Remote file already exists: {demux.hostname}:{file_entry[ 'tar_file_remote' ]}"
        message += "Refusing to overwrite. Delete/move remote file first and then try to upload again."
        demuxLogger.critical( message )
        raise RuntimeError( message )

    scp_client.put( file_entry[ "tar_file_local" ], file_entry[ "tar_file_remote" ] )


def _verify_remote_hashes_against_local_files( demux, ssh_client, file_entry ) -> None:
    """
    Verify remote file integrity by computing remote MD5 and SHA-512 hashes and
    comparing them against the corresponding local checksum files.

    Calculates hashes on the remote host via SSH and reads local checksum files.

    Returns None on success.

    Raises RuntimeError on remote md5sum/sha512sum failure or on any hash mismatch.
    """


    entries              = demux.absoluteFilesToTransferList.values( )
    current_len          = len( file_entry[ 'tar_file_local' ] )
    longest_local_path   = max( ( len( entry[ 'tar_file_local' ] ) for entry in entries ), default = current_len )

    md5sum_stdin,    md5sum_stdout,    md5sum_stderr    = ssh_client.exec_command( f"/usr/bin/md5sum {shlex.quote( file_entry[ 'tar_file_remote' ] )}" )
    sha512sum_stdin, sha512sum_stdout, sha512sum_stderr = ssh_client.exec_command( f"/usr/bin/sha512sum {shlex.quote( file_entry[ 'tar_file_remote' ] )}" )

    if md5sum_stdout.channel.recv_exit_status( ) != 0:
        message = f"RuntimeError: remote md5sum failed for {file_entry['tar_file_remote']}: {md5sum_stderr.read( ).decode( ).strip( )}"
        demuxLogger.critical( message )
        raise RuntimeError( message )

    if sha512sum_stdout.channel.recv_exit_status( ) != 0:
        message = f"RuntimeError: remote sha512sum failed for {file_entry['tar_file_remote']}: {sha512sum_stderr.read( ).decode( ).strip( )}"
        demuxLogger.critical( message )
        raise RuntimeError( message )

    md5_file_remote    = md5sum_stdout.read( ).decode( ).split( )[ 0 ]
    sha512_file_remote = sha512sum_stdout.read( ).decode( ).split( )[ 0 ]

    with open( file_entry[ "md5_file_local" ], "r" ) as handle_md5:
        md5_file_local = handle_md5.read( ).split( )[ 0 ]
    with open( file_entry[ "sha512_file_local" ], "r" ) as handle_sha512:
        sha512_file_local = handle_sha512.read( ).split( )[ 0 ]

    if md5_file_local != md5_file_remote:
        message  = "Error: Local md5 differs from calculated remote md5:\n"
        message += f"LOCAL MD5:  {md5_file_local}  | {file_entry[ 'md5_file_local' ]}\n"
        message += f"REMOTE MD5: {md5_file_remote} | {file_entry[ 'md5_file_remote' ]}"
        message += "Please check both files, delete/move as appropriate and try uploading again."
        demuxLogger.critical( message )
        # raise RemoteHashMismatchError( message ) https://github.com/NorwegianVeterinaryInstitute/DemultiplexRawSequenceData/issues/150
        raise RuntimeError( message )

    if sha512_file_local != sha512_file_remote:
        message  = "Error: Local sha512 differs from calculated remote sha512:\n"
        message += f"LOCAL SHA512:  {sha512_file_local}  | {file_entry[ 'sha512_file_local' ]}\n"
        message += f"REMOTE SHA512: {sha512_file_remote} | {file_entry[ 'sha512_file_remote' ]}\n"
        message += "Please check both files, delete/move as appropriate and try uploading again."
        demuxLogger.critical( message )
        # raise RemoteHashMismatchError( message ) https://github.com/NorwegianVeterinaryInstitute/DemultiplexRawSequenceData/issues/150
        raise RuntimeError( message )

    demuxLogger.info( f"Done: LOCAL:{file_entry[ 'tar_file_local' ]:<{longest_local_path}} REMOTE:{demux.hostname}:{file_entry[ 'tar_file_remote' ]}" )



def _upload_and_verify_file_via_ssh_2fa( demux, tar_file ) -> None:  # worker per file, tar_file is in absolute path format
    """
    Upload and integrity-verify a single local tar file to the remote NIRD upload path
    using a fresh SSH transport authenticated via 2FA.

    Opens and authenticates a new SSH transport, uploads the tar file via SCP with
    overwrite protection, verifies remote integrity by comparing remote MD5 and
    SHA-512 hashes against local checksum files, and finally uploads the checksum
    files themselves.

    All transport, SCP, or verification failures propagate as exceptions; policy violations 
    (for example, remote file already exists) raise RuntimeError.

    Returns None on success. 
    """

    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Uploading file {tar_file} via ssh 2FA started\n", color = "green", attrs = ["bold"] ) )

    transport  = None
    ssh_client = None

    file_entry = demux.absoluteFilesToTransferList[ tar_file ]

    try:
        transport = _open_transport_and_validate_hostkey( demux )
        _auth_transport_2fa( demux, transport )

        ssh_client = SSHClient( )
        ssh_client._transport = transport

        with SCPClient( transport ) as scp_client:
            _upload_tar_via_scp( demux, ssh_client, scp_client, file_entry )
            _verify_remote_hashes_against_local_files( demux, ssh_client, file_entry )
            # Upload checksum files as metadata only; tar integrity is already verified against local checksums
            # so, there is no need to checksum the checksum files. Do so only when they become legally/audit-critical
            # artifacts.
            scp_client.put( file_entry[ "md5_file_local" ],    file_entry[ "md5_file_remote" ] )
            scp_client.put( file_entry[ "sha512_file_local" ], file_entry[ "sha512_file_remote" ] )

    finally:
        if ssh_client is not None:
            ssh_client.close( )
        elif transport is not None:
            transport.close( )
        demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Uploading file {tar_file} via ssh 2FA finished\n", color = "red", attrs = ["bold"] ) )



def _upload_and_verify_file_via_ssh( demux, tar_file ):  # worker per file, tar_file is in absolute path format
    """
    Upload and verify a single local tar file to the NIRD absolute upload path using a new SSH transport each time.
    """
    ssh_client = SSHClient( )
    ssh_client.load_system_host_keys( )
    # The remote host key must already exist known_hosts 
    #   else reject the connection.

    # ssh_client.set_missing_host_key_policy( AutoAddPolicy( ) )
    ssh_client.set_missing_host_key_policy( RejectPolicy( ) ) # do not accept host keys that are not already in place
    ssh_client.connect( hostname = demux.hostname, port = demux.port, username = demux.username, key_filename = demux.key_file )
    # Find the longest string in demux.absoluteFilesToTransferList and tabulate for that
    items = demux.absoluteFilesToTransferList.values( )
    current_len = len( demux.absoluteFilesToTransferList[tar_file][ 'tar_file_local' ] )
    longest_local_path = max( (len( entry[ 'tar_file_local' ] ) for entry in items ), default = current_len )
    try:
        with SCPClient( ssh_client.get_transport( ) ) as scp_client:

            demuxLogger.info( f"Transfering: {demux.absoluteFilesToTransferList[tar_file][ 'tar_file_local' ]}" )
            # test if the tar file we are about to upload exists already, to prevent overwriting
            stdin, stdout, stderr = ssh_client.exec_command( f"/usr/bin/test -f -- {shlex.quote( demux.absoluteFilesToTransferList[ tar_file ][ 'tar_file_remote'] )}" )  # we are not really doing anything with the stdin, stdout, stderr but keep them anyway
            if stdout.channel.recv_exit_status( ) == 0 : # file exists
                message =  f"RuntimeError: Remote file already exists: {demux.hostname}:{demux.absoluteFilesToTransferList[ tar_file ][ 'tar_file_remote' ]}"
                message += f"Refusing to overwrite. Delete/move remote file first and then try to upload again."
                demuxLogger.critical( message )
                raise RuntimeError( messsage )

            try:
                # upload file
                scp_client.put( demux.absoluteFilesToTransferList[tar_file]['tar_file_local'], demux.absoluteFilesToTransferList[tar_file]['tar_file_remote'] )
                # calculate remote checksum via md5
                # calculate remote checksum via sha512
                # check md5 checksum; check sha512 checksum
                # copy the tar file, the md5 file and then the sha512 file
                md5sum_stdin,    md5sum_stdout,    md5sum_stderr    = ssh_client.exec_command( f"/usr/bin/md5sum {shlex.quote( demux.absoluteFilesToTransferList[ tar_file ][ 'tar_file_remote' ] )}" )    # we are not really doing anything with the stdin, stdout, stderr but keep them anyway
                sha512sum_stdin, sha512sum_stdout, sha512sum_stderr = ssh_client.exec_command( f"/usr/bin/sha512sum {shlex.quote( demux.absoluteFilesToTransferList[ tar_file ][ 'tar_file_remote' ] )}" ) # we are not really doing anything with the stdin, stdout, stderr but keep them anyway

                # check exit status
                if md5sum_stdout.channel.recv_exit_status( ) != 0:
                    message = f"RuntimeError: remote md5sum failed for {demux.absoluteFilesToTransferList[tar_file]['tar_file_remote']}: {md5sum_stderr.read( ).decode( ).strip( )}"
                    demuxLogger.critical( message )
                    raise RuntimeError( message )
                if sha512sum_stdout.channel.recv_exit_status( ) != 0:
                    message = f"RuntimeError: remote sha512sum failed for {demux.absoluteFilesToTransferList[tar_file]['tar_file_remote']}: {sha512sum_stderr.read( ).decode( ).strip( ) }"
                    demuxLogger.critical( message )
                    raise RuntimeError( message )

                md5_file_remote    = md5sum_stdout.read( ).decode( ).split( )[0]
                sha512_file_remote = sha512sum_stdout.read( ).decode( ).split( )[0]
                with open( demux.absoluteFilesToTransferList[ tar_file ][ 'md5_file_local' ], 'r' ) as handle_md5:
                    md5_file_local = handle_md5.read( ).split( )[ 0 ]
                with open( demux.absoluteFilesToTransferList[ tar_file ][ 'sha512_file_local' ], 'r' ) as handle_sha512:
                    sha512_file_local = handle_sha512.read( ).split( )[ 0 ]

                if md5_file_local != md5_file_remote:
                    message = ( f"Error: Local md5 differs from calculated remote md5:\n"                                               +
                                f"LOCAL MD5:  {md5_file_local}  | {demux.absoluteFilesToTransferList[tar_file][ 'md5_file_local' ]}\n"  +
                                f"REMOTE MD5: {md5_file_remote} | {demux.absoluteFilesToTransferList[tar_file][ 'md5_file_remote' ]}"   +
                                f"Please check both files, delete/move as appropriate and try uploading again."
                            )
                    demuxLogger.critical( message )
                    raise RuntimeError( message )
                if sha512_file_local != sha512_file_remote:
                    message = ( f"Error: Local sha512 differs from calculated remote sha512:"                                                   +
                                f"LOCAL SHA512:  {sha512_file_local}  | {demux.absoluteFilesToTransferList[tar_file][ 'sha512_file_local' ]}"   +
                                f"REMOTE SHA512: {sha512_file_remote} | {demux.absoluteFilesToTransferList[tar_file][ 'sha512_file_remote' ]}"  + 
                                f"Please check both files, delete/move as appropriate and try uploading again."
                            )
                    demuxLogger.critical( message )
                    raise RuntimeError( message )

                # for an explaination of why there is no point checksumming the checksum see
                # https://github.com/NorwegianVeterinaryInstitute/DemultiplexRawSequenceData/issues/26#issuecomment-3578085128
                scp_client.put( demux.absoluteFilesToTransferList[tar_file]['md5_file_local'],    demux.absoluteFilesToTransferList[tar_file]['md5_file_remote'] )
                scp_client.put( demux.absoluteFilesToTransferList[tar_file]['sha512_file_local'], demux.absoluteFilesToTransferList[tar_file]['sha512_file_remote'] )

                demuxLogger.info( f"Done: LOCAL:{demux.absoluteFilesToTransferList[tar_file]['tar_file_local']:<{longest_local_path}} REMOTE:{demux.hostname}:{demux.absoluteFilesToTransferList[tar_file]['tar_file_remote']}" )

            except Exception as error:
                message = f"RuntimeError: SCP upload failed for {demux.hostname}:{demux.absoluteFilesToTransferList[tar_file]['tar_file_remote']}: {error}"
                demuxLogger.critical( message )
                raise RuntimeError( message )
    finally:
        ssh_client.close( )


def _upload_and_verify_file_via_local_sshfs_mount( demux, tar_file ):
    """
    Upload and verify a single local tar file to NIRD via an already-mounted sshfs path.
    """
    file_info          = demux.absoluteFilesToTransferList[ tar_file ]
    # Find the longest string in demux.absoluteFilesToTransferList and tabulate for that
    items = demux.absoluteFilesToTransferList.values( )
    current_len = len( demux.absoluteFilesToTransferList[tar_file][ 'tar_file_local' ] )
    longest_local_path = max( (len( entry[ 'tar_file_local' ] ) for entry in items ), default = current_len )

    if os.path.exists( file_info[ 'tar_file_remote' ] ):
        message = f"RuntimeError: Remote file already exists: {file_info[ 'tar_file_remote' ]}"
        message += "Refusing to overwrite. Delete/move remote file first and then try to upload again." 
        demuxLogger.critical( message )
        raise RuntimeError( message )

    try:
        shutil.copy2( file_info[ 'tar_file_local' ], file_info[ 'tar_file_remote' ] )  # requires import shutil

        READ_BINARY = "rb"
        READ_TEXT   = "r"

        # read and calculate all hashfiles
        with open( file_info[ 'md5_file_local' ],  READ_TEXT   ) as md5_handle_local:
            md5_file_local     = md5_handle_local.read( ).split( )[ 0 ]
        with open(file_info[ 'sha512_file_local' ], READ_TEXT    ) as sha512_handle_local:
            sha512_file_local  = sha512_handle_local.read().split( )[ 0 ]
        with open( file_info[ 'tar_file_remote' ], READ_BINARY ) as md5_handle_remote:
            md5_file_remote    = hashlib.file_digest( md5_handle_remote, hashlib.md5 ).hexdigest( )
        with open( file_info[ 'tar_file_remote' ], READ_BINARY ) as sha512_handle_remote:
            sha512_file_remote = hashlib.file_digest( sha512_handle_remote, hashlib.sha512 ).hexdigest( )

        if md5_file_local != md5_file_remote:
            message = ( f"Error: Local md5 differs from calculated remote md5:\n"                                               +
                        f"LOCAL MD5:  {md5_file_local}  | {demux.absoluteFilesToTransferList[tar_file][ 'md5_file_local' ]}\n"  +
                        f"REMOTE MD5: {md5_file_remote} | {demux.absoluteFilesToTransferList[tar_file][ 'md5_file_remote' ]}"   +
                        f"Please check both files, delete/move as appropriate and try uploading again."
                    )
            demuxLogger.critical( message )
            raise RuntimeError( message )
        if sha512_file_local != sha512_file_remote:
            message = ( f"Error: Local sha512 differs from calculated remote sha512:"                                                   +
                        f"LOCAL SHA512:  {sha512_file_local}  | {demux.absoluteFilesToTransferList[tar_file][ 'sha512_file_local' ]}"   +
                        f"REMOTE SHA512: {sha512_file_remote} | {demux.absoluteFilesToTransferList[tar_file][ 'sha512_file_remote' ]}"  + 
                        f"Please check both files, delete/move as appropriate and try uploading again."
                    )
            demuxLogger.critical( message )
            raise RuntimeError( message )

        shutil.copy2( file_info[ 'md5_file_local' ], file_info[ 'md5_file_remote' ] )
        shutil.copy2( file_info[ 'sha512_file_local' ], file_info[ 'sha512_file_remote' ] )

        demuxLogger.info( f"Done: LOCAL:{file_info[ 'tar_file_local' ]:<{longest_local_path}} REMOTE:{file_info[ 'tar_file_remote' ]}" )

    except Exception as error:
        message = f"RuntimeError: local sshfs upload failed for {file_info[ 'tar_file_remote' ]}: {error}"
        demuxLogger.critical( message )
        raise RuntimeError( message )


def _upload_files_to_nird( demux ):
    """
    Select the appropriate upload function based on NIRD access mode and execute all file transfers in either serial or parallel form.
    """
    # choose upload implementation
    if constants.NIRD_MODE_SSH       == demux.nird_access_mode:
        upload_func = _upload_and_verify_file_via_ssh
    elif constants.NIRD_MODE_SSH_2FA == demux.nird_access_mode:
        upload_func = _upload_and_verify_file_via_ssh_2fa
    elif constants.NIRD_MODE_MOUNTED == demux.nird_access_mode:
        upload_func = _upload_and_verify_file_via_local_sshfs_mount
    else:
        message = f"Unknown NIRD access mode: {demux.nird_access_mode}"
        demuxLogger.critical( message )
        raise RuntimeError( message )

    # serial / parallel copying switching
    if constants.SERIAL_COPYING == demux.nird_copy_mode:
        demuxLogger.info( "Serial copying enabled." )
        if len( demux.tarFilesToTransferList ) == 0:
            message = f"Length of demux.tarFilesToTransferList is zero while serial copying." # ensure that we get notified there is something wrong
            demuxLogger.critical( message )
            raise RuntimeError( message )
        for tar_file in demux.tarFilesToTransferList:
            upload_func( demux, tar_file )

    elif constants.PARALLEL_COPYING == demux.nird_copy_mode:
        demuxLogger.info( "Parallel copying enabled." )
        if len( demux.tarFilesToTransferList ) == 0:
            message = f"Length of demux.tarFilesToTransferList is zero while parallel copying." # ensure that we get notified there is something wrong
            demuxLogger.critical( message )
            raise RuntimeError( message )
        with ThreadPoolExecutor( max_workers = len( demux.tarFilesToTransferList ) ) as pool:
            futures = [
                pool.submit( upload_func, demux, tar_file )
                for tar_file in demux.tarFilesToTransferList
            ]
            for future in futures:
                try:
                    future.result( )
                except RuntimeError as error:
                    message = f"Upload failed: {error}"
                    demuxLogger.critical( message )
                    raise RuntimeError( message )


def _verify_local_files( demux ):
    """
    Verifies that all three required local files exist for every tar entry in absoluteFilesToTransferList: the tar file,
    its .md5, and its .sha512 file. Exits immediately on the first missing file.
    """

    message = ""

    for entry in demux.absoluteFilesToTransferList.values( ):
        if not os.path.exists( entry[ 'tar_file_local' ] ):
            message = f"File {entry[ 'tar_file_local' ]} does not exist. Check for the existanse of the file and try again."
            demuxLogger.critical( message )
            raise FileNotFoundError( message )
        if not os.path.exists( entry[ 'md5_file_local' ] ):
            message = f"File {entry[ 'md5_file_local' ]} does not exist. Check for the file and try again."
            demuxLogger.critical( message )
            raise FileNotFoundError( message )
        if not os.path.exists( entry[ 'sha512_file_local' ] ):
            message = f"File {entry[ 'sha512_file_local' ]} does not exist. Check for the file and try again."
            demuxLogger.critical( message )
            raise FileNotFoundError( message )



def _select_nird_base_upload_path( demux ):
    """
    Select which base upload path to use depending on access mode (sshfs vs SSH). Central place to extend path-selection rules; if path logic needs augmentation, add it here.
    """
    upload_path = ""
    if constants.NIRD_MODE_MOUNTED   == demux.nird_access_mode:
        upload_path = demux.nird_base_upload_path_local
    elif constants.NIRD_MODE_SSH     == demux.nird_access_mode:
        upload_path = demux.nird_base_upload_path_ssh
    elif constants.NIRD_MODE_SSH_2FA == demux.nird_access_mode:
        upload_path = demux.nird_base_upload_path_ssh
    else:
        message = f"ValueError: NIRD upload method does not guarantee remote directory value. Refusing to continue"
        raise ValueError( message )

    return upload_path



def _build_absolute_paths( demux ):
    """
    Builds and returns a dictonary mapping each tar filename to its full local and remote paths,
    including the associated .md5 and .sha512 files.
    """

    demux.nird_base_upload_path = _select_nird_base_upload_path( demux )

    local_base  = os.path.join( demux.forTransferDir,        demux.RunID )
    remote_base = os.path.join( demux.nird_base_upload_path, demux.RunID )

    for tar_file in demux.tarFilesToTransferList:
        # so here is a weird one that took me two days to debug: if both paths are in absolute format,
        # the last absolute path is returned and everything else is thrown away...
        # demux.tarFilesToTransferList is already in absolute format, so this threw me the fuck off,
        # returned only tar_file
        # https://docs.python.org/3/library/os.path.html#os.path.join
        #   "If a segment is an absolute path (which on Windows requires both a drive and a root), then 
        # all previous segments are ignored and joining continues from the absolute path segment."
        # So it returned tar_file only, fuuuuuuuuu
        # So since we might meet demux.tarFilesToTransferList elsewhere, i am stripping here the absolute path
        # and allowing the tar files to still remain in absolute format
        basenamed_tar_file = os.path.basename( tar_file )
        demux.absoluteFilesToTransferList[ tar_file ] = {
            'tar_file_local':     os.path.join( local_base,  basenamed_tar_file ),
            'tar_file_remote':    os.path.join( remote_base, basenamed_tar_file ),
            'md5_file_local':     os.path.join( local_base,  basenamed_tar_file ) + constants.MD5_SUFFIX,
            'md5_file_remote':    os.path.join( remote_base, basenamed_tar_file ) + constants.MD5_SUFFIX,
            'sha512_file_local':  os.path.join( local_base,  basenamed_tar_file ) + constants.SHA512_SUFFIX,
            'sha512_file_remote': os.path.join( remote_base, basenamed_tar_file ) + constants.SHA512_SUFFIX,
            # 'upload_to_nird' exists already, we are just adding here the rest of the keys
        }


def _ensure_remote_run_directory_mounted( demux ):
    """
    Ensure the remote run directory exists on a locally mounted sshfs path.
    """
    remote_absolute_dir_path = os.path.join(demux.nird_base_upload_path, demux.RunID)
    mount_found = False
    # Verify that the path is on an sshfs filesystem
    for partition in psutil.disk_partitions( all = True ):
        if partition.fstype == 'fuse.sshfs':
            mountpoint_real = os.path.realpath( partition.mountpoint )
            if remote_absolute_dir_path.startswith( mountpoint_real.rstrip( "/" ) + "/"):  # remove any trailing slash (/mnt/x/////) then add exactly one '/'
                mount_found = True                                                         # back so the prefix match behaves consistently whether the mountpoint was /mnt/x or /mnt/x/.
                break  # loop until first match, then abort

    if not mount_found:
        message =  f"RuntimeError: base path {demux.nird_base_upload_path} not found in mounted filesystems. Aborting."
        demuxLogger.critical( message )
        raise RuntimeError( message )

    try:
        os.mkdir(remote_absolute_dir_path)
    except FileExistsError:
        message = f"RuntimeError: {remote_absolute_dir_path} already exists.\nIs this a repeat upload? If yes, delete/move the existing remote directory and try again."
        demuxLogger.critical( message )
        raise RuntimeError( message )
    except FileNotFoundError:
        message = f"RuntimeError: Cannot create {remote_absolute_dir_path} because its parent directory ({os.path.dirname(remote_absolute_dir_path)}) does not exist on the mounted filesystem."
        demuxLogger.critical( message )
        raise RuntimeError( message)



def _ensure_remote_run_directory( demux ):
    """
    Dispatch to the correct remote-directory preparation method
    based on NIRD access mode.
    """
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: checking if remote directrory exists started\n", color="green", attrs=["bold"] ) )

    if constants.NIRD_MODE_SSH == demux.nird_access_mode:
        _ensure_remote_run_directory_ssh( demux )

    elif constants.NIRD_MODE_SSH_2FA == demux.nird_access_mode:
        # this used to be named _ensure_remote_run_directory_ssh_2fa, but got refactored
        # down to credentials logic detected at run time. I am leaving the switch here for
        # verbocity, and to match the 3case we got for selecting a run mode.
        _ensure_remote_run_directory_ssh( demux )

    elif constants.NIRD_MODE_MOUNTED == demux.nird_access_mode:
        _ensure_remote_run_directory_mounted( demux )

    else:
        message = f"Unknown NIRD access mode: {demux.nird_access_mode}"
        demuxLogger.critical( message )
        raise RuntimeError( message )

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Preparing files for archiving to NIRD finished\n", color="red", attrs=["bold"] ) )




########################################################################
# deliver_files_to_NIRD
########################################################################

def deliver_files_to_NIRD( demux ):
    """
    Make connection to NIRD and upload the data
    # the idea is to to 
    # 1. check status of local tar files in demux.tarFilesToTransferList
    # 2. check if the remore the remote directory exists
    # 3.    create if not
    # 4. take each of the files in demux.tarFilesToTransferList and upload them
    #   4.1 in parallel
    # 5. check the remote sha512 and see if it matches local.
    # 6. report upload exit status

    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Preparing files for archiving to NIRD started\n", color="green", attrs=["bold"] ) )

    _setup_ssh_connection( demux )          # setup the ssh connection details
    _build_absolute_paths( demux )          # creates the demux absoluteFilesToTransferList dictonary with the absolute paths of all files involved
    _verify_local_files( demux )            # verify the local files exist before attempting to transfer them
    _ensure_remote_run_directory( demux )   # make sure demux.nird_base_upload_path/demux.RunID exists
    _upload_files_to_nird( demux )          # send the demux object to a dedicated method and it will decide what mode of copying and type of upload it will use

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Preparing files for archiving to NIRD finished\n", color="red", attrs=["bold"] ) )
