from __future__ import annotations

import gzip
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from pm_research.clob_client import CLOBClient, RateLimiter
from pm_research.config import pipeline_config, rate_limit_config
from pm_research.gamma_client import GammaClient
from pm_research.metrics import (
    calc_spread,
    calc_spread_pct_mid,
    depth_within_pct,
)
from pm_research.llm_client import LLMClient
from pm_research.parser import parse_market
from pm_research.scoring import friction_score, rule_score, total_score
from pm_research.storage import (
    insert_events_raw,
    insert_markets_raw,
    insert_orderbook_levels,
    insert_prices,
    insert_rule_parse,
    insert_score,
    upsert_markets,
    utc_now,
)

logger = logging.getLogger(__name__)


def sync_gamma(conn, active: bool, pages: int | None, page_size: int) -> dict[str, int]:
    client = GammaClient()
    markets = list(client.fetch_paginated("/markets", active=active, limit=page_size, pages=pages))
    events = list(client.fetch_paginated("/events", active=active, limit=page_size, pages=pages))

    raw_markets = insert_markets_raw(conn, markets)
    raw_events = insert_events_raw(conn, events)
    upserted = upsert_markets(conn, markets)

    return {"raw_markets": raw_markets, "raw_events": raw_events, "upserted": upserted}


def _extract_levels(book: dict[str, Any], side: str, top_n: int) -> list[dict[str, Any]]:
    levels = []
    for i, lvl in enumerate(book.get(side, [])[:top_n]):
        levels.append({"level": i + 1, "price": float(lvl[0]), "size": float(lvl[1])})
    return levels


def enrich_clob(
    conn,
    token_ids: list[str],
    fetch_prices: bool,
    fetch_books: bool,
    archive_books: bool = False,
) -> dict[str, Any]:
    limiter = RateLimiter(rate_limit_config.requests_per_second, rate_limit_config.burst)
    client = CLOBClient(limiter=limiter)
    fetched_at = utc_now()

    price_rows = []
    level_rows = []
    sample_metrics = []

    archive_dir = Path("archive/books")
    if archive_books:
        archive_dir.mkdir(parents=True, exist_ok=True)

    def handle_token(token_id: str) -> dict[str, Any]:
        payload: dict[str, Any] = {"token_id": token_id}
        if fetch_prices:
            mid = client.midprice(token_id)
            best = client.price(token_id)
            payload["mid"] = float(mid.get("mid", 0) or 0)
            payload["best_bid"] = float(best.get("bestBid", 0) or 0)
            payload["best_ask"] = float(best.get("bestAsk", 0) or 0)
        if fetch_books:
            book = client.book(token_id)
            payload["book"] = book
        return payload

    with ThreadPoolExecutor(max_workers=pipeline_config.clob_max_workers) as executor:
        futures = {executor.submit(handle_token, token_id): token_id for token_id in token_ids}
        for future in as_completed(futures):
            token_id = futures[future]
            try:
                payload = future.result()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed token %s: %s", token_id, exc)
                continue

            mid = payload.get("mid")
            best_bid = payload.get("best_bid")
            best_ask = payload.get("best_ask")
            spread = calc_spread(best_bid, best_ask)
            spread_pct_mid = calc_spread_pct_mid(spread, mid)

            if fetch_prices:
                price_rows.append(
                    {
                        "token_id": token_id,
                        "fetched_at_utc": fetched_at,
                        "mid": mid,
                        "best_bid": best_bid,
                        "best_ask": best_ask,
                        "spread": spread,
                        "spread_pct_mid": spread_pct_mid,
                    }
                )

            book = payload.get("book")
            if fetch_books and book:
                bids = _extract_levels(book, "bids", pipeline_config.orderbook_top_n)
                asks = _extract_levels(book, "asks", pipeline_config.orderbook_top_n)
                for lvl in bids:
                    level_rows.append(
                        {
                            "token_id": token_id,
                            "fetched_at_utc": fetched_at,
                            "side": "bid",
                            **lvl,
                        }
                    )
                for lvl in asks:
                    level_rows.append(
                        {
                            "token_id": token_id,
                            "fetched_at_utc": fetched_at,
                            "side": "ask",
                            **lvl,
                        }
                    )

                if archive_books:
                    archive_path = archive_dir / f"{token_id}_{fetched_at}.json.gz"
                    with gzip.open(archive_path, "wt", encoding="utf-8") as handle:
                        handle.write(json.dumps(book, ensure_ascii=False))

                depth_1pct_bid = depth_within_pct(bids, mid or 0, 0.01, "bid")
                depth_1pct_ask = depth_within_pct(asks, mid or 0, 0.01, "ask")
                depth_2pct_bid = depth_within_pct(bids, mid or 0, 0.02, "bid")
                depth_2pct_ask = depth_within_pct(asks, mid or 0, 0.02, "ask")
                sample_metrics.append(
                    {
                        "token_id": token_id,
                        "mid": mid,
                        "best_bid": best_bid,
                        "best_ask": best_ask,
                        "spread": spread,
                        "spread_pct_mid": spread_pct_mid,
                        "depth_1pct_bid": depth_1pct_bid,
                        "depth_1pct_ask": depth_1pct_ask,
                        "depth_2pct_bid": depth_2pct_bid,
                        "depth_2pct_ask": depth_2pct_ask,
                    }
                )

    insert_prices(conn, price_rows)
    insert_orderbook_levels(conn, level_rows)
    return {
        "prices_written": len(price_rows),
        "levels_written": len(level_rows),
        "sample_metrics": sample_metrics[:3],
    }


def parse_rules(conn, markets: list[dict[str, Any]], client: LLMClient) -> list[dict[str, Any]]:
    results = []
    for row in markets:
        parsed = parse_market(row, client)
        insert_rule_parse(conn, parsed)
        results.append(parsed)
    return results


def score_market(
    conn,
    market_id: str,
    clarity_score: float,
    dispute_risk_score: float,
    trigger_type: str,
    liquidity_score_val: float,
    spread_pct_mid: float | None,
) -> dict[str, Any]:
    r_score = rule_score(clarity_score, dispute_risk_score, trigger_type)
    f_score = friction_score(liquidity_score_val, spread_pct_mid)
    total = total_score(r_score, f_score)
    row = {
        "market_id": market_id,
        "scored_at_utc": utc_now(),
        "total_score": total,
        "features_json": json.dumps(
            {
                "rule_score": r_score,
                "friction_score": f_score,
                "liquidity_score": liquidity_score_val,
                "spread_pct_mid": spread_pct_mid,
            },
            ensure_ascii=False,
        ),
    }
    insert_score(conn, row)
    return row
