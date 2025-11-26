import hashlib
import os
import shlex
import sys

from paramiko import SSHClient, SSHConfig, AutoAddPolicy, RejectPolicy
from scp import SCPClient

from concurrent.futures import ThreadPoolExecutor

from demux.loggers      import demuxLogger, demuxFailureLogger

class demux: 

    RunID                   = "251110_M09180_0048_000000000-M7V7K"
    originating_directory   = "/data/for_transfer/251110_M09180_0048_000000000-M7V7K"
    projectList             = [ '21217', '23015', '31218', '330403', '0048' ]
    tarFilesToTransferList  = [ '251110_M09180.21217-Sta-faar-eus_Staphylococcus.tar',
                                '251110_M09180.23015-APEC_Escherichia.tar',
                                '251110_M09180.31218-INIKA_Escherichia.tar',
                                '251110_M09180.31218-INIKA_Klebsiella.tar', 
                                '251110_M09180.330403-001-A4-GENSURV_Escherichia.tar',
                                '251110_M09180_0048_000000000-M7V7K_qc.tar'
                            ]

    fortransfer_directory   = f"/data/for_transfer/{RunID}"
    nird_upload_host        = "laptop"
    nird_scp_port           = "22" # https://documentation.sigma2.no/getting_help/two_factor_authentication.html#how-to-copy-files-without-using-2fa-otp
    nird_username           = "gmarselis"
    nird_base_upload_path   = "/data/for_transfer/tmp"
    nird_key_filename       = "/home/gmarselis/.ssh/id_ed25519.3jane"

    MD5_SUFFIX              = ".md5"
    MD5_LENGTH              = 16  # 128 bits
    SHA512_SUFFIX           = ".sha512"
    SHA512_LENGTH           = 64  # 512 bits


def _upload_one(local_path):  # worker per file
    """
    _upload_one uploads a single local tar file to the NIRD absolute upload path using the existing SSH transport.
    """
    try:
        with SCPClient( ssh_client.get_transport( ) ) as scp_client:
            remote_path = os.path.join( nird_upload_path, os.path.basename( local_path ) )
            scp_client.put( local_path, remote_path )
    except Exception as error:
        raise RuntimeError(f"SCP upload failed for {local_path}: {error}")

def compute_remote_sha512( ssh_client, remote_path ): 
    command = f"sha256sum {shlex.quote(remote_path)}"
    stdin, stdout, stderr = ssh_client.exec_command( command )
    return stdout.read().decode().split()[0]

def _build_absolute_paths( demux ):
    """
    Builds and returns a dictonary mapping each tar filename to its full local and remote paths,
    including the associated .md5 and .sha512 files.
    """
    absoluteFilesToTransferList = { }

    for tar_file in demux.tarFilesToTransferList:
        local_base  = os.path.join( demux.fortransfer_directory, tar_file )
        remote_base = os.path.join( demux.nird_base_upload_path, demux.RunID, tar_file )
        absoluteFilesToTransferList[ tar_file ] = {
            'tar_file_local':     local_base,
            'tar_file_remote':    remote_base,
            'md5_file_local':     local_base  + demux.MD5_SUFFIX,
            'md5_file_remote':    remote_base + demux.MD5_SUFFIX,
            'sha512_file_local':  local_base  + demux.SHA512_SUFFIX,
            'sha512_file_remote': remote_base + demux.SHA512_SUFFIX,
        }
    return absoluteFilesToTransferList


