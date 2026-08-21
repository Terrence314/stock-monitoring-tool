"""A rule you can override without leaving a trace is a preference.

Two things happened repeatedly because breaking a rule was invisible:

  * The book carried 7 open longs against a cap of 5 from 2026-08-05. The
    dashboard read "空位 0/5" the whole time -- true, and it never once said
    the book was two over.
  * The go-live window moved four times in a month (06-11 -> 07-17 -> 08-05
    -> 08-09), each move resetting the trade counter to zero, which is why a
    30-trade floor under a 60-day clock never matured. No individual change
    looked like a pattern.

Nothing here blocks an override. It records one.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import discipline_log as dl                                        # noqa: E402


@pytest.fixture(autouse=True)
def isolated_log(tmp_path, monkeypatch):
    monkeypatch.setattr(dl, "LOG_FILE", str(tmp_path / "discipline_log.json"))


def test_a_violation_is_recorded_with_a_timestamp():
    e = dl.record_violation("position_cap", "7 open against a cap of 5")
    assert e["kind"] == "violation"
    assert e["rule"] == "position_cap"
    assert e["ts"]
    assert dl.count(kind="violation") == 1


def test_context_is_preserved():
    dl.record_violation("position_cap", "over", tickers=["AAA", "BBB"])
    assert dl.recent()[-1]["tickers"] == ["AAA", "BBB"]


def test_a_parameter_change_records_both_sides():
    dl.record_parameter_change("STOP_LOSS_PCT", 8.0, 3.0, "worst cell of 30")
    e = dl.recent()[-1]
    assert (e["old"], e["new"]) == (8.0, 3.0)
    assert e["reason"]


def test_repeated_overrides_accumulate_rather_than_overwrite():
    """The gate window moved four times and each move looked like the first."""
    for old, new in [("2026-06-11", "2026-07-17"), ("2026-07-17", "2026-08-05"),
                     ("2026-08-05", "2026-08-09"), ("2026-08-09", "2026-08-22")]:
        dl.record_parameter_change("GATE_START_DATE", old, new, "strategy change")
    assert dl.count(kind="parameter_change", rule="GATE_START_DATE") == 4, (
        "the fifth reset must be visible as the fifth"
    )


def test_refusals_are_recorded_separately_from_violations():
    """A refusal is the rules working; a violation is them failing. Counting
    them together would hide the failure inside the success."""
    dl.record_refusal("position_cap", "entry blocked, no slots")
    dl.record_violation("position_cap", "book is over cap")
    assert dl.count(kind="refusal") == 1
    assert dl.count(kind="violation") == 1


def test_the_log_survives_a_missing_file():
    assert dl.recent() == []
    assert dl.count() == 0


def test_a_corrupt_log_does_not_take_the_run_down(tmp_path, monkeypatch):
    """Losing the log is bad. Losing the trading run to protect the log is
    worse, so a damaged file is treated as empty and overwritten."""
    p = tmp_path / "broken.json"
    p.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(dl, "LOG_FILE", str(p))
    assert dl.recent() == []
    dl.record_violation("x", "y")
    assert dl.count(kind="violation") == 1


def test_the_log_is_capped_and_keeps_the_newest():
    for i in range(dl.MAX_ENTRIES + 25):
        dl.record_violation("spam", f"n{i}")
    entries = json.load(open(dl.LOG_FILE, encoding="utf-8"))
    assert len(entries) == dl.MAX_ENTRIES
    assert entries[-1]["detail"] == f"n{dl.MAX_ENTRIES + 24}"


def test_recording_never_raises_into_the_caller():
    """It is called from inside the portfolio write path."""
    dl.record_violation("r", "d", weird=object.__name__)
    assert dl.count(kind="violation") == 1


# ── Wired into the engine ────────────────────────────────────────────────────

def test_saving_an_over_cap_book_records_a_violation(tmp_path, monkeypatch):
    """The cap is enforced at the WRITE, not only where entries are chosen.

    entry_selection already refuses once slots_left <= 0 and that logic is
    correct -- yet the book still reached 7. Two schedules open positions, each
    computing slots from the book as it found it. A rule checked only by the
    caller has as many exceptions as it has callers.
    """
    import paper_trading as pt
    monkeypatch.setattr(pt, "PORTFOLIO_FILE", str(tmp_path / "p.json"))
    monkeypatch.setattr(dl, "LOG_FILE", str(tmp_path / "log.json"))
    monkeypatch.setattr(pt, "record_violation", dl.record_violation)

    over = pt.MAX_OPEN_POSITIONS + 2
    pt._save_portfolio({"trades": [
        {"ticker": f"T{i}", "status": "open", "direction": "long"}
        for i in range(over)
    ]})
    assert dl.count(kind="violation", rule="position_cap") == 1


def test_a_book_within_the_cap_records_nothing(tmp_path, monkeypatch):
    import paper_trading as pt
    monkeypatch.setattr(pt, "PORTFOLIO_FILE", str(tmp_path / "p.json"))
    monkeypatch.setattr(dl, "LOG_FILE", str(tmp_path / "log.json"))
    monkeypatch.setattr(pt, "record_violation", dl.record_violation)

    pt._save_portfolio({"trades": [
        {"ticker": f"T{i}", "status": "open", "direction": "long"}
        for i in range(pt.MAX_OPEN_POSITIONS)
    ]})
    assert dl.count(kind="violation") == 0


def test_an_over_cap_book_is_still_written(tmp_path, monkeypatch):
    """Recording the breach must not cost the book. Refusing to save would
    abort mid-run and lose live state, which is worse than the breach."""
    import paper_trading as pt
    book = tmp_path / "p.json"
    monkeypatch.setattr(pt, "PORTFOLIO_FILE", str(book))
    monkeypatch.setattr(dl, "LOG_FILE", str(tmp_path / "log.json"))
    monkeypatch.setattr(pt, "record_violation", dl.record_violation)

    trades = [{"ticker": f"T{i}", "status": "open", "direction": "long"}
              for i in range(pt.MAX_OPEN_POSITIONS + 3)]
    pt._save_portfolio({"trades": trades})
    assert len(json.loads(book.read_text())["trades"]) == len(trades)
