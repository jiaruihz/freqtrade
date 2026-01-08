import json

from pm_research import db
from pm_research.schema import RuleParse, SCHEMA_VERSION
from pm_research.storage import insert_rule_parse


def test_llm_schema_and_storage(monkeypatch, tmp_path):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db.settings, "PMR_DB_PATH", str(db_path))
    db.init_db()

    payload = {
        "market_id": "m1",
        "slug": "test",
        "time_window": {
            "start_at_utc": None,
            "end_at_utc": "2024-12-31T00:00:00Z",
            "timezone_source": "UTC",
        },
        "settlement_source_type": "official_docs",
        "trigger_type": "definition_driven",
        "trigger_minimum_conditions": ["Rule trigger"],
        "explicit_exclusions": [],
        "entity_definitions": [],
        "ambiguity_flags": ["ambiguity"],
        "clarity_score": 0.8,
        "dispute_risk_score": 0.2,
        "notes_for_humans": "Rule notes",
        "llm_confidence": 0.9,
    }
    parsed = RuleParse.model_validate(payload)

    row = {
        "market_id": parsed.market_id,
        "parsed_at_utc": "2024-01-01T00:00:00Z",
        "schema_version": SCHEMA_VERSION,
        "prompt_version": "1.0",
        "llm_model": "mock-model",
        "parsed_json": parsed.model_dump_json(),
        "raw_response": json.dumps(payload),
        "llm_confidence": parsed.llm_confidence,
        "clarity_score": parsed.clarity_score,
        "dispute_risk_score": parsed.dispute_risk_score,
        "ambiguity_flags_json": json.dumps(parsed.ambiguity_flags),
    }

    with db.db_session() as conn:
        insert_rule_parse(conn, row)
        stored = conn.execute("SELECT * FROM rule_parses").fetchone()

    assert stored["market_id"] == "m1"
    assert json.loads(stored["parsed_json"])["clarity_score"] == 0.8
