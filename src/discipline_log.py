"""A durable record of every rule that fired, was broken, or was changed.

The rules were always there. What was missing is that breaking one left no
trace, so the same breach could recur without anyone noticing it had happened
before:

  * The book held 7 open longs against a cap of 5 from 2026-08-05. The UI
    showed "空位 0/5" throughout -- technically true, and it never once said
    the book was two positions over.
  * The go-live gate window moved four times in one month (2026-06-11 ->
    07-17 -> 08-05 -> 08-09). Each move was individually justified and each
    reset the trade counter to zero, which is why a 30-trade floor under a
    60-day clock never matured. No single change looked like a pattern
    because nothing recorded that the previous three had happened.

A rule you can silently override is a preference. This file is what makes the
difference: overriding still works -- nothing here blocks a change -- but it
leaves a dated entry, and the count of entries is visible.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

LOG_FILE = os.path.join("outputs", "discipline_log.json")
MAX_ENTRIES = 500          # keep the file readable; oldest fall off first


def _load() -> list:
    try:
        with open(LOG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _append(entry: dict) -> dict:
    entries = _load()
    entries.append(entry)
    entries = entries[-MAX_ENTRIES:]
    os.makedirs(os.path.dirname(LOG_FILE) or ".", exist_ok=True)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    return entry


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def record_violation(rule: str, detail: str, **context) -> dict:
    """A rule was broken. Records it; does not undo it.

    Deliberately non-fatal. Raising here would abort a run mid-write and lose
    the book, which is a worse outcome than a recorded breach.
    """
    return _append({"ts": _now(), "kind": "violation",
                    "rule": rule, "detail": detail, **context})


def record_refusal(rule: str, detail: str, **context) -> dict:
    """A rule stopped something happening. The system working as intended --
    logged so the cost of the rules is visible alongside their benefit."""
    return _append({"ts": _now(), "kind": "refusal",
                    "rule": rule, "detail": detail, **context})


def record_parameter_change(name: str, old, new, reason: str) -> dict:
    """A rule itself was changed. The entry that makes the fifth reset of a
    window visible as the fifth."""
    return _append({"ts": _now(), "kind": "parameter_change",
                    "rule": name, "old": old, "new": new, "reason": reason})


def count(kind: str | None = None, rule: str | None = None) -> int:
    return sum(1 for e in _load()
               if (kind is None or e.get("kind") == kind)
               and (rule is None or e.get("rule") == rule))


def recent(n: int = 20) -> list:
    return _load()[-n:]
