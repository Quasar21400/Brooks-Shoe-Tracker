"""HTTP client that looks like Chrome.

brooksrunning.com sits behind Akamai, which rejects Python's default TLS
fingerprint with a 403. curl_cffi impersonates Chrome's handshake and gets
through. urllib is kept as a fallback so the tests run without curl_cffi.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

try:
    from curl_cffi import requests as curl_requests
except ImportError:  # pragma: no cover - exercised only without the dependency
    curl_requests = None

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
RETRY_STATUSES = {403, 408, 425, 429, 500, 502, 503, 504}


class HttpError(Exception):
    def __init__(self, url: str, status: int, snippet: str = ""):
        self.status = status
        super().__init__(f"HTTP {status} from {url}" + (f": {snippet}" if snippet else ""))


@dataclass
class Response:
    url: str
    status: int
    text: str

    def json(self):
        return json.loads(self.text)


class Http:
    def __init__(self, timeout: float = 30, attempts: int = 3, backoff: float = 4):
        self.timeout = timeout
        self.attempts = attempts
        self.backoff = backoff
        self._session = curl_requests.Session(impersonate="chrome") if curl_requests else None

    def get(self, url: str, headers: dict | None = None, ok_statuses=(200,)) -> Response:
        return self._request("GET", url, headers or {}, None, ok_statuses)

    def get_json(self, url: str, headers: dict | None = None):
        hdrs = {"Accept": "application/json, text/javascript, */*; q=0.01"}
        hdrs.update(headers or {})
        return self.get(url, hdrs).json()

    def post_json(self, url: str, payload: dict, headers: dict | None = None):
        hdrs = {"Accept": "application/json", "Content-Type": "application/json"}
        hdrs.update(headers or {})
        return self._request("POST", url, hdrs, json.dumps(payload).encode(), (200,)).json()

    def _request(self, method: str, url: str, headers: dict, body: bytes | None, ok_statuses) -> Response:
        last: Exception | None = None
        for attempt in range(self.attempts):
            if attempt:
                time.sleep(self.backoff * attempt)
            try:
                resp = self._once(method, url, headers, body)
            except Exception as exc:  # network errors, timeouts
                last = exc
                continue
            if resp.status in ok_statuses:
                return resp
            last = HttpError(url, resp.status, resp.text[:120].strip())
            if resp.status not in RETRY_STATUSES:
                raise last
        raise last  # type: ignore[misc]

    def _once(self, method: str, url: str, headers: dict, body: bytes | None) -> Response:
        if self._session is not None:
            r = self._session.request(method, url, headers=headers, data=body, timeout=self.timeout)
            return Response(str(r.url), r.status_code, r.text)
        hdrs = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
        hdrs.update(headers)
        req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return Response(r.geturl(), r.status, r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            return Response(url, exc.code, exc.read().decode("utf-8", "replace"))
