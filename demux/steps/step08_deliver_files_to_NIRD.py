import hashlib
import os
import shlex
import sys
import termcolor
import pprint

from paramiko import SSHClient, SSHConfig, AutoAddPolicy, RejectPolicy
from scp import SCPClient

from concurrent.futures import ThreadPoolExecutor

from demux.config  import constants
from demux.loggers import demuxLogger, demuxFailureLogger

def _upload_and_verify_file_via_ssh( demux, tar_file ):  # worker per file, tar_file is in absolute path format
    """
    Upload and verify a single local tar file to the NIRD absolute upload path using a new SSH transport each time.
    """
    ssh_client = SSHClient( )
    ssh_client.load_system_host_keys( )
    # Check if the key already exists in the known_hosts 
    #   else reject the connection.
    if ssh_client._system_host_keys.lookup( demux.hostname ) is None:
        raise RuntimeError( f"Host key for {demux.hostname} not found in known_hosts" )

    # ssh_client.set_missing_host_key_policy( AutoAddPolicy( ) )
    ssh_client.set_missing_host_key_policy( RejectPolicy( ) ) # do not accept host keys that are not already in place
    ssh_client.connect( hostname = demux.hostname, port = demux.port, username = demux.username, key_filename = demux.key_file )
    # Find the longest string in demux.absoluteFilesToTransferList and tabulate for that
    longest_local_path = max( len( item['tar_file_local'] ) for item in demux.absoluteFilesToTransferList.values( ) )

    with SCPClient( ssh_client.get_transport( ) ) as scp_client:

        demuxLogger.info( f"Transfering: {demux.absoluteFilesToTransferList[tar_file][ 'tar_file_local' ]}" )
        # test if the tar file we are about to upload exists already, to prevent overwriting
        stdin, stdout, stderr = ssh_client.exec_command( f"/usr/bin/test -f {shlex.quote( demux.absoluteFilesToTransferList[tar_file]['tar_file_remote'] )}" ) # we are not really doing anything with the stdin, stdout, stderr but keep them anyway
        if stdout.channel.recv_exit_status( ) == 0 : # file exists
            demuxLogger.critical( f"RuntimeError: Remote file already exists: {demux.hostname}:{demux.absoluteFilesToTransferList[tar_file]['tar_file_remote']}" )
            demuxLogger.critical( f"Refusing to overwrite. Delete/move remote file first and then try to upload again." )
            sys.exit( 1 )

        try:
            # upload file
            scp_client.put( demux.absoluteFilesToTransferList[tar_file]['tar_file_local'], demux.absoluteFilesToTransferList[tar_file]['tar_file_remote'] )
            # calculate remote checksum via md5
            # calculate remote checksum via sha512
            # check md5 checksum; check sha512 checksum
            # copy the tar file, the md5 file and then the sha512 file
            md5sum_stdin,    md5sum_stdout,    md5sum_stderr    = ssh_client.exec_command( f"/usr/bin/md5sum {shlex.quote( demux.absoluteFilesToTransferList[tar_file]['tar_file_remote'] )}" )    # we are not really doing anything with the stdin, stdout, stderr but keep them anyway
            sha512sum_stdin, sha512sum_stdout, sha512sum_stderr = ssh_client.exec_command( f"/usr/bin/sha512sum {shlex.quote( demux.absoluteFilesToTransferList[tar_file]['tar_file_remote'] )}" ) # we are not really doing anything with the stdin, stdout, stderr but keep them anyway

            remote_md5    = md5sum_stdout.read( ).decode( ).split( )[0]
            remote_sha512 = sha512sum_stdout.read( ).decode( ).split( )[0]
            local_md5    = open( demux.absoluteFilesToTransferList[tar_file]['md5_file_local'] ).read( ).split( )[0]
            local_sha512 = open( demux.absoluteFilesToTransferList[tar_file]['sha512_file_local'] ).read( ).split( )[0]

            if local_md5 != remote_md5:
                demuxLogger.critical( f"Error: Local md5 differs from calculated remote md5:" )
                demuxLogger.critical( f"LOCAL MD5:  {local_md5}\nREMOTE MD5: {remote_md5}" ) # extra space after LOCAL MD5 to align hashes for easier comparison
                demuxLogger.critical( f"Please check both files, delete/move as appropriate and try uploading again.")
                sys.exit(1)
            if local_sha512 != remote_sha512:
                demuxLogger.critical( f"Error: Local sha512 differs from calculated remote sha512:" )
                demuxLogger.critical( f"LOCAL SHA512:  {local_sha512}\nREMOTE SHA512: {sha512_file_remote}" ) # extra space after LOCAL SHA512 to align hashes for easier comparison
                demuxLogger.critical( f"Please check both files, delete/move as appropriate and try uploading again.")
                sys.exit(1)

            # for an explaination of why there is no point checksumming the checksum see
            # https://github.com/NorwegianVeterinaryInstitute/DemultiplexRawSequenceData/issues/26#issuecomment-3578085128
            scp_client.put( demux.absoluteFilesToTransferList[tar_file]['md5_file_local'],    demux.absoluteFilesToTransferList[tar_file]['md5_file_remote'] )
            scp_client.put( demux.absoluteFilesToTransferList[tar_file]['sha512_file_local'], demux.absoluteFilesToTransferList[tar_file]['sha512_file_remote'] )

            demuxLogger.info( f"Done: LOCAL:{demux.absoluteFilesToTransferList[tar_file]['tar_file_local']:<{longest_local_path}} REMOTE:{demux.hostname}:{demux.absoluteFilesToTransferList[tar_file]['tar_file_remote']}" )


        except Exception as error:
            demuxLogger.critical( f"RuntimeError: SCP upload failed for {demux.hostname}:{demux.absoluteFilesToTransferList[tar_file]['tar_file_remote']}: {error}" )
            sys.exit( 1 )     

        ssh_client.close()


