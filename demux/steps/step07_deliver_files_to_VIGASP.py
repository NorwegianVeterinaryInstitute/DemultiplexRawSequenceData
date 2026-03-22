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

import dataclasses
import json
import multiprocessing
import os
import queue
import ssl
import time
import typing
import urllib3
import urllib.error
import urllib.parse
import urllib.request


@dataclasses.dataclass(frozen=True)
class IridaAuthConfig:
    """
    Authentication inputs for IRIDA.

    Notes:
        - Assumes you already have: client_id, client_secret, uploader_username, uploader_password.
        - Token acquisition is typically OAuth2-style; this wrapper treats the token as a bearer string
          and refreshes when a request returns HTTP 401.
    """
    base_url: str
    client_id: str
    client_secret: str
    uploader_username: str
    uploader_password: str
    initial_token: str | None = None


@dataclasses.dataclass(frozen=True)
class IridaTlsConfig:
    """
    TLS policy for HTTPS.

    For plain HTTP, keep use_https=False. For HTTPS:
        - Provide ca_bundle_path if you use internal PKI, otherwise system CA store is used.
        - Difficulty is mostly certificate trust and hostname validation, not request logic.
    """
    use_https: bool = False
    ca_bundle_path: str | None = None
    verify_hostname: bool = True


@dataclasses.dataclass(frozen=True)
class UploadJob:
    """
    One upload unit: one sample, one library association, one FASTQ or FASTQ.GZ single-end or paired-end.

    Invariants:
        - Exactly one of (single_fastq_path) or (r1_fastq_path and r2_fastq_path) must be set.
        - project_id and sample_name are stable inputs (no create via API).
    """
    job_id: str
    project_id: int
    sample_name: str
    single_fastq_path: str | None
    r1_fastq_path: str | None
    r2_fastq_path: str | None
    max_attempts: int = 3


@dataclasses.dataclass(frozen=True)
class UploadResult:
    """
    Child-process result payload.

    uploaded_ok means: upload request returned success and child parsed a plausible response.
    verified_ok means: supervisor confirmed presence in the sample sequence file library.

    For v1, the child should fill uploaded_ok and basic response metadata; the supervisor fills verified_ok.
    """
    job_id: str
    uploaded_ok: bool
    verified_ok: bool
    http_status: int | None
    response_json: dict[str, typing.Any] | None
    error_type: str | None
    error_message: str | None


class Reporter:
    """
    Optional IPC hook for future: child can emit status to supervisor.

    Implementations:
        - NullReporter: no-op.
        - QueueReporter: puts dict messages onto multiprocessing.Queue.

    In v1, you can default to NullReporter and keep QueueReporter wiring unimplemented.
    """
    def emit(self, message: dict[str, typing.Any]) -> None:
        raise NotImplementedError


class NullReporter(Reporter):
    """No-op reporter."""
    def emit(self, message: dict[str, typing.Any]) -> None:
        return


class QueueReporter(Reporter):
    """
    Queue-based reporter.

    The supervisor can poll the queue to receive progress events, if you decide to implement IPC later.
    """
    def __init__(self, report_queue: multiprocessing.Queue) -> None:
        self._report_queue: multiprocessing.Queue = report_queue

    def emit(self, message: dict[str, typing.Any]) -> None:
        self._report_queue.put(message)


