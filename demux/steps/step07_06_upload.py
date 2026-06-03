import json
import os
import requests

from demux.config  import constants
from demux.loggers import demuxLogger, demuxFailureLogger


########################################################################
# IRIDA sample name validation
########################################################################

# IRIDA sample name validation regex is ^[^\.]*$ but the error message lists more forbidden characters:
# ? ( ) [ ] / = + < > : ; " ' , * ^ | & .
# Confirmed from IRIDA source: MethodArgumentNotValidException on RESTProjectSamplesController.addSampleToProject
IRIDA_FORBIDDEN_SAMPLE_NAME_CHARS:str = '.?()[]/ =+<>:;"\',*^|&'


def _sanitize_sample_name( sample_name: str ) -> str:
    """
    Replace characters forbidden by IRIDA's sample name validation.

    :param sample_name: original sample name (may contain dots, etc).
    :returns: sanitized sample name safe for IRIDA API.
    """
    sanitized:str = sample_name
    for char in IRIDA_FORBIDDEN_SAMPLE_NAME_CHARS:
        sanitized = sanitized.replace( char, '_' )
    return sanitized



########################################################################
# _upload
########################################################################

def _upload( demux ) -> None:
    """
    Upload FASTQ pairs to IRIDA, one sample at a time.

    For each sample in demux.irida_samples:
        1. Create the sample in the target project via POST /api/projects/{id}/samples
           (if sample does not already exist).
        2. Upload the paired-end .fastq.gz files via POST /api/samples/{id}/sequenceFiles/pairs.

    One sample at a time. Expand to parallel after testing.

    :param demux: demux object with irida_samples, irida_base_url, irida_oauth_token,
                  irida_projects_endpoint, irida_samples_endpoint set.
    :raises RuntimeError: if sample creation or file upload fails.
    :raises ConnectionError: if IRIDA is unreachable.

    Sets on demux:
        :attr demux.irida_uploaded_samples: list of dicts [ { 'sample_name': str, 'sample_id': int, 'project_id': int }, ... ]
    """

    demuxLogger.info( "IRIDA upload: starting" )

    total:int = len( demux.irida_samples )

    # enumerate from 1 so log messages show [1/N] instead of [0/N]
    for current, sample in enumerate( demux.irida_samples, 1 ):
        # keys populated by _get_vigasp_samples() and _resolve_fastq_paths() in step07_01_preflight
        sample_name:str = sample[ 'sample_name' ]
        project_id:int  = sample[ 'project_id' ]
        r1_path:str     = sample[ 'r1' ]
        r2_path:str     = sample[ 'r2' ]

        demuxLogger.info( f"IRIDA upload: [{current}/{total}] {sample_name} -> project {project_id}" )

        # ---- 1. find or create sample in project ----------------------
        sample_id:int = _find_or_create_sample( demux, project_id, sample_name )

        # ---- 2. POST paired-end files ---------------------------------
        _upload_pair( demux, sample_id, r1_path, r2_path )

        # sample_name = Sample_ID from samplesheet
        # sample_id   = IRIDA sample ID (returned by _find_or_create_sample)
        # project_id  = IRIDA project ID from VIGASP_ID column
        demux.irida_uploaded_samples.append( { 'sample_name': sample_name, 'sample_id': sample_id, 'project_id': project_id } )
        demuxLogger.info( f"IRIDA upload: [{current}/{total}] {sample_name} (sample_id={sample_id}) uploaded" )

    demuxLogger.info( f"IRIDA upload: {len( demux.irida_uploaded_samples )}/{total} sample(s) uploaded" )


