#!/usr/bin/env python3

import json
import socket
import subprocess
import paramiko

#####################################################################################
BITWARDEN_ITEM_NAME = "login.nird.sigma2.no"
BITWARDEN_CLI_PATH  = "/usr/local/bin/bw"
REMOTE_HOST         = "login.nird.sigma2.no"
REMOTE_PORT         = 22
#####################################################################################
SAFETY_SECONDS = 5


def run_bw( args ):
    result = subprocess.run( [BITWARDEN_CLI_PATH] + args, check = True, capture_output = True, text = True )
    return result.stdout.strip( )

def get_login_item( ):
    item_json = run_bw( ["get", "item", BITWARDEN_ITEM_NAME] )
    return json.loads( item_json )

def get_password( ):
    return run_bw( ["get", "password", BITWARDEN_ITEM_NAME] )

def get_totp( ):
    return run_bw( ["get", "totp", BITWARDEN_ITEM_NAME] )

def is_totp_window_safe(  ):
    """
    Return True if the current TOTP code has at least safety_seconds of validity left in its 30 second window.
    Otherwise, False. Standard TOTP accepts the current 30s window plus one adjacent 30s window as time drift
    """ 
    remaining = 30 - ( int( time.time( ) ) % 30 )
    return remaining >= SAFETY_SECONDS


def keyboard_interactive_handler( title, instructions, prompts ):
    password = get_password( )
    responses = [ ]

    for prompt, echo in prompts:
        if "One-time password (OATH)" in prompt:
            responses.append(get_totp())
        elif "Password:" in prompt:
            responses.append(password)

    return responses


def main( ):
    item = get_login_item( )
    username = item["login"]["username"]
    password = get_password( )

    sock = socket.create_connection( ( REMOTE_HOST, REMOTE_PORT ) )
    transport = paramiko.Transport( sock )
    transport.start_client( )

    # Optional: load and enforce known_hosts here if you want strict host key checking.

    transport.auth_interactive( username, keyboard_interactive_handler )

    session = transport.open_session( )
    session.exec_command( "/usr/bin/hostname" )
    output = session.recv( 4096 ).decode( "utf-8", errors = "replace" )
    print( output.strip( ) )

    session.close( )
    transport.close( )
    sock.close( )

    Exception socket.error:
    Exception NoValidConnectionsError # if all valid connection targets for the requested hostname (eg IPv4 and IPv6) yielded connection-refused or host-unreachable socket errors.
    Exception BadHostKeyException:
    Exception AuthenticationException:
    Exception UnableToAuthenticate:
    Exception SSHException: # if there was any other error connecting or establishing an SSH session.

if __name__ == "__main__":
    main( )
