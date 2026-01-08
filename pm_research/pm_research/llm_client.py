from __future__ import annotations

from dataclasses import dataclass

import httpx
from pydantic import ValidationError

from pm_research.config import settings
from pm_research.llm_prompts import SYSTEM_PROMPT
from pm_research.schema import RuleParse


@dataclass
class LLMClient:
    base_url: str = settings.LLM_BASE_URL
    api_key: str = settings.LLM_API_KEY
    model: str = settings.LLM_MODEL
    timeout_s: float = 30.0

    def _post(self, messages: list[dict[str, str]]) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        payload = {"model": self.model, "messages": messages, "temperature": 0}
        with httpx.Client(timeout=self.timeout_s) as client:
            resp = client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]["content"]

    def parse(self, user_prompt: str) -> tuple[RuleParse, str]:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        raw = self._post(messages)
        try:
            parsed = RuleParse.model_validate_json(raw)
            return parsed, raw
        except ValidationError:
            retry_messages = messages + [
                {
                    "role": "user",
                    "content": "Output ONLY valid JSON that matches the schema. No extra text.",
                }
            ]
            retry_raw = self._post(retry_messages)
            parsed = RuleParse.model_validate_json(retry_raw)
            return parsed, retry_raw
