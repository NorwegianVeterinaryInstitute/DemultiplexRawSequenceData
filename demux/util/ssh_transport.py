# all ssh transport related stuff

import os
import paramiko
import pprint
import re
import shlex
import socket
import sys
import termcolor

from typing import Any, Dict, List, Optional, Tuple, Mapping

from paramiko               import SSHClient, SSHConfig, AutoAddPolicy, RejectPolicy, Transport, SSHException
from paramiko.ssh_exception import AuthenticationException

from demux.util.bitwarden  import _get_login_credentials
from demux.config          import constants
from demux.loggers         import demuxLogger, demuxFailureLogger


def _verify_ssh_config_policy_for_hop( target_lookup: paramiko.config.SSHConfig ) -> None:
    """
    @in_use by _parse_ssh_config
    Verify that a single SSH hop configuration complies with enforced security
    and simplicity policy.

    Validates required SSH options (host key checking, identity usage, user,
    hostname, known-hosts handling) and rejects unsupported or ambiguous
    configurations. Main design principle is to Keep It Simple.

    Raises:
        ValueError/Keyerror on policy violations

    Returns:
        None on success.
    """

    # Ensure StrictHostKeyChecking is set to yes.
    strict_hostkey_checking = str( target_lookup.get( "stricthostkeychecking" ) ).strip( ).lower( )
    if strict_hostkey_checking != "yes":
        raise ValueError( f"StrictHostKeyChecking must be 'yes' for {target_lookup.get( 'hostname' )}" )

    # Ensure VerifyHostKeyDNS is set to yes
    verify_hostkey_dns = str( target_lookup.get( "verifyhostkeydns" ) ).strip( ).lower( )
    if strict_hostkey_checking != "yes":
        raise ValueError( f"VerifyHostKeyDNS must be 'yes' for {target_lookup.get( 'hostname' )}" )

    # Ensure there is a Hostname key-value
    hostname = ( target_lookup.get( "hostname" ) or "" ).strip( )
    if not hostname:
        raise KeyError( f"Missing HostName for host alias {target_lookup.get( 'hostname' )}" )

    # Ensure we got a User key-value
    username = ( target_lookup.get( "user" ) or "" ).strip( )
    if not username:
        raise ValueError( f"Missing User for host alias {target_lookup.get( 'hostname' )}" )

    # Ensure we got a Port User key-value
    # port_text = str( hop_port or target_lookup.get( "port" ) or "22" ).strip( )
    # try:
    #   port = int( port_text )
    # except ValueError as error:
    #    # from is the only mechanism that allows you to chain the cought exception while allowing
    #    # you to add a custom message
    #    raise ValueError( f"Invalid Port {port_text} for host alias {target_lookup.get( 'hostname )}'" ) from error


    # Ensure we got an IdentityFile key-value and it is unique
    identity_file = target_lookup.get( "identityfile" )
    if isinstance( identity_file, list ):
        if len( identity_file ) > 1:
            raise ValueError( f"IdentityFile must be a single entry for {target_lookup.get( 'hostname' )}, got {len( identity_file )}" )

    # Ensure we are serving only identities stated in ssh_config entry and that we do not spam the host with keys
    identities_only = str( target_lookup.get( "identitiesonly" ) or "" ).strip( ).lower( ) 
    if identities_only != "yes":
        raise ValueError( f"IdentitiesOnly must be 'yes' for {target_lookup.get( 'hostname' )}, so we do not spam the server with keys" )

    # Ensure that we keep things simple by having only one UserKnownHostsFile
    user_known_hosts_file = target_lookup.get( "userknownhostsfile" )
    if isinstance( user_known_hosts_file, list ) and len( user_known_hosts_file ) != 1:
        raise ValueError( f"Multiple IdentityFile values for host alias {target_lookup.get( 'hostname' )}")


