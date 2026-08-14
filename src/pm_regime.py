"""Market regime scorer for the PM Capital Allocation dashboard.

Produces a single 0-100 confidence index from four independent components:

    SPY trend       25 pts   broad market structure
    QQQ trend       20 pts   growth/tech leadership
    VIX regime      25 pts   volatility / fear
    Sector rotation 30 pts   breadth + offensive-vs-defensive tilt

Deployment bands (fixed by spec):
    > 75    FULL        全倉
    60-75   SELECTIVE   選擇性部署 25-50%
    < 60    CASH        空倉

History comes from yfinance — Finnhub's free tier does not serve daily candles
for US equities and has no ^VIX index, so it cannot drive a trend score.
Live quotes still come from Finnhub (see pm_watchlist.fetch_live_quotes).
"""

from __future__ import annotations

import pandas as pd
import yfinance as yf

# Component weights — must sum to MAX_SCORE.
WEIGHT_SPY = 25
WEIGHT_QQQ = 20
WEIGHT_VIX = 25
WEIGHT_SECTOR = 30
MAX_SCORE = 100

BAND_FULL_MIN = 75
BAND_SELECTIVE_MIN = 60

# VIX levels, calm -> panic. Score interpolates linearly between the anchors.
VIX_CALM = 14.0
VIX_ELEVATED = 20.0
VIX_STRESSED = 28.0

SECTOR_ETFS = {
    "XLK": "科技",
    "XLC": "通訊",
    "XLY": "非必需消費",
    "XLI": "工業",
    "XLF": "金融",
    "XLE": "能源",
    "XLB": "原材料",
    "XLV": "醫療",
    "XLP": "必需消費",
    "XLU": "公用",
    "XLRE": "房地產",
}
OFFENSIVE_SECTORS = ("XLK", "XLC", "XLY", "XLI")
DEFENSIVE_SECTORS = ("XLP", "XLU", "XLV")

INDEX_TICKERS = ("SPY", "QQQ", "^VIX")
HISTORY_PERIOD = "1y"
MOMENTUM_LOOKBACK_DAYS = 20
MIN_BARS_REQUIRED = 200


def fetch_history(tickers: tuple[str, ...] | list[str],
                  period: str = HISTORY_PERIOD) -> dict[str, pd.Series]:
    """Download daily closes for `tickers`. Returns {ticker: close series}.

    Tickers that fail or come back empty are omitted rather than raising —
    callers must treat a missing key as "no data" and degrade the score
    component instead of crashing the whole run.
    """
    if not tickers:
        return {}

    try:
        raw = yf.download(
            list(tickers),
            period=period,
            interval="1d",
            auto_adjust=True,
            progress=False,
            group_by="column",
        )
    except Exception as exc:
        print(f"  [pm_regime] yfinance download failed: {exc}")
        return {}

    if raw is None or raw.empty:
        print("  [pm_regime] yfinance returned no rows")
        return {}

    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    if isinstance(closes, pd.Series):  # single ticker, flat frame
        closes = closes.to_frame(name=list(tickers)[0])

    series_by_ticker: dict[str, pd.Series] = {}
    for ticker in tickers:
        cleaned = closes[ticker].dropna() if ticker in closes.columns else pd.Series(dtype=float)
        if cleaned.empty:
            # Batch downloads intermittently drop a symbol — yfinance's shared
            # tz cache throws "database is locked" under concurrent access.
            # A single-ticker retry recovers it; ^VIX is the usual casualty.
            cleaned = _fetch_single(ticker, period)
        if cleaned.empty:
            print(f"  [pm_regime] {ticker} has no usable closes")
            continue
        series_by_ticker[ticker] = cleaned
    return series_by_ticker


def _fetch_single(ticker: str, period: str) -> pd.Series:
    """Fallback one-ticker fetch for symbols the batch download dropped."""
    try:
        hist = yf.Ticker(ticker).history(period=period, auto_adjust=True)
    except Exception as exc:
        print(f"  [pm_regime] {ticker} single-ticker retry failed: {exc}")
        return pd.Series(dtype=float)
    if hist is None or hist.empty or "Close" not in hist:
        return pd.Series(dtype=float)
    print(f"  [pm_regime] {ticker} recovered via single-ticker retry")
    return hist["Close"].dropna()


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _interpolate(value: float, low: float, high: float) -> float:
    """Fraction of the way `value` sits from `low` to `high`, clamped to 0-1."""
    if high == low:
        return 0.0
    return _clamp((value - low) / (high - low), 0.0, 1.0)


def score_trend(closes: pd.Series, weight: int) -> dict:
    """Score one index's trend structure out of `weight` points.

    Four equal sub-tests: price>MA50, price>MA200, MA50>MA200 (golden cross),
    and positive 20-day momentum.
    """
    if closes is None or len(closes) < MIN_BARS_REQUIRED:
        # Not enough history to judge — award the neutral midpoint rather than
        # zero, so a data gap does not masquerade as a bearish signal.
        return {
            "score": weight / 2,
            "max": weight,
            "detail": "歷史數據不足,以中性計",
            "price": None,
            "ma50": None,
            "ma200": None,
        }

    price = float(closes.iloc[-1])
    ma50 = float(closes.rolling(50).mean().iloc[-1])
    ma200 = float(closes.rolling(200).mean().iloc[-1])
    past = float(closes.iloc[-(MOMENTUM_LOOKBACK_DAYS + 1)])
    momentum_pct = (price - past) / past * 100 if past else 0.0

    tests = (
        price > ma50,
        price > ma200,
        ma50 > ma200,
        momentum_pct > 0,
    )
    score = weight * sum(tests) / len(tests)
    labels = ("價>MA50", "價>MA200", "MA50>MA200", "20日動能正")
    passed = [label for label, ok in zip(labels, tests) if ok]

    return {
        "score": round(score, 1),
        "max": weight,
        "detail": " · ".join(passed) if passed else "四項趨勢測試全數不合格",
        "price": round(price, 2),
        "ma50": round(ma50, 2),
        "ma200": round(ma200, 2),
        "momentum_pct": round(momentum_pct, 2),
    }