def _verify_local_files( absoluteFilesToTransferList ):
    """
    Verifies that all three required local files exist for every tar entry in absoluteFilesToTransferList: the tar file,
    its .md5, and its .sha512 file. Exits immediately on the first missing file.
    """
    for entry in absoluteFilesToTransferList.values( ):
        if not os.path.exists( entry[ 'tar_file_local' ] ):
            print( f"File {entry[ 'tar_file_local' ]} does not exist. Check for the existanse of the file and try again." )
            sys.exit(1)
        if not os.path.exists( entry[ 'md5_file_local' ] ):
            print( f"File {entry[ 'md5_file_local' ]} does not exist. Check for the file and try again." )
            sys.exit(1)
        if not os.path.exists( entry[ 'sha512_file_local' ] ):
            print( f"File {entry[ 'sha512_file_local' ]} does not exist. Check for the file and try again." )
            sys.exit(1)



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
    demuxLogger.info( f"==> {demux.n}/{demux.totalTasks} tasks: Preparing files for archiving to NIRD started\n")

    config_path = os.path.expanduser( "~/.ssh/config" ) # this needs to be infered from environment somehow https://github.com/NorwegianVeterinaryInstitute/DemultiplexRawSequenceData/issues/138
    host_config = {}

    if os.path.exists( config_path ):
        with open( config_path ) as handle:
            ssh_config = SSHConfig( )
            ssh_config.parse( handle )
        host_cfg = ssh_config.lookup( demux.nird_upload_host )

    hostname = host_cfg.get( "hostname", demux.nird_upload_host )
    username = host_cfg.get( "user", demux.nird_username ) 
    key_file = host_cfg.get( "identityfile", [ demux.nird_key_filename ] )[0]  # must have arrays, incase there are more than 1 identity files. therefore we encase the default key filename in an array, itself
    port     = int( host_cfg.get( "port", demux.nird_scp_port ) )

    ssh_client = SSHClient( )
    ssh_client.load_system_host_keys( )

    # Check if the key already exists in the known_hosts 
    #   else reject the connection.
    if ssh_client._system_host_keys.lookup( hostname ) is None:
        raise RuntimeError( f"Host key for {hostname} not found in known_hosts" )

    # ssh_client.set_missing_host_key_policy( AutoAddPolicy( ) )
    ssh_client.set_missing_host_key_policy( RejectPolicy( ) ) # do not accept host keys that are not already in place
    ssh_client.connect( hostname = hostname, port = port, username = username, key_filename = key_file )

    # check if the '/nird/projects/NS9305K/SEQ-TECH/data_delivery' + runID directory exists
    #   it does issue warning
    #   if it does not, make it

    remote_absolute_dir_path = os.path.join( demux.nird_base_upload_path, demux.RunID ) 
    stdin, stdout, stderr    = ssh_client.exec_command( f"TERM=xterm /usr/bin/test -d {shlex.quote( remote_absolute_dir_path )}" ) # we are not really doing anything with the stdin, stdout, stderr but keep them anyway

    if stdout.channel.recv_exit_status( ) != 0 : # directory exists
        ssh_client.exec_command( f'TERM=xterm /usr/bin/mkdir -p {shlex.quote( remote_absolute_dir_path )}' )
    else:
        print( f"RuntimeError: {hostname}:{remote_absolute_dir_path} already exists." )
        print( f"Is this a repeat upload? If yes, delete/move the existing remote directory and try again." )
        sys.exit( 1 )

    # break this down in 2 parts: absoluteTarFilesToTransferList, check existance of local files
    absoluteFilesToTransferList = _build_absolute_paths( demux ) # returns a dictonary with the absolute paths of all files involved
    _verify_local_files( absoluteFilesToTransferList )           # verify that the local files exist before attempting to transfer them
    # Find the longest string in absoluteFilesToTransferList and tabulate for that
    longest_local_path = max( len( item['tar_file_local'] ) for item in absoluteFilesToTransferList.values( ) )

    with SCPClient( ssh_client.get_transport( ) ) as scp_client:

        for tar_file in demux.tarFilesToTransferList:

            print( f"LOCAL:{absoluteFilesToTransferList[tar_file]['tar_file_local']:<{longest_local_path}} REMOTE:{hostname}:{absoluteFilesToTransferList[tar_file]['tar_file_remote']}" )
            # test if the tar file we are about to upload exists already, to prevent overwriting
            stdin, stdout, stderr = ssh_client.exec_command( f"/usr/bin/test -f {shlex.quote( absoluteFilesToTransferList[tar_file]['tar_file_remote'] )}" ) # we are not really doing anything with the stdin, stdout, stderr but keep them anyway
            if stdout.channel.recv_exit_status( ) == 0 : # file exists
                print( f"RuntimeError: Remote file already exists: {hostname}:{absoluteFilesToTransferList[tar_file]['tar_file_remote']}" )
                print( f"Refusing to overwrite. Delete/move remote file first and then try to upload again." )
                sys.exit( 1 )

            try:
                # upload file
                scp_client.put( absoluteFilesToTransferList[tar_file]['tar_file_local'], absoluteFilesToTransferList[tar_file]['tar_file_remote'] )
                # calculate remote checksum via md5
                # calculate remote checksum via sha512
                # check md5 checksum
                # check sha512 checksum
                # copy the file
                # copy the md5 file
                # copy the sha512 file
                md5sum_stdin,    md5sum_stdout,    md5sum_stderr    = ssh_client.exec_command( f"/usr/bin/md5sum {shlex.quote( absoluteFilesToTransferList[tar_file]['tar_file_remote'] )}" )    # we are not really doing anything with the stdin, stdout, stderr but keep them anyway
                sha512sum_stdin, sha512sum_stdout, sha512sum_stderr = ssh_client.exec_command( f"/usr/bin/sha512sum {shlex.quote( absoluteFilesToTransferList[tar_file]['tar_file_remote'] )}" ) # we are not really doing anything with the stdin, stdout, stderr but keep them anyway

                remote_md5    = md5sum_stdout.read( ).decode( ).split( )[0]
                remote_sha512 = sha512sum_stdout.read( ).decode( ).split( )[0]
                local_md5    = open( absoluteFilesToTransferList[tar_file]['md5_file_local'] ).read( ).split( )[0]
                local_sha512 = open( absoluteFilesToTransferList[tar_file]['sha512_file_local'] ).read( ).split( )[0]

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
                scp_client.put( absoluteFilesToTransferList[tar_file]['md5_file_local'],    absoluteFilesToTransferList[tar_file]['md5_file_remote'] )
                scp_client.put( absoluteFilesToTransferList[tar_file]['sha512_file_local'], absoluteFilesToTransferList[tar_file]['sha512_file_remote'] )

            except Exception as error:
                print( f"RuntimeError: SCP upload failed for {hostname}:{absoluteFilesToTransferList[tar_file]['tar_file_remote']}: {error}" )
                sys.exit( 1 )     

        # with ThreadPoolExecutor(max_workers=min(5, len(demux.tarFilesToTransferList))) as pool: list(pool.map(upload_one, demux.tarFilesToTransferList))
        # checksum_local, checksum_remote = compute_local_sha512( local_path ), compute_remote_sha512(ssh_client, remote_path);
        # assert checksum_local == checksum_remote, f"Checksum mismatch for {local_path}:  {checksum_local} != {checksum_remote}"

    ssh_client.close()

    demuxLogger.info( f"==< {demux.n}/{demux.totalTasks} tasks: Preparing files for archiving to NIRD finished\n")

