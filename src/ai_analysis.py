from google import genai
from google.genai import types
from datetime import datetime
import time


def setup_gemini(api_key: str, model_name: str = "gemini-2.5-flash"):
    client = genai.Client(api_key=api_key)
    client._model_name = model_name
    return client


def _call(client, prompt: str, retries: int = 3) -> str:
    for attempt in range(retries):
        try:
            response = client.models.generate_content(
                model=client._model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_budget=0)
                ),
            )
            return response.text.strip()
        except Exception as e:
            if "429" in str(e) and attempt < retries - 1:
                wait = 15 * (attempt + 1)
                print(f"  [rate limit] 等待 {wait}s 後重試…")
                time.sleep(wait)
            else:
                return f"[AI分析失敗: {e}]"
        if attempt < retries - 1:
            time.sleep(4)
    return "[AI分析失敗: 超過重試次數]"


def run_morning_brief(model, market_overview: dict) -> str:
    """Run morning workflow F→G→H→I as one combined prompt."""
    today = datetime.now().strftime("%Y/%m/%d %A")

    market_lines = "\n".join(
        f"• {v['name']} ({k}): {v['price']:.2f}  {v['change_pct']:+.2f}%"
        for k, v in market_overview.items()
    )

    prompt = f"""今天日期：{today}

最新市場數據：
{market_lines}

你是一位資深市場分析師，請以繁體中文完成以下四步早盤分析，每步約 80–100 字，條理清晰。

【F・市場消息整理】
整理今日全球市場最重要的動向（Fed 動態、地緣政治、美股、黃金、原油、加密貨幣），告訴我：市場現在真正在交易什麼。

【G・市場情緒判讀】
分析目前市場情緒（Fear & Greed、美元強弱、美債走向、ETF 資金流向、BTC 主導率），最後給出：目前市場偏 Risk-On 還是 Risk-Off。

【H・技術面關鍵價位】
技術面分析 SPY（美股大盤）與 QQQ（科技納指），列出今日最重要的支撐和壓力價位。

【I・今日交易計畫】
綜合消息面、情緒面、技術面，給出今日操作方向（偏多 / 偏空 / 中性）、最值得關注的機會，以及必須警惕的風險事件。"""

    return _call(model, prompt)


def run_stock_quick_view(model, ticker: str, name: str, stock_data: dict, ta: dict) -> str:
    """~120-word structured view for low-signal stocks (score <65)."""
    change = stock_data["price_change_pct"]
    bb_info = ""
    if ta.get("bb_upper") and ta.get("bb_lower"):
        bb_info = f"\nBB上軌：{ta['bb_upper']} | BB下軌：{ta['bb_lower']} | BB%：{ta.get('bb_pct', 'N/A')}"
    kd_info = ""
    if ta.get("kd_k") is not None:
        kd_info = f"\nKD-K：{ta['kd_k']} | KD-D：{ta['kd_d']}"
    prompt = f"""股票：{ticker}（{name}）
現價：${stock_data['current_price']:.2f}  漲跌：{change:+.2f}%
MA5：{ta['ma5']} | MA20：{ta['ma20']} | MA60：{ta['ma60']}
RSI：{ta['rsi']} | MACD Hist：{ta['macd_hist']} | 量比：{ta['vol_ratio']}×{{bb_info}}{{kd_info}}
技術信號分數：{ta['score']}/100（{ta['strength']}）

請用繁體中文，120 字以內，分四點回答（每點一行，直接給結論，不要標題符號）：
①盤面強弱：目前趨勢方向與動能強弱
②關鍵價位：最近支撐位與壓力位（給具體數字）
③高機率劇本：未來3–5個交易日最可能走勢
④主要風險：一個最需警惕的下行風險"""

    return _call(model, prompt)


def run_stock_deep_dive(model, ticker: str, name: str, stock_data: dict, ta: dict) -> dict:
    """Full per-stock analysis — merged into 1 API call (was 3).

    Returns the same dict structure: {"thesis": "...", "risks": "...", "entry": "..."}.
    """
    price = stock_data["current_price"]
    change = stock_data["price_change_pct"]

    prompt = f"""股票：{ticker}（{name}）
現價：${price:.2f}  漲跌：{change:+.2f}%
MA5：{ta['ma5']} | MA20：{ta['ma20']} | MA60：{ta['ma60']}
RSI：{ta['rsi']} | MACD：{ta['macd']} | MACD Signal：{ta['macd_signal']}
技術信號分數：{ta['score']}/100（{ta['strength']}）

你是一位機構交易員，請以繁體中文分析 {ticker}，分三段回答：

【核心論點】約150字：投資論點、Variant Perception、3個催化劑、目前偏多/偏空/中性

【風險矩陣】約100字：3個風險（宏觀/行業/公司各一），每個附先行指標

【擇時建議】約80字：建議買入區間、止損位及邏輯、第一/第二目標價、風險回報比"""

    raw = _call(model, prompt)

    import re

    def extract_section(tag: str) -> str:
        # Match text between this 【tag】 and the next 【 or end of string
        pattern = rf"【{re.escape(tag)}】(.*?)(?=【|$)"
        match = re.search(pattern, raw, re.DOTALL)
        return match.group(1).strip() if match else ""

    thesis = extract_section("核心論點")
    risks  = extract_section("風險矩陣")
    entry  = extract_section("擇時建議")

    # Graceful fallback: if parsing completely failed, keep full response in thesis
    if not thesis and not risks and not entry:
        thesis = raw

    return {"thesis": thesis, "risks": risks, "entry": entry}


