import json
import os
import urllib.parse
import urllib.request

from demux.config  import constants
from demux.loggers import demuxLogger, demuxFailureLogger
from demux.util.bitwarden import _probe_bw_api_state


def _get_vigasp_samples( demux ) -> list:
    """
    Filter project_samples_metadata for samples marked upload_to_vigasp=True.

    :param demux: demux object with project_samples_metadata already populated.
    :returns: list of dicts [ { 'sample_name': str, 'project_id': int, 'project_name': str }, ... ]
    :raises ValueError: if no samples are marked for upload.
    """
    vigasp_samples:list = [ ]

    for project_name, samples in demux.project_samples_metadata.items():
        for sample_id, sample_info in samples.items():
            if not sample_info[ 'upload_to_vigasp' ]:
                continue
            vigasp_samples.append( { 'sample_name': sample_id, 'project_id': int( sample_info[ 'vigas_project_id' ] ), 'project_name': project_name } )

    if not vigasp_samples:
        raise ValueError( "No samples marked upload_to_vigasp=True in project_samples_metadata." )

    return vigasp_samples


def _resolve_fastq_paths( demux, sample_name: str, project_name: str ) -> tuple:
    """
    Find R1 and R2 .fastq.gz paths for a sample in its project directory.

    :param demux: demux object with demultiplexRunIDdir and runIDShort.
    :param sample_name: the Sample_ID to search for.
    :param project_name: the Sample_Project name (pre-rename).
    :returns: ( r1_path, r2_path ) as absolute paths.
    :raises FileNotFoundError: if the project directory does not exist or R1/R2 not found.
    """
    project_dir:str = os.path.join( demux.demultiplexRunIDdir, f"{demux.runIDShort}.{project_name}" )

    if not os.path.isdir( project_dir ):
        raise FileNotFoundError( f"Project directory does not exist: {project_dir}" )

    r1_path:str = ""
    r2_path:str = ""

    for filename in os.listdir( project_dir ):
        if not filename.endswith( constants.COMPRESSED_FASTQ_SUFFIX ):
            continue
        if sample_name not in filename:
            continue
        full_path:str = os.path.join( project_dir, filename )
        if '_R1_' in filename:
            r1_path = full_path
        elif '_R2_' in filename:
            r2_path = full_path

    if not r1_path:
        raise FileNotFoundError( f"R1 file not found for sample '{sample_name}' in '{project_dir}'" )
    if not r2_path:
        raise FileNotFoundError( f"R2 file not found for sample '{sample_name}' in '{project_dir}'" )

    return ( r1_path, r2_path )


def _validate_fastq_paths( r1_path: str, r2_path: str, sample_name: str ) -> None:
    """
    Verify that R1 and R2 paths exist on disk and are regular files.

    :param r1_path: absolute path to R1.fastq.gz.
    :param r2_path: absolute path to R2.fastq.gz.
    :param sample_name: sample name for error messages.
    :raises FileNotFoundError: if either path does not exist or is not a regular file.
    """
    if not os.path.isfile( r1_path ):
        raise FileNotFoundError( f"R1 is not a file: {r1_path} (sample '{sample_name}')" )
    if not os.path.isfile( r2_path ):
        raise FileNotFoundError( f"R2 is not a file: {r2_path} (sample '{sample_name}')" )


def _acquire_oauth_token( demux ) -> None:
    """
    Acquire an OAuth2 bearer token from IRIDA.

    :param demux: demux object with irida_oauth_token_url, irida_client_id,
                  irida_client_secret, irida_username, irida_password set.
    :raises RuntimeError: if the response does not contain an access_token.

    Sets on demux:
        demux.irida_oauth_token - OAuth2 bearer token string.
    """
    token_response:dict = { }
    token_params:bytes  = urllib.parse.urlencode( { 'grant_type': 'password', 'client_id': demux.irida_client_id, 'client_secret': demux.irida_client_secret, 'username': demux.irida_username, 'password': demux.irida_password } ).encode( 'utf-8' )
    token_request       = urllib.request.Request( demux.irida_oauth_token_url, data = token_params, method = 'POST' )
    with urllib.request.urlopen( token_request, timeout = 30 ) as response:
        token_response = json.load( response )

    demux.irida_oauth_token = token_response[ 'access_token' ]

    if not demux.irida_oauth_token:
        raise RuntimeError( "IRIDA OAuth2 token response did not contain an access_token." )


