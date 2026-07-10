"""売買戦略群。すべて同じインターフェースを持つ:

    signal(df_with_indicators, params) -> "BUY" | "SELL" | None

df は core.indicators.add_all() 済みのDataFrameを渡すこと。
判定は「直近2本」だけを見る（過去全体を毎回見直す必要がない = 高速・決定論的）。
"""
from __future__ import annotations

import pandas as pd


def _ready(row: pd.Series, keys: list[str]) -> bool:
    return all(pd.notna(row.get(k)) for k in keys)


# ---------------------------------------------------------------------------
# 1. trend: SMAクロス + RSI過熱フィルター
# ---------------------------------------------------------------------------
def trend_signal(df: pd.DataFrame, params: dict) -> str | None:
    if len(df) < 2:
        return None
    prev, cur = df.iloc[-2], df.iloc[-1]
    if not _ready(prev, ["sma_s", "sma_l"]) or not _ready(cur, ["sma_s", "sma_l", "rsi"]):
        return None

    golden = prev["sma_s"] <= prev["sma_l"] and cur["sma_s"] > cur["sma_l"]
    dead = prev["sma_s"] >= prev["sma_l"] and cur["sma_s"] < cur["sma_l"]

    rsi_buy_max = params.get("rsi_buy_max", 70)
    rsi_sell_min = params.get("rsi_sell_min", 75)

    if golden and cur["rsi"] < rsi_buy_max:
        return "BUY"
    if dead or cur["rsi"] > rsi_sell_min:
        return "SELL"
    return None


# ---------------------------------------------------------------------------
# 2. meanrev: RSI逆張り
# ---------------------------------------------------------------------------
def meanrev_signal(df: pd.DataFrame, params: dict, holding_days: int = 0) -> str | None:
    if len(df) < 1:
        return None
    cur = df.iloc[-1]
    if not _ready(cur, ["rsi"]):
        return None

    buy_th = params.get("meanrev_buy_rsi", 30)
    sell_th = params.get("meanrev_sell_rsi", 55)
    max_hold = params.get("meanrev_max_hold_days", 10)

    if cur["rsi"] < buy_th:
        return "BUY"
    if cur["rsi"] > sell_th or holding_days >= max_hold:
        return "SELL"
    return None


# ---------------------------------------------------------------------------
# 3. breakout: 直近高値更新 + ATRトレーリングストップ
# ---------------------------------------------------------------------------
def breakout_signal(df: pd.DataFrame, params: dict,
                    entry_price: float | None = None,
                    trail_stop: float | None = None) -> tuple[str | None, float | None]:
    """戻り値: (signal, 新しいtrail_stop)。ポジション保有中はtrail_stopの追跡が必要なため
    他2戦略と違い呼び出し側で状態を持ち回す。"""
    if len(df) < 2:
        return None, trail_stop
    cur = df.iloc[-1]
    if not _ready(cur, ["hh", "atr"]):
        return None, trail_stop

    atr_mult = params.get("breakout_atr_mult", 2.5)
    close = float(cur["Close"])

    if entry_price is None:
        # 未保有: 直近高値(自分自身を含まない、1本前までの最高値)を上抜けたら買い
        prev_hh = df["hh"].iloc[-2] if len(df) >= 2 and pd.notna(df["hh"].iloc[-2]) else None
        if prev_hh is not None and close > prev_hh:
            return "BUY", close - atr_mult * float(cur["atr"])
        return None, trail_stop
    else:
        # 保有中: トレーリングストップを更新し、割れたら売り
        new_stop = max(trail_stop or 0, close - atr_mult * float(cur["atr"]))
        if close < new_stop:
            return "SELL", new_stop
        return None, new_stop


STRATEGIES = {
    "trend": trend_signal,
    "meanrev": meanrev_signal,
    "breakout": breakout_signal,
}
