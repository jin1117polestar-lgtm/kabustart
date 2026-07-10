"""学習型配分エンジン。

設計書3章の通り、深層強化学習ではなく2段構成で「学習する配分」を実現する:
  1. 戦略間配分: EXP3型の指数加重バンディット（月次で更新）
  2. 銘柄間配分: ATRベースのリスクパリティ近似（毎回計算、学習不要）

過学習ガードは jobs/run_learn.py 側のウォークフォワード検証で行う。
このモジュール自体は「与えられた実績から次の重みを計算する」ことだけに責任を持つ。
"""
from __future__ import annotations

import math

MIN_WEIGHT = 0.10
MAX_WEIGHT = 0.60


def update_strategy_weights(current_weights: dict[str, float],
                            daily_returns: dict[str, list[float]],
                            eta: float = 0.15, dd_lambda: float = 0.5) -> dict[str, float]:
    """各戦略の直近リターン系列から新しい配分ウェイトを計算する(EXP3型)。

    daily_returns: {"trend": [0.001, -0.002, ...], "meanrev": [...], "breakout": [...]}
    """
    strategies = list(current_weights.keys())
    scores = {}
    for s in strategies:
        rets = daily_returns.get(s, [])
        if not rets:
            scores[s] = 0.0
            continue
        cum_return = sum(rets)
        # 簡易ドローダウン: 累積曲線のピークからの最大下落
        curve, acc = [], 0.0
        for r in rets:
            acc += r
            curve.append(acc)
        peak = curve[0]
        max_dd = 0.0
        for v in curve:
            peak = max(peak, v)
            max_dd = max(max_dd, peak - v)
        scores[s] = cum_return - dd_lambda * max_dd

    # softmax
    max_score = max(scores.values()) if scores else 0.0
    exp_scores = {s: math.exp(eta * (v - max_score)) for s, v in scores.items()}
    total = sum(exp_scores.values()) or 1.0
    raw_weights = {s: v / total for s, v in exp_scores.items()}

    # 上下限クリップ後に再正規化
    clipped = {s: min(max(w, MIN_WEIGHT), MAX_WEIGHT) for s, w in raw_weights.items()}
    total_clipped = sum(clipped.values()) or 1.0
    return {s: round(w / total_clipped, 4) for s, w in clipped.items()}


def risk_parity_sizes(tickers: list[str], atr_pct: dict[str, float],
                      total_budget: float) -> dict[str, float]:
    """ATR(価格に対する%)の逆比例で各銘柄への配分額を決める。

    atr_pct: {ticker: atr/price} のようなボラティリティ指標(値が大きいほどハイリスク)
    ボラティリティが低い銘柄ほど大きな配分を受け取る。
    """
    inv_vol = {}
    for t in tickers:
        v = atr_pct.get(t)
        inv_vol[t] = 1.0 / v if v and v > 0 else 0.0

    total_inv = sum(inv_vol.values())
    if total_inv <= 0:
        # フォールバック: 均等配分
        n = max(len(tickers), 1)
        return {t: total_budget / n for t in tickers}

    return {t: total_budget * (iv / total_inv) for t, iv in inv_vol.items()}
