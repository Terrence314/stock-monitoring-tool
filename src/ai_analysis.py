from google import genai
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
    """50-word stock view for the watchlist — Prompt B style."""
    change = stock_data["price_change_pct"]
    prompt = f"""股票：{ticker}（{name}）
現價：${stock_data['current_price']:.2f}  漲跌：{change:+.2f}%
MA5：{ta['ma5']} | MA20：{ta['ma20']} | MA60：{ta['ma60']}
RSI：{ta['rsi']} | MACD Hist：{ta['macd_hist']} | 量比：{ta['vol_ratio']}×
技術信號分數：{ta['score']}/100（{ta['strength']}）

請用繁體中文，50 字以內，給出：①目前盤面強弱 ②關鍵價位 ③高機率劇本。"""

    return _call(model, prompt)


def run_stock_deep_dive(model, ticker: str, name: str, stock_data: dict, ta: dict) -> dict:
    """Full per-stock analysis — maps to ezone Prompts 3, 7, 10 + btcreal Prompt D."""
    price = stock_data["current_price"]
    change = stock_data["price_change_pct"]

    base_context = f"""股票：{ticker}（{name}）
現價：${price:.2f}  漲跌：{change:+.2f}%
MA5：{ta['ma5']} | MA20：{ta['ma20']} | MA60：{ta['ma60']}
RSI：{ta['rsi']} | MACD：{ta['macd']} | MACD Signal：{ta['macd_signal']}
技術信號分數：{ta['score']}/100（{ta['strength']}）"""

    # Thesis + Catalysts (Prompt D style)
    thesis_prompt = f"""{base_context}

你是一位機構交易員，請以繁體中文分析 {ticker}：
1. 投資核心論點：目前市場定價是否正確？有何 Variant Perception？
2. 關鍵催化劑：未來 1–3 個月哪些事件會觸發股價移動？（列出 3 個）
3. 目前偏多 / 偏空 / 中性，理由一句話。
回答約 150 字。"""

    # Risk matrix (Prompt 3 style)
    risk_prompt = f"""{base_context}

請以繁體中文列出 {ticker} 目前最重要的 3 個風險（宏觀 / 行業 / 公司層面各一），每個風險給出一個投資者應監測的先行指標。約 100 字。"""

    # Entry/Exit (Prompt 10 style)
    entry_prompt = f"""{base_context}

請以繁體中文給出 {ticker} 的擇時建議：
• 建議買入區間
• 止損位（price level）及觸發邏輯
• 第一目標價 / 第二目標價
• 風險回報比估算
約 80 字。"""

    return {
        "thesis":    _call(model, thesis_prompt),
        "risks":     _call(model, risk_prompt),
        "entry":     _call(model, entry_prompt),
    }
