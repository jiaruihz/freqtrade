from pm_research.metrics import calc_spread, calc_spread_pct_mid, depth_within_pct


def test_spread_metrics():
    spread = calc_spread(0.45, 0.5)
    assert spread == 0.05
    assert calc_spread_pct_mid(spread, 0.475) == spread / 0.475


def test_depth_metrics():
    levels = [
        {"price": 0.49, "size": 10},
        {"price": 0.48, "size": 5},
        {"price": 0.46, "size": 2},
    ]
    mid = 0.5
    depth = depth_within_pct(levels, mid, 0.02, "bid")
    assert depth == 15
