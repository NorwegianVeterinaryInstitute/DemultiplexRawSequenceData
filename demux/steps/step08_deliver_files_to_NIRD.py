
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


def _upload_and_verify_file( demux, tar_file ):  # worker per file, tar_file is in absolute path format
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

        print( f"Transfering: {demux.absoluteFilesToTransferList[tar_file][ 'tar_file_local' ]}" )
        # test if the tar file we are about to upload exists already, to prevent overwriting
        stdin, stdout, stderr = ssh_client.exec_command( f"/usr/bin/test -f {shlex.quote( demux.absoluteFilesToTransferList[tar_file]['tar_file_remote'] )}" ) # we are not really doing anything with the stdin, stdout, stderr but keep them anyway
        if stdout.channel.recv_exit_status( ) == 0 : # file exists
            print( f"RuntimeError: Remote file already exists: {demux.hostname}:{demux.absoluteFilesToTransferList[tar_file]['tar_file_remote']}" )
            print( f"Refusing to overwrite. Delete/move remote file first and then try to upload again." )
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
                print( f"Error: Local md5 differs from calculated remote md5:" )
                print( f"LOCAL MD5:  {local_md5}\nREMOTE MD5: {remote_md5}" ) # extra space after LOCAL MD5 to align hashes for easier comparison
                print( f"Please check both files, delete/move as appropriate and try uploading again.")
                sys.exit(1)
            if local_sha512 != remote_sha512:
                print( f"Error: Local sha512 differs from calculated remote sha512:" )
                print( f"LOCAL SHA512:  {local_sha512}\nREMOTE SHA512: {sha512_file_remote}" ) # extra space after LOCAL SHA512 to align hashes for easier comparison
                print( f"Please check both files, delete/move as appropriate and try uploading again.")
                sys.exit(1)

            # for an explaination of why there is no point checksumming the checksum see
            # https://github.com/NorwegianVeterinaryInstitute/DemultiplexRawSequenceData/issues/26#issuecomment-3578085128
            scp_client.put( demux.absoluteFilesToTransferList[tar_file]['md5_file_local'],    demux.absoluteFilesToTransferList[tar_file]['md5_file_remote'] )
            scp_client.put( demux.absoluteFilesToTransferList[tar_file]['sha512_file_local'], demux.absoluteFilesToTransferList[tar_file]['sha512_file_remote'] )

            print( f"Done: LOCAL:{demux.absoluteFilesToTransferList[tar_file]['tar_file_local']:<{longest_local_path}} REMOTE:{demux.hostname}:{demux.absoluteFilesToTransferList[tar_file]['tar_file_remote']}" )


        except Exception as error:
            print( f"RuntimeError: SCP upload failed for {demux.hostname}:{demux.absoluteFilesToTransferList[tar_file]['tar_file_remote']}: {error}" )
            sys.exit( 1 )     

        ssh_client.close()


def _verify_local_files( demux ):
    """
    Verifies that all three required local files exist for every tar entry in absoluteFilesToTransferList: the tar file,
    its .md5, and its .sha512 file. Exits immediately on the first missing file.
    """

    for entry in demux.absoluteFilesToTransferList.values( ):
        if not os.path.exists( entry[ 'tar_file_local' ] ):
            print( f"File {entry[ 'tar_file_local' ]} does not exist. Check for the existanse of the file and try again." )
            sys.exit(1)
        if not os.path.exists( entry[ 'md5_file_local' ] ):
            print( f"File {entry[ 'md5_file_local' ]} does not exist. Check for the file and try again." )
            sys.exit(1)
        if not os.path.exists( entry[ 'sha512_file_local' ] ):
            print( f"File {entry[ 'sha512_file_local' ]} does not exist. Check for the file and try again." )
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

    local_base  = os.path.join( demux.forTransferDir,        demux.RunID )
    remote_base = os.path.join( demux.nird_base_upload_path, demux.RunID )

    for tar_file in demux.tarFilesToTransferList:
        # so here is a wierd one that took me two days to debug: if both paths are in absolute format,
        # the last absolute path is returned and everything else is thrown away...
        # demux.tarFilesToTransferList is already in absolute format, so this threw me the fuck off,
        # returned only tar_file
        # https://docs.python.org/3/library/os.path.html#os.path.join
        #   "If a segment is an absolute path (which on Windows requires both a drive and a root), then 
        # all previous segments are ignored and joining continues from the absolute path segment."
        # So it returned tar_file only, fuuuuuuuuu
        # So since we might meet demux.tarFilesToTransferList elsewhere, i am stripping here the absolute path
        # and allowing the tar files to still remain in absolut format
        basenamed_tar_file = os.path.basename( tar_file )
        demux.absoluteFilesToTransferList[ tar_file ] = {
            'tar_file_local':     os.path.join( local_base,  basenamed_tar_file ),
            'tar_file_remote':    os.path.join( remote_base, basenamed_tar_file ),
            'md5_file_local':     os.path.join( local_base,  basenamed_tar_file ) + constants.MD5_SUFFIX,
            'md5_file_remote':    os.path.join( remote_base, basenamed_tar_file ) + constants.MD5_SUFFIX,
            'sha512_file_local':  os.path.join( local_base,  basenamed_tar_file ) + constants.SHA512_SUFFIX,
            'sha512_file_remote': os.path.join( remote_base, basenamed_tar_file ) + constants.SHA512_SUFFIX,
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
        print( f"RuntimeError: {demux.hostname}:{remote_absolute_dir_path} already exists." )
        print( f"Is this a repeat upload? If yes, delete/move the existing remote directory and try again." )
        sys.exit( 1 )

    ssh_client.close() # close for the commands we will open the same connection in the loop, so we can parallelize the  connections.

########################################################################
# deliver_files_to_NIRD
########################################################################

def deliver_files_to_NIRD( demux ):
    """
    Make connection to NIRD and upload the data
    # the idea is to to 
    # 1. check if the remore the remote directory exists
    # 2.    create if not
    # 3. check status of local tar files in demux.tarFilesToTransferList
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


    # serial version
    # for tar_file in demux.tarFilesToTransferList: # for each tar file open a new ssh connection so, we can parallelize transfer
    #     _upload_and_verify_file( demux, tar_file )

    # parallel version
    with ThreadPoolExecutor( max_workers = len( demux.tarFilesToTransferList ) ) as pool:
        futures = [
            pool.submit(_upload_and_verify_file, demux, tar_file ) for tar_file in demux.tarFilesToTransferList
        ]
        for future in futures:
            future.result( )

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Preparing files for archiving to NIRD finished\n", color="red", attrs=["bold"] ) )
