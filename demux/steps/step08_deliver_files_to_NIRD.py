import hashlib
import json
import os
import paramiko
import psutil
import shlex
import shutil
import socket
import subprocess
import sys
import termcolor
import urllib.request

from typing import Tuple

from paramiko import SSHClient, SSHConfig, AutoAddPolicy, RejectPolicy
from paramiko.ssh_exception import AuthenticationException
from scp import SCPClient

from concurrent.futures import ThreadPoolExecutor

from demux.config  import constants
from demux.loggers import demuxLogger, demuxFailureLogger

def _get_login_credentials_via_bw_cli( demux ) -> Tuple[ str, str, str ]:
    """
    Fetch username, password, and TOTP via bw CLI.
    Returns (username, password, totp) as strings.
    """

    # no need to check again if constants.BITWARDEN_CLI_PATH exists, again
    username_process = subprocess.run( [ constants.BITWARDEN_CLI_PATH, "get", "username", demux.nird_upload_host ], check=True, capture_output=True, text=True )
    password_process = subprocess.run( [ constants.BITWARDEN_CLI_PATH, "get", "password", demux.nird_upload_host ], check=True, capture_output=True, text=True )
    totp_process     = subprocess.run( [ constants.BITWARDEN_CLI_PATH, "get", "totp",     demux.nird_upload_host ], check=True, capture_output=True, text=True )

    username = username_process.stdout.strip( )
    password = password_process.stdout.strip( )
    totp     = totp_process.stdout.strip( )

    return ( username, password, totp )


def _get_login_credentials_via_api( demux ) -> Tuple[ str, str, str ]:
    """
    Fetch username, password, and TOTP via bw serve (localhost HTTP API).
    Returns (username, password, totp) as strings.
    """
    username = ""
    password = ""
    totp     = ""

    with urllib.request.urlopen( f"{demux.bw_baseurl}/object/username/{demux.nird_upload_host}", timeout=1 ) as r:
        username = json.load( r )[ "data" ][ "data" ]
    with urllib.request.urlopen( f"{demux.bw_baseurl}/object/password/{demux.nird_upload_host}", timeout=1 ) as r:
        password = json.load( r )[ "data" ][ "data" ]
    with urllib.request.urlopen( f"{demux.bw_baseurl}/object/totp/{demux.nird_upload_host}",     timeout=1 ) as r:
        totp     = json.load( r )[ "data" ][ "data" ]

    return ( username, password, totp )

def _probe_bw_api_state( demux ) -> Tuple[ bool, bool ]:
    """
    Probe the Bitwarden bw-serve HTTP API.

    Performs a low-level socket connect to determine whether the bw-serve service
    is running, and if reachable, queries /status to determine whether the vault
    is unlocked.

    Returns:
        (port_open: bool, vault_unlocked: bool)

    Raises:
        Exception only on unexpected internal errors (not for normal "service down"
        or "vault locked" states).
    """
    port_open      = False
    vault_unlocked = False

    try:
        socket.create_connection( ( demux.bw_localhost, demux.bw_port ), timeout = 1 ).close( )
        port_open = True
    except Exception:
        # port_open = False is already set
        message = f"Cannot connect to the bw-serve.service socket {demux.bw_port} on {demux.bw_localhost}. Use\n"
        message += termcolor.colored( "    systemctl --user status bw-serve.service\n", color="cyan", attrs=["bold"] )
        message += "as the seqtech user to see if it is running.\n"
        message += "Failing back to the command line BitWarden client."
        demuxLogger.critical( message )

    else:
        try:
            # for more details on the API: https://bitwarden.com/help/vault-management-api/
            with urllib.request.urlopen( f"{demux.bw_baseurl}/status", timeout = 1 ) as r:
                vault_unlocked = json.load( r )[ "data"][ "template" ][ "status" ] == "unlocked" # assigns true to vault_unlocked, if unlocked.
        except Exception:
            vault_unlocked = False
            unlock_vault_cmd = "    /usr/local/bin/unlock_vault.sh"
            unlock_vault_cmd += termcolor.colored(curl_cmd, color="cyan", attrs=["bold"])
            message += "Cannot connect to the bw serve vault. Vault is locked. Use\n"
            message += unlock_vault_cmd
            message += "on the command line to unlock."
            demuxLogger.critical( message )
            raise Exception( message )

    return ( port_open, vault_unlocked )


