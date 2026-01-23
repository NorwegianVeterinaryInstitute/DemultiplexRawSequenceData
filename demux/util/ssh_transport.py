# all ssh transport related stuff

import os
import paramiko
import pprint
import re
import shlex
import sys

from typing import Any, Dict, List, Optional, Tuple, Mapping

from paramiko               import SSHClient, SSHConfig, AutoAddPolicy, RejectPolicy, Transport, SSHException
from paramiko.ssh_exception import AuthenticationException
from scp                    import SCPClient

from demux.util.bitwarden  import _get_login_credentials
from demux.config          import constants
from demux.loggers         import demuxLogger, demuxFailureLogger


def _resolve_proxyjump_chain( ssh_config: paramiko.config.SSHConfig, start_alias: str ) -> List[ paramiko.config.SSHConfig ]:
    """
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
    return resolved_hops


def _parse_ssh_config( demux ) -> List[ paramiko.config.SSHConfig ]:
    """

    Raises:
    
    Returns:
        paramiko.config.SSHConfig for the given demux.nird_upload_host
        if there is a proxy jump on the first item, then we initiate a list of paramiko.config.SSHConfig
        and create an ordered chain of which we got to jump through to reach demux.nird_upload_host
    """

    # check if the ssh config file exists for the current user
    ssh_config_path = os.path.abspath( os.path.expanduser( constants.USER_SSH_CONFIG_PATH ) )
    if not os.path.isfile( ssh_config_path ):
        raise FileNotFoundError(f"User SSH client config not found: {ssh_config_path}")

    with open( ssh_config_path, constants.READ_ONLY_TEXT , encoding = demux.encoding ) as handle:
        ssh_config = paramiko.config.SSHConfig( )
        ssh_config.parse( handle )

    target_lookup = ssh_config.lookup( demux.nird_upload_host )

    # make sure the ssh config is up to spec with our stuff
    _verify_ssh_config_policy_for_hop( target_lookup )

    return _resolve_proxyjump_chain( ssh_config, target_lookup.get( "hostname" ) )


def _verify_ssh_config_policy_for_hop( target_lookup: paramiko.config.SSHConfig ) -> None:
    """
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



def _validate_hostkey( transport: Transport ):
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
        raise RuntimeError( message ) # https://github.com/NorwegianVeterinaryInstitute/DemultiplexRawSequenceData/issues/150



def _auth_transport_ssh_keys( demux, transport: paramiko.Transport ) -> None:
    return None


def _auth_transport_2fa( demux, transport: paramiko.Transport ) -> None:
    """
    Authenticate an existing SSH transport using keyboard-interactive 2FA 
    (paramiko considers this "keyboard-interactive" even if there is not a real user typing)

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



def _get_transport( demux ) -> paramiko.Transport:
    """
    @in_use
    @still_being_thought_out
    Open a new SSH transport to the remote host and strictly validate its host key
    against the local known_hosts database.

    Establishes the TCP/SSH session, retrieves the server host key and rejects the
    connection if the key is missing or does not match the known_hosts entry.
    Returns an authenticated SSH Transport with a verified host key
    """

    # get the ssh connection going and initialize a transport from which we can spawn channels
    hop_config  = _setup_ssh_connection( demux ) # if the user running this has an ~/.ssh/config, load and use it; otherwise, use defaults.
    transport   = _connect_to_upload_host( hop_config )
    _validate_hostkey( transport )
    _auth_transport( demux, transport ) 

    return transport

