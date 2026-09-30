
import paramiko
import termcolor

from demux.loggers import demuxLogger
from demux.util.ssh_transport import (
    _authenticate_transport,
    _connect_next_proxy_jump,
    _parse_ssh_config,
    _select_auth_method,
    _validate_hostkey,
)


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
    hops_list: list[ paramiko.config.SSHConfigDict ] = _parse_ssh_config( demux )
    current_transport: paramiko.Transport | None = None
    next_transport   : paramiko.Transport | None = None
    transport_stack: list[ paramiko.Transport ]  = [ ]  # having a stack of the previous transports would be a good idea
                                                        # so we can close the transports later in reverse order
    demux.transport_stack = transport_stack             # store the list now: if a later hop fails, teardown can still close the hops already open
    if len( hops_list ) == 0:
        raise RuntimeError( "SSH config resolution produced zero hops; cannot build transport chain." )

    message = termcolor.colored( "Null hop", color="cyan", attrs=["bold"] )
    demuxLogger.debug( message )

    for index, hop in enumerate( hops_list ):
        is_last: bool = index == len( hops_list ) - 1
        if is_last:
            message = termcolor.colored( f"Last hop: {hop.get( 'hostname' )}", color="green", attrs=["bold"] )
        else:
            message = f"current hop: {hop.get( 'hostname' )}"
        demuxLogger.debug( message )

        next_transport = _connect_next_proxy_jump( hop, current_transport )

        _validate_hostkey( hop, next_transport )
        auth_method: str = _select_auth_method( hop, is_target = is_last, nird_access_mode = demux.nird_access_mode )
        demuxLogger.debug( f"auth method for {hop.get( 'hostname' )}: {auth_method}" )
        _authenticate_transport( hop, next_transport, auth_method = auth_method )
        transport_stack.append( next_transport )
        current_transport = next_transport

    if current_transport is None or not current_transport.is_active( ):
        raise RuntimeError( "Transport chain construction failed; final transport is None." )

    # Save transport_stack[-1]
    demux.transport = transport_stack[-1]
    # save the transport stack for later, so we can .reverse and walk it backwards.
    demux.transport_stack = transport_stack