def _upload_and_verify_file_via_local_sshfs_mount( demux, tar_file ):
    """
    Upload and verify a single local tar file to NIRD via an already-mounted sshfs path.
    """
    file_info = demux.absoluteFilesToTransferList[tar_file]
    longest_local_path = max( len( item[ 'tar_file_local' ] ) for item in demux.absoluteFilesToTransferList.values( ) )

    if os.path.exists( file_info[ 'tar_file_remote' ] ):
        demuxLogger.critical( f"RuntimeError: Remote file already exists: {file_info[ 'tar_file_remote' ]} ")
        demuxLogger.critical( "Refusing to overwrite. Delete/move remote file first and then try to upload again." )
        sys.exit( 1 )

    READ_BINARY = "rb"

    try:
        shutil.copy2( file_info[ 'tar_file_local' ], file_info[ 'tar_file_remote' ] )  # requires import shutil

        with open( file_info[ 'tar_file_remote' ], READ_BINARY ) as remote_handle:
            remote_md5 = hashlib.file_digest( remote_handle, hashlib.md5( ) ).hexdigest( )
        with open( file_info[ 'tar_file_remote' ], READ_BINARY ) as remote_handle:
            remote_sha512 = hashlib.file_digest( remote_handle, hashlib.sha512( ) ).hexdigest( )

        local_md5 = open(file_info[ 'md5_file_local' ] ).read( ).split( )[0]
        local_sha512 = open(file_info[ 'sha512_file_local' ] ).read( ).split( )[0]

        if local_md5 != remote_md5:
            demuxLogger.critical( "Error: Local md5 differs from calculated remote md5:" )
            demuxLogger.critical( f"LOCAL MD5:  {local_md5}\nREMOTE MD5: {remote_md5}" )
            demuxLogger.critical( "Please check both files, delete/move as appropriate and try uploading again." )
            sys.exit( 1 )

        if local_sha512 != remote_sha512:
            demuxLogger.critical( "Error: Local sha512 differs from calculated remote sha512:" )
            demuxLogger.critical( f"LOCAL SHA512:  {local_sha512}\nREMOTE SHA512: {remote_sha512}" )
            demuxLogger.critical( "Please check both files, delete/move as appropriate and try uploading again." )
            sys.exit( 1 )

        shutil.copy2( file_info[ 'md5_file_local' ], file_info[ 'md5_file_remote' ] )
        shutil.copy2( file_info[ 'sha512_file_local' ], file_info[ 'sha512_file_remote' ] )

        demuxLogger.info(
            f"Done: LOCAL:{file_info[ 'tar_file_local' ]:<{longest_local_path}}"
            f"REMOTE:{file_info['tar_file_remote']}"
        )

    except Exception as error:
        demuxLogger.critical( f"RuntimeError: local sshfs upload failed for {file_info[ 'tar_file_remote' ]}: {error}" )
        sys.exit( 1 )





