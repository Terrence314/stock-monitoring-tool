"""Watchlist scanner for the PM Capital Allocation dashboard.

Scores every ticker in config.json's `watchlist` 0-100 (conviction) and sorts
them into the three buckets the dashboard renders:

    tonight    今晚交易 — short-term setup live right now, with a strategy label
    long_term  長線首選 — structural uptrend worth holding
    avoid      避免交易 — broken or overextended, do not touch

Conviction is a composite of trend structure, momentum, relative strength
against SPY, and volume confirmation. It is a *ranking* score, not a
probability — see the provenance banner on the dashboard.

Prices: Finnhub `/quote` for the live last price, yfinance for the history the
indicators need (Finnhub's free tier serves no US daily candles).
"""

from __future__ import annotations

import pandas as pd
import yfinance as yf

from pm_regime import fetch_history

try:
    import finnhub as _finnhub_module
    _FINNHUB_AVAILABLE = True
except ImportError:
    _FINNHUB_AVAILABLE = False

BENCHMARK = "SPY"
HISTORY_PERIOD = "1y"
MIN_BARS_REQUIRED = 60

# Conviction weights — sum to 100.
WEIGHT_TREND = 40
WEIGHT_MOMENTUM = 30
WEIGHT_RELATIVE_STRENGTH = 20
WEIGHT_VOLUME = 10

# Bucket thresholds.
TONIGHT_MIN_CONVICTION = 65
LONG_TERM_MIN_CONVICTION = 55
AVOID_MAX_CONVICTION = 40

# Display caps. In a broad uptrend most of the watchlist qualifies, and a
# 24-name "tonight" list is not a decision — it is a screener dump. Cap to what
# can actually be sized and executed in one evening.
TONIGHT_MAX = 5
LONG_TERM_MAX = 5
AVOID_MAX = 6

RSI_HEALTHY_LOW = 45
RSI_HEALTHY_HIGH = 70
RSI_OVERBOUGHT = 75
RSI_EXTREME = 80
RSI_OVERSOLD = 30

SHORT_LOOKBACK_DAYS = 20
LONG_LOOKBACK_DAYS = 120


def _rsi(closes: pd.Series, period: int = 14) -> float | None:
    """Wilder RSI of the final bar, or None when history is too short."""
    if len(closes) < period + 1:
        return None
    delta = closes.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    last_loss = float(loss.iloc[-1])
    if last_loss == 0:
        return 100.0
    rs = float(gain.iloc[-1]) / last_loss
    return round(100 - 100 / (1 + rs), 1)


def _macd_histogram(closes: pd.Series) -> float | None:
    """MACD(12,26,9) histogram on the final bar."""
    if len(closes) < 35:
        return None
    fast = closes.ewm(span=12, adjust=False).mean()
    slow = closes.ewm(span=26, adjust=False).mean()
    macd_line = fast - slow
    signal = macd_line.ewm(span=9, adjust=False).mean()
    return round(float((macd_line - signal).iloc[-1]), 4)


def _pct_change(closes: pd.Series, lookback: int) -> float | None:
    if len(closes) <= lookback:
        return None
    past = float(closes.iloc[-(lookback + 1)])
    if not past:
        return None
    return round((float(closes.iloc[-1]) - past) / past * 100, 2)


def fetch_live_quotes(tickers: list[str], api_key: str) -> dict[str, float]:
    """Live last prices from Finnhub. Missing keys mean 'fall back to history'.

    Every ticker is wrapped individually — one bad symbol or a rate-limit hit
    must not cost the whole batch.
    """
    if not _FINNHUB_AVAILABLE or not api_key:
        print("  [pm_watchlist] no Finnhub key — live quotes skipped, using yfinance closes")
        return {}

    client = _finnhub_module.Client(api_key=api_key)
    quotes: dict[str, float] = {}
    for ticker in tickers:
        try:
            payload = client.quote(ticker) or {}
            price = payload.get("c")
            if price:
                quotes[ticker] = float(price)
        except Exception as exc:
            print(f"  [pm_watchlist] Finnhub quote failed for {ticker}: {exc}")
    return quotes


def _score_trend(price: float, ma20: float, ma50: float, ma200: float) -> tuple[float, list[str]]:
    tests = ((price > ma20, "價>MA20", 10),
             (price > ma50, "價>MA50", 15),
             (price > ma200, "價>MA200", 15))
    score = sum(points for ok, _, points in tests if ok)
    passed = [label for ok, label, _ in tests if ok]
    return score, passed


