"""Shared Anthropic call/parse mechanics, factored out of pipeline/personalize.py
and pipeline/hiring_personalize.py (their draft_first_touch()s only genuinely
differ in MODEL/prompts, not in how the call is made or the response parsed)
and out of pipeline/tier_classifier.py and pipeline/hiring_industry_classifier.py
(their on-disk cache file paths were a byte-for-byte duplicate)."""
from __future__ import annotations

import json
import os

FIRST_TOUCH_SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string"},
        "body": {"type": "string"},
    },
    "required": ["subject", "body"],
    "additionalProperties": False,
}


def call_json_schema(model: str, system_prompt: str, user_prompt: str, schema: dict, max_tokens: int = 2048) -> dict:
    """Calls Claude with a JSON-schema-constrained response and returns the
    parsed object. Raises RuntimeError if the model returns no text block -
    same behavior both draft_first_touch()s had inline before this was
    factored out."""
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        output_config={"format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": user_prompt}],
    )
    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        raise RuntimeError(f"call_json_schema: no text content in response (stop_reason={response.stop_reason})")
    return json.loads(text)


def slug_cache_path(cache_dir: str, key: str) -> str:
    """The identical safe-filename-slug scheme tier_classifier.py and
    hiring_industry_classifier.py each had their own private copy of."""
    safe = "".join(c if c.isalnum() else "_" for c in key.lower())[:80]
    return os.path.join(cache_dir, f"{safe}.json")
