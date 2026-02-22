#

import hashlib
import os
import paramiko
import shlex
import shutil
import socket
import sys
import threading

from concurrent.futures   import ThreadPoolExecutor, wait, ALL_COMPLETED
from collections.abc      import ValuesView
from scp                  import SCPClient

from demux.util.bitwarden import _get_login_credentials
from demux.config         import constants
from demux.loggers        import demuxLogger, demuxFailureLogger


import scp


def _verify_remote_hashes_against_local_files( demux, file_entry: dict ) -> None:
    """
    Verify remote file integrity by computing remote MD5 and SHA-512 hashes and
    comparing them against the corresponding local checksum files.

    Calculates hashes on the remote host via SSH and reads local checksum files.

    Returns None on success.

    Raises RuntimeError on remote md5sum/sha512sum failure or on any hash mismatch.
    """
    def _drain_channel( channel: paramiko.Channel, results: dict[ str, tuple[ bytes, bytes, int ] ], key: str ) -> None:
        try:
            stdout_bytes: bytes = channel.makefile( "rb" ).read( )
            stderr_bytes: bytes = channel.makefile_stderr( "rb" ).read( )
            exit_status: int    = channel.recv_exit_status( )
            results[ key ]      = ( stdout_bytes, stderr_bytes, exit_status )
        finally:
            channel.close( )


    entries: dict_values    = demux.absoluteFilesToTransferList.values( )
    current_len: int        = len( file_entry[ 'tar_file_local' ] )
    longest_local_path: int = max( ( len( entry[ 'tar_file_local' ] ) for entry in entries ), default = current_len )

    md5sum_command: str                 = f"/usr/bin/md5sum {shlex.quote( file_entry[ 'tar_file_remote' ] )}"
    sha512sum_command: str              = f"/usr/bin/sha512sum {shlex.quote( file_entry[ 'tar_file_remote' ] )}"

    md5sum_channel: paramiko.Channel    = demux.transport.open_session( )
    sha512sum_channel: paramiko.Channel = demux.transport.open_session( )

    md5sum_channel.exec_command( md5sum_command )
    sha512sum_channel.exec_command( sha512sum_command )

    results: dict[ str, tuple[ bytes, bytes, int ] ] = { }

    # we can devote a core for each process, easily. Cut down on waiting time
    md5_thread: threading.Thread    = threading.Thread( target = _drain_channel, args = ( md5sum_channel, results, "md5" ) )
    sha512_thread: threading.Thread = threading.Thread( target = _drain_channel, args = ( sha512sum_channel, results, "sha512" ) )

    md5_thread.start( )
    sha512_thread.start( )
    md5_thread.join( )
    sha512_thread.join( )

    md5sum_stdout_bytes: bytes
    md5sum_stderr_bytes: bytes
    md5sum_status: int
    md5sum_stdout_bytes, md5sum_stderr_bytes, md5sum_status = results[ "md5" ]

    sha512sum_stdout_bytes: bytes
    sha512sum_stderr_bytes: bytes
    sha512sum_status: int
    sha512sum_stdout_bytes, sha512sum_stderr_bytes, sha512sum_status = results[ "sha512" ]

    if md5sum_status != 0:
        message: str = f"RuntimeError: remote md5sum failed for {file_entry['tar_file_remote']}: {md5sum_stderr_bytes.decode( ).strip( )}"
        demuxLogger.critical( message )
        raise RuntimeError( message )

    if sha512sum_status != 0:
        message: str = f"RuntimeError: remote sha512sum failed for {file_entry['tar_file_remote']}: {sha512sum_stderr_bytes.decode( ).strip( )}"
        demuxLogger.critical( message )
        raise RuntimeError( message )

    md5_file_remote    : str = md5sum_stdout_bytes.decode( ).split( )[ 0 ]
    sha512_file_remote : str = sha512sum_stdout_bytes.decode( ).split( )[ 0 ]

    with open( file_entry[ "md5_file_local" ], "r" ) as handle_md5:
        md5_file_local: str = handle_md5.read( ).split( )[ 0 ]
    with open( file_entry[ "sha512_file_local" ], "r" ) as handle_sha512:
        sha512_file_local: str = handle_sha512.read( ).split( )[ 0 ]

    if md5_file_local != md5_file_remote:
        message: str  = "Error: Local md5 differs from calculated remote md5:\n"
        message += f"LOCAL MD5:  {md5_file_local}  | {file_entry[ 'md5_file_local' ]}\n"
        message += f"REMOTE MD5: {md5_file_remote} | {file_entry[ 'md5_file_remote' ]}\n"
        message += "Please check both files, delete/move as appropriate and try uploading again."
        demuxLogger.critical( message )
        # raise RemoteHashMismatchError( message ) https://github.com/NorwegianVeterinaryInstitute/DemultiplexRawSequenceData/issues/150
        raise RuntimeError( message )

    if sha512_file_local != sha512_file_remote:
        message: str  = "Error: Local sha512 differs from calculated remote sha512:\n"
        message += f"LOCAL SHA512:  {sha512_file_local}  | {file_entry[ 'sha512_file_local' ]}\n"
        message += f"REMOTE SHA512: {sha512_file_remote} | {file_entry[ 'sha512_file_remote' ]}\n"
        message += "Please check both files, delete/move as appropriate and try uploading again."
        demuxLogger.critical( message )
        # raise RemoteHashMismatchError( message ) https://github.com/NorwegianVeterinaryInstitute/DemultiplexRawSequenceData/issues/150
        raise RuntimeError( message )

    demuxLogger.info( f"Done: LOCAL:{file_entry[ 'tar_file_local' ]:<{longest_local_path}} REMOTE:{demux.hostname}:{file_entry[ 'tar_file_remote' ]}" )


