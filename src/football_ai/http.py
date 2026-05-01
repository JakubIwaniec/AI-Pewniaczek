from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


@dataclass
class HttpClient:
    user_agent: str = (
        "football-ai-hobby/0.1 (+https://localhost; contact: none) "
        "python-requests"
    )
    timeout_s: int = 30
    min_delay_s: float = 1.0
    _last_request_ts: float = 0.0

    def _sleep_if_needed(self) -> None:
        elapsed = time.time() - self._last_request_ts
        if elapsed < self.min_delay_s:
            time.sleep(self.min_delay_s - elapsed)

    @retry(
        retry=retry_if_exception_type(requests.RequestException),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def get(
        self,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, str]] = None,
    ) -> Tuple[int, bytes, str]:
        self._sleep_if_needed()
        hdrs = {"User-Agent": self.user_agent}
        if headers:
            hdrs.update(headers)
        resp = requests.get(url, headers=hdrs, params=params, timeout=self.timeout_s)
        self._last_request_ts = time.time()
        return resp.status_code, resp.content, resp.url

