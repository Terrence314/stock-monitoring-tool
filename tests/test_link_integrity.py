"""Every in-page ticker link must resolve to a file stock_detail actually
writes. GitHub Pages is case-sensitive and stock_detail writes TICKER.html
(uppercase), so a single `|lower` in the Universe table 404'd 70 links —
verified live: aapl.html -> 404, AAPL.html -> 200.
"""

import os
import re

SRC = os.path.join(os.path.dirname(__file__), "..", "src")


def _read(name):
    with open(os.path.join(SRC, name), encoding="utf-8") as f:
        return f.read()


def test_detail_pages_are_written_uppercase():
    """The invariant the links depend on."""
    src = _read("stock_detail.py")
    assert 'f"{s[\'ticker\']}.html"' in src or "{s['ticker']}.html" in src


def test_no_case_transform_on_ticker_links():
    """No |lower / |upper between the ticker and .html in any template."""
    for name in ("report_generator.py", "stock_detail.py"):
        src = _read(name)
        offenders = re.findall(r'href="\./\{\{[^}]*\|\s*(?:lower|upper)[^}]*\}\}\.html"', src)
        assert not offenders, f"{name}: case-transformed ticker link(s): {offenders}"


def test_ticker_links_interpolate_the_raw_ticker():
    """Each ./{{ ... }}.html link must use a bare ticker expression."""
    for name in ("report_generator.py", "stock_detail.py"):
        src = _read(name)
        for expr in re.findall(r'href="\./\{\{\s*([^}]+?)\s*\}\}\.html"', src):
            assert "|" not in expr, f"{name}: filter applied to ticker link: {{{{ {expr} }}}}"
            assert expr.endswith("ticker"), f"{name}: unexpected link expression: {{{{ {expr} }}}}"
