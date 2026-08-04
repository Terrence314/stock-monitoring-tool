"""Templates must RENDER, not merely parse.

price_refresh failed on 6 consecutive runs with:

    ValueError: unsupported format character ',' (0x2c) at index 2

from `{{ '%+,.0f'|format(action_box.breaker_usd) }}`. Jinja's `format` filter
is printf-style and has no thousands grouping; `,` is simply an invalid
conversion character there. Thousands grouping needs str.format.

Two things let it reach production:
  1. The pre-flight check only called Template(...) — parsing a template does
     not execute its expressions, so an invalid format string is invisible.
  2. The line sits behind `{% if action_box.breaker_usd %}`. The day it
     shipped the breaker was 0.0 — falsy — so the branch never ran. It broke
     the moment a trade closed and the value went non-zero.

So these tests render with values that FORCE every guarded branch open.
"""

import os
import sys

import pytest
from jinja2 import Template

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import report_generator as rg                                        # noqa: E402
import portfolio as pf                                               # noqa: E402


# ── The mechanism, pinned ─────────────────────────────────────────────────────

def test_printf_format_filter_cannot_group_thousands():
    """The exact failure, so nobody reintroduces `%,.0f`."""
    with pytest.raises(ValueError, match="unsupported format character"):
        Template("{{ '%+,.0f'|format(x) }}").render(x=-1234.5)


def test_str_format_groups_thousands():
    assert Template("{{ '{:+,.0f}'.format(x) }}").render(x=-1234.5) == "-1,234"


def test_no_template_uses_printf_grouping():
    """Static sweep — catches the pattern anywhere in any template string."""
    import glob
    import re

    offenders = []
    src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
    for path in glob.glob(os.path.join(src_dir, "*.py")):
        with open(path, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                if re.search(r"'%[^']*,[^']*'\s*\|\s*format", line):
                    offenders.append(f"{os.path.basename(path)}:{i}")
    assert not offenders, f"printf-style grouping (invalid): {offenders}"


# ── Render the breaker line with the value that broke it ──────────────────────

def _breaker_fragment():
    """The Action Box footer line, extracted from the live template."""
    for line in rg.DASHBOARD_HTML.splitlines():
        if "斷路器" in line and "breaker_usd" in line:
            return line
    pytest.fail("breaker line not found in DASHBOARD_HTML")


@pytest.mark.parametrize("usd,base", [
    (-2502.22, 41000.0),   # the real shape that crashed production
    (1234.56, 9000.0),
    (-0.5, 1000.0),
])
def test_breaker_line_renders_with_non_zero_values(usd, base):
    out = Template(_breaker_fragment()).render(action_box={
        "breaker_pct": -6.1, "breaker_limit": -5.0,
        "breaker_usd": usd, "breaker_base": base, "breaker_trip": True,
    })
    assert "美元" in out
    assert "," in out, "thousands separator missing"


def test_breaker_line_renders_when_zero_and_skips_the_branch():
    """The state that made the bug invisible on the day it shipped."""
    out = Template(_breaker_fragment()).render(action_box={
        "breaker_pct": 0.0, "breaker_limit": -5.0,
        "breaker_usd": 0.0, "breaker_base": 0.0, "breaker_trip": False,
    })
    assert "美元" not in out


def test_breaker_line_renders_when_keys_are_absent():
    """Older action_box.json restored from gh-pages has no breaker_usd."""
    out = Template(_breaker_fragment()).render(action_box={
        "breaker_pct": -1.0, "breaker_limit": -5.0, "breaker_trip": False,
    })
    assert "斷路器" in out


# ── Portfolio page carried the same defect ────────────────────────────────────

def test_portfolio_money_lines_have_no_invalid_format_string():
    """Assert the bug class specifically. A missing template variable raises
    TypeError and is just this test's fixture being incomplete; an invalid
    format string raises ValueError and is the defect."""
    lines = [ln for ln in pf.PORTFOLIO_HTML.splitlines()
             if ",.2f" in ln or ",.0f" in ln]
    assert lines, "expected grouped-money lines in PORTFOLIO_HTML"

    ctx = dict(total_unreal=-1234.5, total_realized=2345.6, amt=-99.9,
               h={"unreal_pnl": -12.3, "realized_pnl": 45.6})
    for ln in lines:
        try:
            Template(ln).render(**ctx)
        except ValueError as e:            # the defect
            pytest.fail(f"invalid format string: {ln.strip()[:80]} -> {e}")
        except Exception:                  # unrelated missing-variable noise
            pass