class IridaHttpClient:
    """
    Minimal IRIDA REST client using urllib with bearer-token auth and keep-alive.

    Responsibilities:
        - Build an opener (connection reuse).
        - Attach Authorization: Bearer <token>.
        - Refresh token on HTTP 401 (one retry).
        - Provide multipart upload helpers for FASTQ and FASTQ.GZ.
    """
    def __init__(self, auth: IridaAuthConfig, tls: IridaTlsConfig, request_timeout_seconds: float) -> None:
        self._auth: IridaAuthConfig = auth
        self._tls: IridaTlsConfig = tls
        self._request_timeout_seconds: float = request_timeout_seconds
        self._token: str | None = auth.initial_token
        self._opener: urllib.request.OpenerDirector = self._build_opener()

    def _build_opener(self) -> urllib.request.OpenerDirector:
        """
        Build a urllib opener with HTTPS context if enabled.

        HTTPS difficulty:
            - If IRIDA uses an internal CA, you must supply ca_bundle_path or install the CA system-wide.
            - Hostname verification failures are configuration, not code.
        """
        handlers: list[urllib.request.BaseHandler] = []
        if self._tls.use_https:
            ssl_context: ssl.SSLContext = ssl.create_default_context(cafile=self._tls.ca_bundle_path)
            if not self._tls.verify_hostname:
                ssl_context.check_hostname = False
            handlers.append(urllib.request.HTTPSHandler(context=ssl_context))
        return urllib.request.build_opener(*handlers)

    def _request(self, method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, dict[str, typing.Any] | None]:
        """
        Execute a single HTTP request and decode JSON if present.

        Raises:
            urllib.error.HTTPError, urllib.error.URLError
        """
        request_headers: dict[str, str] = dict(headers)
        if self._token:
            request_headers["Authorization"] = f"Bearer {self._token}"
        request: urllib.request.Request = urllib.request.Request(url=url, data=body, headers=request_headers, method=method)
        with self._opener.open(request, timeout=self._request_timeout_seconds) as response:
            status_code: int = int(getattr(response, "status", 0))
            raw: bytes = response.read()
        if not raw:
            return status_code, None
        try:
            decoded: dict[str, typing.Any] = json.loads(raw.decode("utf-8"))
            return status_code, decoded
        except Exception:
            return status_code, None

    def _refresh_token(self) -> None:
        """
        Refresh bearer token using your existing client and uploader user.

        This is intentionally left as a hook because IRIDA deployments vary in token endpoint paths.
        You already have a token and client; implement this only if you need refresh-on-expiry.
        """
        raise NotImplementedError

    def request_with_refresh(self, method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, dict[str, typing.Any] | None]:
        """
        Perform request; on HTTP 401, refresh token and retry once.

        Returns:
            (status_code, decoded_json_or_none)
        """
        try:
            return self._request(method=method, url=url, headers=headers, body=body)
        except urllib.error.HTTPError as http_error:
            if int(getattr(http_error, "code", 0)) != 401:
                raise
        self._refresh_token()
        return self._request(method=method, url=url, headers=headers, body=body)

    def get_sample_id(self, project_id: int, sample_name: str) -> int:
        """
        Resolve IRIDA sample id for a known project_id + sample_name.

        Assumptions:
            - project_id and sample_name are stable and already exist in IRIDA.

        Returns:
            IRIDA internal sample id.

        Raises:
            KeyError, ValueError, urllib.error.HTTPError, urllib.error.URLError
        """
        raise NotImplementedError

    def list_sequence_files(self, sample_id: int) -> list[dict[str, typing.Any]]:
        """
        List sequence files attached to the sample.

        Returns:
            List of dicts representing sequence file resources, including filenames and identifiers.

        Raises:
            urllib.error.HTTPError, urllib.error.URLError
        """
        raise NotImplementedError

    def upload_single_end_fastq(self, sample_id: int, fastq_path: str) -> dict[str, typing.Any] | None:
        """
        Upload a single-end FASTQ or FASTQ.GZ to the sample.

        The request is multipart/form-data and uses the IRIDA sequenceFiles endpoint for the sample.

        Returns:
            Decoded JSON response dict if present, else None.

        Raises:
            FileNotFoundError, urllib.error.HTTPError, urllib.error.URLError
        """
        raise NotImplementedError

    def upload_paired_end_fastq(self, sample_id: int, r1_fastq_path: str, r2_fastq_path: str) -> dict[str, typing.Any] | None:
        """
        Upload paired-end FASTQ or FASTQ.GZ (R1, R2) to the sample.

        The request is multipart/form-data and uses the IRIDA sequenceFiles/pairs endpoint for the sample.

        Returns:
            Decoded JSON response dict if present, else None.

        Raises:
            FileNotFoundError, urllib.error.HTTPError, urllib.error.URLError
        """
        raise NotImplementedError


