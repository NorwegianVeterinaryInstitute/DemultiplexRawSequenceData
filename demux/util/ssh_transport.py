# all ssh transport related stuff

import os
import paramiko
import shlex

from paramiko               import SSHClient, SSHConfig, AutoAddPolicy, RejectPolicy, Transport, SSHException
from paramiko.ssh_exception import AuthenticationException
from scp                    import SCPClient

from demux.util.bitwarden  import _get_login_credentials
from demux.config          import constants
from demux.loggers         import demuxLogger, demuxFailureLogger


def _setup_ssh_connection( demux ) -> None:
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


def _open_transport_and_validate_hostkey( demux ) -> Transport:
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
            if  ( "One-time password".lower( ) in prompt_lower ) or ( "totp" in prompt_lower ) or ( "token" in prompt_lower ) or ( "verification" in prompt_lower ) or ( "code" in prompt_lower ) :
                responses.append( totp )
            elif "password" in prompt_lower:
                responses.append( password )
            else:
                responses.append( "" )
        return responses

    transport.auth_interactive( username = username, handler = _kbdint_handler )

    if not transport.is_authenticated( ):
        message = f"AuthenticationException: SSH 2FA authentication failed for {username}@{demux.hostname}:{demux.port} ."
        demuxLogger.critical( message )
        # treat any raised AuthenticationException from auth_interactive() as failure
        # no other reliable signal exists that NIRD changed the TOTP token prompt
        raise AuthenticationException( message )

def _auth_transport( demux, transport: paramiko.Transport ) -> None:
    """
    Authenticate an existing SSH transport using ssh keys or keyboard-interactive 2FA.

    Selects the appropriate mode via the demux.nird_access_mode user configuration

    Raises:
        RuntimeError: when the access mode is misconfigured
    """

    if constants.NIRD_MODE_SSH       == demux.nird_access_mode:
        _auth_transport_ssh_keys( demux, transport )
    elif constants.NIRD_MODE_SSH_2FA == demux.nird_access_mode:
        _auth_transport_2fa( demux, transport )
    elif constants.NIRD_MODE_MOUNTED == demux.nird_access_mode:
        pass # nothing to authenticate here, the sysadmin has already done that part manually or via systemd
    else:
        message = f"RuntimeError: Unknown NIRD access mode: {demux.nird_access_mode}" # https://github.com/NorwegianVeterinaryInstitute/DemultiplexRawSequenceData/issues/138
        demuxLogger.critical( message )
        raise RuntimeError( message )




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
            message = f"Directory creation error: Cannot create {demux.hostname}:{remote_absolute_dir_path} even after original check. "
            message += "Consult the remote end and try to create the directory manually to see what error you get, could be "
            message += "that parent changed permission or was moved.\n"
            message += f"SSHException: {stderr.read( ).decode( ).strip( )}"
            demuxLogger.critical( message )
            raise SSHException(message)
    else:
        message = f"Directory creation error: {demux.hostname}:{remote_absolute_dir_path} already exists.\n"
        message += f"Is this a repeat upload? If yes, delete/move the existing remote directory and try again."
        demuxLogger.critical( message )
        raise SSHException( message )


def _ensure_remote_run_directory_ssh( demux ) -> None:
    """
    Ensure the remote RunID upload directory exists, using SSH key authentication or 2FA.
    Credentials are chosen via user configuration.

    Opens a fresh SSH connection with strict known_hosts checking, validates that
    demux.nird_base_upload_path is non-empty then checks for the remote
    directory (base path + RunID). Creates it if missing; aborts if it already
    exists. Closes the SSH connection unconditionally.

    Raises:
        AuthenticationException: 2FA or credential failure.
        SSHException: remote command execution failure (directory existing)
        RuntimeException: everyting else that needs to percolate
        ValueError if demux.nird_base_upload_path is empty

    Returns:
        None
    """

    transport = None
    ssh_client = None

    # check if the '/nird/projects/NS9305K/SEQ-TECH/data_delivery' directory exists
    if not demux.nird_base_upload_path:
        message = f"ValueError: demux.nird_base_upload_path is empty: ({demux.nird_base_upload_path}). Refusing to continue, as any transfer will "
        message += "end up in the home directory of the uploading user."
        raise ValueError( message )
    
    remote_absolute_dir_path = os.path.join( demux.nird_base_upload_path, demux.RunID ) 

    try:
        transport = _open_transport_and_validate_hostkey( demux )

        # _auth_transport_2fa( demux, transport ) 
        _auth_transport( demux, transport ) 

        ssh_client = SSHClient( )
        ssh_client._transport = transport

        _ensure_remote_dir_via_client( demux, ssh_client, remote_absolute_dir_path )

    finally: # we enclosed the whole thing in a try/finally so we can close the client and the transport
        if ssh_client is not None:
            ssh_client.close( )
        elif transport is not None:
            transport.close( )