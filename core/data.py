"""データ取得層。yfinanceのラッパーと鮮度チェックのみを担当する。

このモジュール以外は yfinance を直接呼ばない
（将来データソースを差し替える時にここだけ直せば済むようにするため）。
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone, timedelta

import pandas as pd
import yfinance as yf

JST = timezone(timedelta(hours=9))


def fetch_daily(ticker: str, period: str = "1y") -> pd.DataFrame | None:
    """日足OHLCVを取得する。失敗時やデータ不足時は None を返す。"""
    try:
        df = yf.download(ticker, period=period, interval="1d",
                         progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df.empty:
            return None
        return df
    except Exception as e:
        print(f"[WARN] {ticker} 取得失敗: {e}", file=sys.stderr)
        return None


def is_stale(df: pd.DataFrame, max_age_days: int = 4) -> bool:
    """最終データが古すぎる（休場や取得失敗の疑い）かどうか"""
    if df is None or df.empty:
        return True
    last_date = df.index[-1].date()
    age = (datetime.now(JST).date() - last_date).days
    return age > max_age_days


def today_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d")
