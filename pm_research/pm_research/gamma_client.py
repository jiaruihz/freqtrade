from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential


@dataclass
class GammaClient:
    base_url: str = "https://gamma-api.polymarket.com"
    timeout_s: float = 10.0

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=1, max=10))
    def _get(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        with httpx.Client(timeout=self.timeout_s) as client:
            resp = client.get(f"{self.base_url}{path}", params=params)
            resp.raise_for_status()
            return resp.json()

    def fetch_paginated(
        self, path: str, active: bool = True, limit: int = 100, pages: int | None = None
    ) -> Iterable[dict[str, Any]]:
        offset = 0
        page_count = 0
        while True:
            params = {"active": str(active).lower(), "limit": limit, "offset": offset}
            data = self._get(path, params)
            if not data:
                break
            for item in data:
                yield item
            offset += limit
            page_count += 1
            if pages is not None and page_count >= pages:
                break

    @staticmethod
    def to_raw_json(item: dict[str, Any]) -> str:
        return json.dumps(item, ensure_ascii=False)
