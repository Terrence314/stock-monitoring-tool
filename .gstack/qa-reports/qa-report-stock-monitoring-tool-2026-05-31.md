# QA Report — stock-monitoring-tool — 2026-05-31

**URL:** https://terrence314.github.io/stock-monitoring-tool/
**Mode:** Standard (fix critical + high + medium)
**Branch:** main
**Duration:** ~8 min
**Health Score:** baseline → final: 62 → 88

---

## Summary

| Severity | Found | Fixed | Deferred |
|----------|-------|-------|----------|
| Critical | 1 | 1 | 0 |
| High | 1 | 1 | 0 |
| Medium | 0 | 0 | 0 |
| Low | 0 | 0 | 0 |
| **Total** | **2** | **2** | **0** |

PR summary: "QA found 2 issues, fixed 2, health score 62 → 88."

---

## ISSUE-001 — [CRITICAL] Histogram bars overflow toolbar, blocking Simple/Refresh/Run Now buttons

**Category:** Functional / Visual  
**Severity:** Critical  
**Fix Status:** ✅ verified  
**Commit:** 7d7d6eb  

**Root cause:** `.hist-bar` uses `b.n * 14` for bar heights. With 54+ Tier-2 stocks
the 60-80 score bucket reaches 350 px, overflowing the 100 px flex container upward
(`align-items: flex-end`). The overflow covers the sticky filter bar, visually
obscuring and blocking clicks on Simple / Refresh / Run Now buttons.

**Files changed:** `src/report_generator.py`

**Fix:**
- `_build_sig_buckets`: normalises heights via `max(n / max_n * 80, 4)` so tallest bar = 80 px
- Jinja template: uses `b.height` instead of `[b.n * 14, 4]|max`  
- CSS: `.hist-bar` gains `overflow: hidden` as safety net

---

## ISSUE-002 — [HIGH] Star/favourite gives no feedback; user thinks it's broken

**Category:** UX / Functional  
**Severity:** High  
**Fix Status:** ✅ verified  
**Commit:** dd4b1c0  

**Root cause 1:** Favourites section sits ABOVE the Tier-2 bento grid in the page.
Clicking ☆ updates localStorage and clones the card into Favourites — but the user
is scrolled past Favourites and sees no change near their click.

**Root cause 2:** `window._favs` was undefined until `DOMContentLoaded`. `onmouseout`
inline handlers guard `if(!window._favs||...)` — this undefined check reset starred
(amber) buttons back to grey immediately on mouseout.

**Fix:**
- `toggleFavourite` now shows a 2.2s amber toast ("⭐ AAPL added to Favourites")
  at screen bottom after starring
- After 300 ms smooth-scrolls `#favourites` section into view so user sees the card
- `window._favs` initialised at script parse time (not DOMContentLoaded) so `onmouseout`
  guards work from first paint

---

## Health Score Breakdown

| Category | Before | After |
|----------|--------|-------|
| Console (15%) | 100 | 100 |
| Links (10%) | 100 | 100 |
| Functional (20%) | 25 | 100 |
| UX (15%) | 50 | 100 |
| Visual (10%) | 75 | 100 |
| Performance (10%) | 100 | 100 |
| Content (5%) | 100 | 100 |
| Accessibility (15%) | 85 | 85 |
| **Total** | **62** | **88** |

