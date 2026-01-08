from __future__ import annotations

from pm_research.config import pipeline_config


def rule_score(clarity_score: float, dispute_risk_score: float, trigger_type: str) -> float:
    base = (clarity_score * 0.7) + ((1 - dispute_risk_score) * 0.3)
    bonus = pipeline_config.trigger_bonus.get(trigger_type, 0.0)
    return min(1.0, base + bonus)


def friction_score(liquidity_score: float, spread_pct_mid: float | None) -> float:
    spread_penalty = 0.0
    if spread_pct_mid is not None:
        spread_penalty = min(spread_pct_mid / 0.1, 1.0) * 0.5
    return max(0.0, (liquidity_score / 100) - spread_penalty)


def total_score(rule_score_val: float, friction_score_val: float) -> float:
    return (
        rule_score_val * pipeline_config.rule_score_weight
        + friction_score_val * pipeline_config.friction_score_weight
    )
