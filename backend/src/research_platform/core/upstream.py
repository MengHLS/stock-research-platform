"""Shared outbound access to public external data services.

Every provider request goes through this module so that timeouts, bounded
retries, per-provider pacing, response size limits and payload decoding are
reviewed in one place (docs/architecture.md "外部数据服务与公共访问"):

- only idempotent GET requests are retried, at most once, and only on connection
  errors or 502/503/504; 4xx, 429 and POST are never retried behind a caller;
- logging records provider, path and error class only, never a query string or
  body, so a Tushare token cannot leak through a log line;
- every failure becomes an explicit ``MARKET_SOURCE_*`` code. An empty payload is
  never substituted for a failure, and 200-with-garbage is a 502, not an empty
  list the caller might read as "no trades today".
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlsplit

import httpx2 as httpx

from .config import Settings
from .errors import DomainError
from .logging import log_event

MAX_RESPONSE_BYTES = 4 * 1024 * 1024
BODY_CHUNK_BYTES = 64 * 1024
RETRYABLE_STATUS = frozenset({502, 503, 504})

# Only failures that prove the request never reached the peer are retried. A
# timeout is deliberately excluded: the request may have been processed, and a
# second attempt doubles the latency a caller already waited for (see
# docs/architecture.md "超时与重试").
# ConnectTimeout is deliberately excluded: a timeout is a timeout, regardless of
# phase, and the reviewed rule is that timeouts are not retried.
RETRYABLE_ERRORS = (httpx.ConnectError, httpx.ReadError)
RETRY_BACKOFF_SECONDS = 0.25
USER_AGENT = "stock-research-platform/0.1 (local research; single user)"

Transport = httpx.BaseTransport


def _close(stream: Any, response: httpx.Response) -> None:
    """Release the response, whether it arrived as a context manager or plain."""
    if hasattr(stream, "__exit__"):
        stream.__exit__(None, None, None)
    else:
        response.close()


class UpstreamClient:
    """Bounded HTTP client for public data sources (GET reads, no credentials in logs)."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: Transport | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        config = settings.upstream
        self._enabled = config.enabled
        self._max_retries = config.max_retries
        self._min_interval = config.min_interval_ms / 1000
        self._host_addresses = {k.lower(): v for k, v in config.host_addresses.items()}
        self._clock = clock
        self._sleep = sleep
        self._last_request: dict[str, float] = {}
        self._pace_lock = threading.Lock()
        self._client = httpx.Client(
            timeout=httpx.Timeout(config.timeout_seconds),
            follow_redirects=False,
            # A local proxy is an explicit opt-in via the environment; silently
            # routing research traffic through one is not a decision this client
            # makes for the operator.
            trust_env=False,
            transport=transport,
            headers={"User-Agent": USER_AGENT},
        )

    def close(self) -> None:
        self._client.close()

    def get_json(
        self,
        *,
        provider: str,
        url: str,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        body = self._request("GET", provider, url, params=params, headers=headers, retryable=True)
        return self._decode_json(provider, body)

    def get_text(
        self,
        *,
        provider: str,
        url: str,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        encoding: str = "utf-8",
    ) -> str:
        body = self._request("GET", provider, url, params=params, headers=headers, retryable=True)
        try:
            return body.decode(encoding, errors="replace")
        except LookupError:
            raise self._bad_response(provider, "unsupported response encoding") from None

    def post_json(
        self,
        *,
        provider: str,
        url: str,
        payload: Mapping[str, Any],
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        # Query APIs that only accept POST are still reads, but they are not
        # retried: repeating a query behind the caller's back hides its failure.
        body = self._request(
            "POST", provider, url, json_body=payload, headers=headers, retryable=False
        )
        return self._decode_json(provider, body)

    def _request(
        self,
        method: str,
        provider: str,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | None = None,
        retryable: bool,
    ) -> bytes:
        if not self._enabled:
            raise DomainError("MARKET_SOURCE_DISABLED")
        path = urlsplit(url).path
        attempts = self._max_retries + 1 if retryable else 1
        for attempt in range(1, attempts + 1):
            # Paced per attempt, not per call: a retry is a real request and must
            # respect the provider's minimum interval like a first attempt.
            self._pace(provider)
            try:
                stream = self._stream_once(
                    method, url, params=params, headers=headers, json_body=json_body
                )
            except httpx.HTTPError as error:
                if attempt < attempts and isinstance(error, RETRYABLE_ERRORS):
                    self._sleep(RETRY_BACKOFF_SECONDS)
                    continue
                log_event(
                    "upstream.request_failed",
                    level=30,
                    provider=provider,
                    path=path,
                    attempt=attempt,
                    error_type=type(error).__name__,
                )
                raise DomainError("MARKET_SOURCE_UNAVAILABLE") from None
            try:
                # ``client.stream()`` yields a context manager, while a custom
                # transport (and MockTransport) may hand back a ready Response.
                # Both are accepted so tests exercise the same code path.
                entered = stream.__enter__() if hasattr(stream, "__enter__") else stream
                response = entered
            except httpx.HTTPError as error:
                # A failure while waiting for the response headers.
                if attempt < attempts and isinstance(error, RETRYABLE_ERRORS):
                    self._sleep(RETRY_BACKOFF_SECONDS)
                    continue
                log_event(
                    "upstream.request_failed",
                    level=30,
                    provider=provider,
                    path=path,
                    attempt=attempt,
                    error_type=type(error).__name__,
                )
                raise DomainError("MARKET_SOURCE_UNAVAILABLE") from None

            if response.status_code in RETRYABLE_STATUS and attempt < attempts:
                _close(stream, response)
                self._sleep(RETRY_BACKOFF_SECONDS)
                continue
            if response.is_redirect:
                # Redirects are not followed: a silent hop to another host would
                # hide that the endpoint moved (and could send the request to a
                # host this project never reviewed). Surfacing it as a source
                # failure keeps the caller's "no data" and "endpoint moved"
                # cases distinct instead of failing later on HTML as bad JSON.
                log_event(
                    "upstream.redirected",
                    level=30,
                    provider=provider,
                    path=path,
                    status=response.status_code,
                )
                _close(stream, response)
                raise DomainError("MARKET_SOURCE_UNAVAILABLE") from None
            if response.status_code >= 400:
                log_event(
                    "upstream.rejected",
                    level=30,
                    provider=provider,
                    path=path,
                    status=response.status_code,
                )
                # Rate limiting is a distinct condition the caller can act on
                # (back off and retry later) and must not be reported as a plain
                # outage; the error table already defines a 429 code.
                _close(stream, response)
                if response.status_code == 429:
                    raise DomainError("MARKET_SOURCE_RATE_LIMITED") from None
                raise DomainError("MARKET_SOURCE_UNAVAILABLE") from None
            try:
                return self._bounded_body(provider, response)
            except DomainError:
                raise
            except httpx.DecodingError:
                # Broken/truncated compression: the peer answered, but the bytes
                # are unusable. That is a payload defect, not an outage, and it is
                # never retried (a re-fetch would return the same bytes).
                log_event(
                    "upstream.decode_failed",
                    level=30,
                    provider=provider,
                    path=path,
                    attempt=attempt,
                )
                raise self._bad_response(provider, "response body cannot be decoded") from None
            except httpx.HTTPError as error:
                # Failures while *consuming* the body (read timeout, connection
                # reset, broken gzip) used to escape as raw httpx errors, which
                # bypass the DomainError-based degradation chain and surface as a
                # generic 500. They are provider failures like any other.
                log_event(
                    "upstream.body_failed",
                    level=30,
                    provider=provider,
                    path=path,
                    attempt=attempt,
                    error_type=type(error).__name__,
                )
                if (
                    attempt < attempts
                    and isinstance(error, RETRYABLE_ERRORS)
                    and not isinstance(error, httpx.DecodingError)
                ):
                    # Closing is the ``finally`` block's job; doing it here too
                    # closed the same stream twice on the retry path.
                    self._sleep(RETRY_BACKOFF_SECONDS)
                    continue
                raise DomainError("MARKET_SOURCE_UNAVAILABLE") from None
            finally:
                _close(stream, response)
        raise DomainError("MARKET_SOURCE_UNAVAILABLE")

    def _bounded_body(self, provider: str, response: httpx.Response) -> bytes:
        """Read the body with a hard size ceiling, aborting a stream that overruns.

        ``response.content`` materialises the whole body before any check, so a
        huge or decompression-bombed reply is already in memory by the time it is
        rejected. Reading in chunks lets the limit stop the download while it is
        happening; ``Content-Length`` is still checked first as a cheap early
        rejection for well-behaved servers.
        """
        declared = response.headers.get("content-length")
        if declared is not None:
            try:
                if int(declared) > MAX_RESPONSE_BYTES:
                    raise self._bad_response(provider, "declared body exceeds size limit")
            except ValueError:
                raise self._bad_response(provider, "invalid content-length") from None
        # A response that already carries ``_content`` (a custom transport such as
        # MockTransport hands back a ready Response) has no raw stream to bound;
        # its size is checked directly. Real network responses are read in fixed
        # chunks so the ceiling stops the download while it is happening.
        if hasattr(response, "_content"):
            body = response.content
            if len(body) > MAX_RESPONSE_BYTES:
                raise self._bad_response(provider, "body exceeds size limit")
            return body
        chunks: list[bytes] = []
        total = 0
        try:
            # ``iter_bytes`` decodes Content-Encoding (gzip/deflate/br); using
            # ``iter_raw`` here would hand compressed bytes to the JSON parser.
            # The explicit chunk size keeps the ceiling observable mid-download.
            for chunk in response.iter_bytes(BODY_CHUNK_BYTES):
                total += len(chunk)
                if total > MAX_RESPONSE_BYTES:
                    raise self._bad_response(provider, "streamed body exceeds size limit")
                chunks.append(chunk)
        finally:
            response.close()
        return b"".join(chunks)

    def _stream_once(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, str] | None,
        headers: Mapping[str, str] | None,
        json_body: Mapping[str, Any] | None,
    ):
        """Issue one request, honouring an optional per-host address pin.

        The pin is applied per *request*, not by mutating global resolver state:
        the URL is rewritten to the configured address while the ``Host`` header
        and the TLS ``sni_hostname`` extension keep the original hostname, so
        certificate verification still proves the peer is the real host. Patching
        ``socket.getaddrinfo`` was rejected because concurrent requests overwrite
        each other's patch and leave the process resolving every later host
        through a stale closure.

        With an empty ``host_addresses`` configuration this adds no header and no
        extension: the request is identical to a plain ``client.request``.
        """
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        addresses = self._host_addresses.get(host)
        if not addresses:
            return self._client.stream(method, url, params=params, headers=headers, json=json_body)
        target = addresses[0]
        pinned_headers = dict(headers or {})
        pinned_headers["Host"] = parts.netloc
        pinned_url = parts._replace(netloc=target).geturl()
        request = self._client.build_request(
            method, pinned_url, params=params, headers=pinned_headers, json=json_body
        )
        request.extensions["sni_hostname"] = host
        log_event("upstream.address_pinned", provider="upstream", host=host)
        return self._client.send(request, stream=True)

    def _pace(self, provider: str) -> None:
        """Reserve the next send slot for a provider atomically, then wait for it.

        Two concerns this closes:

        - **Concurrency**: several threads fetching different symbols share one
          per-provider interval. Reading ``last_request`` without a lock let them
          all see the same previous timestamp and fire together, defeating the
          pacing exactly when it matters (a batch of symbols).
        - **Retries**: pacing used to run once per call, outside the retry loop,
          so a retry could follow the previous attempt after only the fixed
          backoff and violate the configured minimum interval.

        Each *send* now calls this, so retries are paced like first attempts.
        """
        if self._min_interval <= 0:
            return
        with self._pace_lock:
            now = self._clock()
            previous = self._last_request.get(provider)
            target = now if previous is None else max(now, previous + self._min_interval)
            self._last_request[provider] = target
            wait = target - now
        if wait > 0:
            self._sleep(wait)

    def _decode_json(self, provider: str, body: bytes) -> Any:
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise self._bad_response(provider, "payload is not valid JSON") from None

    @staticmethod
    def _bad_response(provider: str, reason: str) -> DomainError:
        log_event("upstream.bad_response", level=30, provider=provider, reason=reason)
        return DomainError("MARKET_SOURCE_BAD_RESPONSE")
