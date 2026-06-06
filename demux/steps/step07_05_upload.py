import concurrent.futures
import json
import os
import requests
import time

from demux.config  import constants
from demux.loggers import demuxLogger, demuxFailureLogger


########################################################################
# _sanitize_sample_name
########################################################################

def _sanitize_sample_name( sample_name: str ) -> str:
    """
    Replace characters forbidden by IRIDA's sample name validation.

    :param sample_name: original sample name (may contain dots, etc).
    :returns: sanitized sample name safe for IRIDA API.
    :example: "2024_EQA13.Strain0020" -> "2024_EQA13_Strain0020"
    """
    return sample_name.translate( str.maketrans( constants.IRIDA_FORBIDDEN_SAMPLE_NAME_CHARS, '_' * len( constants.IRIDA_FORBIDDEN_SAMPLE_NAME_CHARS ) ) )


########################################################################
# _upload
########################################################################


def _upload_one( demux, current: int, total: int, sample: dict ) -> dict:
    """
    Upload one sample: check and create sample in IRIDA, then POST the pair.

    Called from ThreadPoolExecutor workers. Each call operates on a
    distinct sample name so there is no race on _check_and_create_sample.

    :param demux: demux singleton (read-only during upload).
    :param current: 1-based position for log messages.
    :param total: total sample count for log messages.
    :param sample: dict with sample_name, project_id, r1, r2.
    :returns: uploaded sample record dict.
    :raises RuntimeError: propagated from _check_and_create_sample or _upload_pair.
    """
    # keys populated by _get_vigasp_samples() and _resolve_fastq_paths() in step07_01_preflight
    sample_name:str = sample[ 'sample_name' ]
    project_id:int  = sample[ 'project_id' ]
    r1_path:str     = sample[ 'r1' ]
    r2_path:str     = sample[ 'r2' ]

    demuxLogger.info( f"IRIDA upload: [{current}/{total}] {sample_name} -> project {project_id}" )

    sample_id:int = _check_and_create_sample( demux, project_id, sample_name )
    _upload_pair( demux, sample_id, r1_path, r2_path )

    # sample_name = Sample_ID from samplesheet
    # sample_id   = IRIDA sample ID (returned by _check_and_create_sample)
    # project_id  = IRIDA project ID from VIGASP_ID column
    demuxLogger.info( f"IRIDA upload: [{current}/{total}] {sample_name} (sample_id={sample_id}) uploaded" )
    return { 'sample_name': sample_name, 'sample_id': sample_id, 'project_id': project_id }


def _upload( demux ) -> None:
    """
    Upload FASTQ pairs to IRIDA with bounded concurrency and optional batch stagger.

    For each sample in demux.irida_samples:
        1. Check and create the sample in the target project via POST /api/projects/{id}/samples.
        2. Upload the paired-end .fastq.gz files via POST /api/samples/{id}/pairs.

    Samples are submitted in batches of irida_max_in_flight. After each batch completes,
    irida_upload_batch_stagger_seconds is observed before the next batch is submitted,
    giving IRIDA's async GzipFileProcessor/FastQC chain time to drain.

    :param demux: demux object with irida_samples, irida_base_url, irida_oauth_token,
                  irida_projects_endpoint, irida_samples_endpoint set.
    :raises RuntimeError: if sample creation or file upload fails.
    :raises ConnectionError: if IRIDA is unreachable.

    Sets on demux:
        :attr demux.irida_uploaded_samples: list of dicts [ { 'sample_name': str, 'sample_id': int, 'project_id': int }, ... ]
    """

    demuxLogger.info( "IRIDA upload: starting" )

    total:int = len( demux.irida_samples )

    # demux.irida_max_in_flight: max concurrent IRIDA upload workers (each worker POSTs one R1+R2 pair), so N workers -> N*2 files in flight
    futures:list = []
    with concurrent.futures.ThreadPoolExecutor( max_workers = demux.irida_max_in_flight ) as pool:
        for current, sample in enumerate( demux.irida_samples, 1 ):
            futures.append( pool.submit( _upload_one, demux, current, total, sample ) )

            # stagger: after every irida_max_in_flight submissions, wait for the current batch
            # to finish before submitting the next one, giving IRIDA's async processing queue time to drain
            if len( futures ) % demux.irida_max_in_flight == 0:
                for future in concurrent.futures.as_completed( futures[ -demux.irida_max_in_flight: ] ):
                    demux.irida_uploaded_samples.append( future.result() )
                if demux.irida_upload_batch_stagger_seconds > 0:
                    demuxLogger.debug( f"IRIDA upload: staggering {demux.irida_upload_batch_stagger_seconds}s before next batch" )
                    time.sleep( demux.irida_upload_batch_stagger_seconds )

        # collect any remaining futures (last partial batch)
        submitted:int = len( demux.irida_uploaded_samples )
        for future in concurrent.futures.as_completed( futures[ submitted: ] ):
            demux.irida_uploaded_samples.append( future.result() )

    demuxLogger.info( f"IRIDA upload: {len( demux.irida_uploaded_samples )}/{total} sample(s) uploaded" )


def _check_and_create_sample( demux, project_id: int, sample_name: str ) -> int:
    """
    Check if sample exists in project. If it does not exist, create it.

    Sample names are sanitized before IRIDA API calls because IRIDA
    rejects names containing dots and other special characters.
    Confirmed from IRIDA source: MethodArgumentNotValidException: validation regex is '^[^\.]*$'

    Sample uniqueness within a project is application-level only.
    There is no DB constraint on sample name. UniqueConstraint is on
    (project_id, sample_id) in ProjectSampleJoin, not on sample name.

    :param demux: demux object with irida_base_url, irida_oauth_token, irida_projects_endpoint set.
    :param project_id: IRIDA project ID.
    :param sample_name: sample name to check and create.
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

    # ---- check if sample already exists in project --------------------

    list_url:str = f"{demux.irida_base_url}/{demux.irida_projects_endpoint}/{project_id}/{demux.irida_project_samples_subpath}"

    demuxLogger.debug( f"IRIDA upload: GET {list_url}" )

    response = requests.get( list_url, headers = headers, timeout = demux.irida_timeout )
    response.raise_for_status()
    body:dict = response.json()

    # IRIDA HATEOAS response field names; not our constants
    resources:list = body.get( 'resource', { } ).get( 'resources', [ ] )
    for sample_resource in resources:
        if sample_resource.get( 'sampleName' ) == irida_sample_name:
            demuxLogger.debug( f"IRIDA upload: sample '{irida_sample_name}' already exists with id {sample_resource[ 'identifier' ]}" )
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
