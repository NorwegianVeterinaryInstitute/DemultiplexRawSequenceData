import json
import urllib.request

from demux.config  import constants
from demux.loggers import demuxLogger, demuxFailureLogger


########################################################################
# _create_run
########################################################################

def _create_run( demux ) -> None:
    """
    Create a sequencing run in IRIDA via POST /api/sequencingrun.

    The run is created with uploadStatus=UPLOADING (set automatically
    by IRIDA on creation). layoutType is PAIRED_END. sequencerType is
    always "directory" - the IRIDA developers intended to categorize
    by instrument but never followed through, and neither do we.

    :param demux: demux object with irida_base_url, irida_oauth_token,
                  irida_sequencingrun_endpoint set.
    :raises RuntimeError: if the POST fails or response has no run identifier.
    :raises ConnectionError: if IRIDA is unreachable.

    Sets on demux:
        :attr demux.irida_sequencing_run_id: int, the IRIDA sequencing run ID.
    """

    demuxLogger.info( "IRIDA create_run: starting" )

    url:str = f"{demux.irida_base_url}/{demux.irida_sequencingrun_endpoint}"

    # layoutType and sequencerType are IRIDA API field names, see demux/core.py
    payload:bytes = json.dumps( { 'layoutType': demux.irida_layout_type, 'sequencerType': demux.irida_sequencer_type } ).encode( constants.UTF8 )

    request = urllib.request.Request( url, data = payload, method = constants.HTTP_POST )
    request.add_header( constants.HTTP_HEADER_AUTHORIZATION, f'{constants.HTTP_BEARER_PREFIX} {demux.irida_oauth_token}' )
    request.add_header( constants.HTTP_HEADER_CONTENT_TYPE, constants.HTTP_CONTENT_TYPE_JSON )
    request.add_header( constants.HTTP_HEADER_ACCEPT, constants.HTTP_CONTENT_TYPE_JSON )

    try:
        # urlopen raises HTTPError on 4xx/5xx; all 2xx codes are treated as success
        with urllib.request.urlopen( request, timeout = demux.irida_timeout ) as response:
            status_code:int = response.status  # always 2xx here; kept for debugging/logging
            body:dict       = json.load( response )
    except urllib.error.HTTPError as http_error:
        raise RuntimeError( f"IRIDA create_run: POST {url} failed. HTTP {http_error.code}: {http_error.reason}" ) from http_error
    except urllib.error.URLError as url_error:
        raise ConnectionError( f"IRIDA create_run: cannot reach IRIDA: {url_error.reason}" ) from url_error

    # IRIDA HATEOAS response wraps run data under 'resource'; run ID is in 'identifier' or 'id'
    # no need to turn these into constants; they are IRIDA API response field names
    resource:dict = body.get( 'resource', body )
    # IRIDA response is inconsistent: some endpoints return 'identifier', some return 'id' for the same resource ID.
    # Confirmed from IRIDA source: RESTSequencingRunController.java, HATEOAS Identifiable interface vs JPA (Java Persistence API) entity serialization.
    run_id = resource.get( 'identifier', resource.get( 'id' ) )

    if run_id is None:
        raise RuntimeError( f"IRIDA create_run: response did not contain a run identifier. Response body: {json.dumps( body, indent = 2 )}" )

    if not str( run_id ).isdigit():
        raise ValueError( f"IRIDA create_run: expected numeric run ID, got '{run_id}'" )
    demux.irida_sequencing_run_id = int( run_id )

    demuxLogger.info( f"IRIDA create_run: sequencing run {demux.irida_sequencing_run_id} created (sequencerType={demux.irida_sequencer_type}, layoutType={demux.irida_layout_type}, uploadStatus={demux.irida_upload_status_uploading})" )