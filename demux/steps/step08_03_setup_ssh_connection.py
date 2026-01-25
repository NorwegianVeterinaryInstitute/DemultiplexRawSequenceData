def _setup_ssh_connection( demux ) -> paramiko.Transport:
    """
    @in_use by step08_04_ensure_remote_run_directory.py
    @still_being_thought_out
    Open a new SSH transport to the remote host and strictly validate its host key
    against the local known_hosts database.

    Establishes the TCP/SSH session, retrieves the server host key and rejects the
    connection if the key is missing or does not match the known_hosts entry.
    Returns an authenticated SSH Transport with a verified host key
    """


    hops_list: List[ paramiko.config.SSHConfig ] = _parse_ssh_config( demux )
    # _connect_to_destination( hops_list )
    for hop in hops_list:
        _connect_to( hop )
        _validate_hostkey( )
        _auth_transport( ) # _first_transport() returns and you rebind it each hop.

    return transport
