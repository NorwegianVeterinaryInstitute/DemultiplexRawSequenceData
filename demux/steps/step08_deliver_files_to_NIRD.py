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
    md5List                 = [ '251110_M09180.21217-Sta-faar-eus_Staphylococcus.tar.md5',
                              '251110_M09180.23015-APEC_Escherichia.tar.md5',
                              '251110_M09180.31218-INIKA_Escherichia.tar.md5',
                              '251110_M09180.31218-INIKA_Klebsiella.tar.md5', 
                              '251110_M09180.330403-001-A4-GENSURV_Escherichia.tar.md5',
                              '251110_M09180_0048_000000000-M7V7K_qc.tar.md5'
                            ]
    sha512List              = [ '251110_M09180.21217-Sta-faar-eus_Staphylococcus.tar.sha512',
                              '251110_M09180.23015-APEC_Escherichia.tar.sha512',
                              '251110_M09180.31218-INIKA_Escherichia.tar.sha512',
                              '251110_M09180.31218-INIKA_Klebsiella.tar.sha512', 
                              '251110_M09180.330403-001-A4-GENSURV_Escherichia.tar.sha512',
                              '251110_M09180_0048_000000000-M7V7K_qc.tar.sha512'
                            ]
    tarFilesToTransferList  = [ '251110_M09180.21217-Sta-faar-eus_Staphylococcus.tar',
                              '251110_M09180.23015-APEC_Escherichia.tar',
                              '251110_M09180.31218-INIKA_Escherichia.tar',
                              '251110_M09180.31218-INIKA_Klebsiella.tar', 
                              '251110_M09180.330403-001-A4-GENSURV_Escherichia.tar',
                              '251110_M09180_0048_000000000-M7V7K_qc.tar'
                            ]
    fortransfer_directory           = f"/data/for_transfer/{RunID}"
    nird_upload_host                = "laptop"
    nird_scp_port                   = "22" # https://documentation.sigma2.no/getting_help/two_factor_authentication.html#how-to-copy-files-without-using-2fa-otp
    nird_username                   = "gmarselis"
    nird_base_upload_path           = "/data/for_transfer/tmp"
    nird_key_filename               = "/home/gmarselis/.ssh/id_ed25519.3jane"





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


def _compute_local_sha256( local_path ): 
    hash_obj = hashlib.sha256( )
    with open( local_path, "rb" ) as handle:
        for chunk in iter( lambda: handle.read( 1048576 ), b"" ): 
            hash_obj.update(chunk)
            return hash_obj.hexdigest()

def compute_remote_sha512( ssh_client, remote_path ): 
    command = f"sha256sum {shlex.quote(remote_path)}"
    stdin, stdout, stderr = ssh_client.exec_command(command)
    return stdout.read().decode().split()[0]


########################################################################
# deliver_files_to_NIRD
########################################################################

def deliver_files_to_NIRD( demux ):
    """
    Make connection to NIRD and upload the data
    """
    demux.n = demux.n + 1
    demuxLogger.info( f"==> {demux.n}/{demux.totalTasks} tasks: Preparing files for archiving to NIRD started\n")

    # the idea is to to 
    # 1. check if the remore the remote directory exists
    # 2.    create if not
    # 3. check status of local tar files in demux.tarFilesToTransferList
    # 4. take each of the files in demux.tarFilesToTransferList and upload them 
    #   4.1 in parallel
    # 5. check the remote sha512 and see if it matches local.

    config_path = os.path.expanduser( "~/.ssh/config" )
    host_config = {}

    if os.path.exists( config_path ):
        with open( config_path ) as handle:
            ssh_config = SSHConfig( )
            ssh_config.parse( handle )
        host_cfg = ssh_config.lookup( demux.nird_upload_host )

    hostname = ""
    username = ""
    key_file = ""
    port     = int ( )
    port     = int( host_cfg.get( "port", demux.nird_scp_port ) )
    hostname = host_cfg.get( "hostname", demux.nird_upload_host )
    username = host_cfg.get( "user", demux.nird_username ) 
    key_file = host_cfg.get( "identityfile", [ demux.nird_key_filename ] )[0]

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
    stdin, stdout, stderr     = ssh_client.exec_command( f'TERM=xterm /usr/bin/test -d {shlex.quote( remote_absolute_dir_path )}' ) # we are nto really doing anything with the stdin, stdout, stderr but keep them anyway

    if stdout.channel.recv_exit_status( ) != 0 : # directory exists
        ssh_client.exec_command( f'TERM=xterm /usr/bin/mkdir -p {shlex.quote( remote_absolute_dir_path )}' )
    else:
        print( f"RuntimeError: {hostname}:{remote_absolute_dir_path} already exists." )
        print( f"Is this a repeat upload? If yes, delete/move the existing remote directory and try again." )
        sys.exit( 1 )

    with SCPClient(ssh_client.get_transport()) as scp_client:

        for tar_file in demux.tarFilesToTransferList:

            # construct the ABSOLUTE remote tar file name
            # Usingf the ABSOLUTE PATH IS ESSENTIAL! otherwise SCP will drop everything in $HOME ! 
            tar_file_local  = os.path.join( demux.fortransfer_directory, tar_file )
            tar_file_remote = os.path.join( remote_absolute_dir_path, tar_file )

            print( f"LOCAL:{tar_file_local}\t\t\tREMOTE:{hostname}:{tar_file_remote}" )

            # prevent overwriting.
            # test if the tar file we are about to upload exists already
            stdin, stdout, stderr = ssh_client.exec_command( f'/usr/bin/test -f {shlex.quote( tar_file_remote )}' ) # we are nto really doing anything with the stdin, stdout, stderr but keep them anyway
            if stdout.channel.recv_exit_status( ) == 0 : # file exists
                print( f"RuntimeError: Remote file already exists: {hostname}:{tar_file_remote}" )
                print( f"Refusing to overwrite. Delete/ remote file first and then try to upload again." )
                sys.exit( 1 )
            # copy the file
            try:
                scp_client.put( tar_file_local, tar_file_remote )
            except Exception as error:
                print( f"RuntimeError: SCP upload failed for {hostname}:{tar_file_remote}: {error!r}" )
                sys.exit( 1 )     

        # with ThreadPoolExecutor(max_workers=min(5, len(demux.tarFilesToTransferList))) as pool: list(pool.map(upload_one, demux.tarFilesToTransferList))

        # checksum_local, checksum_remote = compute_local_sha512( local_path ), compute_remote_sha512(ssh_client, remote_path);
        # assert checksum_local == checksum_remote, f"Checksum mismatch for {local_path}:  {checksum_local} != {checksum_remote}"

    ssh_client.close()

    demuxLogger.info( f"==< {demux.n}/{demux.totalTasks} tasks: Preparing files for archiving to NIRD finished\n")
    