def _score_momentum(rsi: float | None, macd_hist: float | None) -> tuple[float, list[str]]:
    score = 0.0
    passed: list[str] = []

    if macd_hist is None:
        score += 7.5
    elif macd_hist > 0:
        score += 15
        passed.append("MACD 柱正")

    if rsi is None:
        score += 7.5
    elif RSI_HEALTHY_LOW <= rsi <= RSI_HEALTHY_HIGH:
        score += 15
        passed.append(f"RSI {rsi} 健康區")
    elif rsi > RSI_OVERBOUGHT:
        passed.append(f"RSI {rsi} 超買")
    elif rsi < RSI_OVERSOLD:
        score += 5
        passed.append(f"RSI {rsi} 超賣")
    else:
        score += 8

    return score, passed


def _score_relative_strength(own_pct: float | None, bench_pct: float | None) -> tuple[float, str]:
    if own_pct is None or bench_pct is None:
        return WEIGHT_RELATIVE_STRENGTH / 2, "相對強弱數據不足"
    spread = own_pct - bench_pct
    # -10pp .. +10pp versus SPY spans the full weight.
    fraction = max(0.0, min(1.0, (spread + 10) / 20))
    label = f"20日相對 SPY {spread:+.1f}pp"
    return WEIGHT_RELATIVE_STRENGTH * fraction, label


def _score_volume(volumes: pd.Series | None) -> tuple[float, str]:
    if volumes is None or len(volumes) < 21:
        return WEIGHT_VOLUME / 2, "成交量數據不足"
    latest = float(volumes.iloc[-1])
    average = float(volumes.iloc[-21:-1].mean())
    if not average:
        return WEIGHT_VOLUME / 2, "成交量數據不足"
    ratio = latest / average
    if ratio >= 1.2:
        return WEIGHT_VOLUME, f"量能 {ratio:.1f}× 放大"
    if ratio >= 0.8:
        return WEIGHT_VOLUME * 0.6, f"量能 {ratio:.1f}× 正常"
    return WEIGHT_VOLUME * 0.2, f"量能 {ratio:.1f}× 萎縮"


def _strategy_for(price: float, ma20: float, ma50: float,
                  rsi: float | None, macd_hist: float | None) -> str:
    """Plain-language setup label for a tonight-trade candidate."""
    if rsi is not None and rsi < RSI_HEALTHY_LOW and price > ma50:
        return "回調買入 — 強勢股回落至支撐,分批進場"
    if price > ma20 > ma50 and (macd_hist or 0) > 0:
        return "順勢突破 — 均線多頭排列,突破前高進場"
    if price > ma50 and (macd_hist or 0) > 0:
        return "動能延續 — MACD 轉正,MA50 之上持有"
    return "區間操作 — 結構尚可但無明確突破,小倉試探"


def analyse_ticker(ticker: str, name: str,
                   closes: pd.Series, volumes: pd.Series | None,
                   benchmark_closes: pd.Series,
                   live_price: float | None) -> dict | None:
    """Score one ticker. Returns None when history is too thin to judge."""
    if closes is None or len(closes) < MIN_BARS_REQUIRED:
        print(f"  [pm_watchlist] {ticker} skipped — only {0 if closes is None else len(closes)} bars")
        return None

    price = live_price if live_price else float(closes.iloc[-1])
    price_source = "finnhub" if live_price else "yfinance"

    ma20 = float(closes.rolling(20).mean().iloc[-1])
    ma50 = float(closes.rolling(50).mean().iloc[-1])
    ma200 = (float(closes.rolling(200).mean().iloc[-1])
             if len(closes) >= 200 else float(closes.mean()))

    rsi = _rsi(closes)
    macd_hist = _macd_histogram(closes)

    trend_score, trend_notes = _score_trend(price, ma20, ma50, ma200)
    momentum_score, momentum_notes = _score_momentum(rsi, macd_hist)
    rs_score, rs_note = _score_relative_strength(
        _pct_change(closes, SHORT_LOOKBACK_DAYS),
        _pct_change(benchmark_closes, SHORT_LOOKBACK_DAYS),
    )
    volume_score, volume_note = _score_volume(volumes)

    conviction = round(trend_score + momentum_score + rs_score + volume_score, 1)
    notes = trend_notes + momentum_notes + [rs_note, volume_note]

    return {
        "ticker": ticker,
        "name": name,
        "price": round(price, 2),
        "price_source": price_source,
        "conviction": conviction,
        "rsi": rsi,
        "macd_hist": macd_hist,
        "ma20": round(ma20, 2),
        "ma50": round(ma50, 2),
        "ma200": round(ma200, 2),
        "change_20d_pct": _pct_change(closes, SHORT_LOOKBACK_DAYS),
        "change_120d_pct": _pct_change(closes, LONG_LOOKBACK_DAYS),
        "notes": notes,
        "strategy": _strategy_for(price, ma20, ma50, rsi, macd_hist),
    }