def _probe_bw_cli_state( demux ) -> bool:
    """
    Probe the Bitwarden command-line client state.

    Verifies that the bw CLI is available and determines whether the local
    Bitwarden vault is unlocked for the current user context.

    Returns:
        True if the CLI exists and the vault is unlocked.
        False if the CLI exists but the vault is locked.

    Raises:
        Exception only on unexpected errors (e.g. bw binary present but unusable).
    """

    if not os.access( constants.BITWARDEN_CLI_PATH, os.X_OK ):
        message = f"Bitwarden CLI exists but is not executable: {constants.BITWARDEN_CLI_PATH}"
        demuxLogger.critical(message)
        raise PermissionError(message)

    cli_state_process = subprocess.run( [ constants.BITWARDEN_CLI_PATH, "status" ], check=True, capture_output=True, text=True )

    try:
        status = json.loads( cli_state_process.stdout ).get( "status", "" )
    except json.JSONDecodeError as error:
        message = f"Failed to parse Bitwarden CLI JSON output. Raw output was: {cli_state_process.stdout!r}"
        demuxLogger.critical( message )
        raise ValueError( message ) from error

    if status == "unauthenticated":
        unauthenticated_vault_cmd = termcolor.colored( "    /usr/local/bin/bw login\n", color="cyan", attrs=["bold"] )
        message = f"{constants.BITWARDEN_CLI_PATH} reports that the vault user is not authenticated. Use\n"
        message += unauthenticated_vault_cmd
        message += "on the command line to authenticate.\n"
        demuxLogger.critical( message )
        raise Exception( message )

    if status == "locked":
        unlock_vault_cmd = termcolor.colored( "    /usr/local/bin/bw unlock\n", color="cyan", attrs=["bold"] )
        message = f"{constants.BITWARDEN_CLI_PATH} reports that the vault is locked. Use\n"
        message += unlock_vault_cmd
        message += "on the command line to unlock.\n"
        demuxLogger.critical( message )
        raise Exception( message )


    return status == "unlocked"


def _get_login_credentials( demux ) -> Tuple[ str, str, str ]:
    """
    Get the logging credentials from bitwarden
        if 'bw serve' exists on port 8087 on localhost, it gets
            curl --silent --no-progress-meter -w '\n' \
                http://127.0.0.1:8087/object/username/login.nird.sigma2.no \
                http://127.0.0.1:8087/object/password/login.nird.sigma2.no \
                http://127.0.0.1:8087/object/totp/login.nird.sigma2.no | jq -r '.data.data'
        failing that, it falls back to the command line, which is much much slower: for each
            process, we got to decrypt the vault. which takes 12-14 seconds. So if we got
            fifty tar files to upload, this will take a minute and a half just to authenticate.
    
        So, we will use bw serve as a user systemd process and make curl calls to that, as it
        decrypts the vault once and if that fails, we will go back ot the command line client.
    """

    port_open      = False
    vault_unlocked = False

    port_open, vault_unlocked = _probe_bw_api_state( demux )

    # Tri-state check: make sure if the port is not open or if the binary does not exist
    #   we return an error.
    if port_open and vault_unlocked:
        return _get_login_credentials_via_api( demux )
    elif os.path.isfile( constants.BITWARDEN_CLI_PATH ) and _probe_bw_cli_state( demux ) :
        return _get_login_credentials_via_bw_cli( demux )
    else:
        message = f"bw-serve.service is not running and the command line client does not exist or is locked. Contact your system administrator."
        demuxLogger.critical( message)
        raise FileNotFoundError( message )


def _upload_and_verify_file_via_ssh_2fa( demux, tar_file ):     # worker per file, tar_file is in absolute path format
    """
    Upload and verify a single local tar file to the NIRD absolute upload path using a new SSH transport each time, via 2FA
    """

    # get from bitwarden, using demux.hostname:
    #   * username
    #   * password
    #   * 2fa
    #   store all in dictionary
    # connect using socket
    # instanciate transport
    #   present username, 2FA
    #   present username, password
    # instanciate ssh client using transport
    #   exec /usr/bin/hostname
    # 50 times

    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Uploading file {tar_file} via ssh 2FA started\n", color="green", attrs=["bold"] ) )


    username, password, totp = _get_login_credentials( demux )

    print( f"username: {username} | password: {password} | TOTP: {totp}\n" )


    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Uploading file {tar_file} via ssh 2FA finished\n", color="red", attrs=["bold"] ) )

    # sys.exit( f"{sys._getframe( ).f_code.co_name} is not yet implemented" )


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

    for entry in demux.absoluteFilesToTransferList.values( ):
        if not os.path.exists( entry[ 'tar_file_local' ] ):
            demuxLogger.critical( f"File {entry[ 'tar_file_local' ]} does not exist. Check for the existanse of the file and try again." )
            raise RuntimeError( )
        if not os.path.exists( entry[ 'md5_file_local' ] ):
            demuxLogger.critical( f"File {entry[ 'md5_file_local' ]} does not exist. Check for the file and try again." )
            raise RuntimeError( )
        if not os.path.exists( entry[ 'sha512_file_local' ] ):
            demuxLogger.critical( f"File {entry[ 'sha512_file_local' ]} does not exist. Check for the file and try again." )
            raise RuntimeError( )


