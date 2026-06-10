import json
import urllib.request

from demux.config  import constants
from demux.loggers import demuxLogger, demuxFailureLogger


########################################################################
# _check_projects
########################################################################

def _check_projects( demux ) -> None:
    """
    Verify that every target IRIDA project exists and is accessible.

    Queries GET /api/projects/{id} for each unique project_id in
    demux.irida_samples.

    :param demux: demux object with irida_samples, irida_oauth_token, irida_base_url set.
    :raises RuntimeError: if a project is not accessible (HTTP error).
    :raises ConnectionError: if IRIDA is unreachable.

    Sets on demux:
        :attr demux.irida_verified_projects: dict { project_id: project_name_from_irida }
    """

    demuxLogger.info( "IRIDA check_projects: starting" )

    # deduplicate project IDs so we only verify each IRIDA project once
    unique_project_ids:set = set( sample[ 'project_id' ] for sample in demux.irida_samples )

    demuxLogger.info( f"IRIDA check_projects: verifying {len( unique_project_ids )} project(s)" )

    verified_projects = { }

    for project_id in sorted( unique_project_ids ):
        url:str = f"{demux.irida_base_url}/{demux.irida_projects_endpoint}/{project_id}"

        request = urllib.request.Request( url, method = constants.HTTP_GET )
        request.add_header( constants.HTTP_HEADER_AUTHORIZATION, f'{constants.HTTP_BEARER_PREFIX} {demux.irida_oauth_token}' )
        request.add_header( constants.HTTP_HEADER_ACCEPT, constants.HTTP_CONTENT_TYPE_JSON )

        try:
            # urlopen raises HTTPError on 4xx/5xx;  all 2xx codes are treated as success
            with urllib.request.urlopen( request, timeout = demux.irida_timeout ) as response:
                status_code:int = response.status  # always 2xx here; kept for debugging/logging
                body:dict       = json.load( response )
        except urllib.error.HTTPError as http_error:
            raise RuntimeError( f"IRIDA project {project_id} is not accessible. HTTP {http_error.code}: {http_error.reason}" ) from http_error
        except urllib.error.URLError as url_error:
            raise ConnectionError( f"Cannot reach IRIDA to verify project {project_id}: {url_error.reason}" ) from url_error

        # IRIDA HATEOAS response wraps project data under 'resource'; project name is in 'name' or 'label'
        # no need to turn these into constants; they are IRIDA API response field names
        resource = body.get( 'resource', body )
        project_name_irida = resource.get( 'name', resource.get( 'label', f'project_{project_id}' ) )

        verified_projects[ project_id ] = project_name_irida
        demuxLogger.info( f"IRIDA check_projects: project {project_id} OK ({project_name_irida})" )

    demux.irida_verified_projects = verified_projects

    demuxLogger.info( f"IRIDA check_projects: all {len( verified_projects )} project(s) verified" )
