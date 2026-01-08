from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import pandas as pd
import typer
from rich import print

from pm_research.config import pipeline_config, settings
from pm_research.db import db_session, init_db
from pm_research.llm_client import LLMClient
from pm_research.metrics import (
    calc_spread,
    calc_spread_pct_mid,
    depth_within_pct,
    liquidity_score,
)
from pm_research.pipeline import enrich_clob, parse_rules, score_market, sync_gamma
from pm_research.storage import utc_now

app = typer.Typer(help="Polymarket research-only pipeline")


@app.callback()
def setup() -> None:
    logging.basicConfig(level=settings.PMR_LOG_LEVEL)
    init_db()


@app.command()
def sync(
    active: bool = typer.Option(True, "--active"),
    pages: Optional[int] = typer.Option(None, "--pages"),
    page_size: int = typer.Option(100, "--page-size"),
) -> None:
    """Sync Gamma markets/events (raw + canonical)."""
    with db_session() as conn:
        result = sync_gamma(conn, active=active, pages=pages, page_size=page_size)
    print(
        f"raw_markets={result['raw_markets']} raw_events={result['raw_events']} "
        f"upserted={result['upserted']}"
    )
    print("验收示例: raw_markets=100 raw_events=100 upserted=100")


@app.command()
def enrich(
    prices: bool = typer.Option(True, "--prices"),
    orderbooks: bool = typer.Option(True, "--orderbooks"),
    limit: int = typer.Option(500, "--limit"),
    archive_books: bool = typer.Option(False, "--archive-books"),
) -> None:
    """Enrich prices and orderbooks for token_ids."""
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT clob_token_ids_json FROM markets
            WHERE active=1 AND resolved=0
            ORDER BY updated_at_utc DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        token_ids = []
        for row in rows:
            token_ids.extend(json.loads(row["clob_token_ids_json"] or "[]"))
        token_ids = list(dict.fromkeys(token_ids))

        result = enrich_clob(
            conn,
            token_ids=token_ids,
            fetch_prices=prices,
            fetch_books=orderbooks,
            archive_books=archive_books,
        )

    print(f"prices_written={result['prices_written']} levels_written={result['levels_written']}")
    for sample in result["sample_metrics"]:
        print(sample)
    print("验收示例: prices_written=50 levels_written=200")