def _setup_ssh_connection( demux ):
    """
    Parse ~/.ssh/config and initializes appropriate demux fields using the ssh config entry for the upload host.
    If missing, method falls back to demux defaults.
    """
    config_path = os.path.expanduser( "~/.ssh/config" ) # this needs to be infered from environment somehow https://github.com/NorwegianVeterinaryInstitute/DemultiplexRawSequenceData/issues/138
    host_config = { }

    if os.path.exists( config_path ):
        with open( config_path ) as handle:
            ssh_config = SSHConfig( )
            ssh_config.parse( handle )
        host_config = ssh_config.lookup( demux.nird_upload_host )

    # more stuff that can be thrown into initilization of demux
    demux.hostname = host_config.get( "hostname", demux.nird_upload_host )
    demux.username = host_config.get( "user", demux.nird_username )
    demux.key_file = host_config.get( "identityfile", [ demux.nird_key_filename ] )[0]  # must have arrays, incase there are more than 1 identity files. therefore we encase the default key filename in an array, itself
    demux.port     = int( host_config.get( "port", demux.nird_scp_port ) )


def _select_nird_base_upload_path( demux ):
    """
    Select which base upload path to use depending on access mode (sshfs vs SSH). Central place to extend path-selection rules; if path logic needs augmentation, add it here.
    """
    upload_path = ""
    if constants.NIRD_MODE_MOUNTED == demux.nird_access_mode:
        upload_path = demux.nird_base_upload_path_local
    elif constants.NIRD_MODE_SSH == demux.nird_access_mode:
        upload_path = demux.nird_base_upload_path_ssh

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


def _open_transport_and_validate_hostkey( demux ) -> paramiko.Transport:
    """
    Open a new SSH transport to the remote host and strictly validate its host key
    against the local known_hosts database.

    Establishes the TCP/SSH session, retrieves the server host key and rejects the
    connection if the key is missing or does not match the known_hosts entry.
    Returns an unauthenticated SSH Transport with a verified host key; no user
    authentication has been performed.
    """

    transport = paramiko.Transport( ( demux.hostname, demux.port ) )
    transport.start_client( timeout = 5 )

    # Validate host key against known_hosts (RejectPolicy equivalent)
    host_keys = paramiko.HostKeys( )
    known_hosts_path = os.path.expanduser( "~/.ssh/known_hosts" )
    if os.path.exists( known_hosts_path ):
        host_keys.load( known_hosts_path )

    remote_key = transport.get_remote_server_key( )

    host_key_entry = host_keys.lookup( demux.hostname )
    if ( host_key_entry is None ) and ( demux.port != 22 ):
        host_key_entry = host_keys.lookup( f"[{demux.hostname}]:{demux.port}" )

    if host_key_entry is None:
        message = f"RuntimeError: Host key for {demux.hostname}:{demux.port} not found in {known_hosts_path}. Refusing connection."
        demuxLogger.critical( message )
        raise RuntimeError( message )

    accepted = False
    for key_type, known_key in host_key_entry.items( ):
        if ( key_type == remote_key.get_name( ) ) and ( known_key == remote_key ):
            accepted = True
            break

    if not accepted:
        message = f"RuntimeError: Host key mismatch for {demux.hostname}:{demux.port}. Refusing connection."
        demuxLogger.critical( message )
        raise RuntimeError( message )

    return transport


def _auth_transport_2fa( demux, transport: paramiko.Transport ) -> None:
    """
    Authenticate an existing SSH transport using keyboard-interactive 2FA.

    Retrieves username, password and TOTP credentials and performs interactive
    authentication on the provided transport. Mutates the transport in place.

    Raises:
        AuthenticationException: if 2FA authentication fails or the transport
        remains unauthenticated after the interactive exchange.
    """

    username, password, totp = _get_login_credentials( demux )

    def _kbdint_handler( title, instructions, prompt_list ):
        responses = [ ]
        for prompt_text, echo in prompt_list:
            prompt_lower = prompt_text.lower( )
            if ( "totp" in prompt_lower ) or ( "token" in prompt_lower ) or ( "verification" in prompt_lower ) or ( "code" in prompt_lower ):
                responses.append( totp )
            elif "password" in prompt_lower:
                responses.append( password )
            else:
                responses.append( "" )
        return responses

    transport.auth_interactive( username = username, handler = _kbdint_handler )

    if not transport.is_authenticated( ):
        message = f"RuntimeError: SSH 2FA authentication failed for {username}@{demux.hostname}:{demux.port} ."
        demuxLogger.critical( message )
        raise AuthenticationException( message )


