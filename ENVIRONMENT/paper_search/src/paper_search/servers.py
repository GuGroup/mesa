from __future__ import annotations

import shlex
import subprocess
import time
from dataclasses import dataclass
from urllib.error import URLError
from urllib.request import Request, urlopen

from paper_search.http import DEFAULT_USER_AGENT


@dataclass(slots=True)
class ManagedServerConfig:
    start_cmd: str | None = None
    base_url: str | None = None
    health_path: str = "/api/isalive"
    startup_timeout: float = 30.0
    shutdown_timeout: float = 10.0
    required: bool = False


class ManagedServer:
    def __init__(self, config: ManagedServerConfig) -> None:
        self.config = config
        self.process: subprocess.Popen[bytes] | None = None
        self.startup_error: str | None = None

    def __enter__(self) -> str | None:
        if self.config.base_url and self._is_ready():
            return self.config.base_url
        if not self.config.start_cmd:
            return self.config.base_url
        if not self.config.base_url:
            return self._startup_failed("Managed server start_cmd requires a base_url.")
        try:
            self.process = subprocess.Popen(
                shlex.split(self.config.start_cmd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        except OSError as exc:
            return self._startup_failed(str(exc))
        try:
            self._wait_until_ready()
        except BaseException as exc:
            self.close()
            return self._startup_failed(str(exc))
        return self.config.base_url

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def close(self) -> None:
        if self.process is None:
            return
        if self.process.poll() is not None:
            self.process = None
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=self.config.shutdown_timeout)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        finally:
            self.process = None

    def _startup_failed(self, error: str) -> str | None:
        self.startup_error = error
        if self.config.required:
            raise RuntimeError(error)
        return None

    def _is_ready(self) -> bool:
        if not self.config.base_url:
            return False
        health_url = self.config.base_url.rstrip("/") + self.config.health_path
        try:
            request = Request(health_url, headers={"User-Agent": DEFAULT_USER_AGENT})
            with urlopen(request, timeout=2) as response:
                return 200 <= response.status < 500
        except (URLError, TimeoutError):
            return False

    def _wait_until_ready(self) -> None:
        assert self.config.base_url is not None
        deadline = time.monotonic() + self.config.startup_timeout
        health_url = self.config.base_url.rstrip("/") + self.config.health_path
        last_error = "not checked"
        while time.monotonic() < deadline:
            if self.process and self.process.poll() is not None:
                stderr = self.process.stderr.read(2000).decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"Managed server exited before becoming ready: {stderr}"
                )
            if self._is_ready():
                return
            try:
                request = Request(health_url, headers={"User-Agent": DEFAULT_USER_AGENT})
                urlopen(request, timeout=2).close()
            except URLError as exc:
                last_error = str(exc.reason)
            except TimeoutError as exc:
                last_error = str(exc)
            time.sleep(0.5)
        raise RuntimeError(f"Managed server readiness timed out: {health_url} ({last_error})")
