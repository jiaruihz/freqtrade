from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class EntityDefinition(BaseModel):
    entity: str
    definition: str


class TimeWindow(BaseModel):
    start_at_utc: str | None = None
    end_at_utc: str | None = None
    timezone_source: str | None = None


class RuleParse(BaseModel):
    market_id: str
    slug: str | None = None
    time_window: TimeWindow
    settlement_source_type: Literal[
        "official_docs", "credible_reporting_consensus", "mixed", "unknown"
    ]
    trigger_type: Literal[
        "definition_driven",
        "data_print",
        "procedural_vote",
        "military_action",
        "financial_price_level",
        "other",
    ]
    trigger_minimum_conditions: list[str] = Field(default_factory=list)
    explicit_exclusions: list[str] = Field(default_factory=list)
    entity_definitions: list[EntityDefinition] = Field(default_factory=list)
    ambiguity_flags: list[str] = Field(default_factory=list)
    clarity_score: float = Field(ge=0.0, le=1.0)
    dispute_risk_score: float = Field(ge=0.0, le=1.0)
    notes_for_humans: str
    llm_confidence: float = Field(ge=0.0, le=1.0)


SCHEMA_VERSION = "1.0"