# def _child_upload_worker(auth: IridaAuthConfig, tls: IridaTlsConfig, request_timeout_seconds: float, job: UploadJob, reporter: Reporter, result_queue: multiprocessing.Queue | None) -> None:
def _child_upload_worker(auth: IridaAuthConfig, tls: IridaTlsConfig, request_timeout_seconds: float, job: UploadJob, reporter: Reporter, result_queue: multiprocessing.Queue ) -> None:
    """
    Child process entrypoint: upload exactly one UploadJob.

    Design:
        - Resolve sample_id from (project_id, sample_name).
        - Upload single-end or paired-end.
        - Emit minimal status via reporter (no-op by default).
        - Optionally push UploadResult to result_queue (IPC hook).

    Supervisor remains responsible for verification in IRIDA library.
    """
    http_client: IridaHttpClient = IridaHttpClient(auth=auth, tls=tls, request_timeout_seconds=request_timeout_seconds)
    start_time: float = time.time()
    try:
        reporter.emit({"event": "start", "job_id": job.job_id, "timestamp": start_time})
        sample_id: int = http_client.get_sample_id(project_id=job.project_id, sample_name=job.sample_name)

        response_payload: dict[str, typing.Any] | None
        if job.single_fastq_path is not None:
            response_payload = http_client.upload_single_end_fastq(sample_id=sample_id, fastq_path=job.single_fastq_path)
        else:
            if job.r1_fastq_path is None or job.r2_fastq_path is None:
                raise ValueError("Invalid job: paired upload requires r1_fastq_path and r2_fastq_path.")
            response_payload = http_client.upload_paired_end_fastq(sample_id=sample_id, r1_fastq_path=job.r1_fastq_path, r2_fastq_path=job.r2_fastq_path)

        reporter.emit({"event": "uploaded", "job_id": job.job_id, "timestamp": time.time()})
        result: UploadResult = UploadResult(job_id=job.job_id, uploaded_ok=True, verified_ok=False, http_status=None, response_json=response_payload, error_type=None, error_message=None)
    except Exception as exception:
        reporter.emit({"event": "error", "job_id": job.job_id, "timestamp": time.time(), "error": repr(exception)})
        result = UploadResult(job_id=job.job_id, uploaded_ok=False, verified_ok=False, http_status=None, response_json=None, error_type=type(exception).__name__, error_message=str(exception))

    if result_queue is not None:
        result_queue.put(dataclasses.asdict(result))


class IridaUploadSupervisor:
    """
    Bounded-concurrency upload supervisor.

    Core behavior:
        - Pre-initialize a queue of UploadJob.
        - Maintain at most max_in_flight child processes.
        - Reap children, then verify uploads are present in the sample sequence file library.
        - Retry with backoff up to job.max_attempts.

    No shared state between children besides IRIDA itself (child gets its own urllib opener).
    """
    def __init__(self, auth: IridaAuthConfig, tls: IridaTlsConfig, request_timeout_seconds: float, max_in_flight: int) -> None:
        self._auth: IridaAuthConfig = auth
        self._tls: IridaTlsConfig = tls
        self._request_timeout_seconds: float = request_timeout_seconds
        self._max_in_flight: int = max_in_flight
        self._http_client: IridaHttpClient = IridaHttpClient(auth=auth, tls=tls, request_timeout_seconds=request_timeout_seconds)

    def run(self, jobs: list[UploadJob]) -> tuple[list[UploadResult], list[UploadResult]]:
        """
        Run the bounded-concurrency upload loop until all jobs succeed or exhaust retries.

        Returns:
            (successful_results, failed_results)

        IPC:
            - v1 can set result_queue=None and rely on child exit codes only.
            - v2 can pass a multiprocessing.Queue to receive UploadResult dicts.
        """
        raise NotImplementedError

    # def _spawn_child(self, job: UploadJob, reporter: Reporter, result_queue: multiprocessing.Queue | None) -> multiprocessing.Process:
    def _spawn_child(self, job: UploadJob, reporter: Reporter, result_queue: multiprocessing.Queue ) -> multiprocessing.Process:
        """
        Spawn one child process for one job.

        Child is unsupervised in the sense that it runs independently after spawn.
        Supervisor still owns lifecycle (join, terminate if needed).
        """
        process: multiprocessing.Process = multiprocessing.Process(target=_child_upload_worker, args=(self._auth, self._tls, self._request_timeout_seconds, job, reporter, result_queue))
        process.start()
        return process

    def _verify_job_present(self, project_id: int, sample_name: str, expected_basenames: list[str]) -> bool:
        """
        Verify that uploaded files are visible in the IRIDA sample sequence file library.

        Implementation:
            - Resolve sample_id from (project_id, sample_name).
            - List sequence files for the sample.
            - Compare against expected basenames.

        Returns:
            True if all expected files appear, else False.
        """
        raise NotImplementedError

    def _expected_basenames(self, job: UploadJob) -> list[str]:
        """
        Return expected filename basenames for verification.

        Uses os.path.basename on provided paths.
        """
        if job.single_fastq_path is not None:
            return [os.path.basename(job.single_fastq_path)]
        basenames: list[str] = []
        if job.r1_fastq_path is not None:
            basenames.append(os.path.basename(job.r1_fastq_path))
        if job.r2_fastq_path is not None:
            basenames.append(os.path.basename(job.r2_fastq_path))
        return basenames

def deliver_files_to_VIGASP( demux ):
    """
    Write the uploader file needed to upload the data to VIGASP and then
        upload the relevant files.
    """
    demux.n = demux.n + 1
    demuxLogger.info( f"==> {demux.n}/{demux.totalTasks} tasks: Preparing files for uploading to VIGASP started\n")


    demuxLogger.info( f"==< {demux.n}/{demux.totalTasks} tasks: Preparing files for uploading to VIGASP finished\n")import dataclasses