def _upload_files_to_nird( demux ):
    """
    Select the appropriate upload function based on NIRD access mode and execute all file transfers in either serial or parallel form.
    """

    # choose upload implementation
    if demux.nird_access_mode == demux.NIRD_MODE_SSH:
        upload_func = _upload_and_verify_file_via_ssh
    elif demux.nird_access_mode == demux.NIRD_MODE_MOUNTED:
        upload_func = _upload_and_verify_file_via_local_sshfs_mount
    else:
        demuxLogger.critical( f"Unknown NIRD access mode: {demux.nird_access_mode}" )
        sys.exit( 1 )

    # serial / parallel switching
    if demux.copy_method == demux.SERIAL_COPYING:
        for tar_file in demux.tarFilesToTransferList:
            upload_func(demux, tar_file)

    elif demux.copy_method == demux.PARALLEL_COPYING:
        with ThreadPoolExecutor(max_workers=len(demux.tarFilesToTransferList)) as pool:
            futures = [
                pool.submit(upload_func, demux, tar_file)
                for tar_file in demux.tarFilesToTransferList
            ]
            for future in futures:
                future.result()



def _verify_local_files( demux ):
    """
    Verifies that all three required local files exist for every tar entry in absoluteFilesToTransferList: the tar file,
    its .md5, and its .sha512 file. Exits immediately on the first missing file.
    """

    for entry in demux.absoluteFilesToTransferList.values( ):
        if not os.path.exists( entry[ 'tar_file_local' ] ):
            demuxLogger.critical( f"File {entry[ 'tar_file_local' ]} does not exist. Check for the existanse of the file and try again." )
            sys.exit(1)
        if not os.path.exists( entry[ 'md5_file_local' ] ):
            demuxLogger.critical( f"File {entry[ 'md5_file_local' ]} does not exist. Check for the file and try again." )
            sys.exit(1)
        if not os.path.exists( entry[ 'sha512_file_local' ] ):
            demuxLogger.critical( f"File {entry[ 'sha512_file_local' ]} does not exist. Check for the file and try again." )
            sys.exit(1)


def _setup_ssh_connection( demux ):
    """
    Parse ~/.ssh/config and initializes appropriate demux fields using the ssh config entry for the upload host.
    If missing, method falls back to demux defaults.
    """
    config_path = os.path.expanduser( "~/.ssh/config" ) # this needs to be infered from environment somehow https://github.com/NorwegianVeterinaryInstitute/DemultiplexRawSequenceData/issues/138
    host_config = { }

    if os.path.exists( config_path ):
        with open( config_path ) as handle:
            ssh_config = SSHConfig( )
            ssh_config.parse( handle )
        host_config = ssh_config.lookup( demux.nird_upload_host )

    # more stuff that can be thrown into initilization of demux
    demux.hostname = host_config.get( "hostname", demux.nird_upload_host )
    demux.username = host_config.get( "user", demux.nird_username ) 
    demux.key_file = host_config.get( "identityfile", [ demux.nird_key_filename ] )[0]  # must have arrays, incase there are more than 1 identity files. therefore we encase the default key filename in an array, itself
    demux.port     = int( host_config.get( "port", demux.nird_scp_port ) )


