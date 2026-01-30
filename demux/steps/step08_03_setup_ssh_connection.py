import paramiko

from typing import Any, Dict, List, Optional, Tuple, Mapping

from demux.util.ssh_transport import _build_proxyjump_transport_chain, _validate_hostkey, _authenticate_transport, _parse_ssh_config

def _setup_ssh_connection( demux, *, timeout: float = 30 ) -> paramiko.Transport:
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


    for hop in hops_list:
        next_transport: paramiko.Transport = _build_proxyjump_transport_chain( hop, current_transport )
        next_transport.start_client( timeout )
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