def _ensure_remote_dir_via_client( demux, ssh_client, remote_absolute_dir_path ) -> None:
    """
    Ensure the remote run directory exists using an already-authenticated SSH client.

    Checks for the existence of the target directory on the remote host and creates it
    if missing. Aborts if the directory already exists or if creation fails.

    Raises:
        SSHException: if the directory already exists or if remote creation fails
        due to permission, missing parent or other remote filesystem errors.
    """

    stdin, stdout, stderr    = ssh_client.exec_command( f"TERM=xterm /usr/bin/test -d -- {shlex.quote( remote_absolute_dir_path )}" )
    exit_status = stdout.channel.recv_exit_status( )

    if exit_status != 0:
        stdin, stdout, stderr = ssh_client.exec_command( f"TERM=xterm /usr/bin/mkdir {shlex.quote( remote_absolute_dir_path )}" )
        mkdir_status = stdout.channel.recv_exit_status( )
        if mkdir_status != 0:
            message = f"Directory creation error: Cannot create {demux.hostname}:{remote_absolute_dir_path} even after original check.\n"
            message += "Consult the remote end and try to create the directory manually to see what error you get, could be\n"
            message += "that parent changed permission or was moved.\n"
            message += f"Remote error: {stderr.read().decode().strip()}"
            demuxLogger.critical( message )
            raise SSHException(message)
    else:
        message = f"Directory creation error: {demux.hostname}:{remote_absolute_dir_path} already exists.\n"
        message += f"Is this a repeat upload? If yes, delete/move the existing remote directory and try again."
        demuxLogger.critical( message )
        raise SSHException( message )


def _ensure_remote_run_directory_ssh_2fa( demux ):
    """
    Ensure the remote run directory exists using SSH with 2FA authentication.

    Establishes an authenticated SSH session, verifies the existence of the
    remote run directory and creates it if missing.

    Raises:
        AuthenticationException: 2FA or credential failure.
        SSHException: remote command execution failure
        RuntimeException: everyting else that needs to percolate
    """

    transport = None
    ssh_client = None

    try:
        transport = _open_transport_and_validate_hostkey( demux )
        _auth_transport_2fa( demux, transport )

        ssh_client = SSHClient( )
        ssh_client._transport = transport
        remote_absolute_dir_path = os.path.join( demux.nird_base_upload_path, demux.RunID )

        _ensure_remote_dir_via_client( demux, ssh_client, remote_absolute_dir_path )

    finally: # we enclosed the whole thing in a try/finally so we can close the client and the transport
        if ssh_client is not None:
            ssh_client.close( )
        elif transport is not None:
            transport.close( )


def _ensure_remote_run_directory_ssh( demux ):
    """
    Ensure the remote run directory exists by opening a fresh SSH connection, validating host keys, creating the directory if missing and aborting if it already exists.
    """

    ssh_client = SSHClient( )
    ssh_client.load_system_host_keys( )
    # Check if the key already exists in the known_hosts 
    #   else reject the connection.

    ssh_client.set_missing_host_key_policy( RejectPolicy( ) )      # do not accept host keys that are not already in place
    ssh_client.connect( hostname = demux.hostname, port = demux.port, username = demux.username, key_filename = demux.key_file )

    try:
        # check if the '/nird/projects/NS9305K/SEQ-TECH/data_delivery' + runID directory exists
        remote_absolute_dir_path = os.path.join( demux.nird_base_upload_path, demux.RunID ) 
        stdin, stdout, stderr    = ssh_client.exec_command( f"TERM=xterm /usr/bin/test -d -- {shlex.quote( remote_absolute_dir_path )}" ) # we are not really doing anything with the stdin, stdout, stderr but keep them anyway

        if stdout.channel.recv_exit_status( ) != 0 : # directory does not exist, wwe can make it
            ssh_client.exec_command( f'TERM=xterm /usr/bin/mkdir -p {shlex.quote( remote_absolute_dir_path )}' )
        else:
            message = f"RuntimeError: {demux.hostname}:{remote_absolute_dir_path} already exists."
            message += f"Is this a repeat upload? If yes, delete/move the existing remote directory and try again."
            demuxLogger.critical( message )
            raise RuntimeError( message )
    finally:
        ssh_client.close() # close for the commands we will open the same connection in the loop, so we can parallelize the  connections.


def _ensure_remote_run_directory( demux ):
    """
    Dispatch to the correct remote-directory preparation method
    based on NIRD access mode.
    """
    if constants.NIRD_MODE_SSH == demux.nird_access_mode:
        _ensure_remote_run_directory_ssh( demux )

    elif constants.NIRD_MODE_SSH_2FA == demux.nird_access_mode:
        _ensure_remote_run_directory_ssh_2fa( demux )

    elif constants.NIRD_MODE_MOUNTED == demux.nird_access_mode:
        _ensure_remote_run_directory_mounted( demux )

    else:
        demuxLogger.critical(f"Unknown NIRD access mode: {demux.nird_access_mode}")
        raise RuntimeError()



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
