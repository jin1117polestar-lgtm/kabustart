"""バックテスト: 過去データで売買ルールの成績を検証する

使い方:
    python backtest.py            # config.json の銘柄で過去3年を検証
    python backtest.py 5y         # 期間を指定 (例: 1y, 3y, 5y, 10y)

各銘柄に同額を割り当て、strategy.py と同じルールで
売買した場合の成績を表示する。手数料・税・スリッページは考慮しない。
"""
import json
import os
import sys

import pandas as pd
import yfinance as yf

import strategy

BASE = os.path.dirname(os.path.abspath(__file__))


def backtest_ticker(ticker: str, period: str, params: dict, capital: float):
    df = yf.download(ticker, period=period, interval="1d",
                     progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if df.empty or len(df) < params["sma_long"] + 5:
        return None

    df = strategy.add_indicators(df, params)

    cash = capital
    shares = 0
    entry = 0.0
    wins = losses = 0
    equity_curve = []

    for i in range(1, len(df)):
        prev, cur = df.iloc[i - 1], df.iloc[i]
        price = float(cur["Close"])
        sig = strategy.make_signal(prev, cur, params)

        if sig == "BUY" and shares == 0:
            shares = int(cash // price)
            if shares > 0:
                cash -= shares * price
                entry = price
        elif sig == "SELL" and shares > 0:
            cash += shares * price
            if price > entry:
                wins += 1
            else:
                losses += 1
            shares = 0

        equity_curve.append(cash + shares * price)

    final = cash + shares * float(df["Close"].iloc[-1])
    curve = pd.Series(equity_curve)
    drawdown = ((curve - curve.cummax()) / curve.cummax()).min() * 100
    total_trades = wins + losses

    # 比較用: 同期間ずっと持ち続けた場合(バイ&ホールド)
    bh = (float(df["Close"].iloc[-1]) / float(df["Close"].iloc[0]) - 1) * 100

    return {
        "ticker": ticker,
        "return_pct": (final / capital - 1) * 100,
        "buy_hold_pct": bh,
        "trades": total_trades,
        "win_rate": (wins / total_trades * 100) if total_trades else 0.0,
        "max_drawdown_pct": drawdown,
    }


def main():
    period = sys.argv[1] if len(sys.argv) > 1 else "3y"
    with open(os.path.join(BASE, "config.json"), encoding="utf-8") as f:
        config = json.load(f)
    params = config["strategy"]
    per_ticker = config["initial_capital"] / len(config["tickers"])

    print(f"=== バックテスト (期間: {period}, 1銘柄あたり {per_ticker:,.0f}円) ===\n")
    results = []
    for t in config["tickers"]:
        r = backtest_ticker(t, period, params, per_ticker)
        if r is None:
            print(f"{t}: データ不足のためスキップ")
            continue
        results.append(r)
        print(f"{r['ticker']:>8} | 戦略 {r['return_pct']:+7.1f}% "
              f"| 持ちっぱなし {r['buy_hold_pct']:+7.1f}% "
              f"| 取引 {r['trades']:3d}回 | 勝率 {r['win_rate']:5.1f}% "
              f"| 最大DD {r['max_drawdown_pct']:6.1f}%")

    if results:
        avg = sum(r["return_pct"] for r in results) / len(results)
        avg_bh = sum(r["buy_hold_pct"] for r in results) / len(results)
        print(f"\n平均: 戦略 {avg:+.1f}% / 持ちっぱなし {avg_bh:+.1f}%")
        print("\n※手数料・税・スリッページ・単元株制約は未考慮の参考値です。")
        print("※過去の成績は将来の利益を保証しません。")


if __name__ == "__main__":
    main()
