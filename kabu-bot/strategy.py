"""売買判断ロジック（移動平均クロス + RSIフィルター）

bot.py と backtest.py の両方から使う共通モジュール。
ルールを変えたいときはこのファイルと config.json を編集する。
"""
import pandas as pd


def add_indicators(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """終値からSMA短期/長期とRSIを計算して列を追加する"""
    df = df.copy()
    close = df["Close"]
    df["sma_s"] = close.rolling(params["sma_short"]).mean()
    df["sma_l"] = close.rolling(params["sma_long"]).mean()

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(params["rsi_period"]).mean()
    loss = (-delta.clip(upper=0)).rolling(params["rsi_period"]).mean()
    rs = gain / loss
    df["rsi"] = 100 - 100 / (1 + rs)
    return df


def make_signal(prev: pd.Series, cur: pd.Series, params: dict) -> str | None:
    """直近2本のバーからシグナルを判定する

    BUY : ゴールデンクロス かつ RSIが買われすぎでない
    SELL: デッドクロス または RSIが買われすぎ
    None: 何もしない
    """
    if pd.isna(prev["sma_l"]) or pd.isna(cur["sma_l"]) or pd.isna(cur["rsi"]):
        return None

    golden = prev["sma_s"] <= prev["sma_l"] and cur["sma_s"] > cur["sma_l"]
    dead = prev["sma_s"] >= prev["sma_l"] and cur["sma_s"] < cur["sma_l"]

    if golden and cur["rsi"] < params["rsi_buy_max"]:
        return "BUY"
    if dead or cur["rsi"] > params["rsi_sell_min"]:
        return "SELL"
    return None


def latest_signal(df: pd.DataFrame, params: dict) -> str | None:
    """指標計算済みDataFrameの最新バーに対するシグナル"""
    if len(df) < 2:
        return None
    return make_signal(df.iloc[-2], df.iloc[-1], params)
