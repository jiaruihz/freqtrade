from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterable, Sequence

from pm_research.config import settings


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.PMR_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_session() -> Iterable[sqlite3.Connection]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def execute_many(conn: sqlite3.Connection, sql: str, rows: Sequence[Sequence[object]]) -> None:
    if not rows:
        return
    conn.executemany(sql, rows)


def init_db() -> None:
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS markets_raw (
                market_id TEXT,
                fetched_at_utc TEXT,
                json TEXT,
                PRIMARY KEY (market_id, fetched_at_utc)
            );
            CREATE TABLE IF NOT EXISTS events_raw (
                event_id TEXT,
                fetched_at_utc TEXT,
                json TEXT,
                PRIMARY KEY (event_id, fetched_at_utc)
            );
            CREATE TABLE IF NOT EXISTS markets (
                market_id TEXT PRIMARY KEY,
                slug TEXT,
                question TEXT,
                description TEXT,
                rules TEXT,
                category TEXT,
                active INTEGER,
                resolved INTEGER,
                end_at_utc TEXT,
                volume REAL,
                liquidity REAL,
                clob_token_ids_json TEXT,
                updated_at_utc TEXT,
                last_synced_at_utc TEXT
            );
            CREATE TABLE IF NOT EXISTS prices (
                token_id TEXT,
                fetched_at_utc TEXT,
                mid REAL,
                best_bid REAL,
                best_ask REAL,
                spread REAL,
                spread_pct_mid REAL,
                PRIMARY KEY (token_id, fetched_at_utc)
            );
            CREATE TABLE IF NOT EXISTS orderbook_levels (
                token_id TEXT,
                fetched_at_utc TEXT,
                side TEXT CHECK(side in ('bid','ask')),
                level INTEGER,
                price REAL,
                size REAL,
                PRIMARY KEY (token_id, fetched_at_utc, side, level)
            );
            CREATE TABLE IF NOT EXISTS rule_parses (
                market_id TEXT,
                parsed_at_utc TEXT,
                schema_version TEXT,
                prompt_version TEXT,
                llm_model TEXT,
                parsed_json TEXT,
                raw_response TEXT,
                llm_confidence REAL,
                clarity_score REAL,
                dispute_risk_score REAL,
                ambiguity_flags_json TEXT,
                PRIMARY KEY (market_id, schema_version, prompt_version)
            );
            CREATE TABLE IF NOT EXISTS scores (
                market_id TEXT,
                scored_at_utc TEXT,
                total_score REAL,
                features_json TEXT,
                PRIMARY KEY (market_id, scored_at_utc)
            );
            """
        )
