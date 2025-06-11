"""
Execution module for Coinbase International Exchange HFT Bot.
Handles smart order placement and risk management.
"""
import logging
import time
import uuid
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime as dt
import quickfix as fix

import config
from quickfix_client import CoinbaseQuickFIXClient

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
        """
        Initialize the execution engine.
        
        Args:
            fix: FIX client for order execution
            book: Order book for price discovery
            latency_ms: Latency budget in milliseconds
        """
        self.fix = fix
        self.book = book
        self.latency_ms = latency_ms
        self.active_orders = {}
        self.orders = {}
        logger.info(f"ExecutionEngine initialized with latency budget: {latency_ms}ms")

    def _gen_cloid(self):
        """Generate a unique client order ID."""
        return dt.utcnow().strftime('%Y%m%d%H%M%S') + uuid.uuid4().hex[:8]

    def send_limit(self, side, qty):
        """
        Send a limit order.
        
        Args:
            side: Order side ('BUY' or 'SELL')
            qty: Order quantity
        """
        price = self.book.bids.keys().__iter__().__next__() if side=='BUY' else self.book.asks.keys().__iter__().__next__()
        cloid = self._gen_cloid()
        self.fix.place_limit_order(cloid, side, qty, price)
        self.active_orders[cloid] = {'sent': time.time(), 'side': side, 'qty': qty, 'price': price}

    def monitor(self):
        """Monitor active orders and convert to IOC if latency budget exceeded."""
        now = time.time()
        for cloid, meta in list(self.active_orders.items()):
            if (now - meta['sent']) * 1000 > self.latency_ms:
                self.fix.cancel_order(cloid)
                self.fix.place_market_order(meta['side'], meta['qty'])
                self.active_orders.pop(cloid, None)
                
    def place_smart_order(self, symbol, side, quantity, price=None):
        """
        Place a smart order with latency-aware execution.
        
        Args:
            symbol: Trading symbol
            side: Order side ('BUY' or 'SELL')
            quantity: Order quantity
            price: Order price (optional for market orders)
        """
        order_id = self._gen_cloid()
        
        order = Order(
            symbol=symbol,
            side=side,
            order_type="LIMIT" if price else "MARKET",
            quantity=quantity,
            price=price,
            client_order_id=order_id
        )
        
        self.orders[order_id] = order
        
        if price:
            logger.info(f"Placing limit order: {order}")
            self.fix.place_limit_order(order_id, side, quantity, price)
            self.active_orders[order_id] = {
                'sent': time.time(),
                'side': side,
                'qty': quantity,
                'price': price
            }
        else:
            logger.info(f"Placing market order: {order}")
            self.fix.place_market_order(order_id, side, quantity)
        
        return order_id
    
    def on_execution_report(self, message):
        """
        Process execution report message.
        
        Args:
            message: FIX execution report message
        """
        try:
            clord_id_field = fix.ClOrdID()
            if message.isSetField(clord_id_field.getField()):
                message.getField(clord_id_field)
                client_order_id = clord_id_field.getValue()
            else:
                return
            
            exec_type_field = fix.ExecType()
            if message.isSetField(exec_type_field.getField()):
                message.getField(exec_type_field)
                exec_type = exec_type_field.getValue()
            else:
                exec_type = ""
            
            order_status_field = fix.OrdStatus()
            if message.isSetField(order_status_field.getField()):
                message.getField(order_status_field)
                order_status = order_status_field.getValue()
            else:
                order_status = ""
            
            if client_order_id in self.active_orders and order_status in ["2", "4"]:  # Filled or Canceled
                self.active_orders.pop(client_order_id, None)
            
            if client_order_id in self.orders:
                order = self.orders[client_order_id]
                
                cum_qty = 0.0
                cum_qty_field = fix.CumQty()
                if message.isSetField(cum_qty_field.getField()):
                    message.getField(cum_qty_field)
                    cum_qty = float(cum_qty_field.getValue())
                
                avg_px = 0.0
                avg_px_field = fix.AvgPx()
                if message.isSetField(avg_px_field.getField()):
                    message.getField(avg_px_field)
                    avg_px = float(avg_px_field.getValue())
                
                last_qty = 0.0
                last_qty_field = fix.LastQty()
                if message.isSetField(last_qty_field.getField()):
                    message.getField(last_qty_field)
                    last_qty = float(last_qty_field.getValue())
                
                last_px = 0.0
                last_px_field = fix.LastPx()
                if message.isSetField(last_px_field.getField()):
                    message.getField(last_px_field)
                    last_px = float(last_px_field.getValue())
                
                order_id = ""
                order_id_field = fix.OrderID()
                if message.isSetField(order_id_field.getField()):
                    message.getField(order_id_field)
                    order_id = order_id_field.getValue()
                
                exec_report = {
                    "order_status": order_status,
                    "exec_type": exec_type,
                    "cum_qty": cum_qty,
                    "avg_px": avg_px,
                    "last_qty": last_qty,
                    "last_px": last_px,
                    "order_id": order_id
                }
                
                order.update_from_execution_report(exec_report)
                
                logger.info(f"Order update: {order}")
        
        except Exception as e:
            logger.error(f"Error processing execution report: {e}")