def score_vix(closes: pd.Series, weight: int = WEIGHT_VIX) -> dict:
    """Score volatility regime out of `weight` points — lower VIX scores higher."""
    if closes is None or closes.empty:
        return {"score": weight / 2, "max": weight,
                "detail": "VIX 數據缺失,以中性計", "level": None}

    level = float(closes.iloc[-1])

    if level <= VIX_CALM:
        fraction = 1.0
        label = "平靜"
    elif level <= VIX_ELEVATED:
        fraction = 1.0 - 0.4 * _interpolate(level, VIX_CALM, VIX_ELEVATED)
        label = "偏高"
    elif level <= VIX_STRESSED:
        fraction = 0.6 - 0.45 * _interpolate(level, VIX_ELEVATED, VIX_STRESSED)
        label = "緊張"
    else:
        fraction = _clamp(0.15 - 0.15 * _interpolate(level, VIX_STRESSED, 40.0), 0.0, 0.15)
        label = "恐慌"

    return {
        "score": round(weight * fraction, 1),
        "max": weight,
        "detail": f"VIX {level:.1f} — {label}",
        "level": round(level, 2),
        "label": label,
    }


def score_sector_rotation(sector_closes: dict[str, pd.Series],
                          weight: int = WEIGHT_SECTOR) -> dict:
    """Score sector breadth and offensive tilt out of `weight` points.

    Two halves: how many sectors hold their MA50 (breadth), and whether
    offensive sectors are outrunning defensive ones over 20 days (tilt).
    """
    usable = {t: s for t, s in sector_closes.items() if len(s) > 50}
    if not usable:
        return {"score": weight / 2, "max": weight,
                "detail": "板塊數據缺失,以中性計",
                "breadth_pct": None, "leaders": [], "laggards": []}

    above_ma50 = 0
    momentum_by_ticker: dict[str, float] = {}
    for ticker, closes in usable.items():
        price = float(closes.iloc[-1])
        ma50 = float(closes.rolling(50).mean().iloc[-1])
        if price > ma50:
            above_ma50 += 1
        if len(closes) > MOMENTUM_LOOKBACK_DAYS:
            past = float(closes.iloc[-(MOMENTUM_LOOKBACK_DAYS + 1)])
            momentum_by_ticker[ticker] = (price - past) / past * 100 if past else 0.0

    breadth_pct = above_ma50 / len(usable) * 100
    breadth_score = weight / 2 * (breadth_pct / 100)

    offensive = [momentum_by_ticker[t] for t in OFFENSIVE_SECTORS if t in momentum_by_ticker]
    defensive = [momentum_by_ticker[t] for t in DEFENSIVE_SECTORS if t in momentum_by_ticker]
    if offensive and defensive:
        spread = sum(offensive) / len(offensive) - sum(defensive) / len(defensive)
        # -3% .. +3% spread maps across the full half-weight range.
        tilt_score = weight / 2 * _interpolate(spread, -3.0, 3.0)
        tilt_label = "進攻板塊領先" if spread > 0 else "防守板塊領先"
    else:
        spread = 0.0
        tilt_score = weight / 4
        tilt_label = "攻守數據不足"

    ranked = sorted(momentum_by_ticker.items(), key=lambda kv: kv[1], reverse=True)
    to_named = lambda pairs: [
        {"ticker": t, "name": SECTOR_ETFS.get(t, t), "momentum_pct": round(m, 2)}
        for t, m in pairs
    ]

    return {
        "score": round(breadth_score + tilt_score, 1),
        "max": weight,
        "detail": f"{above_ma50}/{len(usable)} 板塊企穩 MA50 · {tilt_label}",
        "breadth_pct": round(breadth_pct, 1),
        "offense_minus_defense_pct": round(spread, 2),
        "leaders": to_named(ranked[:3]),
        "laggards": to_named(ranked[-3:][::-1]),
    }


def classify(score: float) -> dict:
    """Map a 0-100 score to the deployment band fixed by the spec."""
    if score > BAND_FULL_MIN:
        return {"band": "FULL", "label": "全倉",
                "deploy_pct": "100%",
                "instruction": "信心指數 >75 — 全倉部署"}
    if score >= BAND_SELECTIVE_MIN:
        return {"band": "SELECTIVE", "label": "選擇性部署",
                "deploy_pct": "25-50%",
                "instruction": "信心指數 60-75 — 只做最高信心標的,倉位 25-50%"}
    return {"band": "CASH", "label": "空倉",
            "deploy_pct": "0%",
            "instruction": "信心指數 <60 — 空倉觀望,不開新倉"}


def compute_regime() -> dict:
    """Fetch data and return the full regime payload for the dashboard."""
    index_history = fetch_history(INDEX_TICKERS)
    sector_history = fetch_history(tuple(SECTOR_ETFS))

    components = {
        "spy": score_trend(index_history.get("SPY"), WEIGHT_SPY),
        "qqq": score_trend(index_history.get("QQQ"), WEIGHT_QQQ),
        "vix": score_vix(index_history.get("^VIX")),
        "sector": score_sector_rotation(sector_history),
    }
    total = round(sum(c["score"] for c in components.values()), 1)
    degraded = [name for name, c in components.items() if "缺失" in c["detail"] or "不足" in c["detail"]]

    return {
        "score": total,
        "max": MAX_SCORE,
        **classify(total),
        "components": components,
        "degraded_components": degraded,
    }
