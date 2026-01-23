
def _verify_local_files( demux ):
    """
    @in_use
    
    Verifies that all three required local files exist for every tar entry in absoluteFilesToTransferList: the tar file,
    its .md5, and its .sha512 file. Exits immediately on the first missing file.
    """

    message = ""

    for entry in demux.absoluteFilesToTransferList.values( ):
        if not os.path.exists( entry[ 'tar_file_local' ] ):
            message = f"File {entry[ 'tar_file_local' ]} does not exist. Check for the existanse of the file and try again."
            demuxLogger.critical( message )
            raise FileNotFoundError( message )
        if not os.path.exists( entry[ 'md5_file_local' ] ):
            message = f"File {entry[ 'md5_file_local' ]} does not exist. Check for the file and try again."
            demuxLogger.critical( message )
            raise FileNotFoundError( message )
        if not os.path.exists( entry[ 'sha512_file_local' ] ):
            message = f"File {entry[ 'sha512_file_local' ]} does not exist. Check for the file and try again."
            demuxLogger.critical( message )
            raise FileNotFoundError( message )
