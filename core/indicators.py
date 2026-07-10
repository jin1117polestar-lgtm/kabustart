"""テクニカル指標計算。全戦略・スクリーナー・バックテストから共用する。"""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(close: pd.Series, window: int) -> pd.Series:
    return close.rolling(window).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss
    return 100 - 100 / (1 + rs)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range。High/Low/Closeが必要。"""
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def momentum(close: pd.Series, lookback: int = 252, skip: int = 21) -> float | None:
    """12-1ヶ月モメンタム: 直近skip日を除いたlookback日間のリターン"""
    if len(close) < lookback:
        return None
    start = close.iloc[-lookback]
    end = close.iloc[-skip] if skip > 0 else close.iloc[-1]
    if start <= 0:
        return None
    return float(end / start - 1)


def rolling_high(high: pd.Series, window: int) -> pd.Series:
    return high.rolling(window).max()


def add_all(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """戦略に必要な指標一式をまとめて付与する"""
    df = df.copy()
    close = df["Close"]
    df["sma_s"] = sma(close, params.get("sma_short", 5))
    df["sma_l"] = sma(close, params.get("sma_long", 25))
    df["rsi"] = rsi(close, params.get("rsi_period", 14))
    df["atr"] = atr(df, params.get("atr_period", 14))
    df["hh"] = rolling_high(df["High"], params.get("breakout_window", 20))
    return df
