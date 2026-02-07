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
    first_transport  : paramiko.Transport | None = None
    current_transport: paramiko.Transport | None = None
    next_transport   : paramiko.Transport | None = None
    transport_stack: List[ paramiko.Transport ]  = [ ]  # having a stack of the previous transports would be a good idea
                                                        # so we can close the transports later in reverse order
    if len( hops_list ) == 0:
        raise RuntimeError( "SSH config resolution produced zero hops; cannot build transport chain." )

    pprint_hops =  termcolor.colored( pprint.pprint( hops_list ), color="cyan", attrs=["bold"] )
    demuxLogger.debug( f"current hop:{pprint_hops}\n" )


    for index, hop in enumerate( hops_list ):
        is_last: bool = index == len( hops_list ) - 1
        demuxLogger.debug( termcolor.colored( hop.get( "hostname" ), color="green", attrs=["bold"] ) if is_last else hop.get( "hostname" ) )
        next_transport: paramiko.Transport = _connect_next_proxy_jump( hop, current_transport )

        print( f"id( transport ), before_validate_hostkey:: {id( next_transport )}" )
        _validate_hostkey( hop, next_transport )
        print( f"id( transport ) after _validate_hostkey: {id( next_transport )}" )
        _authenticate_transport( hop, next_transport )
        print( f"id( transport ) after _authenticate_transport: {id( next_transport )}" )
        transport_stack.append( next_transport )
        current_transport = next_transport

    if not current_transport.is_active( ):
        raise RuntimeError( "Transport chain construction failed; final transport is None." )

    # Save transport_stack[-1]
    demux.transport = transport_stack[-1]
    # save the transport stack for later, so we can .reverse and walk it backwards.
    demux.transport_stack = transport_stack