@app.command()
def parse(
    llm: bool = typer.Option(True, "--llm"),
    batch: int = typer.Option(100, "--batch"),
) -> None:
    """Parse rules with LLM extractor."""
    if not llm:
        raise typer.Exit(code=0)
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT m.* FROM markets m
            LEFT JOIN rule_parses r
            ON m.market_id = r.market_id
            WHERE r.market_id IS NULL AND m.active=1
            LIMIT ?
            """,
            (batch,),
        ).fetchall()
        markets = [dict(row) for row in rows]
        client = LLMClient()
        parsed = parse_rules(conn, markets, client)
    for item in parsed[:3]:
        parsed_json = json.loads(item["parsed_json"])
        print(
            {
                "market_id": item["market_id"],
                "trigger_type": parsed_json.get("trigger_type"),
                "clarity_score": parsed_json.get("clarity_score"),
                "ambiguity_flags": parsed_json.get("ambiguity_flags"),
            }
        )
    print("验收示例: {'market_id': '123', 'trigger_type': 'data_print', ...}")


@app.command()
def candidates(
    min_volume: float = typer.Option(20000, "--min-volume"),
    max_spread: float = typer.Option(0.06, "--max-spread"),
    output: Path = typer.Option(Path("candidates.csv"), "--output"),
) -> None:
    """Filter and export candidate list."""
    with db_session() as conn:
        markets = pd.read_sql_query(
            """
            SELECT * FROM markets
            WHERE active=1 AND resolved=0 AND volume >= ?
            """,
            conn,
            params=(min_volume,),
        )
        prices = pd.read_sql_query(
            """
            SELECT p.* FROM prices p
            INNER JOIN (
                SELECT token_id, MAX(fetched_at_utc) AS fetched_at_utc
                FROM prices
                GROUP BY token_id
            ) latest
            ON p.token_id = latest.token_id AND p.fetched_at_utc = latest.fetched_at_utc
            """,
            conn,
        )
        rule_parses = pd.read_sql_query(
            """
            SELECT market_id, parsed_json FROM rule_parses
            """,
            conn,
        )
        orderbook = pd.read_sql_query(
            """
            SELECT * FROM orderbook_levels
            """,
            conn,
        )

    if markets.empty or prices.empty or rule_parses.empty:
        print("No data available for candidates.")
        raise typer.Exit(code=0)

    rule_parses["parsed_json"] = rule_parses["parsed_json"].apply(json.loads)
    rule_parses = pd.concat(
        [rule_parses.drop(columns=["parsed_json"]), rule_parses["parsed_json"].apply(pd.Series)],
        axis=1,
    )

    def token_metrics(token_id: str, volume: float) -> dict:
        ob = orderbook[orderbook["token_id"] == token_id]
        if ob.empty:
            return {}
        mid = prices.loc[prices["token_id"] == token_id, "mid"].max()
        bids = (
            ob[ob["side"] == "bid"]
            .sort_values("level")
            .head(pipeline_config.orderbook_top_n)
            .to_dict("records")
        )
        asks = (
            ob[ob["side"] == "ask"]
            .sort_values("level")
            .head(pipeline_config.orderbook_top_n)
            .to_dict("records")
        )
        depth_1pct_bid = depth_within_pct(bids, mid or 0, 0.01, "bid")
        depth_1pct_ask = depth_within_pct(asks, mid or 0, 0.01, "ask")
        depth_2pct_bid = depth_within_pct(bids, mid or 0, 0.02, "bid")
        depth_2pct_ask = depth_within_pct(asks, mid or 0, 0.02, "ask")
        spread = calc_spread(
            prices.loc[prices["token_id"] == token_id, "best_bid"].max(),
            prices.loc[prices["token_id"] == token_id, "best_ask"].max(),
        )
        spread_pct_mid = calc_spread_pct_mid(spread, mid)
        return {
            "mid": mid,
            "spread": spread,
            "spread_pct_mid": spread_pct_mid,
            "depth_1pct_bid": depth_1pct_bid,
            "depth_1pct_ask": depth_1pct_ask,
            "depth_2pct_bid": depth_2pct_bid,
            "depth_2pct_ask": depth_2pct_ask,
            "liquidity_score": liquidity_score(
                float(volume or 0),
                depth_1pct_bid + depth_1pct_ask,
                depth_2pct_bid + depth_2pct_ask,
                spread_pct_mid,
            ),
        }

    markets["token_id"] = markets["clob_token_ids_json"].apply(
        lambda x: (json.loads(x or "[]") or [None])[0]
    )

    merged = markets.merge(rule_parses, on="market_id", how="inner")
    merged = merged.merge(prices, left_on="token_id", right_on="token_id", how="left")
    merged = merged[merged["spread"].fillna(0) <= max_spread]
    merged = merged[merged["clarity_score"] >= 0.7]
    merged = merged[merged["dispute_risk_score"] <= 0.4]

    metrics_rows = []
    for _, row in merged.iterrows():
        tm = token_metrics(row["token_id"], row["volume"])
        metrics_rows.append(tm)

    metrics_df = pd.DataFrame(metrics_rows)
    merged = pd.concat([merged.reset_index(drop=True), metrics_df], axis=1)

    merged["trigger_minimum_conditions"] = merged["trigger_minimum_conditions"].apply(
        lambda x: "; ".join(x)[:120] if isinstance(x, list) else str(x)[:120]
    )
    merged["notes_for_humans"] = merged["notes_for_humans"].astype(str).str[:160]

    output_cols = [
        "slug",
        "market_id",
        "end_at_utc",
        "category",
        "volume",
        "liquidity",
        "mid",
        "best_bid",
        "best_ask",
        "spread",
        "spread_pct_mid",
        "depth_1pct_bid",
        "depth_1pct_ask",
        "depth_2pct_bid",
        "depth_2pct_ask",
        "trigger_type",
        "clarity_score",
        "dispute_risk_score",
        "ambiguity_flags",
        "trigger_minimum_conditions",
        "notes_for_humans",
    ]
    merged = merged[output_cols]

    merged.to_csv(output, index=False)
    print(f"Wrote {len(merged)} candidates to {output}")
    print(merged.head(20).to_string(index=False))
    print("验收示例: slug, market_id, ... (前20行预览)")


if __name__ == "__main__":
    app()
