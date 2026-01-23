def _setup_ssh_connection( demux ) -> paramiko.Transport:

    transport = paramiko.Transport( )
    hops_list: List[ paramiko.config.SSHConfig ] = _parse_ssh_config( demux )
    # _connect_to_destination( hops_list )
    _validate_hostkey( )
    _auth_transport( ) # _first_transport() returns and you rebind it each hop.

    return transport
