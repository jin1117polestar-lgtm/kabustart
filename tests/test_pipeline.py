"""オフライン動作検証スクリプト。pytest不要、`python tests/test_pipeline.py` で実行できる。

yfinanceの実通信をモックに差し替え、
  週次スクリーニング → 日次売買(BUY/SELL) → 月次学習 → ダッシュボード生成
の一連が壊れていないことを確認する。CI導入時はこのファイルをそのまま使える。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from unittest import mock

import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)


def make_fake_fetch(trend: float = 0.0):
    def fake_fetch(ticker, period="1y"):
        n = 1250 if period == "5y" else 300
        idx = pd.bdate_range(end=pd.Timestamp.now(), periods=n)
        np.random.seed(hash((ticker, period)) % 100000)
        close = 2000 * np.exp(np.cumsum(np.random.randn(n) * 0.011 + trend))
        vol = np.random.uniform(5e5, 2e6, n)
        return pd.DataFrame(
            {"Open": close, "High": close * 1.01, "Low": close * 0.99,
             "Close": close, "Volume": vol}, index=idx)
    return fake_fetch


def backup_state():
    src = os.path.join(BASE, "state")
    dst = os.path.join(BASE, "state_test_backup")
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return dst


def restore_state(backup_dir):
    src = os.path.join(BASE, "state")
    shutil.rmtree(src)
    shutil.copytree(backup_dir, src)
    shutil.rmtree(backup_dir)


def run():
    backup = backup_state()
    try:
        import core.data as data_mod

        with mock.patch.object(data_mod, "fetch_daily", side_effect=make_fake_fetch()):
            import jobs.run_screen as rs
            rs.main()
            universe = json.load(open(os.path.join(BASE, "state", "universe.json")))
            assert len(universe["tickers"]) > 0, "スクリーニングで銘柄が選定されなかった"
            print("[PASS] weekly_screen")

            import jobs.run_daily as rd
            rd.main()
            pf = json.load(open(os.path.join(BASE, "state", "portfolio.json")))
            assert pf["last_run_date"] is not None, "日次ジョブが実行済みとして記録されなかった"
            pf_before = json.dumps(pf, sort_keys=True)
            rd.main()  # 二重実行
            pf_after = json.load(open(os.path.join(BASE, "state", "portfolio.json")))
            assert json.dumps(pf_after, sort_keys=True) == pf_before, "同日2回実行で状態が変化した(冪等性違反)"
            print("[PASS] daily_trade (冪等性含む)")

            os.environ["FORCE_RUN"] = "1"
            import jobs.run_learn as rl
            rl.main()
            log = json.load(open(os.path.join(BASE, "state", "learn_log.json")))
            assert len(log["entries"]) > 0, "学習ログが生成されなかった"
            print("[PASS] monthly_learn")

            import dashboard.build as db
            db.main()
            dd = json.load(open(os.path.join(BASE, "docs", "data.json")))
            assert "radar" in dd and "equity_curve" in dd, "ダッシュボードデータの必須キーが欠落"
            print("[PASS] dashboard build")

        print("\nALL TESTS PASSED")
    finally:
        restore_state(backup)


if __name__ == "__main__":
    run()
