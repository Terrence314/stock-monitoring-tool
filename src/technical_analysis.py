import pandas as pd


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


def _macd(series: pd.Series, fast=12, slow=26, signal=9):
    ema_fast   = series.ewm(span=fast, adjust=False).mean()
    ema_slow   = series.ewm(span=slow, adjust=False).mean()
    macd_line  = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram  = macd_line - signal_line
    return macd_line, signal_line, histogram


def _bollinger(series: pd.Series, period: int = 20, std_dev: float = 2.0):
    mid        = series.rolling(period).mean()
    std        = series.rolling(period).std()
    upper      = mid + std_dev * std
    lower      = mid - std_dev * std
    band_range = (upper - lower).replace(0, float("nan"))
    pct_b      = (series - lower) / band_range  # 0 = at lower band, 1 = at upper
    return upper, mid, lower, pct_b


def calculate_indicators(history: pd.DataFrame) -> dict:
    df = history.copy()

    # ── Moving Averages ──────────────────────────────────────────────────────
    df["MA5"]  = df["Close"].rolling(5).mean()
    df["MA20"] = df["Close"].rolling(20).mean()
    df["MA60"] = df["Close"].rolling(60).mean()

    # ── RSI ──────────────────────────────────────────────────────────────────
    df["RSI"] = _rsi(df["Close"])

    # ── MACD ─────────────────────────────────────────────────────────────────
    df["MACD"], df["MACD_signal"], df["MACD_hist"] = _macd(df["Close"])

    # ── Volume Ratio ─────────────────────────────────────────────────────────
    df["Vol_MA20"]  = df["Volume"].rolling(20).mean()
    df["Vol_ratio"] = df["Volume"] / df["Vol_MA20"]

    # ── Bollinger Bands (display — not included in score) ────────────────────
    df["BB_upper"], df["BB_mid"], df["BB_lower"], df["BB_pct"] = _bollinger(df["Close"])
    df["BB_bw"]     = (df["BB_upper"] - df["BB_lower"]) / df["BB_mid"].replace(0, float("nan"))
    df["BB_bw_avg"] = df["BB_bw"].rolling(20).mean()

    latest = df.iloc[-1]
    prev   = df.iloc[-2]

    # ── Signal Scoring (0–100, 5 factors × 20 pts each) ──────────────────────
    score   = 0
    signals = []

    # 1. Trend alignment
    c, m5, m20, m60 = latest["Close"], latest["MA5"], latest["MA20"], latest["MA60"]
    if c > m5 > m20 > m60:
        score += 20
        signals.append("✅ 多頭排列（價格 > MA5 > MA20 > MA60）")
    elif c > m20 > m60:
        score += 12
        signals.append("🟡 中多頭（價格 > MA20 > MA60）")
    elif c > m60:
        score += 5
        signals.append("⚠️ 價格站上 MA60")
    else:
        score += 0
        signals.append("❌ 空頭排列（價格低於 MA60）")

    # 2. RSI
    rsi = latest["RSI"]
    prev_rsi = prev["RSI"]
    if 45 <= rsi <= 70 and rsi > prev_rsi:
        score += 20
        signals.append(f"✅ RSI 動能走強（{rsi:.1f} ↑）")
    elif 30 <= rsi < 45:
        score += 10
        signals.append(f"🟡 RSI 低位回升（{rsi:.1f}）")
    elif rsi < 30:
        score += 8
        signals.append(f"🔵 RSI 超賣（{rsi:.1f}）— 留意反彈")
    elif rsi > 75:
        score += 5
        signals.append(f"⚠️ RSI 超買（{rsi:.1f}）— 注意回調")
    else:
        signals.append(f"RSI 中性（{rsi:.1f}）")

    # 3. MACD
    macd_h     = latest["MACD_hist"]
    prev_macd_h = prev["MACD_hist"]
    macd_line  = latest["MACD"]
    macd_sig   = latest["MACD_signal"]
    if macd_line > macd_sig and macd_h > 0 and macd_h > prev_macd_h:
        score += 20
        signals.append("✅ MACD 金叉且動能擴張")
    elif macd_line > macd_sig and macd_h > 0:
        score += 12
        signals.append("🟡 MACD 金叉（動能略收）")
    elif macd_h > prev_macd_h and macd_h < 0:
        score += 8
        signals.append("🟡 MACD 死叉收斂（底部跡象）")
    else:
        score += 0
        signals.append("❌ MACD 偏空")

    # 4. Volume
    vol_ratio = latest["Vol_ratio"]
    if vol_ratio >= 1.5:
        score += 20
        signals.append(f"✅ 爆量（成交量 {vol_ratio:.1f}× 均量）")
    elif vol_ratio >= 1.0:
        score += 10
        signals.append(f"🟡 量能正常（{vol_ratio:.1f}× 均量）")
    else:
        score += 0
        signals.append(f"⚠️ 量能不足（{vol_ratio:.1f}× 均量）")

    # 5. Distance from MA60
    if pd.isna(m60) or m60 == 0:
        signals.append("MA60 資料不足")
    else:
        dist = (c - m60) / m60 * 100
        if dist > 5:
            score += 20
            signals.append(f"✅ 站穩 MA60 上方 {dist:.1f}%")
        elif dist > 0:
            score += 12
            signals.append(f"🟡 略高於 MA60（+{dist:.1f}%）")
        else:
            score += 0
            signals.append(f"❌ 跌破 MA60（{dist:.1f}%）")

    # ── Strength Label ────────────────────────────────────────────────────────
    if score >= 80:
        strength = "強力做多 🔥"
        strength_en = "Strong Buy"
    elif score >= 60:
        strength = "偏多 📈"
        strength_en = "Buy"
    elif score >= 40:
        strength = "中性觀望 ⚖️"
        strength_en = "Neutral"
    elif score >= 20:
        strength = "偏空 📉"
        strength_en = "Sell"
    else:
        strength = "強力做空 ❄️"
        strength_en = "Strong Sell"

    # ── BB squeeze: current bandwidth < 75% of 20-bar average ──────────────
    bb_squeeze = (
        not pd.isna(latest["BB_bw"])
        and not pd.isna(latest["BB_bw_avg"])
        and float(latest["BB_bw"]) < float(latest["BB_bw_avg"]) * 0.75
    )

    def _safe(val):
        return round(float(val), 2) if not pd.isna(val) else None

    return {
        "score":        score,
        "strength":     strength,
        "strength_en":  strength_en,
        "signals":      signals,
        "ma5":          _safe(latest["MA5"]),
        "ma20":         _safe(latest["MA20"]),
        "ma60":         _safe(latest["MA60"]),
        "rsi":          _safe(rsi),
        "macd":         _safe(latest["MACD"]),
        "macd_signal":  _safe(latest["MACD_signal"]),
        "macd_hist":    _safe(latest["MACD_hist"]),
        "vol_ratio":    _safe(vol_ratio),
        "bb_upper":     _safe(latest["BB_upper"]),
        "bb_mid":       _safe(latest["BB_mid"]),
        "bb_lower":     _safe(latest["BB_lower"]),
        "bb_pct":       _safe(latest["BB_pct"]),
        "bb_squeeze":   bb_squeeze,
        "df":           df,
    }
