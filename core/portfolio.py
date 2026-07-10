"""仮想ポートフォリオの状態管理。state/portfolio.json の読み書きを一手に引き受ける。

状態の形:
{
  "cash": float,
  "positions": {
      "7203.T": {"shares": int, "avg_price": float, "strategy": "trend",
                 "entry_date": "2026-07-10", "trail_stop": float|null}
  },
  "history": [ {date, ticker, side, shares, price, strategy, pnl?} ],
  "equity_curve": [ {date, equity} ],
  "last_run_date": "2026-07-10"
}
"""
from __future__ import annotations

import json
import os


def load(path: str, initial_capital: float) -> dict:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {
        "cash": initial_capital,
        "positions": {},
        "history": [],
        "equity_curve": [],
        "last_run_date": None,
    }


def save(path: str, state: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def already_ran_today(state: dict, today: str) -> bool:
    """同日の二重約定を防ぐための冪等性チェック"""
    return state.get("last_run_date") == today


def mark_ran(state: dict, today: str) -> None:
    state["last_run_date"] = today


def equity(state: dict, prices: dict[str, float]) -> float:
    """現金 + 保有評価額 の合計。pricesは {ticker: 現在値}。"""
    total = state["cash"]
    for ticker, pos in state["positions"].items():
        price = prices.get(ticker, pos["avg_price"])
        total += pos["shares"] * price
    return total


def record_trade(state: dict, today: str, ticker: str, side: str,
                 shares: int, price: float, strategy: str,
                 pnl: float | None = None) -> None:
    entry = {"date": today, "ticker": ticker, "side": side,
             "shares": shares, "price": round(price, 2), "strategy": strategy}
    if pnl is not None:
        entry["pnl"] = round(pnl, 2)
    state["history"].append(entry)


def append_equity_point(state: dict, today: str, equity_value: float) -> None:
    # 同日分が既にあれば上書き（再実行時に重複させない）
    curve = state["equity_curve"]
    if curve and curve[-1]["date"] == today:
        curve[-1]["equity"] = round(equity_value, 2)
    else:
        curve.append({"date": today, "equity": round(equity_value, 2)})