def progress(filename, size, sent) -> None:
    """
    Progress callback for SCP transfers.

    Args:
        filename: Name of the file being transferred.
        size: Total file size in bytes.
        sent: Bytes sent so far.

    Prints percentage completion to stdout.
    """
    sys.stdout.write("%s progress: %.2f%%   \r" % ( filename, float( sent )/float( size )*100 ) )


def _resolve_hostname(ip_address: str) -> str:
    """
    Resolve an IP address to a hostname once and cache the result
    for the lifetime of the process.

    Args:
        ip_address: IPv4 or IPv6 address string.

    Returns:
        Hostname from reverse DNS, or the original IP if lookup fails.
    """
    if not hasattr( _resolve_hostname, "cache" ):
        _resolve_hostname.cache: dict[ str, str ] = { }

    cache: dict[ str, str ] = _resolve_hostname.cache

    if ip_address not in cache:
        try:
            hostname, _, _  = socket.gethostbyaddr( ip_address )
        except socket.herror:
            hostname        = ip_address
        cache[ ip_address ] = hostname

    return cache[ip_address]

def progress4(filename, size, sent, peername) -> None:
    """
    Extended progress callback including remote peer info.

    Args:
        filename: Name of the file being transferred.
        size: Total file size in bytes.
        sent: Bytes sent so far.
        peername: (host, port) tuple of the remote endpoint.

    Prints percentage completion with peer address to stdout.
    """
    hostname: str =  _resolve_hostname( peername[ 0 ] )
    sys.stdout.write("(%s:%s) %s progress: %.2f%%   \r" % ( hostname, peername[ 1 ], filename, float( sent )/float( size )*100 ) )

def _upload_tar_via_scp( demux, file_entry: dict ) -> None:
    """
    Upload a single local tar file to its remote path via an existing SCP session.

    Asserts that the remote target does not already exist, then performs a single
    SCP put operation. Does not perform verification by hashing the uploaded files.

    Returns None on success.

    Raises RuntimeError if remote file exists or if the files passed are not in absolute format
    """
 
    for key in ( "tar_file_remote", "md5_file_remote", "sha512_file_remote" ):
        if not os.path.isabs( file_entry[ key ] ):
            raise RuntimeError( f"Remote path is not absolute: {file_entry[ key ]}" )

    tar_file: str = file_entry[ 'tar_file_local' ]
    demuxLogger.info( f"Transferring: {tar_file}" ) # mention which local tar file we are uploading

    # Find the longest string in demux.absoluteFilesToTransferList and tabulate for that
    items = demux.absoluteFilesToTransferList.values( )
    current_len = len( demux.absoluteFilesToTransferList[tar_file][ 'tar_file_local' ] )
    longest_local_path = max( (len( entry[ 'tar_file_local' ] ) for entry in items ), default = current_len )

    try:
        sftp_client: paramiko.SFTPClient = paramiko.SFTPClient.from_transport( demux.transport )
        try:
            sftp_client.stat( file_entry[ "tar_file_remote" ] )
        except FileNotFoundError:
            pass
        else:
            message = f"RuntimeError: Remote file already exists: {demux.hostname}:{file_entry[ 'tar_file_remote' ]}"
            message += "Refusing to overwrite. Delete/move remote file first and then try to upload again."
            demuxLogger.critical( message )
            raise RuntimeError( message)
    finally:
        try:
            sftp_client.close( )
        except Exception:
            pass

    # scp_client = SCPClient( transport )
    # scp_client = SCPClient( transport, progress = progress )
    scp_client = SCPClient( demux.transport, progress4 = progress4 )

    try: 
        scp_client.put( file_entry[ "tar_file_local" ],    file_entry[ "tar_file_remote" ] )
        scp_client.put( file_entry[ "md5_file_local" ],    file_entry[ "md5_file_remote" ] )
        scp_client.put( file_entry[ "sha512_file_local" ], file_entry[ "sha512_file_remote" ] )
    except scp.SCPException as error:
        if "Disk quota exceeded" in str( error ) or "No space left on device" in str( error ):
            raise RuntimeError( f"Remote disk quota exceeded on {demux.hostname}" ) from error
        raise
    finally:
        scp_client.close( )

    demuxLogger.info( f"Done: LOCAL:{tar_file:<{longest_local_path}} REMOTE:{demux.hostname}:{tar_file}" )




