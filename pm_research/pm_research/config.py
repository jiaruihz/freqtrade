from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    PMR_DB_PATH: str = "./pm_research.db"
    PMR_LOG_LEVEL: str = "INFO"

    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"


@dataclass(frozen=True)
class RateLimitConfig:
    requests_per_second: float = 5.0
    burst: int = 5


@dataclass(frozen=True)
class PipelineConfig:
    orderbook_top_n: int = 20
    clob_batch_size: int = 50
    clob_max_workers: int = 8
    gamma_page_size: int = 100

    rule_score_weight: float = 0.6
    friction_score_weight: float = 0.4

    trigger_bonus: dict[str, float] | None = None

    def __post_init__(self) -> None:
        if self.trigger_bonus is None:
            object.__setattr__(
                self,
                "trigger_bonus",
                {
                    "definition_driven": 0.1,
                    "procedural_vote": 0.1,
                    "data_print": 0.1,
                },
            )


settings = Settings()
rate_limit_config = RateLimitConfig()
pipeline_config = PipelineConfig()
