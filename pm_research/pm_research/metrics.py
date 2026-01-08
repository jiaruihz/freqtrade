from __future__ import annotations

from typing import Iterable


def calc_spread(best_bid: float | None, best_ask: float | None) -> float | None:
    if best_bid is None or best_ask is None:
        return None
    return best_ask - best_bid


def calc_spread_pct_mid(spread: float | None, mid: float | None) -> float | None:
    if spread is None or mid in (None, 0):
        return None
    return spread / mid


def depth_within_pct(levels: Iterable[dict], mid: float, pct: float, side: str) -> float:
    if mid <= 0:
        return 0.0
    threshold = mid * (1 + pct) if side == "ask" else mid * (1 - pct)
    total = 0.0
    for lvl in levels:
        price = lvl["price"]
        if side == "ask" and price <= threshold:
            total += lvl["size"]
        if side == "bid" and price >= threshold:
            total += lvl["size"]
    return total


def liquidity_score(volume: float | None, depth_1pct: float, depth_2pct: float, spread_pct_mid: float | None) -> float:
    vol_component = min((volume or 0) / 10000, 1.0) * 40
    depth_component = min((depth_1pct + depth_2pct) / 2000, 1.0) * 40
    spread_component = 0 if spread_pct_mid is None else max(0.0, (0.1 - spread_pct_mid) / 0.1) * 20
    return round(vol_component + depth_component + spread_component, 2)
