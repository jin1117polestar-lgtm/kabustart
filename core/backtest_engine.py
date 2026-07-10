"""バックテスト共通エンジン。単一銘柄・単一戦略の成績を計算する。

backtest.py(手動CLI)と jobs/run_learn.py(自動ウォークフォワード)の両方から使う。
手数料・税・スリッページ・単元株制約は考慮しない参考値。
"""
from __future__ import annotations

import pandas as pd

from core import indicators, strategies


def run_single(df: pd.DataFrame, strategy_name: str, params: dict,
               capital: float) -> dict | None:
    """1銘柄・1戦略のバックテストを実行し成績指標を返す。df は生のOHLCV。"""
    if len(df) < 40:
        return None
    d = indicators.add_all(df, params)

    cash = capital
    shares = 0
    entry_price = 0.0
    entry_date = None
    trail_stop = None
    wins = losses = 0
    equity_curve = []

    for i in range(30, len(d)):
        window = d.iloc[:i + 1]
        cur = window.iloc[-1]
        price = float(cur["Close"])

        if strategy_name == "trend":
            prev, curr = window.iloc[-2], window.iloc[-1]
            sig = strategies.trend_signal(window, params)
        elif strategy_name == "meanrev":
            hold_days = (window.index[-1] - entry_date).days if entry_date is not None else 0
            sig = strategies.meanrev_signal(window, params, hold_days)
        elif strategy_name == "breakout":
            sig, new_stop = strategies.breakout_signal(
                window, params, entry_price if shares > 0 else None, trail_stop)
            trail_stop = new_stop
        else:
            sig = None

        if sig == "BUY" and shares == 0:
            shares = int(cash // price)
            if shares > 0:
                cash -= shares * price
                entry_price = price
                entry_date = window.index[-1]
        elif sig == "SELL" and shares > 0:
            cash += shares * price
            if price > entry_price:
                wins += 1
            else:
                losses += 1
            shares = 0
            entry_date = None
            trail_stop = None

        equity_curve.append(cash + shares * price)

    if not equity_curve:
        return None

    final = cash + shares * float(d["Close"].iloc[-1])
    curve = pd.Series(equity_curve)
    running_max = curve.cummax()
    drawdown = ((curve - running_max) / running_max).min() * 100
    total_trades = wins + losses

    return {
        "return_pct": (final / capital - 1) * 100,
        "trades": total_trades,
        "win_rate": (wins / total_trades * 100) if total_trades else 0.0,
        "max_drawdown_pct": float(drawdown) if pd.notna(drawdown) else 0.0,
    }


def score(result: dict, dd_lambda: float = 0.5) -> float:
    """複数候補パラメータを比較するための単一スコア。リターン重視+DDペナルティ。"""
    if result is None:
        return -1e9
    return result["return_pct"] + dd_lambda * result["max_drawdown_pct"]  # DDは負値なので加算でペナルティ