def run_news_sentiment(model, ticker: str, headlines: list) -> dict:
    """Score overall news sentiment for a ticker using Gemini.

    Args:
        model:     Gemini client returned by setup_gemini()
        ticker:    Stock ticker symbol (for context)
        headlines: List of headline strings (deduplicated, combined from all sources)

    Returns:
        {"score": int | None, "summary": str}
        Score is -10 (extremely bearish) to +10 (extremely bullish), or None if unavailable.
    """
    if len(headlines) < 2:
        return {"score": None, "summary": "無新聞數據"}

    headlines_text = "\n".join(f"• {h}" for h in headlines)

    prompt = f"""以下是 {ticker} 的最新新聞標題：

{headlines_text}

請以繁體中文完成以下兩件事：
1. 根據上述新聞，給出整體情緒評分，範圍從 -10（極度看空）到 +10（極度看多），只輸出一個整數。
2. 用一句話說明你的評分理由。

輸出格式範例：
評分：+5
理由：公司財報優於預期，帶動市場樂觀情緒。

請嚴格按此格式回答。"""

    raw = _call(model, prompt)

    # Extract numeric score from the response
    score = None
    summary = raw.strip()
    try:
        import re
        # Match an integer between -10 and +10 preceded by "評分：" or similar
        match = re.search(r"評分[：:]\s*([+-]?\d+)", raw)
        if match:
            candidate = int(match.group(1))
            if -10 <= candidate <= 10:
                score = candidate
        else:
            # Fallback: find any standalone integer in the range
            for token in re.findall(r"[+-]?\d+", raw):
                candidate = int(token)
                if -10 <= candidate <= 10:
                    score = candidate
                    break

        # Extract the one-sentence rationale
        reason_match = re.search(r"理由[：:]\s*(.+)", raw)
        if reason_match:
            summary = reason_match.group(1).strip()
    except Exception:
        pass

    return {"score": score, "summary": summary}



def run_hk_morning_brief(model, hk_data: dict, market_data: dict) -> str:
    """Generate a HK pre-market brief in Traditional Chinese using Gemini.

    hk_data: output of fetch_hk_indicators()
    market_data: output of fetch_market_overview() — US indices context

    Returns a markdown string suitable for rendering in the HK tab of the dashboard.
    """

    def _fmt(item: dict) -> str:
        if item.get("price") is None:
            return "無數據"
        chg = item.get("change_pct")
        arrow = "▲" if (chg or 0) >= 0 else "▼"
        chg_str = f"{arrow}{abs(chg):.2f}%" if chg is not None else ""
        return f"{item['price']:,.2f} {chg_str}"

    lines = ["【美股及港股風向指標（最新數據）】"]
    for ticker, info in hk_data.items():
        lines.append(f"- {info['label']} ({ticker}): {_fmt(info)}")

    data_block = "\n".join(lines)

    prompt = f"""你是香港財經分析師，請用繁體中文（香港財經用語）撰寫一份簡潔的港股盤前分析。

{data_block}

請輸出以下格式（使用 Markdown，每節不超過150字）：

## 🌍 昨夜美股概況
（用1-2句說明美股整體走勢、強弱板塊）

## 📊 港股開盤預測
（根據上述數據，判斷今日港股偏多/偏空/中性，港指預計高開/平開/低開，給出明確結論）

## 🔍 重點關注
（列出3項今日最值得注意的市場信號或板塊，每項一行，附簡短白話解釋）

## ⚠️ 風險提示
（1-2句，今日最大的不確定因素）

## 💡 新手小提示
（1句，用最簡單的話告訴新手今天應持什麼態度：積極/保守/觀望）

注意：
- 上漲用「↑紅」，下跌用「↓綠」描述（文字描述，非HTML顏色）
- 所有分析必須基於上方提供的真實數據
- 每個技術術語第一次出現時附白話解釋
- 必須給出明確結論，不可模糊"""

    return _call(model, prompt)
