import json
import os
import uuid
import urllib.request

from demux.loggers import demuxLogger, demuxFailureLogger


########################################################################
# multipart helpers
########################################################################

def _build_multipart_body( files: dict, boundary: str ) -> bytes:
    """
    Build a multipart/form-data body from a files dict.

    :param files: { field_name: ( filename, file_bytes, content_type ) }
    :param boundary: multipart boundary string.
    :returns: raw bytes of the multipart body.
    """
    # multipart header field names are per RFC 2046; not our constants
    lines:list = [ ]
    for field_name, ( filename, file_bytes, content_type ) in files.items():
        lines.append( f'--{boundary}'.encode( constants.UTF8 ) )
        # multipart header field names are per RFC 2046; not our constants
        lines.append( f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"'.encode( constants.UTF8 ) )
        lines.append( f'Content-Type: {content_type}'.encode( constants.UTF8 ) )
        lines.append( b'' )
        lines.append( file_bytes )
    lines.append( f'--{boundary}--'.encode( constants.UTF8 ) )
    lines.append( b'' )
    # CRLF line ending is required by RFC 2046 for multipart boundaries
    return constants.CRLF.join( lines )



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

    :param demux: demux object with irida_samples, irida_base_url, irida_oauth_token, irida_projects_endpoint, irida_samples_endpoint set.
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

    Sample uniqueness within a project is application-level only.
    There is no DB constraint on sample name. UniqueConstraint is on
    (project_id, sample_id) in ProjectSampleJoin, not on sample name.

    :param demux: demux object with irida_base_url, irida_oauth_token, irida_projects_endpoint set.
    :param project_id: IRIDA project ID.
    :param sample_name: sample name to find or create.
    :returns: IRIDA sample ID.
    :raises RuntimeError: if sample creation fails.
    """

    # ---- try to find existing sample by listing project samples -------

    list_url:str = f"{demux.irida_base_url}/{demux.irida_projects_endpoint}/{project_id}/samples"

    request = urllib.request.Request( list_url, method = constants.HTTP_GET )
    request.add_header( constants.HTTP_HEADER_AUTHORIZATION, f'{constants.HTTP_BEARER_PREFIX} {demux.irida_oauth_token}' )
    request.add_header( constants.HTTP_HEADER_ACCEPT, constants.HTTP_CONTENT_TYPE_JSON )

    # urlopen raises HTTPError on 4xx/5xx; all 2xx codes are treated as success
    with urllib.request.urlopen( request, timeout = demux.irida_timeout ) as response:
        body:dict = json.load( response )

    # IRIDA HATEOAS response field names; not our constants
    resources:list = body.get( 'resource', { } ).get( 'resources', [ ] )
    for sample_resource in resources:
        if sample_resource.get( 'sampleName' ) == sample_name:
            return int( sample_resource[ 'identifier' ] )

    # ---- sample not found; create it ----------------------------------

    create_url:str = f"{demux.irida_base_url}/{demux.irida_projects_endpoint}/{project_id}/samples"

    # sampleName is an IRIDA API field name; not our constant
    payload:bytes = json.dumps( { 'sampleName': sample_name } ).encode( constants.UTF8 )

    request = urllib.request.Request( create_url, data = payload, method = constants.HTTP_POST )
    request.add_header( constants.HTTP_HEADER_AUTHORIZATION, f'{constants.HTTP_BEARER_PREFIX} {demux.irida_oauth_token}' )
    request.add_header( constants.HTTP_HEADER_CONTENT_TYPE, constants.HTTP_CONTENT_TYPE_JSON )
    request.add_header( constants.HTTP_HEADER_ACCEPT, constants.HTTP_CONTENT_TYPE_JSON )

    try:
        # urlopen raises HTTPError on 4xx/5xx; all 2xx codes are treated as success
        with urllib.request.urlopen( request, timeout = demux.irida_timeout ) as response:
            create_body:dict = json.load( response )
    except urllib.error.HTTPError as http_error:
        raise RuntimeError( f"Failed to create sample '{sample_name}' in project {project_id}. HTTP {http_error.code}: {http_error.reason}" ) from http_error

    # IRIDA response is inconsistent: some endpoints return 'identifier', some return 'id' for the same resource ID.
    # Confirmed from IRIDA source: RESTSequencingRunController.java, HATEOAS Identifiable interface vs JPA (Java Persistence API) entity serialization.
    resource:dict = create_body.get( 'resource', create_body )
    sample_id = resource.get( 'identifier', resource.get( 'id' ) )

    if sample_id is None:
        raise RuntimeError( f"IRIDA did not return a sample identifier after creating '{sample_name}'. Response: {json.dumps( create_body, indent = 2 )}" )

    if not str( sample_id ).isdigit():
        raise ValueError( f"IRIDA: expected numeric sample ID, got '{sample_id}'" )

    demuxLogger.info( f"IRIDA upload: created sample '{sample_name}' with id {sample_id}" )
    return int( sample_id )




def _upload_pair( demux, sample_id: int, r1_path: str, r2_path: str ) -> dict:
    """
    Upload a paired-end FASTQ pair to IRIDA via
    POST /api/samples/{id}/sequenceFiles/pairs.

    :param demux: demux object with irida_base_url, irida_oauth_token,
                  irida_samples_endpoint set.
    :param sample_id: IRIDA sample ID.
    :param r1_path: absolute path to R1.fastq.gz.
    :param r2_path: absolute path to R2.fastq.gz.
    :returns: IRIDA response body dict.
    :raises RuntimeError: if the upload fails.
    """

    # /sequenceFiles/pairs is a sub-resource of /api/samples/{id}; not a separate endpoint
    url:str = f"{demux.irida_base_url}/{demux.irida_samples_endpoint}/{sample_id}/sequenceFiles/pairs"

    r1_basename:str = os.path.basename( r1_path )
    r2_basename:str = os.path.basename( r2_path )

    with open( r1_path, constants.FILE_READ_BINARY ) as fh:
        r1_bytes:bytes = fh.read()
    with open( r2_path, constants.FILE_READ_BINARY ) as fh:
        r2_bytes:bytes = fh.read()

    boundary:str = uuid.uuid4().hex

    # file1/file2 are IRIDA multipart field names; not our constants
    body:bytes = _build_multipart_body(
        files = { 'file1': ( r1_basename, r1_bytes, constants.HTTP_CONTENT_TYPE_GZIP ), 'file2': ( r2_basename, r2_bytes, constants.HTTP_CONTENT_TYPE_GZIP ) },
        boundary = boundary,
    )

    request = urllib.request.Request( url, data = body, method = constants.HTTP_POST )
    request.add_header( constants.HTTP_HEADER_AUTHORIZATION, f'{constants.HTTP_BEARER_PREFIX} {demux.irida_oauth_token}' )
    # multipart/form-data content type with boundary is per RFC 2046; not a constant, boundary is dynamic
    request.add_header( constants.HTTP_HEADER_CONTENT_TYPE, f'multipart/form-data; boundary={boundary}' )
    request.add_header( constants.HTTP_HEADER_ACCEPT, constants.HTTP_CONTENT_TYPE_JSON )

    try:
        # urlopen raises HTTPError on 4xx/5xx; all 2xx codes are treated as success
        # timeout is higher here; uploading multi-gigabyte files to IRIDA on NREC mechanical drives
        with urllib.request.urlopen( request, timeout = demux.irida_upload_timeout ) as response:
            response_body:dict = json.load( response )
    except urllib.error.HTTPError as http_error:
        raise RuntimeError( f"Failed to upload pair for sample {sample_id}. HTTP {http_error.code}: {http_error.reason}" ) from http_error

    return response_body
