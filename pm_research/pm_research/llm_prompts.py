SYSTEM_PROMPT = """
You are a research-only rules extractor. Output ONLY valid JSON conforming to the provided schema.
Do NOT provide betting advice, trading direction, or any recommendation.
Do NOT fabricate facts. Use only the input text.
If you cite a rule snippet, keep it under 25 words.
""".strip()

PROMPT_VERSION = "1.0"

FEW_SHOT = {
    "input": {
        "market_id": "123",
        "slug": "sample-market",
        "question": "Will City X declare a state of emergency in 2024?",
        "description": "Resolution source: official city press releases.",
        "rules": "Resolves YES if the city issues an official emergency declaration before 2025-01-01 UTC.",
        "end_at_utc": "2024-12-31T23:59:59Z",
        "category": "Politics",
    },
    "output": {
        "market_id": "123",
        "slug": "sample-market",
        "time_window": {
            "start_at_utc": None,
            "end_at_utc": "2024-12-31T23:59:59Z",
            "timezone_source": "UTC"
        },
        "settlement_source_type": "official_docs",
        "trigger_type": "procedural_vote",
        "trigger_minimum_conditions": [
            "Official emergency declaration issued by City X"
        ],
        "explicit_exclusions": [],
        "entity_definitions": [
            {"entity": "City X", "definition": "The municipal government of City X"}
        ],
        "ambiguity_flags": ["official declaration wording"],
        "clarity_score": 0.75,
        "dispute_risk_score": 0.25,
        "notes_for_humans": "Resolve based on official city press releases; check declaration wording.",
        "llm_confidence": 0.7
    }
}


def build_user_prompt(payload: dict) -> str:
    return (
        "Extract the rule structure from the following market. "
        "Return ONLY a single JSON object matching the schema.\n\n"
        f"Input JSON:\n{payload}\n\n"
        "Use the fields: question, description, rules, end_at_utc, category."
    )
