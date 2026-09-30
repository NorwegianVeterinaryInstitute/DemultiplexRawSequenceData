 # close off the channels we opened and any transports



def _tear_down_transport( demux ) -> None:
    """
    Best-effort teardown of the active SSH transport stack.

    Iterates the transport stack in reverse creation order (last hop first),
    closing each transport. Close failures are collected and reported together
    after teardown completes, preserving per-hop failure context via chained
    exceptions. 

    Raises ExceptionGroup if one or more transports fail to close.
    """

    transport_closing_failures: list[ Exception ] = [ ]

    for index, transport in reversed( list( enumerate( demux.transport_stack or [ ] ) ) ):
        try:
            transport.close( )
        except Exception as error:   # noqa: BLE001 - collect every close failure, then raise them together as an ExceptionGroup below
            wrapped = RuntimeError( f"Transport close failed at stack index {index}: {transport!r}" )
            wrapped.__cause__ = error   # Python language builtin (PEP 3134).
            transport_closing_failures.append( wrapped )

    if transport_closing_failures:
        raise ExceptionGroup( "Transport teardown failures", transport_closing_failures )