def _resolve_proxyjump_chain( ssh_config: paramiko.config.SSHConfig, start_alias: str ) -> List[ paramiko.config.SSHConfig ]:
    """
    @in_use by ssh_transport:_parse_ssh_config
    Resolve a ProxyJump chain starting from a given SSH alias.

    Raises RuntimeError on detecting a ProxyJump loop

    Returns an ordered list of per-hop SSHConfig-derived option mappings,
    with all nested ProxyJump directives expanded depth-first and cycles
    detected. The resulting order is suitable for sequential SSH transport
    construction (first hop -> next hop -> .. -> last hop).
    """

    resolved_hops, seen_aliases, pending_aliases = [ ], set( ), [ start_alias ]

    while pending_aliases:
        current_alias = pending_aliases.pop( 0 )

        if current_alias in seen_aliases:
            raise RuntimeError( f"ProxyJump loop detected at '{current_alias}'" )

        seen_aliases.add( current_alias )
        current_lookup = ssh_config.lookup( current_alias )
        proxyjump_value = ( current_lookup.get( "proxyjump" ) or "" ).strip( )
        hop_aliases = [ hop.strip( ) for hop in proxyjump_value.split(" ") if hop.strip( ) ]
        # ProxyJump allows [user@]host[:port] and ssh:// URIs. We reject them to enforce
        # single-source-of-truth per hop, keep parsing trivial, and avoid user/port
        # override ambiguity. ProxyJump must reference aliases only.
        INLINE_JUMP_RE = re.compile( r"^(?:ssh://)?(?:[^@/]+@)?[^:/\s,]+(?::\d+)?(?:/.*)?$" )
        if any( INLINE_JUMP_RE.match( hop_alias ) and ( ( "@" in hop_alias ) or ( ":" in hop_alias ) or hop_alias.startswith( "ssh://" ) ) for hop_alias in hop_aliases ):
            raise ValueError( f"ProxyJump must be aliases only; This library has no support for [user@]host[:port] or ssh:// URIs in ssh client config." )
        if hop_aliases:
            pending_aliases = hop_aliases + pending_aliases
        else:
            resolved_hops.append( current_lookup )

    # add the first link as last to finish the resolved chain
    final_lookup: paramiko.config.SSHConfig = ssh_config.lookup( start_alias )
    if resolved_hops[ -1 ] != final_lookup :
        resolved_hops.append( final_lookup )

    if not resolved_hops:
        raise ValueError( f"ValueError: no hops, not even {demux.nird_upload_host}" )
    # delete any existing value in the array to signal to caller the array is over

    return resolved_hops



def _parse_ssh_config( demux ) -> List[ paramiko.config.SSHConfig ]:
    """
    @in_use by step08_03_setup_ssh_connection.py:_setup_ssh_connection
    Parse the user SSH client configuration and resolve the effective connection chain for
    demux.nird_upload_host.

    Reads the SSH config file, validates the target host entry against demux policy and
    resolves any ProxyJump directives into an ordered list of paramiko.config.SSHConfig hop
    definitions representing the full jump chain.

    Returns:
        List[paramiko.config.SSHConfig]: Ordered hop configurations from the local client to
        the final target host.

    Raises:
        FileNotFoundError: If the user SSH client configuration file does not exist.
    """

    # check if the ssh config file exists for the current user
    ssh_config_path : str = os.path.abspath( os.path.expanduser( constants.USER_SSH_CONFIG_PATH ) )
    if not os.path.isfile( ssh_config_path ):
        raise FileNotFoundError(f"User SSH client config not found: {ssh_config_path}")

    with open( ssh_config_path, constants.READ_ONLY_TEXT , encoding = demux.encoding ) as handle:
        ssh_config : paramiko.config.SSHConfig = paramiko.config.SSHConfig( )
        ssh_config.parse( handle )

    target_lookup = ssh_config.lookup( demux.nird_upload_host )

    # demuxLogger.debug( "target lookup:" )
    # demuxLogger.debug( pprint.pprint( target_lookup ) )
    # make sure the ssh config is up to spec with our stuff
    _verify_ssh_config_policy_for_hop( target_lookup )

    return _resolve_proxyjump_chain( ssh_config, target_lookup.get( "hostname" ) )



def _validate_hostkey( hop: paramiko.config.SSHConfig, transport: paramiko.Transport, *, timeout: float = 30 ):
    """
    Validate the remote server host key for an already-created SSH Transport.

    Performs strict known_hosts verification (RejectPolicy semantics) without opening
    or authenticating the transport.
    Looks up host keys by hostname and by [host]:port for non-22 ports.

    Raise:
        RuntimeError if the host key is missing or does not exactly match; no
        accepting any non-known ssh keys, that is the job of the infra team to
        deal with
    """

    hostname = hop.get( 'hostname' )
    port     = hop.get( 'port' )

    # Validate host key against known_hosts (RejectPolicy equivalent)
    host_keys = paramiko.HostKeys( )
    known_hosts_path = os.path.abspath( os.path.expanduser( constants.USER_SSH_KNOWN_HOSTS_PATH ) )
    if os.path.exists( known_hosts_path ):
        host_keys.load( known_hosts_path )

    remote_key = transport.get_remote_server_key( )

    host_key_entry = host_keys.lookup( hostname )

    if host_key_entry is None:
        message = f"RuntimeError: Host key for {hostname}:{port} not found in {known_hosts_path}. Refusing connection."
        demuxLogger.critical( message )
        raise RuntimeError( message )

    accepted = False
    for key_type, known_key in host_key_entry.items( ):
        if ( key_type == remote_key.get_name( ) ) and ( known_key == remote_key ):
            accepted = True
            break

    if not accepted:
        message = f"RuntimeError: Host key mismatch for {hostname}:{port}. Refusing connection."
        demuxLogger.critical( message )
        raise RuntimeError( message ) # https://github.com/NorwegianVeterinaryInstitute/DemultiplexRawSequenceData/issues/150


