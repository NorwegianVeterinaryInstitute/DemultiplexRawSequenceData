import json
import time
import urllib.request

from demux.config  import constants
from demux.loggers import demuxLogger, demuxFailureLogger


########################################################################
# _verify
########################################################################

def _verify( demux ) -> None:
    """
    Post-upload verification: compare local sha256 hashes against the
    uploadSha256 field in the IRIDA sequence file metadata.

    IRIDA does not perform server-side checksum verification on uploaded
    files. The irida-uploader sets SampleStatus.uploaded=True immediately
    after send_sequence_files() returns without error - no sha256
    verification, no confirmation. "Uploaded" = "POST returned 200."

    uploadSha256 is computed asynchronously by IRIDA after upload, so
    this step polls GET /api/samples/{id}/sequenceFiles until the field
    is populated, then compares against demux.irida_local_hashes.

    No files are downloaded. This is a metadata comparison only.

    For each sample in demux.irida_uploaded_samples:
        1. GET /api/samples/{id}/sequenceFiles to list files.
        2. Read the uploadSha256 field from each file resource.
        3. Match R1/R2 by filename convention (_R1_, _R2_).
        4. Compare against local hashes in demux.irida_local_hashes.

    :param demux: demux object with irida_uploaded_samples, irida_local_hashes,
                  irida_base_url, irida_oauth_token, irida_samples_endpoint,
                  irida_verify_max_poll_attempts, irida_verify_poll_interval_seconds set.
    :raises RuntimeError: on hash mismatch. Do NOT PATCH sequencing run to COMPLETE.

    Sets on demux:
        :attr demux.irida_verification_passed: bool
    """

    demuxLogger.info( "IRIDA verify: starting" )

    mismatches:list = [ ]
    total:int = len( demux.irida_uploaded_samples )

    # enumerate from 1 so log messages show [1/N] instead of [0/N]
    for current, upload_info in enumerate( demux.irida_uploaded_samples, 1 ):
        # keys populated by _upload() in step07_06
        sample_name:str = upload_info[ 'sample_name' ]
        sample_id:int   = upload_info[ 'sample_id' ]
        expected:dict   = demux.irida_local_hashes.get( sample_name )

        if expected is None:
            mismatches.append( f"{sample_name}: no local hash found" )
            continue

        demuxLogger.info( f"IRIDA verify: [{current}/{total}] verifying {sample_name} (sample_id={sample_id})" )

        r1_remote_hash:str = ""
        r2_remote_hash:str = ""

        # uploadSha256 is computed asynchronously post-upload; poll until populated
        for attempt in range( 1, demux.irida_verify_max_poll_attempts + 1 ):
            url:str = f"{demux.irida_base_url}/{demux.irida_samples_endpoint}/{sample_id}/{demux.irida_sequence_files_subpath}"

            request = urllib.request.Request( url, method = constants.HTTP_GET )
            request.add_header( constants.HTTP_HEADER_AUTHORIZATION, f'{constants.HTTP_BEARER_PREFIX} {demux.irida_oauth_token}' )
            request.add_header( constants.HTTP_HEADER_ACCEPT, constants.HTTP_CONTENT_TYPE_JSON )

            try:
                # urlopen raises HTTPError on 4xx/5xx; all 2xx codes are treated as success
                with urllib.request.urlopen( request, timeout = demux.irida_timeout ) as response:
                    files_body:dict = json.load( response )
            except urllib.error.HTTPError as http_error:
                mismatches.append( f"{sample_name}: failed to list files, HTTP {http_error.code}" )
                break

            # IRIDA HATEOAS response field names; not our constants
            resources:list = files_body.get( 'resource', { } ).get( 'resources', [ ] )

            r1_remote_hash = ""
            r2_remote_hash = ""

            for file_resource in resources:
                # IRIDA API response field names; not our constants
                file_name:str      = file_resource.get( 'fileName', '' )
                upload_sha256:str  = file_resource.get( 'uploadSha256', '' )

                if sample_name not in file_name:
                    continue

                if '_R1_' in file_name:
                    r1_remote_hash = upload_sha256
                elif '_R2_' in file_name:
                    r2_remote_hash = upload_sha256

            # if both hashes are populated, stop polling
            if r1_remote_hash and r2_remote_hash:
                break

            if attempt < demux.irida_verify_max_poll_attempts:
                demuxLogger.debug( f"IRIDA verify: [{current}/{total}] uploadSha256 not yet populated for {sample_name}, polling again in {demux.irida_verify_poll_interval_seconds}s (attempt {attempt}/{demux.irida_verify_max_poll_attempts})" )
                time.sleep( demux.irida_verify_poll_interval_seconds )

        # compare
        if not r1_remote_hash:
            mismatches.append( f"{sample_name}: R1 uploadSha256 not populated after {demux.irida_verify_max_poll_attempts} attempts" )
        elif r1_remote_hash != expected[ 'r1_sha256' ]:
            mismatches.append( f"{sample_name} R1: local={expected[ 'r1_sha256' ]} remote={r1_remote_hash}" )

        if not r2_remote_hash:
            mismatches.append( f"{sample_name}: R2 uploadSha256 not populated after {demux.irida_verify_max_poll_attempts} attempts" )
        elif r2_remote_hash != expected[ 'r2_sha256' ]:
            mismatches.append( f"{sample_name} R2: local={expected[ 'r2_sha256' ]} remote={r2_remote_hash}" )

        if r1_remote_hash == expected[ 'r1_sha256' ] and r2_remote_hash == expected[ 'r2_sha256' ]:
            demuxLogger.info( f"IRIDA verify: [{current}/{total}] {sample_name} OK" )

    if mismatches:
        demux.irida_verification_passed = False
        mismatch_report:str = '\n'.join( mismatches )
        demuxLogger.critical( f"IRIDA verify: sha256 mismatches detected:\n{mismatch_report}" )
        raise RuntimeError( f"IRIDA verify: {len( mismatches )} hash mismatch(es) detected. Do NOT PATCH sequencing run to COMPLETE.\n{mismatch_report}" )

    demux.irida_verification_passed = True
    demuxLogger.info( f"IRIDA verify: all {total} sample(s) verified" )