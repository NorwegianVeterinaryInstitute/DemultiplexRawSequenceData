def _auth_transport( demux, transport: paramiko.Transport ) -> None:
    """
    @in_use
    Authenticate an existing SSH transport using ssh keys or keyboard-interactive 2FA.

    Selects the appropriate mode via the demux.nird_access_mode user configuration

    Raises:
        RuntimeError: when the access mode is misconfigured
    """

    if constants.NIRD_MODE_SSH       == demux.nird_access_mode:
        _auth_transport_ssh_keys( demux, transport )
    elif constants.NIRD_MODE_SSH_2FA == demux.nird_access_mode:
        _auth_transport_2fa( demux, transport )
    elif constants.NIRD_MODE_MOUNTED == demux.nird_access_mode:
        pass # nothing to authenticate here, the sysadmin has already done that part manually or via systemd
    else:
        message = f"RuntimeError: Unknown NIRD access mode: {demux.nird_access_mode}" # https://github.com/NorwegianVeterinaryInstitute/DemultiplexRawSequenceData/issues/138
        demuxLogger.critical( message )
        raise RuntimeError( message )





def _ensure_remote_run_directory_mounted( demux ) -> None:
    """
    @in_use
    Ensure the remote run directory exists on a locally mounted sshfs path.
    """
    remote_absolute_dir_path = os.path.join(demux.nird_base_upload_path, demux.RunID)
    mount_found = False
    # Verify that the path is on an sshfs filesystem
    for partition in psutil.disk_partitions( all = True ):
        if partition.fstype == 'fuse.sshfs':
            mountpoint_real = os.path.realpath( partition.mountpoint )
            if remote_absolute_dir_path.startswith( mountpoint_real.rstrip( "/" ) + "/"):  # remove any trailing slash (/mnt/x/////) then add exactly one '/'
                mount_found = True                                                         # back so the prefix match behaves consistently whether the mountpoint was /mnt/x or /mnt/x/.
                break  # loop until first match, then abort

    if not mount_found:
        message =  f"RuntimeError: base path {demux.nird_base_upload_path} not found in mounted filesystems. Aborting."
        demuxLogger.critical( message )
        raise RuntimeError( message )

    try:
        os.mkdir(remote_absolute_dir_path)
    except FileExistsError:
        message = f"RuntimeError: {remote_absolute_dir_path} already exists.\nIs this a repeat upload? If yes, delete/move the existing remote directory and try again."
        demuxLogger.critical( message )
        raise RuntimeError( message )
    except FileNotFoundError:
        message = f"RuntimeError: Cannot create {remote_absolute_dir_path} because its parent directory ({os.path.dirname(remote_absolute_dir_path)}) does not exist on the mounted filesystem."
        demuxLogger.critical( message )
        raise RuntimeError( message)


def _ensure_remote_run_directory_ssh( demux ) -> None:
    """
    @in_use
    @needs_refactor
    Ensure the remote RunID upload directory exists, using SSH key authentication or 2FA.
    Credentials are chosen via user configuration.

    Opens a fresh SSH connection with strict known_hosts checking, validates that
    demux.nird_base_upload_path is non-empty then checks for the remote
    directory (base path + RunID). Creates it if missing; aborts if it already
    exists. Closes the SSH connection unconditionally.

    Raises:
        AuthenticationException: 2FA or credential failure.
        SSHException: remote command execution failure (directory existing)
        RuntimeException: everyting else that needs to percolate
        ValueError if demux.nird_base_upload_path is empty

    Returns:
        None
    """

    transport = None
    ssh_client = None

    # check if the '/nird/projects/NS9305K/SEQ-TECH/data_delivery' directory exists
    if not demux.nird_base_upload_path:
        message = f"ValueError: demux.nird_base_upload_path is empty: ({demux.nird_base_upload_path}). Refusing to continue, as any transfer will "
        message += "end up in the home directory of the uploading user."
        raise ValueError( message )
    
    # make sure the remote directory we will use is in absolute path
    remote_absolute_dir_path = os.path.join( demux.nird_base_upload_path, demux.RunID )
    if not os.path.isabs( remote_absolute_dir_path ):
        message = f"ValueError: {remote_absolute_dir_path} is not an absolute path. Refusing to continue, as any transfer will "
        message += "end up in the home directory of the uploading user."
        raise ValueError( message )

    try:
        transport = _get_transport( demux ) # this needs refactoring

        ssh_client = SSHClient( )
        ssh_client._transport = transport

        _ensure_remote_dir_via_client( demux, ssh_client, remote_absolute_dir_path )

    finally: # we enclosed the whole thing in a try/finally so we can close the client and the transport
        if ssh_client is not None:
            ssh_client.close( )
        elif transport is not None:
            transport.close( )


def _ensure_remote_run_directory( demux ):
    """
    @in_use
    Dispatch to the correct remote-directory preparation method
    based on NIRD access mode.
    """
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: checking if remote directrory exists started\n", color="green", attrs=["bold"] ) )

    if constants.NIRD_MODE_SSH == demux.nird_access_mode:
        _ensure_remote_run_directory_ssh( demux )

    elif constants.NIRD_MODE_SSH_2FA == demux.nird_access_mode:
        # this used to be named _ensure_remote_run_directory_ssh_2fa, but got refactored
        # down to credentials logic detected at run time. I am leaving the switch here for
        # verbocity, and to match the 3case we got for selecting a run mode.
        _ensure_remote_run_directory_ssh( demux )

    elif constants.NIRD_MODE_MOUNTED == demux.nird_access_mode:
        _ensure_remote_run_directory_mounted( demux )

    else:
        message = f"Unknown NIRD access mode: {demux.nird_access_mode}"
        demuxLogger.critical( message )
        raise RuntimeError( message )

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Preparing files for archiving to NIRD finished\n", color="red", attrs=["bold"] ) )
