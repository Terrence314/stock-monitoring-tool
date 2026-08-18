"""The landing page's track record must come from the live portfolio.

It was a hardcoded string quoting 17 closed trades / 35.3% / PF 0.58 /
-$333.91, copied out of gate-decision-2026-08-12.md. On 2026-08-18 the engine
had closed 60 for -$2,600.67 at 33.3% and PF 0.35 — so the single figure on
the site that tells a reader how well this works understated the loss ~8x, and
by construction could only ever drift further.

The failure mode matters more than the arithmetic: a literal describing live
state looks correct on the day it is written and is never wrong loudly. These
tests pin it to the file instead.
"""

import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pm_dashboard as pm                                            # noqa: E402


def _write(tmp_path, trades):
    p = tmp_path / "paper_portfolio.json"
    p.write_text(json.dumps({"trades": trades}), encoding="utf-8")
    return p


def _closed(pnl):
    return {"status": "closed", "pnl": pnl}


# ── Reading the record ────────────────────────────────────────────────────────

def test_record_counts_only_closed_trades(tmp_path):
    r = pm._track_record(_write(tmp_path, [
        _closed(100.0), _closed(-50.0),
        {"status": "open", "pnl": None},
    ]))
    assert r["trades"] == 2


def test_winrate_profit_factor_and_net(tmp_path):
    r = pm._track_record(_write(tmp_path, [
        _closed(100.0), _closed(50.0), _closed(-30.0), _closed(-120.0),
    ]))
    assert r["trades"] == 4
    assert r["winrate"] == 50.0
    assert r["pf"] == pytest.approx(150 / 150)
    assert r["net"] == pytest.approx(0.0)


def test_profit_factor_is_undefined_without_a_losing_trade(tmp_path):
    """Not infinity. 'PF ∞' off a thin sample reads as a verified edge."""
    r = pm._track_record(_write(tmp_path, [_closed(10.0), _closed(20.0)]))
    assert r["pf"] is None
    assert "PF —" in pm.build_provenance(r)


@pytest.mark.parametrize("trades", [[], [{"status": "open", "pnl": None}]])
def test_no_closed_trades_reads_as_no_record(tmp_path, trades):
    assert pm._track_record(_write(tmp_path, trades)) is None


def test_a_missing_file_reads_as_no_record(tmp_path):
    assert pm._track_record(tmp_path / "absent.json") is None


def test_malformed_json_reads_as_no_record(tmp_path):
    p = tmp_path / "paper_portfolio.json"
    p.write_text("{not json", encoding="utf-8")
    assert pm._track_record(p) is None


# ── Rendering the line ────────────────────────────────────────────────────────

def test_line_quotes_the_live_figures(tmp_path):
    note = pm.build_provenance(pm._track_record(_write(tmp_path, [
        _closed(-100.0), _closed(-200.0), _closed(50.0),
    ])))
    assert "3 筆已平倉" in note
    assert "33.3%" in note
    assert "−$250.00" in note


def test_a_loss_and_a_gain_carry_the_right_sign(tmp_path):
    up = pm.build_provenance(pm._track_record(
        _write(tmp_path, [_closed(500.0), _closed(-100.0)])))
    assert "+$400.00" in up
    down = pm.build_provenance(pm._track_record(
        _write(tmp_path, [_closed(100.0), _closed(-500.0)])))
    assert "−$400.00" in down


def test_large_figures_are_grouped(tmp_path):
    note = pm.build_provenance(pm._track_record(
        _write(tmp_path, [_closed(-2600.67), _closed(1.0)])))
    assert "$2,599.67" in note


def test_verdict_is_derived_not_asserted(tmp_path):
    """A future PASS must update the sentence without anyone editing it."""
    failing = pm.build_provenance(pm._track_record(
        _write(tmp_path, [_closed(100.0), _closed(-400.0)])))
    assert "未通過自身 gate" in failing

    passing = pm.build_provenance(pm._track_record(_write(tmp_path, [
        _closed(300.0), _closed(300.0), _closed(300.0), _closed(-100.0),
    ])))
    assert "已通過自身 gate" in passing


def test_the_gate_terms_are_stated_in_the_line(tmp_path):
    note = pm.build_provenance(pm._track_record(
        _write(tmp_path, [_closed(1.0), _closed(-1.0)])))
    assert "WR≥45%" in note and "PF≥1.0" in note


def test_an_unreadable_record_says_so_rather_than_showing_nothing(tmp_path):
    note = pm.build_provenance(None)
    assert "讀取不到" in note
    assert "%" not in note.split("以下標的")[0].replace("勝率/PF", "")


def test_no_string_literal_carries_a_track_record():
    """No STRING LITERAL may bake in trade counts, win rates or P&L.

    Scoped to literals via the AST rather than grepping the file, because the
    docstrings here and in pm_dashboard deliberately quote the old figures to
    explain what went wrong — a plain substring sweep flags its own
    explanation and teaches you to delete the explanation.
    """
    import ast
    src = os.path.join(os.path.dirname(__file__), "..", "src", "pm_dashboard.py")
    with open(src, encoding="utf-8") as f:
        body = f.read()
    tree = ast.parse(body)
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))
        and node.body and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    offenders = [
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and id(node) not in docstrings
        # A digit must be adjacent: f-string fragments like " 筆已平倉 — 勝率 "
        # are the template doing its job, not a baked figure.
        and re.search(r"\d+\s*筆已平倉|勝率\s*\d|PF\s*\d|\$\s*[\d,]+\.\d",
                      node.value)
    ]
    assert not offenders, f"a track record is baked into a literal: {offenders}"


def test_the_caveat_survives_every_path(tmp_path):
    """The 'not a verified edge' warning is the point of the line."""
    for record in (None, pm._track_record(_write(tmp_path, [_closed(5.0)]))):
        assert "非已驗證 edge" in pm.build_provenance(record)
