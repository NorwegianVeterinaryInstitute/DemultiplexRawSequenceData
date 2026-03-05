import termcolor

from demux.loggers import demuxLogger, demuxFailureLogger

# Based on what you've described, you want:
# 1. Read IRIDA credentials from config
# 2. Initialize `iridauploader` API client
# 3. Queue of `UploadJob` items
# 4. Bounded concurrency worker pool dispatching jobs from the queue
# 5. Verify each upload completed successfully in IRIDA
# 6. Retry with backoff on failure
# 7. Rate limiting to not hammer the IRIDA server


########################################################################
# deliver_files_to_VIGASP
########################################################################

def deliver_files_to_VIGASP( demux ):
    """
    Write the uploader file needed to upload the data to VIGASP and then
        upload the relevant files.
    """
    demux.n = demux.n + 1
    demuxLogger.info( f"==> {demux.n}/{demux.totalTasks} tasks: Preparing files for uploading to VIGASP started\n")


    demuxLogger.info( f"==< {demux.n}/{demux.totalTasks} tasks: Preparing files for uploading to VIGASP finished\n")import dataclasses
