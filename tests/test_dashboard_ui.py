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


def test_expert_is_opt_in_not_the_default():
    """Only an explicit saved 'expert' preference leaves beginner mode."""
    assert re.search(r"mode\s*!==\s*'expert'", RG), \
        "default view is no longer Simple"


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
