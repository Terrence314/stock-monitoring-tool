"""The real account value must never reach the public site or the public logs.

This repo is public, so its GitHub Pages site and its Actions logs are public
too. Until 2026-09-20 the account's net liquidation reached them four ways:

  1. ibkr_positions.json, restored into outputs/ by CI and redeployed.
  2. action_box.json, as equity_usd and breaker_equity.
  3. The dashboard: "倉位 $4,650 × 7–12%" and "帳戶 $X" on the breaker line.
  4. The Actions log: "[paper_trading] ... equity $5,000 (fallback)".

And a fifth, by arithmetic: every published paper trade carries `notional`,
and POSITION_PCT is public, so notional / band% gives the account back
exactly (score 80 -> 10% -> 500 -> 5,000). Hiding the four direct channels
would have achieved nothing while sizing still read the real figure.

The fix removes the need, not just the display: the paper book sizes from
a fixed simulation account, so no real figure exists in CI to leak.
"""

import inspect
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import entry_selection as es                                       # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
WORKFLOWS = os.path.join(ROOT, ".github", "workflows")
REAL = 8123.45                     # a real-looking figure that must never surface


def _write_snapshot(d):
    import json
    from datetime import datetime
    with open(os.path.join(d, "ibkr_positions.json"), "w") as f:
        json.dump({"synced_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                   "account": {"net_liquidation_usd": REAL}}, f)


# ── Channel 1: the snapshot file ─────────────────────────────────────────────

def test_no_workflow_restores_the_account_snapshot():
    """Anything restored into outputs/ is republished on deploy."""
    for wf in os.listdir(WORKFLOWS):
        with open(os.path.join(WORKFLOWS, wf), encoding="utf-8") as f:
            lists = " ".join(re.findall(r"for FILE in ([^;]+); do", f.read()))
        assert "ibkr_positions.json" not in lists, wf


# ── Channel 2: the published Action Box ──────────────────────────────────────

def test_the_published_action_box_carries_no_account_figure(tmp_path):
    from report_generator import _build_action_box
    _write_snapshot(str(tmp_path))
    box = _build_action_box([], str(tmp_path))
    for key in ("equity_usd", "breaker_equity", "breaker_basis"):
        assert key not in box, f"{key} is published to a public site"
    assert str(REAL) not in repr(box) and "8,123" not in repr(box)


# ── Channel 3: the rendered page ─────────────────────────────────────────────

def test_the_dashboard_template_formats_no_account_value():
    import report_generator as rg
    for field in ("equity_usd", "breaker_equity"):
        assert not re.search(r"format\(action_box\.%s\)" % field, rg.DASHBOARD_HTML), (
            f"the dashboard renders {field}"
        )


def test_a_buy_ticket_shows_a_share_not_dollars():
    """Dollars of a $5,000 simulation are wrong for a real order and, if the
    sizing base ever changed, would leak it. A share of the account is right
    at any size."""
    import report_generator as rg
    assert "b.pct" in rg.DASHBOARD_HTML
    assert "format(b.notional)" not in rg.DASHBOARD_HTML


# ── Channel 4: the public Actions log ────────────────────────────────────────

def test_the_engine_log_line_prints_no_account_figure():
    import paper_trading as pt
    src = inspect.getsource(pt.run_paper_trading)
    line = src[src.index("[paper_trading] regime="):]
    line = line[:line.index("\n\n")]
    assert "equity" not in line, "Actions logs on a public repo are public"


# ── Channel 5: arithmetic on the published notional ──────────────────────────

def test_published_notional_reveals_only_the_simulation(tmp_path):
    """notional / band% must give back PAPER_EQUITY_USD, never the real value,
    even when a fresh real snapshot is sitting in the output directory."""
    _write_snapshot(str(tmp_path))
    stocks = [{"ticker": "SPY", "score": es.REGIME_NORMAL, "price": 500.0},
              *[{"ticker": t, "score": sc, "price": 50.0, "sector": s,
                 "entry_verdict": {"label": "GO"}, "vol_ratio": 1.5}
                for t, sc, s in [("AAA", 95, "A"), ("BBB", 85, "B"), ("CCC", 75, "C")]]]
    entries, _ = es.select_entries(stocks, [], output_dir=str(tmp_path))
    assert entries, "fixture should produce entries"
    for e in entries:
        implied = e["notional"] / (e["pct"] / 100)
        assert round(implied, 2) == es.PAPER_EQUITY_USD, (
            f"{e['ticker']}: notional reveals {implied}, not the simulation"
        )


def test_paper_sizing_does_not_read_the_snapshot():
    """The structural guard: select_entries must not call the reader at all."""
    body = inspect.getsource(es.select_entries)
    assert "account_equity_usd(" not in body
