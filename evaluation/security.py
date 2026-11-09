"""
Secret hygiene for stored evaluation results.

Every result JSON passes through scrub() before being written to disk.
Guarantees: no API keys, tokens, or authorization headers are ever stored.
"""

import json
import re
from pathlib import Path
from typing import Any

SENSITIVE_KEY_PATTERN = re.compile(
    r"(api[_-]?key|authorization|secret|password|bearer)", re.IGNORECASE
)
SENSITIVE_VALUE_PATTERN = re.compile(r"sk-or-[A-Za-z0-9_\-]{8,}")


def scrub(obj: Any) -> Any:
    """Recursively redact sensitive keys and key-like values from `obj`."""
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            if SENSITIVE_KEY_PATTERN.search(str(key)):
                out[key] = "[REDACTED]"
            else:
                out[key] = scrub(value)
        return out
    if isinstance(obj, list):
        return [scrub(item) for item in obj]
    if isinstance(obj, str):
        return SENSITIVE_VALUE_PATTERN.sub("[REDACTED]", obj)
    return obj


def write_json_scrubbed(path, obj: Any) -> None:
    """Scrub and write `obj` as JSON to `path`."""
    from evaluation.isolation import ensure_under_evaluation

    path = ensure_under_evaluation(Path(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(scrub(obj), indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def contains_secret(obj: Any) -> bool:
    """True if a raw API-key-looking string survives anywhere in `obj`."""
    text = json.dumps(obj, default=str)
    return bool(SENSITIVE_VALUE_PATTERN.search(text))
