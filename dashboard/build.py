"""ダッシュボードデータ生成。各ジョブの最後に呼ばれ、state/ の内容を
docs/data.json に集計する。docs/index.html はこのファイルを fetch するだけ。
"""
from __future__ import annotations

import json
import os
import statistics
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)


def load_json(path, default=None):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def compute_radar(state: dict, initial_capital: float) -> dict:
    """5軸レーダーチャート用のスコア(0-100)を計算する"""
    history = [h for h in state["history"] if h["side"] == "SELL"]
    curve = [p["equity"] for p in state["equity_curve"]]

    # 勝率
    wins = sum(1 for h in history if h.get("pnl", 0) > 0)
    win_rate = (wins / len(history) * 100) if history else 50.0

    # 損益率 (0%を50点、+30%以上を100点、-30%以下を0点となるよう線形マップ)
    total_return_pct = (curve[-1] / initial_capital - 1) * 100 if curve else 0.0
    return_score = max(0, min(100, 50 + total_return_pct / 30 * 50))

    # 最大DD耐性 (DDが小さいほど高得点。-30%で0点、0%で100点)
    if curve:
        peak = curve[0]
        max_dd = 0.0
        for v in curve:
            peak = max(peak, v)
            dd = (peak - v) / peak * 100 if peak > 0 else 0
            max_dd = max(max_dd, dd)
    else:
        max_dd = 0.0
    dd_score = max(0, min(100, 100 - max_dd / 30 * 100))

    # 取引効率 (簡易プロフィットファクター: 総利益/総損失)
    gains = sum(h["pnl"] for h in history if h.get("pnl", 0) > 0)
    losses = abs(sum(h["pnl"] for h in history if h.get("pnl", 0) < 0))
    pf = (gains / losses) if losses > 0 else (2.0 if gains > 0 else 1.0)
    pf_score = max(0, min(100, pf / 3 * 100))

    # 安定性 (日次リターンの標準偏差が小さいほど高得点)
    if len(curve) >= 3:
        rets = [(curve[i] / curve[i - 1] - 1) for i in range(1, len(curve)) if curve[i - 1] > 0]
        std = statistics.pstdev(rets) if len(rets) >= 2 else 0.0
    else:
        std = 0.0
    stability_score = max(0, min(100, 100 - (std / 0.03) * 100))

    return {
        "win_rate": round(win_rate, 1),
        "return": round(return_score, 1),
        "dd_resilience": round(dd_score, 1),
        "efficiency": round(pf_score, 1),
        "stability": round(stability_score, 1),
    }


def main():
    config = load_json(os.path.join(BASE, "config.json"))
    state = load_json(os.path.join(BASE, "state", "portfolio.json"),
                      {"cash": config["initial_capital"], "positions": {},
                       "history": [], "equity_curve": []})
    weights = load_json(os.path.join(BASE, "state", "weights.json"), {})
    learn_log = load_json(os.path.join(BASE, "state", "learn_log.json"), {"entries": []})
    universe = load_json(os.path.join(BASE, "state", "universe.json"), {"tickers": []})

    initial_capital = config["initial_capital"]
    curve = state.get("equity_curve", [])
    current_equity = curve[-1]["equity"] if curve else initial_capital
    total_return_pct = (current_equity / initial_capital - 1) * 100

    positions = []
    for ticker, pos in state.get("positions", {}).items():
        positions.append({
            "ticker": ticker, "shares": pos["shares"],
            "avg_price": round(pos["avg_price"], 1),
            "strategy": pos.get("strategy", "?"),
            "entry_date": pos.get("entry_date"),
        })

    recent_trades = list(reversed(state.get("history", [])))[:20]

    data = {
        "generated_at": load_json(os.path.join(BASE, "state", "portfolio.json"), {}).get("last_run_date"),
        "mode": config["mode"],
        "current_equity": round(current_equity, 0),
        "initial_capital": initial_capital,
        "total_return_pct": round(total_return_pct, 2),
        "radar": compute_radar(state, initial_capital),
        "equity_curve": curve,
        "strategy_weights": {k: weights.get(k) for k in ("trend", "meanrev", "breakout")},
        "positions": positions,
        "recent_trades": recent_trades,
        "universe": universe.get("tickers", []),
        "learn_log": learn_log.get("entries", [])[-6:],
    }

    out_path = os.path.join(BASE, "docs", "data.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[OK] ダッシュボードデータ生成完了: {out_path}")


if __name__ == "__main__":
    main()
