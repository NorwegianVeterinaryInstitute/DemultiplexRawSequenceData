import json
import urllib.request

from demux.config  import constants
from demux.loggers import demuxLogger, demuxFailureLogger


########################################################################
# _complete
########################################################################

def _complete( demux ) -> None:
    """
    Mark the IRIDA sequencing run as COMPLETE via
    PATCH /api/sequencingrun/{id} with uploadStatus=COMPLETE.

    This step runs ONLY after verify has passed. If verify failed,
    the caller must NOT call this function. The sequencing run stays
    in UPLOADING state and the operator is notified.

    PATCH /api/sequencingrun/{id} with uploadStatus=ERROR has no side
    effects - just updates the field in DB; no cleanup, no notification,
    no blocking. Confirmed from source: RESTSequencingRunController.java
    delegates to generic CRUDServiceImpl.update(). We deliberately do
    NOT PATCH to ERROR on failure; that is the caller's decision.

    :param demux: demux object with irida_base_url, irida_oauth_token,
                  irida_sequencing_run_id, irida_verification_passed set.
    :raises RuntimeError: if verification has not passed or PATCH fails.
    :raises ConnectionError: if IRIDA is unreachable.

    Sets on demux:
        :attr demux.irida_run_completed: bool
    """

    demuxLogger.info( "IRIDA complete: starting" )

    if not demux.irida_verification_passed:
        raise RuntimeError( f"IRIDA complete: refusing to PATCH run {demux.irida_sequencing_run_id} to {demux.irida_upload_status_complete} because irida_verification_passed is not True." )

    url:str = f"{demux.irida_base_url}/{demux.irida_sequencingrun_endpoint}/{demux.irida_sequencing_run_id}"

    # uploadStatus is an IRIDA API field name; not our constant
    payload:bytes = json.dumps( { 'uploadStatus': demux.irida_upload_status_complete } ).encode( constants.UTF8 )

    request = urllib.request.Request( url, data = payload, method = constants.HTTP_PATCH )
    request.add_header( constants.HTTP_HEADER_AUTHORIZATION, f'{constants.HTTP_BEARER_PREFIX} {demux.irida_oauth_token}' )
    request.add_header( constants.HTTP_HEADER_CONTENT_TYPE, constants.HTTP_CONTENT_TYPE_JSON )
    request.add_header( constants.HTTP_HEADER_ACCEPT, constants.HTTP_CONTENT_TYPE_JSON )

    try:
        # urlopen raises HTTPError on 4xx/5xx; all 2xx codes are treated as success
        with urllib.request.urlopen( request, timeout = demux.irida_timeout ) as response:
            body:dict = json.load( response )
    except urllib.error.HTTPError as http_error:
        raise RuntimeError( f"IRIDA complete: PATCH {url} failed. HTTP {http_error.code}: {http_error.reason}" ) from http_error
    except urllib.error.URLError as url_error:
        raise ConnectionError( f"IRIDA complete: cannot reach IRIDA: {url_error.reason}" ) from url_error

    demux.irida_run_completed = True

    demuxLogger.info( f"IRIDA complete: sequencing run {demux.irida_sequencing_run_id} set from {demux.irida_upload_status_uploading} to {demux.irida_upload_status_complete}" )