def _avoid_reason(row: dict) -> str | None:
    rsi = row["rsi"]
    if row["conviction"] < AVOID_MAX_CONVICTION:
        return f"信心分僅 {row['conviction']} — 結構未成形"
    if row["price"] < row["ma200"] and (row["macd_hist"] or 0) < 0:
        return "跌破 MA200 且 MACD 為負 — 下降趨勢中"
    if rsi is not None and rsi >= RSI_EXTREME:
        return f"RSI {rsi} 極度超買 — 追高風險大"
    return None


def bucket(rows: list[dict], regime_band: str) -> dict[str, list[dict]]:
    """Sort scored rows into the dashboard's three lists.

    `regime_band` gates the tonight list: in a CASH regime no new position is
    opened regardless of individual conviction, which is the whole point of
    having a market-regime card.
    """
    avoid, tonight, long_term = [], [], []

    for row in rows:
        reason = _avoid_reason(row)
        if reason:
            avoid.append({**row, "reason": reason})
            continue

        is_tonight_setup = (
            row["conviction"] >= TONIGHT_MIN_CONVICTION
            and row["price"] > row["ma20"]
            and (row["macd_hist"] or 0) > 0
            and (row["rsi"] is None or row["rsi"] < RSI_OVERBOUGHT)
        )
        if is_tonight_setup and regime_band != "CASH":
            tonight.append(row)

        is_long_term = (
            row["price"] > row["ma200"]
            and row["ma50"] > row["ma200"]
            and row["conviction"] >= LONG_TERM_MIN_CONVICTION
            and (row["change_120d_pct"] or 0) > 0
        )
        if is_long_term:
            long_term.append(row)

    by_conviction = sorted(tonight, key=lambda r: r["conviction"], reverse=True)
    by_conviction_long = sorted(long_term, key=lambda r: r["conviction"], reverse=True)
    by_weakness = sorted(avoid, key=lambda r: r["conviction"])

    return {
        "tonight": by_conviction[:TONIGHT_MAX],
        "long_term": by_conviction_long[:LONG_TERM_MAX],
        "avoid": by_weakness[:AVOID_MAX],
        "qualified_counts": {
            "tonight": len(by_conviction),
            "long_term": len(by_conviction_long),
            "avoid": len(by_weakness),
        },
    }


def scan(watchlist: list[dict], regime_band: str, finnhub_key: str = "") -> dict:
    """Full watchlist pass. `watchlist` is config.json's list of ticker dicts."""
    us_entries = [entry for entry in watchlist
                  if entry.get("ticker") and entry.get("market", "US") == "US"]
    tickers = [entry["ticker"] for entry in us_entries]
    if not tickers:
        return {"tonight": [], "long_term": [], "avoid": [],
                "qualified_counts": {"tonight": 0, "long_term": 0, "avoid": 0},
                "scanned": 0, "skipped": [], "live_quote_count": 0,
                "suppressed_by_regime": False}

    history = fetch_history(tuple(dict.fromkeys(tickers + [BENCHMARK])), HISTORY_PERIOD)
    volumes = _fetch_volumes(tickers)
    live_quotes = fetch_live_quotes(tickers, finnhub_key)
    benchmark_closes = history.get(BENCHMARK, pd.Series(dtype=float))

    rows, skipped = [], []
    for entry in us_entries:
        ticker = entry["ticker"]
        row = analyse_ticker(
            ticker,
            entry.get("name", ticker),
            history.get(ticker),
            volumes.get(ticker),
            benchmark_closes,
            live_quotes.get(ticker),
        )
        if row is None:
            skipped.append(ticker)
            continue
        rows.append(row)

    buckets = bucket(rows, regime_band)
    return {
        **buckets,
        "scanned": len(rows),
        "skipped": skipped,
        "live_quote_count": len(live_quotes),
        "suppressed_by_regime": regime_band == "CASH",
    }


def _fetch_volumes(tickers: list[str]) -> dict[str, pd.Series]:
    """Daily volume series per ticker — separate call so a failure here only
    degrades the volume component instead of the whole scan."""
    try:
        raw = yf.download(tickers, period="6mo", interval="1d",
                          auto_adjust=True, progress=False, group_by="column")
    except Exception as exc:
        print(f"  [pm_watchlist] volume download failed: {exc}")
        return {}
    if raw is None or raw.empty or "Volume" not in raw:
        return {}

    volume_frame = raw["Volume"]
    if isinstance(volume_frame, pd.Series):
        return {tickers[0]: volume_frame.dropna()}
    return {t: volume_frame[t].dropna() for t in tickers if t in volume_frame.columns}