def _load_private_key( identity_file_path: str, passphrase: Optional[ str ] ) -> paramiko.PKey:
    """
    Load an SSH private key from disk, expanding "~" and resolving to an absolute path.

    Attempts all supported Paramiko key formats in sequence (RSA, Ed25519, ECDSA, DSS).
    If the key is encrypted and no passphrase is provided, a PasswordRequiredException
    is raised during loading attempts.

    On failure (missing file, unreadable key, unsupported format), raises RuntimeError
    chained to the last encountered exception.
    """

    expanded_path: str = os.path.abspath( os.path.expanduser( identity_file_path ) )
    last_error: Optional[ BaseException ] = None

    for key_loader in ( paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.DSSKey ):
        try:
            return key_loader.from_private_key_file( expanded_path, password = passphrase )
        except ( paramiko.SSHException, FileNotFoundError, paramiko.ssh_exception.PasswordRequiredException ) as error:
            last_error = error

    raise RuntimeError( f"Could not load private key: {expanded_path}" ) from last_error



def _auth_transport_ssh_keys( transport: paramiko.Transport, hop: paramiko.config.SSHConfig  ) -> None:
    """
    Authenticate an existing SSH Transport using public key credentials.

    Loads the private key defined for the hop, retrying with a passphrase if the key is
    encrypted, then performs public key authentication against the remote server.

    Raises ValueError when a passphrase is required but unavailable, and
    AuthenticationException if the server rejects the key.
    """

    # identity_file_path: str  = str( hop.get( "identityfile" ) )
    # passphrase        : str  = str( demux.util.bitwarden.get_passphrase( hostname ) )

    username:str            = hop.get( "user" )
    hostname:str            = hop.get( "hostname" )

    if not username:
        raise ValueError( f"ValueError: No username providged for hostname {hostname} trying to load ssh keys for transport from ssh agent. Aborting." )

    agent: paramiko.Agent   = paramiko.Agent()
    for agent_key in agent.get_keys():
        try:
            message  = termcolor.colored( "In _auth_transport_ssh, trying key:\n", color="yellow", attrs=["bold"] ) 
            message += termcolor.colored( f"{agent_key}\n", color="yellow", attrs=["bold"] ) 
            message += termcolor.colored( "from agent:\n", color="yellow", attrs=["bold"] ) 
            message += f"id( transport ): {id(transport)}\n"
            message += f"transport.is_active( ): {transport.is_active( )}\n"
            ip, port = transport.getpeername( )
            message += f"transport.getpeername( ): {ip}:{port}\n"
            message += termcolor.colored( "---------------------------------", color="yellow", attrs=["bold"] )
            demuxLogger.debug( message )
            transport.auth_publickey( username, agent_key )
            if transport.is_authenticated( ):
                break
        except paramiko.AuthenticationException:
            continue
        except OSError as exception:
            if not transport.is_active( ):
                raise OSError(9, "Peer closed the connection") from exception
            else:
                raise # raise the original OSError unchanged


    # this is cheating, but i will accept this for now

    # try:
    #     private_key: paramiko.PKey = _load_private_key( identity_file_path, passphrase = None )
    # except paramiko.ssh_exception.PasswordRequiredException:
    #     if not passphrase:
    #         raise ValueError( f"Passphrase-protected key but no passphrase in BitWarden. Aborting authentication for {username}@{hostname}" )
    #     private_key = _load_private_key( identity_file_path, passphrase = passphrase )
    # transport.auth_publickey( username = username, key = private_key )
    # if not transport.is_authenticated( ):
    #     raise paramiko.AuthenticationException( f"Public key authentication failed for {username}@{hostname}" )


