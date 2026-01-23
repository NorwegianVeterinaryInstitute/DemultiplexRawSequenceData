import hashlib
import json
import os
import paramiko
import psutil
import shlex
import shutil
import socket
import subprocess
import sys
import termcolor
import urllib.request

from typing import Tuple

# from paramiko                 import SSHClient, SSHConfig, AutoAddPolicy, RejectPolicy, Transport, SSHException
from paramiko.ssh_exception   import AuthenticationException
from scp                      import SCPClient

from concurrent.futures       import ThreadPoolExecutor

from demux.util.ssh_transport import _setup_ssh_connection, _ensure_remote_run_directory_ssh, _auth_transport_2fa, _open_transport_and_validate_hostkey

from demux.config             import constants
from demux.loggers            import demuxLogger, demuxFailureLogger





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
    # 6. report upload exit status

    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Preparing files for archiving to NIRD started\n", color="green", attrs=["bold"] ) )

    _setup_ssh_connection( demux )          # setup the ssh connection details
    _build_absolute_paths( demux )          # creates the demux absoluteFilesToTransferList dictonary with the absolute paths of all files involved
    _verify_local_files( demux )            # verify the local files exist before attempting to transfer them
    _ensure_remote_run_directory( demux )   # make sure demux.nird_base_upload_path/demux.RunID exists
    _upload_files_to_nird( demux )          # send the demux object to a dedicated method and it will decide what mode of copying and type of upload it will use

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Preparing files for archiving to NIRD finished\n", color="red", attrs=["bold"] ) )
