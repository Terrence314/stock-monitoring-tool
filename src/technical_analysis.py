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



def _stochastic(high: pd.Series, low: pd.Series, close: pd.Series,
                k_period: int = 9, k_smooth: int = 3, d_smooth: int = 3):
    """Slow Stochastic KD(k_period, k_smooth, d_smooth) — standard Taiwan KD(9,3,3)."""
    low_min  = low.rolling(k_period).min()
    high_max = high.rolling(k_period).max()
    raw_k    = 100 * (close - low_min) / (high_max - low_min).replace(0, float("nan"))
    slow_k   = raw_k.rolling(k_smooth).mean()
    slow_d   = slow_k.rolling(d_smooth).mean()
    return slow_k, slow_d

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


    # ── KD Stochastic (9,3,3) ─────────────────────────────────────────────────
    df["KD_K"], df["KD_D"] = _stochastic(df["High"], df["Low"], df["Close"])

    latest = df.iloc[-1]
    prev   = df.iloc[-2]


    # ── KD values ─────────────────────────────────────────────────────────────
    kd_k      = float(latest["KD_K"])  if not pd.isna(latest["KD_K"])  else None
    kd_d      = float(latest["KD_D"])  if not pd.isna(latest["KD_D"])  else None
    prev_kd_k = float(prev["KD_K"])    if not pd.isna(prev["KD_K"])    else None
    prev_kd_d = float(prev["KD_D"])    if not pd.isna(prev["KD_D"])    else None

    kd_oversold = (
        kd_k is not None and kd_d is not None
        and kd_k < 20 and kd_d < 20
    )
    # K crossed above D while still in low zone (< 30) — classic bottom reversal
    kd_golden_cross_low = (
        kd_k is not None and kd_d is not None
        and prev_kd_k is not None and prev_kd_d is not None
        and kd_k > kd_d and prev_kd_k <= prev_kd_d
        and kd_k < 30
    )
    # K crossed below D while still in high zone (> 70) — top reversal warning
    kd_death_cross_high = (
        kd_k is not None and kd_d is not None
        and prev_kd_k is not None and prev_kd_d is not None
        and kd_k < kd_d and prev_kd_k >= prev_kd_d
        and kd_k > 70
    )

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
    # Zero-line filter: golden cross above 0 = confirmed bullish zone (full credit).
    # Golden cross below 0 = price still in bearish territory — discount per 0軸理論.
    macd_above_zero = macd_line > 0
    if macd_line > macd_sig and macd_h > 0 and macd_h > prev_macd_h:
        if macd_above_zero:
            score += 20
            signals.append("✅ MACD 金叉且動能擴張（0軸以上）")
        else:
            score += 12  # cross below zero — discounted
            signals.append("🟡 MACD 金叉動能擴張（0軸以下，力度打折）")
    elif macd_line > macd_sig and macd_h > 0:
        if macd_above_zero:
            score += 12
            signals.append("🟡 MACD 金叉（動能略收）")
        else:
            score += 6   # cross below zero — halved
            signals.append("🟡 MACD 金叉（0軸以下，信號偏弱）")
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


    # KD Stochastic signal (informational — does not affect 5-factor score)
    if kd_golden_cross_low:
        signals.append(f"✅ KD 底部金叉（K={kd_k:.1f} ↑ D={kd_d:.1f}）底部反轉訊號")
    elif kd_death_cross_high:
        signals.append(f"❌ KD 高位死叉（K={kd_k:.1f} ↓ D={kd_d:.1f}）高位回落")
    elif kd_oversold:
        signals.append(f"🔵 KD 超賣（K={kd_k:.1f} · D={kd_d:.1f}）等待金叉確認")
    elif kd_k is not None and kd_d is not None:
        if kd_k > 80 and kd_d > 80:
            signals.append(f"⚠️ KD 超買（K={kd_k:.1f} · D={kd_d:.1f}）")
        else:
            signals.append(f"KD 中性（K={kd_k:.1f} · D={kd_d:.1f}）")

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

    # ── BB Squeeze Breakout: squeeze just fired (bands expanding after compression) ──
    # Up:   prev session was in squeeze → today bands expanding → price in upper zone (BB%B > 0.85)
    # Down: prev session was in squeeze → today bands expanding → price in lower zone (BB%B < 0.15)
    _bw_ok = (
        not pd.isna(latest["BB_bw"]) and not pd.isna(latest["BB_bw_avg"])
        and not pd.isna(prev["BB_bw"]) and not pd.isna(prev["BB_bw_avg"])
    )
    if _bw_ok:
        _prev_squeezed   = float(prev["BB_bw"])   < float(prev["BB_bw_avg"])   * 0.75
        _today_expanding = float(latest["BB_bw"]) >= float(latest["BB_bw_avg"]) * 0.75
        _bb_pct_now      = float(latest["BB_pct"]) if not pd.isna(latest["BB_pct"]) else 0.5
        bb_squeeze_breakout_up   = _prev_squeezed and _today_expanding and _bb_pct_now > 0.85
        bb_squeeze_breakout_down = _prev_squeezed and _today_expanding and _bb_pct_now < 0.15
    else:
        bb_squeeze_breakout_up   = False
        bb_squeeze_breakout_down = False

    # ── BB Walking: price hugging upper/lower band for 3+ consecutive sessions ──
    # Walking up:   BB%B > 0.80 for last 3 bars — strong uptrend in progress, hold signal
    # Walking down: BB%B < 0.20 for last 3 bars — strong downtrend, avoid/exit signal
    _recent_pct = df["BB_pct"].dropna().tail(3)
    if len(_recent_pct) >= 3:
        bb_walking_up   = bool(all(v > 0.80 for v in _recent_pct))
        bb_walking_down = bool(all(v < 0.20 for v in _recent_pct))
    else:
        bb_walking_up   = False
        bb_walking_down = False

    # ── BB Band Touch: price at extreme with oscillator confirmation ──────────
    # Lower touch: bb_pct ≤ 0.10 AND RSI < 35 — price at lower band + oversold
    # Upper touch: bb_pct ≥ 0.90 AND RSI > 70 — price at upper band + overbought
    # Card C "反轉觸及邊界" + Card D "軌道觸及 + RSI 能量確認"
    _bb_pct_val = float(latest["BB_pct"]) if not pd.isna(latest["BB_pct"]) else 0.5
    _rsi_val    = float(rsi) if not pd.isna(rsi) else 50.0
    bb_lower_touch = _bb_pct_val <= 0.10 and _rsi_val < 35
    bb_upper_touch = _bb_pct_val >= 0.90 and _rsi_val > 70

    # Add informational signals for combined band-touch conditions
    if bb_lower_touch and not bb_walking_down:
        signals.append(f"🔵 BB下軌觸及 + RSI超賣（RSI={_rsi_val:.0f}）— 留意反彈確認")
    if bb_upper_touch and not bb_walking_up:
        signals.append(f"⚠️ BB上軌觸及 + RSI超買（RSI={_rsi_val:.0f}）— 高位謹慎追入")

    def _safe(val):
        return round(float(val), 2) if not pd.isna(val) else None

    return {
        "score":                    score,
        "strength":                 strength,
        "strength_en":              strength_en,
        "signals":                  signals,
        "ma5":                      _safe(latest["MA5"]),
        "ma20":                     _safe(latest["MA20"]),
        "ma60":                     _safe(latest["MA60"]),
        "rsi":                      _safe(rsi),
        "macd":                     _safe(latest["MACD"]),
        "macd_signal":              _safe(latest["MACD_signal"]),
        "macd_hist":                _safe(latest["MACD_hist"]),
        "vol_ratio":                _safe(vol_ratio),
        "bb_upper":                 _safe(latest["BB_upper"]),
        "bb_mid":                   _safe(latest["BB_mid"]),
        "bb_lower":                 _safe(latest["BB_lower"]),
        "bb_pct":                   _safe(latest["BB_pct"]),
        "bb_bw":                    _safe(latest["BB_bw"]),
        "bb_squeeze":               bb_squeeze,
        "bb_squeeze_breakout_up":   bb_squeeze_breakout_up,
        "bb_squeeze_breakout_down": bb_squeeze_breakout_down,
        "bb_walking_up":            bb_walking_up,
        "bb_walking_down":          bb_walking_down,
        "kd_k":                     round(kd_k, 1) if kd_k is not None else None,
        "kd_d":                     round(kd_d, 1) if kd_d is not None else None,
        "kd_golden_cross_low":      kd_golden_cross_low,
        "kd_death_cross_high":      kd_death_cross_high,
        "kd_oversold":              kd_oversold,
        "bb_lower_touch":            bb_lower_touch,
        "bb_upper_touch":            bb_upper_touch,
        "df":                       df,
    }
