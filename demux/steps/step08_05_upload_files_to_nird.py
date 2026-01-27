import scp
import threading

from paramiko               import SSHClient, SSHConfig, AutoAddPolicy, RejectPolicy, Transport, SSHException
from paramiko.ssh_exception import AuthenticationException



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


def progress(filename, size, sent):
    """
    Progress callback for SCP transfers.

    Args:
        filename: Name of the file being transferred.
        size: Total file size in bytes.
        sent: Bytes sent so far.

    Prints percentage completion to stdout.
    """
    sys.stdout.write("%s progress: %.2f%%   \r" % ( filename, float( sent )/float( size )*100 ) )

def progress4(filename, size, sent, peername):
    """
    Extended progress callback including remote peer info.

    Args:
        filename: Name of the file being transferred.
        size: Total file size in bytes.
        sent: Bytes sent so far.
        peername: (host, port) tuple of the remote endpoint.

    Prints percentage completion with peer address to stdout.
    """
    sys.stdout.write("(%s:%s) %s progress: %.2f%%   \r" % ( peername[ 0 ], peername[ 1 ], filename, float( sent )/float( size )*100 ) )

def _upload_tar_via_scp( demux, transport: paramiko.Transport, file_entry ) -> None:
    """
    @in_use by _upload_and_verify_file_via_ssh_2fa
    Upload a single local tar file to its remote path via an existing SCP session.

    Asserts that the remote target does not already exist, then performs a single
    SCP put operation. Does not perform verification by hashing the uploaded files.

    Returns None on success.

    Raises RuntimeError if remote file exists.
    """

    demuxLogger.info( f"Transferring: {file_entry[ 'tar_file_local' ]}" )

    test_command: str              = f"/usr/bin/test -f -- {shlex.quote( file_entry[ 'tar_file_remote' ] )}"
    test_channel: paramiko.Channel = transport.open_session( )
    test_channel.exec_command( test_command )
    test_stderr                    = test_channel.makefile_stderr( "r" ).read( )
    test_status: int               = test_channel.recv_exit_status( )    

    if test_status == 0:
        message  = f"RuntimeError: Remote file already exists: {demux.hostname}:{file_entry[ 'tar_file_remote' ]}"
        message += "Refusing to overwrite. Delete/move remote file first and then try to upload again."
        demuxLogger.critical( message )
        raise RuntimeError( message )

    # scp_client = SCPClient( transport )
    # scp_client = SCPClient( transport, progress = progress )
    scp_client = SCPClient( transport, progress4 = progress4 )

    try: 
        scp_client.put( file_entry[ "tar_file_local" ], file_entry[ "tar_file_remote" ] )
    finally:
        scp_client.close( )



def _upload_and_verify_file_via_ssh( demux, tar_file ):  # worker per file, tar_file is in absolute path format
    """
    @in_use
    @needs_refactor
    @needs_better_docstring
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




def _upload_files_to_nird( demux ):
    """
    @in_use
    @needs_better_docstring
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