def _find_or_create_sample( demux, project_id: int, sample_name: str ) -> int:
    """
    Find sample by name in project. If it does not exist, create it.

    Sample names are sanitized before IRIDA API calls because IRIDA
    rejects names containing dots and other special characters.
    Confirmed from IRIDA source: MethodArgumentNotValidException,
    validation regex ^[^\.]*$

    Sample uniqueness within a project is application-level only.
    There is no DB constraint on sample name. UniqueConstraint is on
    (project_id, sample_id) in ProjectSampleJoin, not on sample name.

    :param demux: demux object with irida_base_url, irida_oauth_token, irida_projects_endpoint set.
    :param project_id: IRIDA project ID.
    :param sample_name: sample name to find or create.
    :returns: IRIDA sample ID.
    :raises RuntimeError: if sample creation fails.
    """

    # IRIDA rejects sample names with dots and other special characters; sanitize before API calls
    irida_sample_name:str = _sanitize_sample_name( sample_name )

    if irida_sample_name != sample_name:
        demuxLogger.debug( f"IRIDA upload: sanitized sample name '{sample_name}' -> '{irida_sample_name}'" )

    headers:dict = {
        constants.HTTP_HEADER_AUTHORIZATION: f'{constants.HTTP_BEARER_PREFIX} {demux.irida_oauth_token}',
        constants.HTTP_HEADER_ACCEPT: constants.HTTP_CONTENT_TYPE_JSON,
    }

    # ---- try to find existing sample by listing project samples -------

    list_url:str = f"{demux.irida_base_url}/{demux.irida_projects_endpoint}/{project_id}/{demux.irida_project_samples_subpath}"

    demuxLogger.debug( f"IRIDA upload: GET {list_url}" )

    response = requests.get( list_url, headers = headers, timeout = demux.irida_timeout )
    response.raise_for_status()
    body:dict = response.json()

    # IRIDA HATEOAS response field names; not our constants
    resources:list = body.get( 'resource', { } ).get( 'resources', [ ] )
    for sample_resource in resources:
        if sample_resource.get( 'sampleName' ) == irida_sample_name:
            demuxLogger.debug( f"IRIDA upload: found existing sample '{irida_sample_name}' with id {sample_resource[ 'identifier' ]}" )
            return int( sample_resource[ 'identifier' ] )

    # ---- sample not found; create it ----------------------------------

    create_url:str = f"{demux.irida_base_url}/{demux.irida_projects_endpoint}/{project_id}/{demux.irida_project_samples_subpath}"

    # sampleName is an IRIDA API field name; not our constant
    payload:dict = { 'sampleName': irida_sample_name }

    demuxLogger.debug( f"IRIDA upload: creating sample '{irida_sample_name}' in project {project_id}" )
    demuxLogger.debug( f"IRIDA upload: POST {create_url}" )
    demuxLogger.debug( f"IRIDA upload: payload {payload}" )

    create_headers:dict = {
        constants.HTTP_HEADER_AUTHORIZATION: f'{constants.HTTP_BEARER_PREFIX} {demux.irida_oauth_token}',
        constants.HTTP_HEADER_CONTENT_TYPE: constants.HTTP_CONTENT_TYPE_JSON,
        constants.HTTP_HEADER_ACCEPT: constants.HTTP_CONTENT_TYPE_JSON,
    }

    response = requests.post( create_url, headers = create_headers, json = payload, timeout = demux.irida_timeout )

    if response.status_code not in ( 200, 201 ):
        raise RuntimeError( f"Failed to create sample '{irida_sample_name}' in project {project_id}. POST {create_url} HTTP {response.status_code}: {response.reason}\n{response.text}" )

    create_body:dict = response.json()

    # IRIDA response is inconsistent: some endpoints return 'identifier', some return 'id' for the same resource ID.
    # Confirmed from IRIDA source: RESTSequencingRunController.java, HATEOAS Identifiable interface vs JPA (Java Persistence API) entity serialization.
    resource:dict = create_body.get( 'resource', create_body )
    sample_id = resource.get( 'identifier', resource.get( 'id' ) )

    if sample_id is None:
        raise RuntimeError( f"IRIDA did not return a sample identifier after creating '{irida_sample_name}'. Response: {json.dumps( create_body, indent = 2 )}" )

    if not str( sample_id ).isdigit():
        raise ValueError( f"IRIDA: expected numeric sample ID, got '{sample_id}'" )

    demuxLogger.info( f"IRIDA upload: created sample '{irida_sample_name}' with id {sample_id}" )
    return int( sample_id )



def _upload_pair( demux, sample_id: int, r1_path: str, r2_path: str ) -> dict:
    """
    Upload a paired-end FASTQ pair to IRIDA via
    POST /api/samples/{id}/pairs.

    Multipart body contains four parts:
        file1       - R1.fastq.gz binary (application/octet-stream)
        file2       - R2.fastq.gz binary (application/octet-stream)
        parameters1 - JSON metadata for R1 (miseqRunId, layoutType)
        parameters2 - JSON metadata for R2 (miseqRunId, layoutType)

    :param demux: demux object with irida_base_url, irida_oauth_token,
                  irida_samples_endpoint, irida_sequence_files_pairs_subpath,
                  irida_sequencing_run_id, irida_layout_type set.
    :param sample_id: IRIDA sample ID.
    :param r1_path: absolute path to R1.fastq.gz.
    :param r2_path: absolute path to R2.fastq.gz.
    :returns: IRIDA response body dict.
    :raises RuntimeError: if the upload fails.
    """

    url:str = f"{demux.irida_base_url}/{demux.irida_samples_endpoint}/{sample_id}/{demux.irida_sequence_files_pairs_subpath}"

    demuxLogger.debug( f"IRIDA pair upload URL: {url}" )

    r1_basename:str = os.path.basename( r1_path )
    r2_basename:str = os.path.basename( r2_path )

    with open( r1_path, constants.READ_ONLY_BINARY ) as fh:
        r1_bytes:bytes = fh.read()
    with open( r2_path, constants.READ_ONLY_BINARY ) as fh:
        r2_bytes:bytes = fh.read()

    demuxLogger.debug( f"IRIDA pair upload: R1={r1_basename} ({len( r1_bytes )} bytes), R2={r2_basename} ({len( r2_bytes )} bytes)" )

    # miseqRunId and layoutType are IRIDA API field names; not our constants
    # both parameters1 and parameters2 get the same JSON
    params_json:str = json.dumps( { 'miseqRunId': str( demux.irida_sequencing_run_id ), 'layoutType': demux.irida_layout_type } )

    headers:dict = { constants.HTTP_HEADER_AUTHORIZATION: f'{constants.HTTP_BEARER_PREFIX} {demux.irida_oauth_token}' }

    # requests library handles multipart/form-data boundary automatically
    files:dict = {
        'file1':       ( r1_basename, r1_bytes, 'application/octet-stream' ),
        'file2':       ( r2_basename, r2_bytes, 'application/octet-stream' ),
        'parameters1': ( None, params_json, 'application/json' ),
        'parameters2': ( None, params_json, 'application/json' ),
    }

    response = requests.post( url, headers = headers, files = files, timeout = demux.irida_upload_timeout )

    if response.status_code not in ( 200, 201 ):
        raise RuntimeError( f"Failed to upload pair for sample {sample_id}. POST {url} HTTP {response.status_code}: {response.reason}\n{response.text}" )

    response_body:dict = response.json()

    demuxLogger.debug( f"IRIDA pair upload: pair uploaded for sample {sample_id}" )
    return response_body
