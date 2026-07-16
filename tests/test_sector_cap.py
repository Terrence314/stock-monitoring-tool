"""Tests for the per-sector position cap (fix 2026-07-17).

The 2026-06-19 cohort opened MRVL, ON, NXPI, and QCOM together — four
semiconductor longs, all closed at heavy losses. The cap blocks a new long
once MAX_PER_SECTOR positions are already open in the same sector.

Run: python3 tests/test_sector_cap.py
No pytest dependency — plain asserts, exits non-zero on failure.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from paper_trading import _sector_cap_ok, MAX_PER_SECTOR


def _open(ticker, sector):
    return {"ticker": ticker, "status": "open", "direction": "long", "sector": sector}


def test_cap_blocks_third_position_in_sector():
    trades = [_open("MRVL", "Technology"), _open("NXPI", "Technology")]
    assert MAX_PER_SECTOR == 2
    ok = _sector_cap_ok("ON", {"ON": "Technology"}, trades)
    assert not ok, "third Technology long must be blocked"


def test_cap_allows_below_limit():
    trades = [_open("MRVL", "Technology")]
    assert _sector_cap_ok("ON", {"ON": "Technology"}, trades)


def test_other_sector_not_affected():
    trades = [_open("MRVL", "Technology"), _open("NXPI", "Technology")]
    assert _sector_cap_ok("JPM", {"JPM": "Financial Services"}, trades)


def test_closed_positions_do_not_count():
    trades = [
        _open("MRVL", "Technology"),
        {"ticker": "NXPI", "status": "closed", "direction": "long", "sector": "Technology"},
    ]
    assert _sector_cap_ok("ON", {"ON": "Technology"}, trades)


def test_unknown_sector_never_blocked():
    """Fail-open: missing sector data must not block entries."""
    trades = [_open("AAA", "Unknown"), _open("BBB", "Unknown"), _open("CCC", "Unknown")]
    assert _sector_cap_ok("DDD", {}, trades)


def test_legacy_trades_without_sector_field():
    """Pre-fix open trades have no 'sector' key — fall back to the sector map."""
    trades = [
        {"ticker": "MRVL", "status": "open", "direction": "long"},
        {"ticker": "NXPI", "status": "open", "direction": "long"},
    ]
    smap = {"MRVL": "Technology", "NXPI": "Technology", "ON": "Technology"}
    assert not _sector_cap_ok("ON", smap, trades)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  ✅ {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  ❌ {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