def _build_absolute_paths( demux ):
    """
    Builds and returns a dictonary mapping each tar filename to its full local and remote paths,
    including the associated .md5 and .sha512 files.
    """

    if demux.NIRD_MODE_MOUNTED == demux.nird_access_mode:
        demux.nird_base_upload_path = demux.nird_base_upload_path_local
    elif demux.NIRD_MODE_SSH == demux.nird_access_mode:
        demux.nird_base_upload_path = demux.nird_base_upload_path_ssh

    local_base  = os.path.join( demux.forTransferDir,        demux.RunID )
    remote_base = os.path.join( demux.nird_base_upload_path, demux.RunID )

    for tar_file in demux.tarFilesToTransferList:
        # so here is a weird one that took me two days to debug: if both paths are in absolute format,
        # the last absolute path is returned and everything else is thrown away...
        # demux.tarFilesToTransferList is already in absolute format, so this threw me the fuck off,
        # returned only tar_file
        # https://docs.python.org/3/library/os.path.html#os.path.join
        #   "If a segment is an absolute path (which on Windows requires both a drive and a root), then 
        # all previous segments are ignored and joining continues from the absolute path segment."
        # So it returned tar_file only, fuuuuuuuuu
        # So since we might meet demux.tarFilesToTransferList elsewhere, i am stripping here the absolute path
        # and allowing the tar files to still remain in absolute format
        basenamed_tar_file = os.path.basename( tar_file )
        demux.absoluteFilesToTransferList[ tar_file ] = {
            'tar_file_local':     os.path.join( local_base,  basenamed_tar_file ),
            'tar_file_remote':    os.path.join( remote_base, basenamed_tar_file ),
            'md5_file_local':     os.path.join( local_base,  basenamed_tar_file ) + constants.MD5_SUFFIX,
            'md5_file_remote':    os.path.join( remote_base, basenamed_tar_file ) + constants.MD5_SUFFIX,
            'sha512_file_local':  os.path.join( local_base,  basenamed_tar_file ) + constants.SHA512_SUFFIX,
            'sha512_file_remote': os.path.join( remote_base, basenamed_tar_file ) + constants.SHA512_SUFFIX,
            # 'upload_to_nird' exists already, we are just adding here
        }


def _ensure_remote_run_directory( demux ):
    """
    Ensure the remote run directory exists by opening a fresh SSH connection, validating host keys, creating the directory if missing and aborting if it already exists.
    """

    ssh_client = SSHClient( )
    ssh_client.load_system_host_keys( )
    # Check if the key already exists in the known_hosts 
    #   else reject the connection.
    if ssh_client._system_host_keys.lookup( demux.hostname ) is None:
        raise RuntimeError( f"Host key for {demux.hostname} not found in known_hosts" )

    ssh_client.set_missing_host_key_policy( RejectPolicy( ) )      # do not accept host keys that are not already in place
    ssh_client.connect( hostname = demux.hostname, port = demux.port, username = demux.username, key_filename = demux.key_file )

    # check if the '/nird/projects/NS9305K/SEQ-TECH/data_delivery' + runID directory exists
    remote_absolute_dir_path = os.path.join( demux.nird_base_upload_path, demux.RunID ) 
    stdin, stdout, stderr    = ssh_client.exec_command( f"TERM=xterm /usr/bin/test -d {shlex.quote( remote_absolute_dir_path )}" ) # we are not really doing anything with the stdin, stdout, stderr but keep them anyway

    if stdout.channel.recv_exit_status( ) != 0 : # directory exists
        ssh_client.exec_command( f'TERM=xterm /usr/bin/mkdir -p {shlex.quote( remote_absolute_dir_path )}' )
    else:
        demuxLogger.critical( f"RuntimeError: {demux.hostname}:{remote_absolute_dir_path} already exists." )
        demuxLogger.critical( f"Is this a repeat upload? If yes, delete/move the existing remote directory and try again." )
        sys.exit( 1 )

    ssh_client.close() # close for the commands we will open the same connection in the loop, so we can parallelize the  connections.

########################################################################
# deliver_files_to_NIRD
########################################################################

def deliver_files_to_NIRD( demux ):
    """
    Make connection to NIRD and upload the data
    # the idea is to to 
    # 1. check status of local tar files in demux.tarFilesToTransferList
    # 2. check if the remore the remote directory exists
    # 3.    create if not
    # 4. take each of the files in demux.tarFilesToTransferList and upload them
    #   4.1 in parallel
    # 5. check the remote sha512 and see if it matches local.

    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Preparing files for archiving to NIRD started\n", color="green", attrs=["bold"] ) )

    _setup_ssh_connection( demux )          # setup the ssh connection details
    _build_absolute_paths( demux )          # creates the demux absoluteFilesToTransferList dictonary with the absolute paths of all files involved
    _ensure_remote_run_directory( demux )   # make sure demux.nird_base_upload_path/demux.RunID exists
    _verify_local_files( demux )            # verify the local files exist before attempting to transfer them
    _upload_files_to_nird( demux )          # send the demux object to a dedicated method and it will decide what mode of copying and type of upload it will use

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Preparing files for archiving to NIRD finished\n", color="red", attrs=["bold"] ) )
