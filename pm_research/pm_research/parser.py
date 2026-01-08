from __future__ import annotations

import json
from typing import Any

from pm_research.llm_client import LLMClient
from pm_research.llm_prompts import FEW_SHOT, PROMPT_VERSION, build_user_prompt
from pm_research.schema import RuleParse, SCHEMA_VERSION
from pm_research.storage import utc_now


def build_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "market_id": row.get("market_id"),
        "slug": row.get("slug"),
        "question": row.get("question"),
        "description": row.get("description"),
        "rules": row.get("rules"),
        "end_at_utc": row.get("end_at_utc"),
        "category": row.get("category"),
    }


def parse_market(row: dict[str, Any], client: LLMClient) -> dict[str, Any]:
    payload = build_payload(row)
    prompt_payload = {
        "schema": RuleParse.model_json_schema(),
        "few_shot": FEW_SHOT,
        "market": payload,
    }
    prompt = build_user_prompt(json.dumps(prompt_payload, ensure_ascii=False))
    parsed, raw = client.parse(prompt)
    return {
        "market_id": parsed.market_id,
        "parsed_at_utc": utc_now(),
        "schema_version": SCHEMA_VERSION,
        "prompt_version": PROMPT_VERSION,
        "llm_model": client.model,
        "parsed_json": parsed.model_dump_json(),
        "raw_response": raw,
        "llm_confidence": parsed.llm_confidence,
        "clarity_score": parsed.clarity_score,
        "dispute_risk_score": parsed.dispute_risk_score,
        "ambiguity_flags_json": json.dumps(parsed.ambiguity_flags, ensure_ascii=False),
    }
