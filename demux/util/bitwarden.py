import json
import socket
import subprocess
import urllib.request

from typing import Tuple

from demux.config  import constants
from demux.loggers import demuxLogger, demuxFailureLogger

# bitwarden methods

def get_password( hostname: str ):
    if not hostname:
        raise ValueError( "ValueError: hostname not provided, cannot return password. Aborting." )

    with urllib.request.urlopen( f"{demux.bw_baseurl}/object/password/{hostname}", timeout = 1 ) as r:
        password:str = json.load( r )[ "data" ][ "data" ]

    if not password:
        raise ValueError( f"ValueError: no password returned from BitWarden for host {hostname}. Aborting." )

    return password

# def get_totp( hostname: str ):
#     if not hostname:
#         raise ValueError( "ValueError: hostname not provided, cannot return TOTP token. Aborting." )
#
#     with urllib.request.urlopen( f"{demux.bw_baseurl}/object/totp/{hostname}",     timeout = 1 ) as r:
#         totp:int     = json.load( r )[ "data" ][ "data" ]
#
#     return totp
#
# def get_passphrase( hostname: str ):
#     if not hostname:
#         raise ValueError( "ValueError: hostname not provided, cannot return passphrase for key. Aborting." )
#
#     with urllib.request.urlopen( f"{demux.bw_baseurl}/object/totp/{hostname}",     timeout = 1 ) as r:
#         passphrase:str     = json.load( r )[ "data" ][ "data" ]
#
#     return totp



def _get_login_credentials_via_bw_cli( demux ) -> Tuple[ str, str, str ]:
    """
    Fetch username, password, and TOTP via bw CLI.
    Returns (username, password, totp) as strings.
    """

    # no need to check again if constants.BITWARDEN_CLI_PATH exists, again
    username_process = subprocess.run( [ constants.BITWARDEN_CLI_PATH, "get", "username", demux.nird_upload_host ], check = True, capture_output = True, text = True )
    password_process = subprocess.run( [ constants.BITWARDEN_CLI_PATH, "get", "password", demux.nird_upload_host ], check = True, capture_output = True, text = True )
    totp_process     = subprocess.run( [ constants.BITWARDEN_CLI_PATH, "get", "totp",     demux.nird_upload_host ], check = True, capture_output = True, text = True )

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

    with urllib.request.urlopen( f"{demux.bw_baseurl}/object/username/{demux.nird_upload_host}", timeout = 1 ) as r:
        username = json.load( r )[ "data" ][ "data" ]
    with urllib.request.urlopen( f"{demux.bw_baseurl}/object/password/{demux.nird_upload_host}", timeout = 1 ) as r:
        password = json.load( r )[ "data" ][ "data" ]
    with urllib.request.urlopen( f"{demux.bw_baseurl}/object/totp/{demux.nird_upload_host}",     timeout = 1 ) as r:
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

    cli_state_process = subprocess.run( [ constants.BITWARDEN_CLI_PATH, "status" ], check = True, capture_output = True, text = True )

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
        raise PermissionError( message )

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