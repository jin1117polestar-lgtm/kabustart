"""日次仮想売買ボット

GitHub Actions から平日の大引け後に実行される想定。
1. yfinance で日足を取得
2. strategy.py のルールでシグナル判定
3. 仮想ポートフォリオ(portfolio.json)に対して仮想約定
4. 結果を Discord に通知し、ログを logs/ に残す

※これは仮想売買です。実際の発注は一切行いません。
"""
import json
import os
import sys
from datetime import datetime, timezone, timedelta

import pandas as pd
import requests
import yfinance as yf

import strategy

JST = timezone(timedelta(hours=9))
BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE, "config.json")
PORTFOLIO_PATH = os.path.join(BASE, "portfolio.json")
LOG_DIR = os.path.join(BASE, "logs")


def load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_daily(ticker: str) -> pd.DataFrame | None:
    """直近6ヶ月の日足を取得。失敗時は None"""
    try:
        df = yf.download(ticker, period="6mo", interval="1d",
                         progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df.empty:
            return None
        return df
    except Exception as e:
        print(f"[WARN] {ticker} の取得に失敗: {e}", file=sys.stderr)
        return None


def notify_discord(message: str):
    url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not url:
        print("[INFO] DISCORD_WEBHOOK_URL 未設定のため通知をスキップ")
        return
    try:
        requests.post(url, json={"content": message}, timeout=15)
    except Exception as e:
        print(f"[WARN] Discord通知に失敗: {e}", file=sys.stderr)


def main():
    config = load_json(CONFIG_PATH, None)
    if config is None:
        print("config.json が見つかりません", file=sys.stderr)
        sys.exit(1)

    params = config["strategy"]
    portfolio = load_json(PORTFOLIO_PATH, {
        "cash": config["initial_capital"],
        "positions": {},
        "history": [],
    })

    today = datetime.now(JST).strftime("%Y-%m-%d")
    lines = [f"📊 **仮想売買レポート {today}**"]
    trades = []
    stale = []
    equity_positions = 0.0

    per_slot = config["initial_capital"] / max(config["max_positions"], 1)

    for ticker in config["tickers"]:
        df = fetch_daily(ticker)
        if df is None or len(df) < params["sma_long"] + 2:
            stale.append(ticker)
            continue

        # データ鮮度チェック（3営業日以上古ければ休場/未更新とみなす）
        last_date = df.index[-1].date()
        age = (datetime.now(JST).date() - last_date).days
        if age > 4:
            stale.append(f"{ticker}(最終:{last_date})")
            continue

        df = strategy.add_indicators(df, params)
        sig = strategy.latest_signal(df, params)
        price = float(df["Close"].iloc[-1])
        pos = portfolio["positions"].get(ticker)

        if pos:
            equity_positions += pos["shares"] * price

        if sig == "BUY" and pos is None:
            if len(portfolio["positions"]) >= config["max_positions"]:
                lines.append(f"⏸ {ticker}: BUYシグナルだが保有上限のため見送り")
            else:
                budget = min(per_slot, portfolio["cash"])
                shares = int(budget // price)
                if shares >= 1:
                    cost = shares * price
                    portfolio["cash"] -= cost
                    portfolio["positions"][ticker] = {
                        "shares": shares, "avg_price": price, "date": today,
                    }
                    equity_positions += cost
                    trades.append({"date": today, "ticker": ticker,
                                   "side": "BUY", "shares": shares,
                                   "price": price})
                    lines.append(f"🟢 **買い** {ticker} × {shares}株 @ {price:,.0f}円")
                else:
                    lines.append(f"⏸ {ticker}: 資金不足でBUY見送り")

        elif sig == "SELL" and pos is not None:
            proceeds = pos["shares"] * price
            pnl = (price - pos["avg_price"]) * pos["shares"]
            portfolio["cash"] += proceeds
            equity_positions -= proceeds
            del portfolio["positions"][ticker]
            trades.append({"date": today, "ticker": ticker, "side": "SELL",
                           "shares": pos["shares"], "price": price,
                           "pnl": round(pnl)})
            emoji = "🔴" if pnl < 0 else "🔵"
            lines.append(
                f"{emoji} **売り** {ticker} × {pos['shares']}株 @ {price:,.0f}円 "
                f"(損益 {pnl:+,.0f}円)")

    portfolio["history"].extend(trades)

    equity = portfolio["cash"] + equity_positions
    ret = (equity / config["initial_capital"] - 1) * 100
    if not trades:
        lines.append("本日のシグナルはありません（様子見）")
    lines.append("")
    lines.append(f"💰 評価額: {equity:,.0f}円 (現金 {portfolio['cash']:,.0f}円) "
                 f"/ 通算 {ret:+.2f}%")
    if portfolio["positions"]:
        held = ", ".join(f"{t}×{p['shares']}"
                         for t, p in portfolio["positions"].items())
        lines.append(f"📦 保有: {held}")
    if stale:
        lines.append(f"⚠️ データ未更新/休場の可能性: {', '.join(stale)}")

    message = "\n".join(lines)
    print(message)

    save_json(PORTFOLIO_PATH, portfolio)
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(os.path.join(LOG_DIR, f"{today}.md"), "w", encoding="utf-8") as f:
        f.write(message + "\n")

    notify_discord(message)


if __name__ == "__main__":
    main()
