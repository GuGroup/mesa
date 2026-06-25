from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_USER_AGENT = "paper-search/0.1 (mailto:unset@example.com)"


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 4
    backoff_seconds: tuple[float, ...] = (5.0, 15.0, 60.0)
    retry_statuses: frozenset[int] = frozenset({429, 500, 502, 503, 504})
    respect_retry_after: bool = True
    max_sleep_seconds: float = 120.0


@dataclass(slots=True)
class HttpResponse:
    url: str
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


class HttpClient:
    def __init__(
        self,
        user_agent: str | None = None,
        timeout: int = 30,
        retry_policy: RetryPolicy | None = None,
        opener: Any = urlopen,
        sleeper: Any = time.sleep,
    ) -> None:
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        self.timeout = timeout
        self.retry_policy = retry_policy or RetryPolicy(max_attempts=1)
        self.opener = opener
        self.sleeper = sleeper
        self.retry_events: list[dict[str, Any]] = []
        # The client is shared across search threads; guard event recording.
        self._retry_events_lock = threading.Lock()

    def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        accept: str | None = None,
        max_attempts: int | None = None,
    ) -> HttpResponse:
        # max_attempts overrides the policy for this call only. Unreliable
        # fallback endpoints (e.g. Sci-Hub mirrors) pass 1 to fail fast instead
        # of burning the full retry/backoff budget on a dead mirror.
        attempts = max(max_attempts or self.retry_policy.max_attempts, 1)
        for attempt in range(1, attempts + 1):
            request = Request(url, headers=self._headers(headers, accept))
            try:
                with self.opener(request, timeout=self.timeout) as response:
                    return HttpResponse(
                        url=response.geturl(),
                        status=response.status,
                        headers={k.lower(): v for k, v in response.headers.items()},
                        body=response.read(),
                    )
            except HTTPError as exc:
                body = exc.read()
                if self._should_retry_http(exc, attempt, attempts):
                    self._wait_before_retry(
                        url,
                        attempt,
                        status=exc.code,
                        headers=exc.headers,
                    )
                    continue
                raise RuntimeError(
                    f"GET {url} failed with HTTP {exc.code} after {attempt} "
                    f"attempt(s): {body[:300]!r}"
                ) from exc
            except URLError as exc:
                if attempt < attempts:
                    self._wait_before_retry(url, attempt, error=str(exc.reason))
                    continue
                raise RuntimeError(
                    f"GET {url} failed after {attempt} attempt(s): {exc.reason}"
                ) from exc
        raise RuntimeError(f"GET {url} failed after {attempts} attempt(s)")

    def _headers(
        self,
        headers: dict[str, str] | None,
        accept: str | None,
    ) -> dict[str, str]:
        merged_headers = {"User-Agent": self.user_agent}
        if accept:
            merged_headers["Accept"] = accept
        if headers:
            merged_headers.update(headers)
        return merged_headers

    def _should_retry_http(
        self,
        exc: HTTPError,
        attempt: int,
        attempts: int,
    ) -> bool:
        return attempt < attempts and exc.code in self.retry_policy.retry_statuses

    def _wait_before_retry(
        self,
        url: str,
        attempt: int,
        status: int | None = None,
        headers: Any = None,
        error: str | None = None,
    ) -> None:
        sleep_seconds = self._sleep_seconds(attempt, headers)
        event = {
            "url": url,
            "attempt": attempt,
            "sleep_seconds": sleep_seconds,
        }
        if status is not None:
            event["status"] = status
        if error is not None:
            event["error"] = error
        with self._retry_events_lock:
            self.retry_events.append(event)
        if sleep_seconds > 0:
            self.sleeper(sleep_seconds)

    def _sleep_seconds(self, attempt: int, headers: Any = None) -> float:
        retry_after = None
        if self.retry_policy.respect_retry_after and headers:
            retry_after = _retry_after_seconds(headers.get("Retry-After"))
        if retry_after is None:
            backoff = self.retry_policy.backoff_seconds
            if not backoff:
                retry_after = 0.0
            else:
                index = min(max(attempt - 1, 0), len(backoff) - 1)
                retry_after = backoff[index]
        cap = max(float(self.retry_policy.max_sleep_seconds), 0.0)
        return min(max(float(retry_after), 0.0), cap)


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    value = value.strip()
    try:
        return float(value)
    except ValueError:
        pass
    try:
        retry_time = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if retry_time.tzinfo is None:
        retry_time = retry_time.replace(tzinfo=timezone.utc)
    return (retry_time - datetime.now(timezone.utc)).total_seconds()
