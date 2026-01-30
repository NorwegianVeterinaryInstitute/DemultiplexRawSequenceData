import os

from demux.config import constants

def _select_nird_base_upload_path( demux ):
    """
    @in_use
    Select which base upload path to use depending on access mode (sshfs vs SSH). Central place to extend path-selection rules; if path logic needs augmentation, add it here.
    """
    upload_path = ""
    if constants.NIRD_MODE_MOUNTED   == demux.nird_access_mode:
        upload_path = demux.nird_base_upload_path_local
    elif constants.NIRD_MODE_SSH     == demux.nird_access_mode:
        upload_path = demux.nird_base_upload_path_ssh
    elif constants.NIRD_MODE_SSH_2FA == demux.nird_access_mode:
        upload_path = demux.nird_base_upload_path_ssh
    else:
        message = f"ValueError: NIRD upload method does not guarantee remote directory value. Refusing to continue."
        raise ValueError( message )

    return upload_path


def _build_absolute_paths( demux ) -> None:
    """
    @in_use
    Builds and returns a dictonary mapping each tar filename to its full local and remote paths,
    including the associated .md5 and .sha512 files.
    """

    demux.nird_base_upload_path = _select_nird_base_upload_path( demux )

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
            # 'upload_to_nird' exists already, we are just adding here the rest of the keys
        }
