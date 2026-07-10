"""手動バックテストCLI。

使い方:
    python backtest.py                  # 現行universe銘柄・現行paramsで3戦略を検証
    python backtest.py --period 5y      # 期間指定
    python backtest.py --ticker 7203.T  # 単一銘柄のみ

過去の成績は将来の利益を保証しません。手数料・税・スリッページは未考慮の参考値です。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from core import data, backtest_engine as be  # noqa: E402


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", default="3y")
    ap.add_argument("--ticker", default=None, help="単一銘柄のみ検証したい場合")
    ap.add_argument("--capital", type=float, default=200_000)
    args = ap.parse_args()

    params_all = load_json(os.path.join(BASE, "state", "params.json"))
    universe = [args.ticker] if args.ticker else \
        load_json(os.path.join(BASE, "state", "universe.json"))["tickers"]

    print(f"=== バックテスト (期間: {args.period}) ===\n")
    totals = {s: [] for s in params_all}

    for ticker in universe:
        df = data.fetch_daily(ticker, period=args.period)
        if df is None or len(df) < 60:
            print(f"{ticker}: データ不足のためスキップ")
            continue
        print(f"[{ticker}]")
        for strat, params in params_all.items():
            r = be.run_single(df, strat, params, args.capital)
            if r is None:
                print(f"  {strat:>9}: データ不足")
                continue
            totals[strat].append(r["return_pct"])
            print(f"  {strat:>9}: リターン {r['return_pct']:+7.1f}% | "
                  f"取引 {r['trades']:3d}回 | 勝率 {r['win_rate']:5.1f}% | "
                  f"最大DD {r['max_drawdown_pct']:6.1f}%")

    print("\n=== 戦略別平均 ===")
    for strat, rets in totals.items():
        if rets:
            avg = sum(rets) / len(rets)
            print(f"  {strat:>9}: 平均リターン {avg:+.1f}% ({len(rets)}銘柄)")

    print("\n※手数料・税・スリッページ・単元株制約は未考慮の参考値です。")
    print("※過去の成績は将来の利益を保証しません。")


if __name__ == "__main__":
    main()
