import paramiko

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

    hops_list: List[ paramiko.config.SSHConfig ] = kot._parse_ssh_config( )

    current_transport : Optional[ paramiko.Transport ] = None

    for hop in hops_list:
        next_transport: paramiko.Transport = _build_transport( hop, current_transport ) # returns the next transport

        pprint.pprint( next_transport )
        sys.exit( 0 )

        _validate_hostkey( next_transport )         # this is practically written
        _authenticate_transport( next_transport )   # this is not written 
        current_transport = next_transport

    return current_transport # fully chained and authenticated


