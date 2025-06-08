"""
Execution module for Coinbase International Exchange HFT Bot.
Handles smart order placement and risk management.
"""
Execution module for Coinbase International Exchange HFT Bot.
Handles smart order placement and risk management.
"""
import logging
import time
import asyncio
import uuid
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime as dt

import config
from fix_client import CoinbaseFIXClient

logger = logging.getLogger("coinbase_hft.execution")

class OrderStatus:
    """Order status constants."""
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"

class Order:
    """Represents an order."""
    def __init__(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float] = None,
        client_order_id: Optional[str] = None,
        time_in_force: str = "GTC",
    ):
        """
        Initialize an order.
        
        Args:
            symbol: Trading symbol (e.g., 'BTC-USD')
            side: Order side ('BUY' or 'SELL')
            order_type: Order type ('LIMIT', 'MARKET', 'STOP', 'STOP_LIMIT')
            quantity: Order quantity
            price: Order price (required for LIMIT and STOP_LIMIT orders)
            client_order_id: Client order ID (generated if not provided)
            time_in_force: Time in force ('GTC', 'IOC', 'FOK', 'GTD')
        """
        self.symbol = symbol
        self.side = side
        self.order_type = order_type
        self.quantity = quantity
        self.price = price
        self.client_order_id = client_order_id or f"HFT-{int(time.time() * 1000)}"
        self.time_in_force = time_in_force
        
        self.status = OrderStatus.NEW
        self.filled_quantity = 0.0
        self.average_fill_price = 0.0
        self.creation_time = time.time()
        self.last_update_time = time.time()
        self.exchange_order_id = None
        self.fills = []
    
    def __repr__(self) -> str:
        return (f"Order(symbol={self.symbol}, side={self.side}, "
                f"order_type={self.order_type}, quantity={self.quantity}, "
                f"price={self.price}, status={self.status}, "
                f"filled_quantity={self.filled_quantity})")
    
    def update_from_execution_report(self, exec_report: Dict[str, Any]) -> None:
        """
        Update order from execution report.
        
        Args:
            exec_report: Execution report dictionary
        """
        self.status = exec_report.get("order_status", self.status)
        self.filled_quantity = exec_report.get("cum_qty", self.filled_quantity)
        self.average_fill_price = exec_report.get("avg_px", self.average_fill_price)
        self.last_update_time = time.time()
        self.exchange_order_id = exec_report.get("order_id", self.exchange_order_id)
        
        if exec_report.get("exec_type") in ["F", "1"]:  # Fill or Partial Fill
            fill = {
                "timestamp": time.time(),
                "price": exec_report.get("last_px", 0.0),
                "quantity": exec_report.get("last_qty", 0.0),
            }
            self.fills.append(fill)
    
    def is_active(self) -> bool:
        """
        Check if order is active.
        
        Returns:
            bool: True if order is active
        """
        return self.status in [OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED]
    
    def is_complete(self) -> bool:
        """
        Check if order is complete.
        
        Returns:
            bool: True if order is complete
        """
        return self.status in [OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED, OrderStatus.EXPIRED]
    
    def time_in_market(self) -> float:
        """
        Get time in market in milliseconds.
        
        Returns:
            float: Time in market in milliseconds
        """
        return (time.time() - self.creation_time) * 1000  # Convert to milliseconds

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
            # `meta['sent']` is stored in seconds. Multiply the elapsed time by
            # 1000 before comparing to the latency budget.
            if (now - meta['sent']) * 1000 > self.latency_ms:
                # convert to IOC market order
                self.fix.cancel_order(cloid)
                self.fix.place_market_order(meta['side'], meta['qty'])
                self.active_orders.pop(cloid, None)
