from pm_research.gamma_client import GammaClient


def test_gamma_pagination(monkeypatch):
    client = GammaClient()

    pages = [
        [{"id": "1"}, {"id": "2"}],
        [{"id": "3"}],
        [],
    ]
    calls = {"i": 0}

    def fake_get(path, params):
        out = pages[calls["i"]]
        calls["i"] += 1
        return out

    monkeypatch.setattr(client, "_get", fake_get)

    data = list(client.fetch_paginated("/markets", limit=2))
    assert [d["id"] for d in data] == ["1", "2", "3"]
    assert calls["i"] == 3
