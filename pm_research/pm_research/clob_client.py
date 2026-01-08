from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


class RateLimiter:
    def __init__(self, rate_per_sec: float, burst: int) -> None:
        self.rate = rate_per_sec
        self.capacity = burst
        self.tokens = burst
        self.updated = time.monotonic()
        self.lock = threading.Lock()

    def acquire(self) -> None:
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.updated
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.updated = now
            if self.tokens < 1:
                sleep_for = (1 - self.tokens) / self.rate
                time.sleep(sleep_for)
                self.tokens = 0
            self.tokens -= 1


@dataclass
class CLOBClient:
    base_url: str = "https://clob.polymarket.com"
    timeout_s: float = 10.0
    limiter: RateLimiter | None = None

    def _request(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        if self.limiter:
            self.limiter.acquire()
        with httpx.Client(timeout=self.timeout_s) as client:
            resp = client.get(f"{self.base_url}{path}", params=params)
            if resp.status_code == 429:
                raise httpx.HTTPStatusError("rate limited", request=resp.request, response=resp)
            resp.raise_for_status()
            return resp.json()

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.HTTPStatusError),
    )
    def midprice(self, token_id: str) -> dict[str, Any]:
        return self._request("/midprice", {"token_id": token_id})

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.HTTPStatusError),
    )
    def price(self, token_id: str) -> dict[str, Any]:
        return self._request("/price", {"token_id": token_id})

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.HTTPStatusError),
    )
    def book(self, token_id: str) -> dict[str, Any]:
        return self._request("/book", {"token_id": token_id})

    @staticmethod
    def to_raw_json(item: dict[str, Any]) -> str:
        return json.dumps(item, ensure_ascii=False)


def fetch_with(client: CLOBClient, fn: Callable[[str], dict[str, Any]], token_id: str) -> dict[str, Any]:
    return fn(token_id)