def _fetch_irida_credentials( demux ) -> None:
    """
    Fetch IRIDA credentials from Bitwarden via bw serve HTTP API.

    Username and password come from the login fields.
    client_id and client_secret come from the notes field.
    UUID-based lookup is mandatory; name-based fuzzy matching is unreliable.

    :param demux: demux object with bw_baseurl, irida_bw_item_uuid,
                  irida_bw_item_endpoint set.
    :raises ValueError: if irida_bw_item_uuid is not set or any credential is empty.
    :raises ConnectionError: if bw serve is not reachable.
    :raises RuntimeError: if the vault is locked.

    Sets on demux:
        demux.irida_username
        demux.irida_password
        demux.irida_client_id
        demux.irida_client_secret
    """
    _probe_bw_api_state( )  # raises ConnectionError or RuntimeError internally on failure; return values are irrelevant

    if not demux.irida_bw_item_uuid:
        raise ValueError( "demux.irida_bw_item_uuid is not set. Cannot fetch IRIDA credentials from Bitwarden." )

    bw_item:dict      = { }
    bw_item_url:str   = f"{demux.bw_baseurl}{demux.irida_bw_item_endpoint}"
    with urllib.request.urlopen( bw_item_url, timeout = 5 ) as response:
        bw_item       = json.load( response )

    login_data:dict   = bw_item[ "data" ][ "login" ]
    notes_parsed:dict = dict( line.split( ":", 1 ) for line in bw_item[ "data" ][ "notes" ].strip( ).split( "\n" ) )

    demux.irida_username      = login_data[ "username" ]
    demux.irida_password      = login_data[ "password" ]
    demux.irida_client_id     = notes_parsed[ "client_id" ]
    demux.irida_client_secret = notes_parsed[ "token" ]

    if not demux.irida_username:
        raise ValueError( "IRIDA username is empty after Bitwarden lookup." )
    if not demux.irida_password:
        raise ValueError( "IRIDA password is empty after Bitwarden lookup." )
    if not demux.irida_client_id:
        raise ValueError( "IRIDA client_id is empty after Bitwarden lookup." )
    if not demux.irida_client_secret:
        raise ValueError( "IRIDA client_secret is empty after Bitwarden lookup." )



########################################################################
# _preflight
########################################################################

def _preflight( demux ) -> None:
"""
    IRIDA upload preflight checks.

    1. Fetch IRIDA credentials from Bitwarden (bw serve HTTP API, UUID-based lookup).
    2. Acquire OAuth2 bearer token from IRIDA.
    3. Walk demux.project_samples_metadata, collect samples marked
       upload_to_vigasp=True, verify R1+R2 .fastq.gz files exist on disk.

    The samplesheet is already parsed before this step runs.
    project_samples_metadata is already populated with
    Sample_Project -> Sample_ID -> { upload_to_vigasp, vigas_project_id, ... }.

    :param demux: demux object (pipeline singleton or _StandaloneContext).
    :raises ValueError: if credentials are empty or no samples marked for upload.
    :raises FileNotFoundError: if R1/R2 .fastq.gz files are missing.
    :raises ConnectionError: if Bitwarden or IRIDA is unreachable.
    :raises RuntimeError: if OAuth2 token acquisition fails.

    Sets on demux:
        :attr demux.irida_oauth_token:   OAuth2 bearer token (from IRIDA).
        :attr demux.irida_client_id:     OAuth2 client ID (from Bitwarden notes).
        :attr demux.irida_client_secret: OAuth2 client secret (from Bitwarden notes).
        :attr demux.irida_username:      IRIDA uploader username (from Bitwarden).
        :attr demux.irida_password:      IRIDA uploader password (from Bitwarden).
        :attr demux.irida_samples:       list of dicts [ { 'sample_name': str, 'project_id': int, 'r1': path, 'r2': path }, ... ]
    """

    demuxLogger.info( "IRIDA preflight: starting" )

    # ---- 1. credentials from Bitwarden ---------------------------------

    demuxLogger.info( "IRIDA preflight: fetching credentials from Bitwarden" )
    _fetch_irida_credentials( demux )
    demuxLogger.info( "IRIDA preflight: credentials OK" )

    # ---- 2. acquire OAuth2 token ---------------------------------------

    demuxLogger.info( "IRIDA preflight: acquiring OAuth2 token" )
    _acquire_oauth_token( demux )
    demuxLogger.info( "IRIDA preflight: token acquired" )

    # ---- 3. check R1+R2 for every VIGAS-bound sample -------------------

    demuxLogger.info( "IRIDA preflight: checking that all R1+R2 .fastq.gz files exist on disk for each VIGASP-bound sample" )

    vigasp_samples:list = _get_vigasp_samples( demux )
    irida_samples:list  = [ ]

    for sample in vigasp_samples:
        r1_path, r2_path = _resolve_fastq_paths( demux, sample[ 'sample_name' ], sample[ 'project_name' ] )
        _validate_fastq_paths( r1_path, r2_path, sample[ 'sample_name' ] )
        irida_samples.append( { 'sample_name': sample[ 'sample_name' ], 'project_id': sample[ 'project_id' ], 'r1': r1_path, 'r2': r2_path } )

    demux.irida_samples = irida_samples

    demuxLogger.info( f"IRIDA preflight: {len( irida_samples )} sample(s) ready for upload" )
    demuxLogger.info( "IRIDA preflight: complete" )
