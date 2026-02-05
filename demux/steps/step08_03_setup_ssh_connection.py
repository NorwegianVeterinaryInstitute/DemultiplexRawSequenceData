import paramiko
import pprint
import termcolor

from typing import Any, Dict, List, Optional, Tuple, Mapping

from demux.util.ssh_transport   import _connect_next_proxy_jump, _validate_hostkey, _authenticate_transport, _parse_ssh_config
from demux.loggers              import demuxLogger, demuxFailureLogger

def _setup_ssh_connection( demux, *, timeout: float = 30 ):
    """
    @still_being_thought_out

    Build an authenticated SSH Transport chain for the target host (and any ProxyJump hops),
    validating each hop host key against known_hosts before authenticating and proceeding.

    Returns:
        A fully chained, authenticated `paramiko.Transport` for the final hop.

    Raises:
        RuntimeError: if no hops are produced, or if transport construction fails.
    """
    hops_list: List[ paramiko.config.SSHConfig ] = _parse_ssh_config( demux )
    current_transport: paramiko.Transport | None = None
    transport_stack: List[ paramiko.Transport ] = [ ]   # having a stack of the previous transports would be a good idea
                                                        # so we can close the transports later in reverse order
    if len( hops_list ) == 0:
        raise RuntimeError( "SSH config resolution produced zero hops; cannot build transport chain." )

    pprint_hops =  termcolor.colored( pprint.pprint( hops_list ), color="cyan", attrs=["bold"] )
    demuxLogger.debug( f"current hop:{pprint_hops}\n" )


    for hop in hops_list:
        demuxLogger.debug( f"current hop:{hop.get( 'hostname' )}\n" )
        next_transport: paramiko.Transport = _connect_next_proxy_jump( hop, current_transport )
        if not hasattr( next_transport, 'open_channel'):
            raise ValueError('next_transport is not connnected')
        try:
            peer_ip, port = next_transport.getpeername( )
            pprint_peer = termcolor.colored( peer_ip, color="yellow", attrs=["bold"] )
            demuxLogger.debug( f"current peer:{pprint_peer}\n" )
            next_transport.start_client( timeout = timeout )  # Perform SSH handshake on the new transport
        except socket.timeout as error:
            raise RuntimeError("SSH handshake timeout") from error
        except EOFError as error:
            raise RuntimeError("SSH connection closed during handshake") from error
        except paramiko.SSHException as error:
            raise RuntimeError("SSH protocol or key exchange failure") from error
        except OSError as error:
            raise RuntimeError("Underlying socket failure during SSH handshake") from error

        if not next_transport.is_active( ):  # Verify transport state after handshake
            raise RuntimeError( "SSH transport inactive after handshake" )

        _validate_hostkey( hop, next_transport )
        _authenticate_transport( hop, next_transport )
        transport_stack.append( next_transport )
        current_transport = next_transport
    if current_transport is None:
        raise RuntimeError( "Transport chain construction failed; final transport is None." )

    # save the transport
    demux.transport = current_transport
    # save the transport stack for later, so we can .reverse and walk it backwards.
    demux.transport_stack = transport_stack