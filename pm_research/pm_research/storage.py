from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable

from pm_research.db import execute_many


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_markets(conn, rows: Iterable[dict[str, Any]]) -> int:
    data = []
    for row in rows:
        data.append(
            (
                row.get("id"),
                row.get("slug"),
                row.get("question"),
                row.get("description"),
                row.get("rules"),
                row.get("category"),
                int(bool(row.get("active", False))),
                int(bool(row.get("resolved", False))),
                row.get("endDate"),
                row.get("volume"),
                row.get("liquidity"),
                json.dumps(row.get("clobTokenIds") or []),
                row.get("updatedAt"),
                utc_now(),
            )
        )
    execute_many(
        conn,
        """
        INSERT INTO markets (
            market_id, slug, question, description, rules, category,
            active, resolved, end_at_utc, volume, liquidity,
            clob_token_ids_json, updated_at_utc, last_synced_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(market_id) DO UPDATE SET
            slug=excluded.slug,
            question=excluded.question,
            description=excluded.description,
            rules=excluded.rules,
            category=excluded.category,
            active=excluded.active,
            resolved=excluded.resolved,
            end_at_utc=excluded.end_at_utc,
            volume=excluded.volume,
            liquidity=excluded.liquidity,
            clob_token_ids_json=excluded.clob_token_ids_json,
            updated_at_utc=excluded.updated_at_utc,
            last_synced_at_utc=excluded.last_synced_at_utc
        """,
        data,
    )
    return len(data)


def insert_markets_raw(conn, rows: Iterable[dict[str, Any]]) -> int:
    fetched_at = utc_now()
    data = []
    for row in rows:
        data.append((row.get("id"), fetched_at, json.dumps(row, ensure_ascii=False)))
    execute_many(
        conn,
        "INSERT INTO markets_raw (market_id, fetched_at_utc, json) VALUES (?, ?, ?)",
        data,
    )
    return len(data)


def insert_events_raw(conn, rows: Iterable[dict[str, Any]]) -> int:
    fetched_at = utc_now()
    data = []
    for row in rows:
        data.append((row.get("id"), fetched_at, json.dumps(row, ensure_ascii=False)))
    execute_many(
        conn,
        "INSERT INTO events_raw (event_id, fetched_at_utc, json) VALUES (?, ?, ?)",
        data,
    )
    return len(data)


def insert_prices(conn, rows: Iterable[dict[str, Any]]) -> int:
    data = []
    for row in rows:
        data.append(
            (
                row["token_id"],
                row["fetched_at_utc"],
                row.get("mid"),
                row.get("best_bid"),
                row.get("best_ask"),
                row.get("spread"),
                row.get("spread_pct_mid"),
            )
        )
    execute_many(
        conn,
        """
        INSERT INTO prices (
            token_id, fetched_at_utc, mid, best_bid, best_ask, spread, spread_pct_mid
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(token_id, fetched_at_utc) DO UPDATE SET
            mid=excluded.mid,
            best_bid=excluded.best_bid,
            best_ask=excluded.best_ask,
            spread=excluded.spread,
            spread_pct_mid=excluded.spread_pct_mid
        """,
        data,
    )
    return len(data)


def insert_orderbook_levels(conn, rows: Iterable[dict[str, Any]]) -> int:
    data = []
    for row in rows:
        data.append(
            (
                row["token_id"],
                row["fetched_at_utc"],
                row["side"],
                row["level"],
                row["price"],
                row["size"],
            )
        )
    execute_many(
        conn,
        """
        INSERT INTO orderbook_levels (
            token_id, fetched_at_utc, side, level, price, size
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(token_id, fetched_at_utc, side, level) DO UPDATE SET
            price=excluded.price,
            size=excluded.size
        """,
        data,
    )
    return len(data)


def insert_rule_parse(conn, row: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO rule_parses (
            market_id, parsed_at_utc, schema_version, prompt_version, llm_model,
            parsed_json, raw_response, llm_confidence, clarity_score,
            dispute_risk_score, ambiguity_flags_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(market_id, schema_version, prompt_version) DO UPDATE SET
            parsed_at_utc=excluded.parsed_at_utc,
            llm_model=excluded.llm_model,
            parsed_json=excluded.parsed_json,
            raw_response=excluded.raw_response,
            llm_confidence=excluded.llm_confidence,
            clarity_score=excluded.clarity_score,
            dispute_risk_score=excluded.dispute_risk_score,
            ambiguity_flags_json=excluded.ambiguity_flags_json
        """,
        (
            row["market_id"],
            row["parsed_at_utc"],
            row["schema_version"],
            row["prompt_version"],
            row["llm_model"],
            row["parsed_json"],
            row["raw_response"],
            row["llm_confidence"],
            row["clarity_score"],
            row["dispute_risk_score"],
            row["ambiguity_flags_json"],
        ),
    )


def insert_score(conn, row: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO scores (market_id, scored_at_utc, total_score, features_json)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(market_id, scored_at_utc) DO UPDATE SET
            total_score=excluded.total_score,
            features_json=excluded.features_json
        """,
        (
            row["market_id"],
            row["scored_at_utc"],
            row["total_score"],
            row["features_json"],
        ),
    )