def _upload_and_verify_file_via_ssh( demux, tar_file: str ) -> None:
    """
    Upload a single local tar file over an already-initialized, authenticated SSH Transport
    stored in 'demux' then verify remote integrity using MD5 and SHA-512.

    The Transport is shared, persistent, and reused across operations; only per-command
    SSH channels are opened and closed.

    Raises RuntimeError on SCP failure, remote hash computation failure or hash mismatch.
    """

    tar_file_entry = demux.absoluteFilesToTransferList[ tar_file ]

    _upload_tar_via_scp( demux, tar_file_entry )
    _verify_remote_hashes_against_local_files( demux, tar_file_entry  )




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


        # read and calculate all hashfiles
        with open( file_info[ 'md5_file_local' ],  READ_ONLY_TEXT   ) as md5_handle_local:
            md5_file_local     = md5_handle_local.read( ).split( )[ 0 ]
        with open(file_info[ 'sha512_file_local' ], READ_ONLY_TEXT    ) as sha512_handle_local:
            sha512_file_local  = sha512_handle_local.read().split( )[ 0 ]
        with open( file_info[ 'tar_file_remote' ], READ_ONLY_BINARY ) as md5_handle_remote:
            md5_file_remote    = hashlib.file_digest( md5_handle_remote, hashlib.md5 ).hexdigest( )
        with open( file_info[ 'tar_file_remote' ], READ_ONLY_BINARY ) as sha512_handle_remote:
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




def _upload_files_to_nird( demux ) -> None:
    """
    Dispatch tar uploads to NIRD using the access mode defined on `demux`
    (SSH, SSH+2FA, or mounted sshfs) and execute transfers either serially
    or via a ThreadPoolExecutor.

    Serial mode executes uploads inline and fails immediately on error.
    Parallel mode submits one future per tar, blocks until ALL_COMPLETE,
    collects per-tar exceptions (including EOFError from transport drops),
    and raises a single RuntimeError after synchronization if any upload failed.

    """

    if len( demux.tarFilesToTransferList ) == 0:
        message = f"Length of demux.tarFilesToTransferList is zero while copying." # check if we got passed garbage
        demuxLogger.critical( message )
        raise RuntimeError( message )

    # choose upload implementation
    if constants.NIRD_MODE_SSH       == demux.nird_access_mode:
        upload_func = _upload_and_verify_file_via_ssh
    elif constants.NIRD_MODE_SSH_2FA == demux.nird_access_mode:
        upload_func = _upload_and_verify_file_via_ssh
    elif constants.NIRD_MODE_MOUNTED == demux.nird_access_mode:
        upload_func = _upload_and_verify_file_via_local_sshfs_mount
    else:
        message = f"Unknown NIRD access mode: {demux.nird_access_mode}"
        demuxLogger.critical( message )
        raise RuntimeError( message )

    # serial / parallel copying switching
    if constants.SERIAL_COPYING == demux.nird_copy_mode:
        demuxLogger.info( "Serial copying enabled." )
        for tar_file in demux.tarFilesToTransferList:
            upload_func( demux, tar_file )

    elif constants.PARALLEL_COPYING == demux.nird_copy_mode:
        demuxLogger.info( "Parallel copying enabled." )

        future_to_tar: dict[ Any, Any ] = { }

        with ThreadPoolExecutor( max_workers = demux.max_workers ) as pool:
            for tar_file in demux.tarFilesToTransferList:
                future: Any = pool.submit( upload_func, demux, tar_file )
                future_to_tar[ future ] = tar_file

            done, not_done = wait( list( future_to_tar.keys( ) ), return_when = ALL_COMPLETED ) # we are blocking till all files are uploaded
            errors: list[ BaseException ] = [ ]

            for future in done:
                tar_file: Any = future_to_tar[ future ]
                try:
                    future.result( )
                except EOFError as exception:
                    demuxLogger.critical( f"Upload failed (EOFError): {tar_file} {exception!r}" )
                    errors.append( exception )
                except BaseException as exception:
                    demuxLogger.critical( f"Upload failed: {tar_file} {exception!r}" )
                    errors.append( exception )

        if errors:
            raise RuntimeError( f"{len(errors)} upload(s) failed; first={errors[0]!r}" )
    else:
        message: str = f"Unknown NIRD copy mode: {demux.nird_copy_mode}"
        demuxLogger.critical( message )
        raise RuntimeError( message )