def _auth_transport_2fa( transport: paramiko.Transport, hop: paramiko.config.SSHConfig ) -> None:
    """
    Authenticate an existing SSH transport using keyboard-interactive 2FA 
    (paramiko considers this "keyboard-interactive" even if there is not a real user typing)

    Retrieves username, password and TOTP credentials and performs interactive
    authentication on the provided transport. Mutates the transport in place. demux

    Raises:
        AuthenticationException: if 2FA authentication fails or the transport
        remains unauthenticated after the interactive exchange.
    """
    hostname                 = hop.get( "hostname" )
    port                     = hop.get( "port" )
    username, password, totp = _get_login_credentials( hostname ) 

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
        message = f"AuthenticationException: SSH 2FA authentication failed for {username}@{hostname}:{port} ."
        demuxLogger.critical( message )
        # treat any raised AuthenticationException from auth_interactive() as failure
        # no other reliable signal exists that NIRD changed the TOTP token prompt
        raise AuthenticationException( message )


def _authenticate_transport( hop: paramiko.config.SSHConfig, transport: paramiko.Transport ) -> None:
    """
    Authenticate an existing SSH Transport for a single hop using the credentials
    defined in the SSH client configuration and BitWarden.

    Resolves the target hostname and user, selects the authentication mechanism in
    priority order (public key, keyboard-interactive 2FA and finally password). Applies
    it directly to the provided Transport.

    Raises ValueError for missing required lookup fields or unavailable 2FA secrets,
    and AuthenticationException when the remote server rejects the selected method.

    Returns the same Transport instance after successful authentication.
    """

    hostname          : str  = str( hop.get( "hostname" ) or "" )
    username          : str  = str( hop.get( "user" ) or "" )
    # password          : str  = str( demux.util.bitwarden.get_password( hostname ) or "" )
    identity_file_path: str  = str( hop.get( "identityfile" ) )
    totp_enabled      : bool = bool( hop.get( "TOTPEnabled", "no" ).lower( ) == "yes" ) # the "no" here is a safe dict.get(key, default)
    # if two_fa_enabled:
    #     topt:int          : int  = int( bitwarden.get_topt( hostname ) or None )f

    if not hostname:
        raise ValueError( f"Missing lookup fields for hop {hop.get( 'host' )}: hostname" )
    if not username:
        raise ValueError( f"Missing lookup fields for hop {hop.get( 'hostname' )}: username" )
    # if not password:
    #     raise ValueError( f"Missing lookup fields for hop {hop.get( 'hostname' )}: password" )
    # if not identity_file_path:
    #     raise ValueError( f"Missing lookup fields for hop {hop.get( 'hostname' )}: identityfile" )
    # if not identity_password:
    #     raise ValueError( f"Missing lookup fields for hop {hop.get( 'hostname' )}: identity_password" )
    if totp_enabled and not topt:
        raise ValueError( f"ValueError: could not get TOTP from BitWarden for hop {hop.get( 'hostname' )}" )

    message = termcolor.colored( "--------------------------------\n", color="yellow")
    message += "in _auth_transport_ssh_keys:\n"
    message += termcolor.colored( f"identity_file_path: {identity_file_path}\n", color="cyan", attrs=["bold"] )
    message += termcolor.colored( f"totp_enabled:       {totp_enabled}\n",       color="cyan", attrs=["bold"] )
    demuxLogger.debug( message )

    if identity_file_path:
        _auth_transport_ssh_keys( transport, hop  )
    elif totp_enabled:
        _auth_transport_2fa( transport, hop  )
    else:
        transport.auth_password( username = username, password = password )
        if not transport.is_authenticated( ):
            raise paramiko.AuthenticationException( f"Password authentication failed for {username}@{hostname}" )




