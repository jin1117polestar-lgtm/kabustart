"""月次ジョブ: ウォークフォワード検証によるパラメータ最適化 + 戦略間配分の更新。

過学習ガード(設計書3.3): 学習期間で最良だったパラメータ候補を、
学習期間とは別の検証期間で評価し、現行パラメータを上回った場合のみ採用する。
毎月第1土曜に実行される想定。
"""
from __future__ import annotations

import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from core import data, backtest_engine as be, allocator, risk  # noqa: E402

VALIDATION_DAYS = 126   # 約6ヶ月
CAPITAL_PER_TEST = 200_000

# 各戦略の探索候補(小さめのグリッド。Actions実行時間を抑えるため)
GRIDS = {
    "trend": [
        {"sma_short": 5, "sma_long": 25, "rsi_period": 14, "rsi_buy_max": 70, "rsi_sell_min": 75},
        {"sma_short": 8, "sma_long": 30, "rsi_period": 14, "rsi_buy_max": 70, "rsi_sell_min": 75},
        {"sma_short": 5, "sma_long": 40, "rsi_period": 14, "rsi_buy_max": 65, "rsi_sell_min": 80},
        {"sma_short": 10, "sma_long": 50, "rsi_period": 14, "rsi_buy_max": 70, "rsi_sell_min": 75},
    ],
    "meanrev": [
        {"rsi_period": 14, "meanrev_buy_rsi": 30, "meanrev_sell_rsi": 55, "meanrev_max_hold_days": 10},
        {"rsi_period": 14, "meanrev_buy_rsi": 25, "meanrev_sell_rsi": 50, "meanrev_max_hold_days": 7},
        {"rsi_period": 14, "meanrev_buy_rsi": 35, "meanrev_sell_rsi": 60, "meanrev_max_hold_days": 14},
    ],
    "breakout": [
        {"breakout_window": 20, "atr_period": 14, "breakout_atr_mult": 2.5},
        {"breakout_window": 15, "atr_period": 14, "breakout_atr_mult": 2.0},
        {"breakout_window": 30, "atr_period": 14, "breakout_atr_mult": 3.0},
    ],
}


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def eval_params(dfs: list, strategy: str, params: dict, split_idx_list: list[int]) -> tuple[float, float]:
    """複数銘柄のtrain/valid平均スコアを返す (train_score, valid_score)"""
    train_scores, valid_scores = [], []
    for df, split_idx in zip(dfs, split_idx_list):
        train_df = df.iloc[:split_idx]
        valid_df = df.iloc[split_idx:]
        if len(train_df) < 60 or len(valid_df) < 30:
            continue
        r_train = be.run_single(train_df, strategy, params, CAPITAL_PER_TEST)
        r_valid = be.run_single(valid_df, strategy, params, CAPITAL_PER_TEST)
        if r_train:
            train_scores.append(be.score(r_train))
        if r_valid:
            valid_scores.append(be.score(r_valid))
    tr = sum(train_scores) / len(train_scores) if train_scores else -1e9
    va = sum(valid_scores) / len(valid_scores) if valid_scores else -1e9
    return tr, va


def main():
    if risk.is_killed(BASE):
        print("[INFO] KILL_SWITCH が存在するため何もせず終了します")
        return

    # cronは「毎週土曜」で起動するため、月内で最初の土曜(1日〜7日)以外はここで終了する
    import datetime
    force = os.environ.get("FORCE_RUN") == "1"
    if not force and datetime.date.fromisoformat(data.today_jst()).day > 7:
        print("[INFO] 今月最初の土曜ではないため月次学習をスキップします")
        return

    universe = load_json(os.path.join(BASE, "state", "universe.json"))["tickers"]
    params_path = os.path.join(BASE, "state", "params.json")
    params_all = load_json(params_path)
    weights_path = os.path.join(BASE, "state", "weights.json")
    weights = load_json(weights_path)
    learn_log_path = os.path.join(BASE, "state", "learn_log.json")
    learn_log = load_json(learn_log_path) if os.path.exists(learn_log_path) else {"entries": []}

    print(f"[INFO] {len(universe)}銘柄でウォークフォワード検証を開始")
    dfs, split_idxs = [], []
    for t in universe:
        df = data.fetch_daily(t, period="5y")
        if df is None or len(df) < VALIDATION_DAYS + 60:
            continue
        dfs.append(df)
        split_idxs.append(len(df) - VALIDATION_DAYS)

    today = data.today_jst()
    entry = {"date": today, "changes": []}

    for strategy, grid in GRIDS.items():
        current_params = params_all[strategy]
        _, current_valid = eval_params(dfs, strategy, current_params, split_idxs)

        best_params, best_valid = current_params, current_valid
        for candidate in grid:
            _, valid_score = eval_params(dfs, strategy, candidate, split_idxs)
            if valid_score > best_valid:
                best_params, best_valid = candidate, valid_score

        if best_params != current_params and best_valid > current_valid:
            params_all[strategy] = best_params
            entry["changes"].append({
                "strategy": strategy, "action": "adopted",
                "old_valid_score": round(current_valid, 2),
                "new_valid_score": round(best_valid, 2),
                "new_params": best_params,
            })
            print(f"[UPDATE] {strategy}: 検証スコア {current_valid:.2f} → {best_valid:.2f} で新パラメータ採用")
        else:
            entry["changes"].append({
                "strategy": strategy, "action": "kept",
                "valid_score": round(current_valid, 2),
            })
            print(f"[KEEP] {strategy}: 現行パラメータを維持(検証スコア {current_valid:.2f})")

    # 戦略間配分の更新(日次ログの蓄積から)
    daily_returns = weights.get("daily_returns_log", {})
    current_weights = {k: weights[k] for k in ("trend", "meanrev", "breakout")}
    new_weights = allocator.update_strategy_weights(current_weights, daily_returns)
    for k, v in new_weights.items():
        weights[k] = v
    weights["updated"] = today
    entry["new_weights"] = new_weights

    learn_log["entries"] = (learn_log.get("entries", []) + [entry])[-24:]  # 直近24回分のみ保持

    save_json(params_path, params_all)
    save_json(weights_path, weights)
    save_json(learn_log_path, learn_log)
    print(f"[OK] 月次学習完了。新配分: {new_weights}")


if __name__ == "__main__":
    main()
