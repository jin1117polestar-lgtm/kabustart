"""リスク管理層。日次損失上限・ドローダウン上限・KILL_SWITCHを扱う。

設計方針: ここでの判定はすべて「新規の買いを止める」か「全停止する」かの
どちらかで、既存ポジションの決済(SELL)は常に許可する
（リスク管理が理由でポジションを塩漬けにしない）。
"""
from __future__ import annotations

import os


def kill_switch_path(base_dir: str) -> str:
    return os.path.join(base_dir, "state", "KILL_SWITCH")


def is_killed(base_dir: str) -> bool:
    return os.path.exists(kill_switch_path(base_dir))


def trigger_kill_switch(base_dir: str, reason: str) -> None:
    path = kill_switch_path(base_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(reason + "\n")


def check_daily_loss_limit(equity_today: float, equity_yesterday: float,
                           limit_pct: float = 2.0) -> bool:
    """当日の損失が上限を超えたら True (新規買い停止)"""
    if equity_yesterday <= 0:
        return False
    loss_pct = (equity_yesterday - equity_today) / equity_yesterday * 100
    return loss_pct > limit_pct


def check_drawdown_limit(equity_curve: list[dict], limit_pct: float = 15.0) -> bool:
    """通算ドローダウンが上限を超えたら True (全停止すべき)"""
    if not equity_curve:
        return False
    values = [p["equity"] for p in equity_curve]
    peak = values[0]
    for v in values:
        peak = max(peak, v)
        dd = (peak - v) / peak * 100 if peak > 0 else 0
        if dd > limit_pct:
            return True
    return False


def max_position_value(total_equity: float, max_pct: float = 25.0) -> float:
    """1銘柄あたりの最大投資額"""
    return total_equity * max_pct / 100
