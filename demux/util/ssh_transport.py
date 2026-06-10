# all ssh transport related stuff

import base64
import hashlib
import os
import paramiko
import pprint
import re
import shlex
import socket
import stat
import sys
import termcolor

from typing import Any, Dict, List, Optional, Tuple, Mapping

from paramiko               import SSHClient, SSHConfig, AutoAddPolicy, RejectPolicy, Transport, SSHException
from paramiko.ssh_exception import AuthenticationException

from demux.util.bitwarden  import _get_login_credentials, _get_password
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
    if verify_hostkey_dns != "yes":
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
    @in_use by step08_03_setup_ssh_connection.py:_setup_ssh_connection
    Validate the remote host key for a single SSH hop against the user's known_hosts file.

    Reads the known_hosts file associated with the hop's UserKnownHostsFile entry,
    loads all host keys and compares the transport's remote host key against them.
    Raises an SSHException if the key is not found or does not match.

    Args:
        hop: Paramiko SSHConfig entry for the hop (must contain 'hostname' and optionally
             'userknownhostsfile').
        transport: Active Paramiko Transport whose server key will be validated.
        timeout: Currently unused; reserved for future socket-level timeout enforcement.

    Raises:
        FileNotFoundError: If no known_hosts file is found for the hop.
        SSHException: If the remote host key does not match any entry in known_hosts.
    """

    hostname: str = hop.get( "hostname" )

    known_hosts_paths: list[ str ] = [ ]
    user_known_hosts = hop.get( "userknownhostsfile" )

    if isinstance( user_known_hosts, list ):
        known_hosts_paths = [ os.path.expanduser( p ) for p in user_known_hosts ]
    elif isinstance( user_known_hosts, str ):
        known_hosts_paths = [ os.path.expanduser( user_known_hosts ) ]
    else:
        known_hosts_paths = [ os.path.expanduser( "~/.ssh/known_hosts" ) ]

    existing_paths: list[ str ] = [ p for p in known_hosts_paths if os.path.isfile( p ) ]
    if not existing_paths:
        raise FileNotFoundError( f"No known_hosts file found for hop {hostname}: tried {known_hosts_paths}" )

    remote_key: paramiko.PKey = transport.get_remote_server_key( )

    host_keys: paramiko.HostKeys = paramiko.HostKeys( )
    for path in existing_paths:
        host_keys.load( path )

    known_for_host: paramiko.HostKeys.SubDict = host_keys.lookup( hostname )
    if not known_for_host:
        raise paramiko.SSHException( f"No host key found for {hostname} in {existing_paths}" )

    key_type: str        = remote_key.get_name( )
    expected_key         = known_for_host.get( key_type )
    if expected_key is None:
        raise paramiko.SSHException( f"No {key_type} key for {hostname} in known_hosts; found types: {list( known_for_host.keys( ) )}" )
    if expected_key != remote_key:
        raise paramiko.SSHException( f"Host key mismatch for {hostname}: known_hosts has {expected_key.get_base64( )[:20]}..., got {remote_key.get_base64( )[:20]}..." )

    demuxLogger.debug( f"Host key verified for {hostname}" )



def _load_private_key( identityfile: str, *, passphrase: str = "" ) -> paramiko.PKey:
    """
    Load a private key from disk, trying all supported key types in order.

    Attempts Ed25519 first (most common for modern NVI keys), then RSA, ECDSA,
    and DSS. Returns the first key that loads successfully.

    Args:
        identityfile: Absolute path to the private key file.
        passphrase:   Optional passphrase for encrypted keys.

    Returns:
        A loaded paramiko.PKey instance.

    Raises:
        paramiko.SSHException: If no supported key type matches the file.
        paramiko.PasswordRequiredException: If the key is encrypted and no passphrase is given.
    """

    pkey_password: bytes | None = passphrase.encode( ) if passphrase else None

    for key_class in ( paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey, paramiko.DSSKey ):
        try:
            return key_class.from_private_key_file( identityfile, password = pkey_password )
        except paramiko.SSHException:
            continue
        except Exception:
            continue

    raise paramiko.SSHException( f"Could not load private key from {identityfile}: no supported key type matched." )



def _auth_via_agent( transport: paramiko.Transport, username: str, identityfile_pub: str ) -> bool:
    """
    Attempt public key authentication using a key already loaded in the SSH agent.

    Computes the SHA-256 fingerprint of the on-disk public key file and matches it
    against keys available in the running SSH agent. If a matching key is found,
    presents it to the remote server via the transport.

    Args:
        transport:        An active, unauthenticated Paramiko Transport.
        username:         The SSH username to authenticate as.
        identityfile_pub: Absolute path to the public key file (.pub) corresponding
                          to the desired identity.

    Returns:
        True if authentication succeeded via the agent key.
        False if the matching key was not found in the agent (caller should fall back
        to disk key).

    Raises:
        FileNotFoundError: If identityfile_pub does not exist.
        paramiko.AuthenticationException: If the agent key was found but rejected by
                                          the server.
        OSError: On transport-level errors during authentication.
    """

    if not os.path.isfile( identityfile_pub ):
        raise FileNotFoundError( f"Public key file not found: {identityfile_pub}" )

    with open( identityfile_pub, constants.READ_ONLY_TEXT ) as fh:
        pub_line: str        = fh.read( ).split( )
        pub_b64: str         = pub_line[ 1 ] if len( pub_line ) >= 2 else ""
    pub_bytes: bytes         = base64.b64decode( pub_b64 )
    disk_fingerprint: str    = hashlib.sha256( pub_bytes ).digest( ).hex( )

    agent: paramiko.Agent    = paramiko.Agent( )
    agent_keys               = agent.get_keys( )

    for agent_key in agent_keys:
        agent_fingerprint: str = hashlib.sha256( agent_key.asbytes( ) ).digest( ).hex( )
        if agent_fingerprint != disk_fingerprint:
            continue

        # matching key found in agent - attempt authentication
        try:
            transport.auth_publickey( username, agent_key )
        except paramiko.AuthenticationException:
            raise
        except OSError as exception:
            if getattr( exception, "errno", None ) == 9:
                raise OSError( 9, "Peer closed the connection" ) from exception
            raise # raise the original error, in case something comes up we have not anticipated

        if not transport.is_authenticated( ):
            raise paramiko.AuthenticationException( "public key authentication attempt returned without success." )
        return True

    return False # requested key not present in ssh-agent



def _validate_ssh_key_auth_inputs( hop: paramiko.config.SSHConfig ) -> tuple[str, str, str]:
    """
    Validate SSH key authentication inputs resolved from SSHConfig.

    Ensures user, hostname and IdentityFile are present and that IdentityFile is an
    absolute, readable, non-symlink regular file suitable for key loading.

    Returns (username, hostname, identityfile); 

    Raises ValueError on validation failure.
    """

    username: str     = hop.get( "user" )
    hostname: str     = hop.get( "hostname" )
    identityfile: str = os.path.abspath( os.path.expanduser( hop.get( "identityfile" )[0] ) )

    if not username:
        raise ValueError( f"ValueError: No username provided for hostname {hostname}. Aborting." )

    if not os.path.isabs( identityfile ):
        raise ValueError( f"ValueError: identityfile must be an absolute path: '{identityfile}'" )
    if os.path.islink( identityfile ):
        raise ValueError( f"ValueError: identityfile must not be a symlink: '{identityfile}'" )

    stat_result: os.stat_result = os.stat( identityfile )
    if not stat.S_ISREG( stat_result.st_mode ):
        raise ValueError( f"ValueError: identityfile is not a regular file: '{identityfile}'" )
    if stat_result.st_size == 0:
        raise ValueError( f"ValueError: identityfile is empty: '{identityfile}'" )
    if not os.access( identityfile, os.R_OK ):
        raise ValueError( f"ValueError: identityfile is not readable: '{identityfile}'" )

    return username, hostname, identityfile


def _auth_via_private_key( transport: paramiko.Transport, username: str, private_key: paramiko.PKey ) -> None:
    """
    Authenticate an existing SSH transport using a private key loaded from disk.

    Called as fallback when the matching key is not present in the SSH agent.
    Presents the pre-loaded key directly to the server via the transport.

    Args:
        transport:   An active, unauthenticated Paramiko Transport.
        username:    The SSH username to authenticate as.
        private_key: A loaded paramiko.PKey instance (from _load_private_key).

    Raises:
        paramiko.AuthenticationException: If the server rejects the key.
        OSError: On transport-level errors during authentication.
    """

    try:
        transport.auth_publickey( username, private_key )
    except paramiko.AuthenticationException:
        raise
    except OSError as exception:
        if getattr( exception, "errno", None ) == 9:
            raise OSError( 9, "Peer closed the connection" ) from exception
        raise

    if not transport.is_authenticated( ):
        raise paramiko.AuthenticationException( f"Private key authentication returned without success for {username}." )


def _auth_transport_ssh_keys( hop: paramiko.config.SSHConfig, transport: paramiko.Transport  ) -> None:
    """
    Authenticate an existing SSH Transport using public key credentials.

    Loads the private key defined for the hop, retrying with a passphrase if the key is
    encrypted, then performs public key authentication against the remote server.

    Raises ValueError when a passphrase is required but unavailable, and
    AuthenticationException if the server rejects the key.
    ---------------------------------------------------------------------------------------------------
    Authentication strategy for a known SSH server with minimal authentication attempts.

    The server is trusted and regularly accessed, so the goal is to minimize failed
    authentication attempts and unnecessary key offers.

    Strategy:
    1. Resolve effective host options from SSH config (HostName, User, IdentityFile)
       and canonicalize the target. Only one IdentityFile is permitted per host entry.
    2. If IdentityFile is defined:
       a. Compute the fingerprint of the on-disk key.
       b. Iterate ssh-agent keys and select the matching key by fingerprint.
       c. If found, present that key to the server.
    3. If the key is not present in the agent:
       a. Load the IdentityFile from disk using the passphrase stored in Bitwarden.
       b. Present the loaded key to the server.
    4. Attempt authentication exactly once.
    5. Stop immediately on success or authentication failure.
    6. Abort immediately on transport-level failure.
    """

    username: str                    = ""
    hostname: str                    = ""
    identityfile: str                = ""
    username, hostname, identityfile = _validate_ssh_key_auth_inputs( hop )                       # validation for all three happens in method
    passphrase: str                  = _get_password( "main2" )                                   # demux.util.bitwarden
    private_key: paramiko.PKey       = _load_private_key( identityfile, passphrase = passphrase ) # load the private key, no transport auth
    identityfile_pub: str            = f"{identityfile}.pub"


    authenticated_via_agent: bool    = _auth_via_agent( transport, username, identityfile_pub )   # try to auth via in memory key
    if authenticated_via_agent:
        return

    _auth_via_private_key( transport, username, private_key )                                     # try to auth via key on disk

    if not transport.is_authenticated( ):
        raise paramiko.AuthenticationException( f"Authentication attempt using {identityfile} returned without success." )




def _auth_transport_2fa( hop: paramiko.config.SSHConfig, transport: paramiko.Transport ) -> None:
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

    hostname     : str  = hop.get( "hostname" )
    username     : str  = hop.get( "user" )
    identityfile : str  = hop.get( "identityfile" )
    totp_enabled : bool = not bool( identityfile )
    if hostname == "login.nird.sigma2.no": #cheating
        totp_enabled = True
    # if two_fa_enabled:
    #     topt:int          : int  = int( bitwarden.get_topt( hostname ) or None )

    if identityfile:
        _auth_transport_ssh_keys( hop, transport )
    elif totp_enabled:
        _auth_transport_2fa( hop, transport )
    else:
        password: str  = _get_password( hostname ) # demux.util.bitwarden
        if not password:
            raise ValueError( f"Missing lookup fields for hop {hop.get( 'hostname' )}: password" )
        transport.auth_password( username = username, password = password )

    if not transport.is_authenticated( ):
        raise paramiko.AuthenticationException( f"Password authentication failed for {username}@{hostname}" )



def _ensure_remote_dir_via_sftp( demux, remote_absolute_dir_path: str ) -> None:
    """
    Ensure the remote run directory exists using an already-authenticated SFTP session.

    Checks for the existence of the target directory on the remote host and creates it
    if missing. Aborts if the directory already exists or if creation fails.

    Raises:
        SSHException: if the directory already exists, if the transport is inactive,
        or if remote creation fails due to permission, missing parent, or other
        remote filesystem errors.
    """

    ip, port = demux.transport.getpeername( )[:2]  # make sure that if we are running a dual stack, we only grab the first two parameters

    if not os.path.isabs( remote_absolute_dir_path ):
        message = f"Remote directory is not in absolute path: {remote_absolute_dir_path}"
        raise RuntimeError( message )

    if not demux.transport.is_active( ):
        message = f"TransportError: transport not active at hop {ip}"
        demuxLogger.critical( message )
        raise SSHException( message )

    try:
        sftp_client: paramiko.SFTPClient = paramiko.SFTPClient.from_transport( demux.transport )
    except Exception as error:
        message = f"SFTPError: failed to create SFTP session at hop {ip}:{port}"
        demuxLogger.critical( message )
        raise SSHException( message ) from error

    try:
        attributes: paramiko.SFTPAttributes | None = None
        try:
            attributes = sftp_client.stat( remote_absolute_dir_path )
        except FileNotFoundError:
            pass
        except OSError as error:
            message = f"SFTPError: stat failed for {ip}:{port}:{remote_absolute_dir_path}: {error}"
            demuxLogger.critical( message )
            raise SSHException( message ) from error

        if attributes is not None:
            if stat.S_ISDIR( attributes.st_mode ):
                message = f"{ip}:{remote_absolute_dir_path} already exists.\n"
                message += "Is this a repeat upload? If yes, delete/move the existing remote directory and try again."
                demuxLogger.critical( message )
                raise SSHException( message )
            raise SSHException( f"{ip}:{remote_absolute_dir_path} exists but is not a directory." )

        try:
            sftp_client.mkdir( remote_absolute_dir_path )
        except OSError as error:
            message = f"Directory creation error: cannot create {ip}:{port}:{remote_absolute_dir_path}. "
            message += f"SFTPError: {error}"
            demuxLogger.critical( message )
            raise SSHException( message ) from error

        demuxLogger.info( termcolor.colored( "Remote directory does not exist, created\n", color="cyan", attrs=["bold"] ) )
    finally:
        try:
            sftp_client.close( )
        except Exception:
            pass



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
        channel = transport.open_channel( kind = "direct-tcpip", dest_addr = ( hostname, port ), src_addr = transport.getpeername( ), timeout = timeout ) # src_addr here is a tupple, so the assignment is correct
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
    if not next_transport.is_active( ):
        raise RuntimeError( f"SSH transport inactive after handshake at hop {hostname}" )

    return next_transport
