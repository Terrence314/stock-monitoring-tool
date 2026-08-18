"""UI invariants for the dashboard, from the 2026-08-02 usability audit.

Measured on the live page before these changes:
  - 0 of 14 nav items visible on a phone. `.nav-pills { display: none }` below
    900px with nothing in its place, so Backtest / Paper Trade / Patterns /
    Portfolio — standalone pages with no other link — were unreachable.
  - The 📖 Simple readability toggle carried `mob-hide`, so it was hidden on
    the small screen where it helps most.
  - Simple mode was a shell: the class toggle, CSS and localStorage all
    existed but only 2 elements were tagged `expert-only`, so switching modes
    hid essentially nothing.
  - The 💼 Portfolio pill pointed at portfolio.html, which is deliberately
    never published — a permanent 404 for every visitor.
"""

import os
import re

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "src")

with open(os.path.join(SRC, "report_generator.py"), encoding="utf-8") as _f:
    RG = _f.read()

# Sections dense enough to belong behind Expert.
EXPERT_SECTIONS = [
    "watchlist", "brief", "headlines", "sectors",
    "etf-panel", "stocks", "universe", "hkbrief",
]
# What Simple keeps: the decision, market state, alerts, starred names.
SIMPLE_SECTIONS = ["overview", "alerts", "favourites"]


# ── Simple is the default view ────────────────────────────────────────────────

def test_simple_mode_applied_before_first_paint():
    """A <head> script sets the class so the dense layout never flashes."""
    head = RG.split("</head>")[0]
    assert "data-boot-mode" in head
    assert "signalViewMode" in head


def test_expert_is_the_default_and_simple_is_opt_in():
    """Simple was briefly the default. Hiding 8 of 11 sections on load read
    as the tool having lost features — a far worse failure than a dense
    page — so it applies only when explicitly chosen."""
    assert re.search(r"mode\s*===\s*'beginner'", RG), \
        "Simple is no longer opt-in — the default view must be Expert"
    assert not re.search(r"mode\s*!==\s*'expert'", RG), \
        "Simple-by-default logic has come back"


@pytest.mark.parametrize("section", EXPERT_SECTIONS)
def test_dense_sections_are_expert_only(section):
    m = re.search(r'<section id="%s"[^>]*>' % re.escape(section), RG)
    assert m, f"section #{section} missing"
    assert "expert-only" in m.group(0), f"#{section} should be behind Expert"


@pytest.mark.parametrize("section", SIMPLE_SECTIONS)
def test_simple_sections_stay_visible(section):
    m = re.search(r'<section id="%s"[^>]*>' % re.escape(section), RG)
    assert m, f"section #{section} missing"
    assert "expert-only" not in m.group(0), f"#{section} must stay in Simple"


# ── Mobile navigation exists ──────────────────────────────────────────────────

def test_mobile_nav_has_exactly_four_destinations():
    m = re.search(r'<nav class="mobile-nav">(.*?)</nav>', RG, re.S)
    assert m, "mobile bottom nav missing"
    assert len(re.findall(r"<a\b", m.group(1))) == 4


def test_more_sheet_carries_the_remaining_destinations():
    m = re.search(r'<div class="more-sheet"[^>]*>(.*?)</div>\s*</div>', RG, re.S)
    assert m, "More sheet missing"
    assert len(re.findall(r"<a\b", m.group(1))) >= 10


def test_standalone_pages_are_reachable_on_mobile():
    """Backtest / Paper Trade / Patterns have no in-page anchor to fall back on."""
    mobile = RG[RG.index('<nav class="mobile-nav">'):]
    for page in ("paper_trading.html", "backtest.html", "pattern_backtest.html"):
        assert page in mobile, f"{page} unreachable from mobile navigation"


def test_readability_toggle_is_shown_on_mobile():
    assert "#mode-toggle.mob-hide" in RG, \
        "Simple/Expert toggle is hidden on mobile again"


def test_bottom_bar_does_not_cover_page_content():
    assert re.search(r"body\s*\{\s*padding-bottom:\s*\d+px", RG), \
        "no bottom padding reserved for the fixed nav"


# ── The Portfolio 404 stays gone ──────────────────────────────────────────────

def test_no_public_link_to_the_unpublished_portfolio_page():
    """portfolio.html holds real IBKR holdings and is never deployed."""
    assert 'href="./portfolio.html"' not in RG


# ── Nav pills never wrap ──────────────────────────────────────────────────────
#
# Measured live on 2026-08-18: the `← 配置頁` pill added with the landing-page
# swap rendered 39px wide and 99px tall at top:-19px — it overflowed the 60px
# header and sat on top of the brand block, pushing the ticker search off-row.
#
# Cause: `.nav-pill` is a flex child with the default `flex-shrink: 1` and no
# `white-space` rule. Fourteen pills overflow the row, so every one of them
# shrinks. Latin labels break at their spaces and mostly survive; CJK has no
# spaces, so `配置頁` broke one character per line and grew three lines tall.
#
# The nav scrolls horizontally instead. That needs all three declarations:
# nowrap and no-shrink on the pill, and `min-width: 0` on the container so the
# flex item is allowed to shrink below its content width and actually scroll.

def _nav_pill_css():
    m = re.search(r"\.nav-pill\s*\{(.*?)\}", RG, re.S)
    assert m, ".nav-pill rule not found"
    return m.group(1)


def _nav_pills_css():
    m = re.search(r"\.nav-pills\s*\{(.*?)\}", RG, re.S)
    assert m, ".nav-pills rule not found"
    return m.group(1)


def test_nav_pills_do_not_wrap():
    """CJK labels wrap per character when allowed to. Never allow it."""
    assert re.search(r"white-space:\s*nowrap", _nav_pill_css()), (
        "a shrinking .nav-pill wraps CJK one character per line and grows "
        "taller than the 60px header — see this block's comment"
    )


def test_nav_pills_do_not_shrink():
    assert re.search(r"flex-shrink:\s*0", _nav_pill_css()), (
        "nowrap alone still lets the pill shrink and clip its own label"
    )


def test_nav_row_can_scroll_instead_of_overflowing():
    css = _nav_pills_css()
    assert re.search(r"overflow-x:\s*auto", css), "nav must scroll, not spill"
    assert re.search(r"min-width:\s*0", css), (
        "without min-width:0 the flex item refuses to shrink, so overflow-x "
        "never engages and the row overflows the header anyway"
    )


def test_brand_block_is_not_squeezed_by_the_nav():
    m = re.search(r"\.brand\s*\{(.*?)\}", RG, re.S)
    assert m, ".brand rule not found"
    assert re.search(r"flex-shrink:\s*0", m.group(1)), (
        "the brand collapsed under the overflowing nav on 2026-08-18"
    )