def _ensure_remote_dir_via_client( demux, remote_absolute_dir_path: str ) -> None:
    """
    Ensure the remote run directory exists using an already-authenticated SSH client.

    Checks for the existence of the target directory on the remote host and creates it
    if missing. Aborts if the directory already exists or if creation fails.

    Raises:
        SSHException: if the directory already exists or if remote creation fails
        due to permission, missing parent or other remote filesystem errors.
    """

    test_command: str              = f"/usr/bin/test -d -- {shlex.quote( remote_absolute_dir_path )}"
    test_status: int               = 0
    ip, port                       = demux.transport.getpeername( )
    
    if not demux.transport.is_active( ):
        messsage = f"TransportError: transport not active at hop {ip}"
        demuxLogger.critical( message )
        raise SSHException( message )

    test_channel: paramiko.Channel = demux.transport.open_session( )
    if not test_channel.active:
        messsage = f"ChannelError: Channel not active after instantiation at hop {ip}"
        demuxLogger.critical( message )
        raise SSHException( message )

    test_channel.exec_command( test_command )
    try:
        if test_channel.exit_status_ready( ):
            test_stderr                    = test_channel.makefile_stderr( "r" ).read( ).decode( 'utf-8' )
            test_status: int               = test_channel.recv_exit_status( )
    finally:
        test_channel.close( )

    if not test_status:
        ip, port = demux.transport.getpeername( )
        message = f"Directory creation error: {ip}:{remote_absolute_dir_path} already exists.\n"
        message += f"Is this a repeat upload? If yes, delete/move the existing remote directory and try again."
        demuxLogger.critical( message )
        raise SSHException( message )



    mkdir_command: str              = f"/usr/bin/mkdir -- {shlex.quote( remote_absolute_dir_path )}"
    mkdir_status: int               = 0
    mkdir_channel: paramiko.Channel = demux.transport.open_session( )
    mkdir_channel.exec_command( mkdir_command )
    try:
        # we only need to catch stderr here
        if mkdir_channel.exit_status_ready( ):
            mkdir_stderr                    = mkdir_channel.makefile_stderr( "r" ).read( ).decode( 'utf-8' )
            mkdir_status: int               = mkdir_channel.recv_exit_status( )
    finally:
        mkdir_channel.close()

    if mkdir_status:
        ip, port = demux.transport.getpeername( )
        message = f"Directory creation error: Cannot create {ip}:{port}:{remote_absolute_dir_path} even after original check. "
        message += "Consult the remote end and try to create the directory manually to see what error you get, could be "
        message += "that parent changed permission or was moved.\n"
        message += f"SSHException: {mkdir_stderr.decode( demux.decodeScheme ).strip( )}"
        demuxLogger.critical( message )
        raise SSHException(message)
    else:
        demuxLogger.info( termcolor.colored( f"Remote directory does not exist, created\n", color="cyan", attrs=["bold"] ) )




def _connect_next_proxy_jump( hop: paramiko.config.SSHConfig, transport: Optional[ paramiko.Transport ], *, port: int = 22, timeout: float = 30.0, keepalive: int = 30 ) -> paramiko.Transport:
    """
    Build a new SSH Transport for a single hop described by a parsed SSHConfig
    entry, either by opening a direct TCP connection (first hop) or by tunneling
    through an existing Transport using a direct-tcpip channel (ProxyJump-style).

    The hop is assumed to already be ordered in a resolved jump chain, so only
    the resolved hostname field is used (no ProxyJump re-evaluation).

    The returned Transport has completed the SSH client handshake but is not
    authenticated.

    Args:
        hop: Paramiko SSHConfig entry for the next hop (must contain 'hostname').
        transport: Existing Transport to tunnel through, or None for the first hop.
        port: SSH port for the hop (default: 22).
        timeout: Socket and SSH handshake timeout in seconds.

    Returns:
        An initialized but unauthenticated Paramiko Transport for the hop.

    Raises:
        socket.error: If the TCP connection fails on the hop.
        RuntimeError: If the TCP connection fails or if opening the ProxyJump
        channel fails for the hop.
    """

    next_transport: paramiko.Transport | None = None
    hostname: str = hop.get( 'hostname' ) # since we already have an ordered list of hops, we do not need to do some crazy
                                          # checking to see if ProxyJump is set and use that or not. We just select the 
                                          # hostname.
    if transport is None:   # first hop
        tcp_socket: socket.socket = socket.create_connection( ( hostname, port ), timeout = timeout )
        next_transport = paramiko.Transport( tcp_socket )

    elif transport.is_active( ):                   # second hop and onwards
        channel = transport.open_channel( kind = "direct-tcpip", dest_addr = ( hostname, port ), src_addr = transport.getpeername( ), timeout = timeout )
        if not channel.active:
            raise RuntimeError( f"RuntimeError: channel not active at hop:{hostname}")
        next_transport = paramiko.Transport( channel )
    else:
        raise RuntimeError( "RuntimeError: in _connect_next_proxy_jump, transport was neither 'None' nor active")
    

    # check if transport exists and is open
    if next_transport is None:
        raise RuntimeError( f"Transport creation failed at hop {hostname}" )
    next_transport.set_keepalive( keepalive )
    next_transport.start_client( timeout = timeout ) # Perform SSH handshake on the new transport
    print( f"_connect_next_proxy_jump: id( transport ), after start_client( ): {id( transport )}" )
    if not next_transport.is_active( ):
        raise RuntimeError( f"SSH transport inactive after handshake at hop {hostname}" )

    return next_transport

