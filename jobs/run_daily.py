"""日次ジョブ: 対象銘柄のデータ取得→3戦略のシグナル判定→配分に基づき仮想約定→
リスクチェック→状態保存→ダッシュボードデータ再生成。

GitHub Actions から平日大引け後に実行される。
"""
from __future__ import annotations

import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from core import data, indicators, strategies, allocator, portfolio, risk, broker  # noqa: E402


def load_json(path, default=None):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def main():
    if risk.is_killed(BASE):
        print("[INFO] KILL_SWITCH が存在するため何もせず終了します")
        return

    config = load_json(os.path.join(BASE, "config.json"))
    params_all = load_json(os.path.join(BASE, "state", "params.json"))
    weights = load_json(os.path.join(BASE, "state", "weights.json"))
    universe = load_json(os.path.join(BASE, "state", "universe.json"))["tickers"]
    pf_path = os.path.join(BASE, "state", "portfolio.json")
    state = portfolio.load(pf_path, config["initial_capital"])

    today = data.today_jst()
    if portfolio.already_ran_today(state, today):
        print(f"[INFO] 本日({today})は既に実行済みのためスキップします")
        return

    equity_before = portfolio.equity(
        state, {t: p["avg_price"] for t, p in state["positions"].items()})

    br = broker.make_broker(config["mode"], state)
    enabled = config["strategies_enabled"]
    max_positions = config["max_positions"]
    total_capital = config["initial_capital"]

    prices_today: dict[str, float] = {}
    strategy_returns_today: dict[str, float] = {"trend": 0.0, "meanrev": 0.0, "breakout": 0.0}
    stale_tickers = []

    for ticker in universe:
        df = data.fetch_daily(ticker, period="1y")
        if df is None or data.is_stale(df):
            stale_tickers.append(ticker)
            continue

        pos = state["positions"].get(ticker)
        strat_name = pos["strategy"] if pos else None
        # 未保有の場合、有効な戦略を順に試し、最初にBUYを出した戦略を採用
        candidates = [strat_name] if strat_name else enabled

        for strat in candidates:
            p = params_all[strat]
            d = indicators.add_all(df, p)
            price = float(d["Close"].iloc[-1])
            prices_today[ticker] = price

            if strat == "breakout":
                entry_price = pos["avg_price"] if pos else None
                trail_stop = pos.get("trail_stop") if pos else None
                sig, new_stop = strategies.breakout_signal(d, p, entry_price, trail_stop)
            elif strat == "meanrev":
                hold_days = 0
                if pos and pos.get("entry_date"):
                    hold_days = max(0, (
                        __import__("datetime").date.fromisoformat(today) -
                        __import__("datetime").date.fromisoformat(pos["entry_date"])
                    ).days)
                sig = strategies.meanrev_signal(d, p, hold_days)
                new_stop = None
            else:
                sig = strategies.trend_signal(d, p)
                new_stop = None

            if sig == "BUY" and pos is None:
                if len(state["positions"]) >= max_positions:
                    break
                budget = total_capital * weights.get(strat, 0.33) / max_positions
                budget = min(budget, state["cash"],
                            risk.max_position_value(equity_before, config["risk"]["max_position_pct"]))
                shares = int(budget // price)
                if shares >= 1:
                    br.buy(ticker, shares, price)
                    state["positions"][ticker] = {
                        "shares": shares, "avg_price": price, "strategy": strat,
                        "entry_date": today, "trail_stop": new_stop,
                    }
                    portfolio.record_trade(state, today, ticker, "BUY", shares, price, strat)
                break  # 1銘柄1戦略のみ判定

            elif sig == "SELL" and pos is not None:
                proceeds_shares = pos["shares"]
                pnl = (price - pos["avg_price"]) * proceeds_shares
                br.sell(ticker, proceeds_shares, price)
                del state["positions"][ticker]
                portfolio.record_trade(state, today, ticker, "SELL", proceeds_shares,
                                       price, strat, pnl=pnl)
                strategy_returns_today[strat] += pnl / total_capital
                break

            elif pos is not None and strat == "breakout":
                # トレーリングストップの更新のみ(シグナルなし)
                state["positions"][ticker]["trail_stop"] = new_stop
                break

    equity_after = portfolio.equity(state, prices_today)

    # リスクチェック: 日次損失上限
    if risk.check_daily_loss_limit(equity_after, equity_before,
                                   config["risk"]["daily_loss_limit_pct"]):
        print(f"[WARN] 当日損失が上限を超過。明日は新規買いなしを推奨(自動反映は次回実行時)")

    portfolio.append_equity_point(state, today, equity_after)

    # 通算ドローダウン: 超過したらKILL_SWITCH
    if risk.check_drawdown_limit(state["equity_curve"], config["risk"]["drawdown_limit_pct"]):
        risk.trigger_kill_switch(BASE, f"{today}: ドローダウン上限超過のため自動停止")
        print("[ALERT] ドローダウン上限超過。KILL_SWITCHを作成しました")

    # 戦略別日次リターンをログに追記(月次学習が使用)
    for s, r in strategy_returns_today.items():
        weights.setdefault("daily_returns_log", {}).setdefault(s, []).append(r)
        weights["daily_returns_log"][s] = weights["daily_returns_log"][s][-120:]  # 直近120日分のみ保持

    portfolio.mark_ran(state, today)
    save_json(pf_path, state)
    save_json(os.path.join(BASE, "state", "weights.json"), weights)

    if stale_tickers:
        print(f"[INFO] データ未更新: {stale_tickers}")
    print(f"[OK] {today} 日次ジョブ完了。評価額: {equity_after:,.0f}円")


if __name__ == "__main__":
    main()
