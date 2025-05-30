"""Parses FIX market‑data and maintains an in‑memory limit‑order book."""
from collections import OrderedDict, deque
import numpy as np
import datetime as dt

class LimitOrderBook:
    def __init__(self, depth=50, window=120):
        self.bids = OrderedDict()   # price -> size
        self.asks = OrderedDict()
        self.mid_history = deque(maxlen=window)
        self.depth = depth

    # ----- book maintenance -------------------------------------------------
    def update(self, side:str, price:float, size:float):
        book = self.bids if side == 'B' else self.asks
        if size == 0:
            book.pop(price, None)
        else:
            book[price] = size
        # keep books sorted
        self.bids = OrderedDict(sorted(self.bids.items(), key=lambda x: -x[0]))
        self.asks = OrderedDict(sorted(self.asks.items(), key=lambda x: x[0]))

    def top_levels(self, n):
        bids = list(self.bids.items())[:n]
        asks = list(self.asks.items())[:n]
        return bids, asks

    # ----- derived metrics --------------------------------------------------
    def mid_price(self):
        if not self.bids or not self.asks:
            return None
        return (next(iter(self.bids))[0] + next(iter(self.asks))[0]) / 2

    def channel(self):
        if len(self.mid_history) < self.mid_history.maxlen:
            return None, None
        return max(self.mid_history), min(self.mid_history)

    def obi(self, k=10):
        bids, asks = self.top_levels(k)
        bid_vol = sum(sz for _, sz in bids)
        ask_vol = sum(sz for _, sz in asks)
        if bid_vol + ask_vol == 0:
            return 0.0
        return (bid_vol - ask_vol) / (bid_vol + ask_vol)

    # ----- tick ingestion ----------------------------------------------------
    def on_tick(self):
        mid = self.mid_price()
        if mid:
            self.mid_history.append(mid)
