import termcolor
import hashlib
import shlex


from paramiko import SSHClient
from scp import SCPClient

from concurrent.futures import ThreadPoolExecutor
from demux.loggers      import demuxLogger, demuxFailureLogger


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
    # 1. create the remote directory
    # 2. take each of the files in demux.tarFilesToTransferList and upload them 
    #   2.1 in parallel
    # 3. check the remote sha512 and see if it matches local.

    ssh_client = SSHClient( )
    ssh_client.load_system_host_keys( )
    ssh_client.connect( hostname = demux.nird_upload_host, port = demux.nird_scp_port, username = nird_username, key_filename = nird_key_filename )

    with SCPClient(ssh_client.get_transport()) as scp_client:
        #
        # check if upload location exists
        #
        for tar_file_local in demux.tarFilesToTransferList:
            # construct the ABSOLUTE remote tar file name
            tar_file_remote = os.path.join( demux.nird_base_upload_path, 
            # Usingf the ABSOLUTE PATH IS ESSENTIAL! otherwise SCP will drop everything in $HOME ! 
            tar_file_remote = "/path/to/upload"
            scp_client.put(tar_file, tar_file_remote )

        # with ThreadPoolExecutor(max_workers=min(5, len(demux.tarFilesToTransferList))) as pool: list(pool.map(upload_one, demux.tarFilesToTransferList))

        # checksum_local, checksum_remote = compute_local_sha512( local_path ), compute_remote_sha512(ssh_client, remote_path);
        # assert checksum_local == checksum_remote, f"Checksum mismatch for {local_path}:  {checksum_local} != {checksum_remote}"

    ssh_client.close()


    demuxLogger.info( f"==< {demux.n}/{demux.totalTasks} tasks: Preparing files for archiving to NIRD finished\n")
