"""Broker抽象化層。

V3では VirtualBroker のみ実装する。TachibanaBroker は将来の実弾/デモ移行時に
このインターフェースを満たす形で実装する（V3のスコープ外、スタブのみ）。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Trade:
    ticker: str
    side: str      # "BUY" or "SELL"
    shares: int
    price: float


class Broker(ABC):
    @abstractmethod
    def get_cash(self) -> float: ...

    @abstractmethod
    def get_positions(self) -> dict: ...

    @abstractmethod
    def buy(self, ticker: str, shares: int, price: float) -> Trade: ...

    @abstractmethod
    def sell(self, ticker: str, shares: int, price: float) -> Trade: ...


class VirtualBroker(Broker):
    """state(dict)を直接書き換える仮想ブローカー。手数料・税は考慮しない参考値。"""

    def __init__(self, state: dict):
        self.state = state

    def get_cash(self) -> float:
        return self.state["cash"]

    def get_positions(self) -> dict:
        return self.state["positions"]

    def buy(self, ticker: str, shares: int, price: float) -> Trade:
        cost = shares * price
        if cost > self.state["cash"]:
            raise ValueError(f"資金不足: 必要 {cost}, 現金 {self.state['cash']}")
        self.state["cash"] -= cost
        return Trade(ticker, "BUY", shares, price)

    def sell(self, ticker: str, shares: int, price: float) -> Trade:
        self.state["cash"] += shares * price
        return Trade(ticker, "SELL", shares, price)


class TachibanaBroker(Broker):
    """立花証券e支店API接続用スタブ。V3では未実装。

    実弾/デモ移行時にここへ実装する。config.json の "mode" を
    "demo" または "live" に切り替えた際、jobs/run_daily.py が
    VirtualBroker の代わりにこのクラスを使うよう分岐する想定。
    """

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "TachibanaBrokerはV3では未実装です。実弾移行フェーズで実装してください。")

    def get_cash(self) -> float:
        raise NotImplementedError

    def get_positions(self) -> dict:
        raise NotImplementedError

    def buy(self, ticker: str, shares: int, price: float) -> Trade:
        raise NotImplementedError

    def sell(self, ticker: str, shares: int, price: float) -> Trade:
        raise NotImplementedError


def make_broker(mode: str, state: dict) -> Broker:
    if mode == "paper":
        return VirtualBroker(state)
    if mode in ("demo", "live"):
        return TachibanaBroker()
    raise ValueError(f"未知のmode: {mode}")
