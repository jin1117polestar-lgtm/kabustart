"""週次ジョブ: 固定候補リストから流動性フィルター→モメンタム上位を選定し、
state/universe.json を更新する。土曜朝に実行される想定(市場休場中に処理)。
"""
from __future__ import annotations

import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from core import data, indicators  # noqa: E402

TOP_N = 10
MIN_AVG_TURNOVER = 3e8  # 60日平均売買代金の足切り(円)。流動性が低すぎる銘柄を除外


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def main():
    from core import risk
    if risk.is_killed(BASE):
        print("[INFO] KILL_SWITCH が存在するため何もせず終了します")
        return

    candidates = load_json(os.path.join(BASE, "core", "candidates.json"))["tickers"]
    scored = []

    for ticker in candidates:
        df = data.fetch_daily(ticker, period="1y")
        if df is None or data.is_stale(df, max_age_days=7) or len(df) < 260:
            continue

        turnover = (df["Close"] * df["Volume"]).tail(60).mean()
        if turnover < MIN_AVG_TURNOVER:
            continue

        mom = indicators.momentum(df["Close"], lookback=252, skip=21)
        if mom is None:
            continue

        scored.append((ticker, mom, float(turnover)))

    scored.sort(key=lambda x: x[1], reverse=True)
    top = [t for t, _, _ in scored[:TOP_N]]

    universe_path = os.path.join(BASE, "state", "universe.json")
    save_json(universe_path, {
        "tickers": top if top else load_json(universe_path)["tickers"],
        "updated": data.today_jst(),
        "scored_count": len(scored),
    })
    print(f"[OK] スクリーニング完了。候補{len(candidates)}銘柄中{len(scored)}銘柄が有効、"
          f"上位{len(top)}銘柄を採用: {top}")


if __name__ == "__main__":
    main()
