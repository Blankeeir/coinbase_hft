"""Order management and latency‑sensitive execution logic."""
import time, uuid
import datetime as dt
from collections import deque

class ExecutionEngine:
    def __init__(self, fix, book, latency_ms=200):
        self.fix = fix
        self.book = book
        self.latency_ms = latency_ms
        self.active_orders = {}

    def _gen_cloid(self):
        return dt.datetime.utcnow().strftime('%Y%m%d%H%M%S') + uuid.uuid4().hex[:8]

    def send_limit(self, side, qty):
        price = self.book.bids.keys().__iter__().__next__() if side=='BUY' else self.book.asks.keys().__iter__().__next__()
        cloid = self._gen_cloid()
        self.fix.place_limit_order(cloid, side, qty, price)
        self.active_orders[cloid] = {'sent': time.time(), 'side': side, 'qty': qty, 'price': price}

    def monitor(self):
        now = time.time()
        for cloid, meta in list(self.active_orders.items()):
            if now - meta['sent']*1000 > self.latency_ms:
                # convert to IOC market order
                self.fix.cancel_order(cloid)
                self.fix.place_market_order(meta['side'], meta['qty'])
                self.active_orders.pop(cloid, None)
