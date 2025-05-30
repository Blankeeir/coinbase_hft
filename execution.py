"""
Execution module for Coinbase International Exchange HFT Bot.
Handles smart order placement and risk management.
"""
import logging
import time
import asyncio
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime

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
    """
    Execution engine for order placement and management.
    Handles smart order routing and risk management.
    """
    def __init__(self, fix_client: CoinbaseFIXClient):
        """
        Initialize the execution engine.
        
        Args:
            fix_client: FIX client for order entry
        """
        self.fix_client = fix_client
        self.orders: Dict[str, Order] = {}  # client_order_id -> Order
        self.active_orders: Dict[str, Order] = {}  # client_order_id -> Order
        self.latency_budget = config.LATENCY_BUDGET  # milliseconds
        self.position_limits = {
            "BTC-USD": config.MAX_POSITION,  # BTC
            "ETH-USD": 1.0,  # ETH
        }
        self.notional_limits = {
            "BTC-USD": config.MAX_NOTIONAL_VALUE,  # USD
            "ETH-USD": 5000.0,  # USD
        }
    
    def on_execution_report(self, message: Any) -> None:
        """
        Process execution report.
        
        Args:
            message: FIX execution report message
        """
        try:
            client_order_id = message.get_field(11, "")
            order_status = message.get_field(39, "")
            exec_type = message.get_field(150, "")
            symbol = message.get_field(55, "")
            side = message.get_field(54, "")
            order_qty = float(message.get_field(38, "0"))
            cum_qty = float(message.get_field(14, "0"))
            leaves_qty = float(message.get_field(151, "0"))
            avg_px = float(message.get_field(6, "0"))
            order_id = message.get_field(37, "")
            
            last_qty = float(message.get_field(32, "0"))
            last_px = float(message.get_field(31, "0"))
            
            status_map = {
                "0": OrderStatus.NEW,
                "1": OrderStatus.PARTIALLY_FILLED,
                "2": OrderStatus.FILLED,
                "4": OrderStatus.CANCELED,
                "8": OrderStatus.REJECTED,
                "C": OrderStatus.EXPIRED,
            }
            order_status = status_map.get(order_status, order_status)
            
            exec_report = {
                "client_order_id": client_order_id,
                "order_status": order_status,
                "exec_type": exec_type,
                "symbol": symbol,
                "side": side,
                "order_qty": order_qty,
                "cum_qty": cum_qty,
                "leaves_qty": leaves_qty,
                "avg_px": avg_px,
                "order_id": order_id,
                "last_qty": last_qty,
                "last_px": last_px,
            }
            
            if client_order_id in self.orders:
                order = self.orders[client_order_id]
                order.update_from_execution_report(exec_report)
                
                if exec_type in ["F", "1"]:  # Fill or Partial Fill
                    logger.info(f"Order {client_order_id} filled: {last_qty} @ {last_px}")
                
                if order.is_complete():
                    if client_order_id in self.active_orders:
                        del self.active_orders[client_order_id]
                    logger.info(f"Order {client_order_id} completed with status {order_status}")
            else:
                logger.warning(f"Received execution report for unknown order: {client_order_id}")
            
        except Exception as e:
            logger.error(f"Error processing execution report: {e}")
    
    async def place_order(self, order: Order) -> str:
        """
        Place an order.
        
        Args:
            order: Order to place
            
        Returns:
            str: Client order ID
        """
        try:
            if not self._check_risk_limits(order):
                logger.warning(f"Order {order.client_order_id} rejected by risk limits")
                return ""
            
            client_order_id = await self.fix_client.place_order(
                symbol=order.symbol,
                side=order.side,
                order_type=order.order_type,
                quantity=order.quantity,
                price=order.price,
                time_in_force=order.time_in_force,
                order_id=order.client_order_id,
            )
            
            if client_order_id:
                self.orders[client_order_id] = order
                self.active_orders[client_order_id] = order
                logger.info(f"Placed order {client_order_id}: {order}")
            else:
                logger.error(f"Failed to place order: {order}")
            
            return client_order_id
            
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return ""
    
    async def cancel_order(self, client_order_id: str) -> bool:
        """
        Cancel an order.
        
        Args:
            client_order_id: Client order ID
            
        Returns:
            bool: True if cancel request sent successfully
        """
        try:
            if client_order_id not in self.orders:
                logger.warning(f"Cannot cancel unknown order: {client_order_id}")
                return False
            
            order = self.orders[client_order_id]
            if not order.is_active():
                logger.warning(f"Cannot cancel inactive order: {client_order_id}")
                return False
            
            cancel_id = await self.fix_client.cancel_order(
                client_order_id=client_order_id,
                symbol=order.symbol,
            )
            
            if cancel_id:
                logger.info(f"Sent cancel request for order {client_order_id}")
                return True
            else:
                logger.error(f"Failed to cancel order {client_order_id}")
                return False
            
        except Exception as e:
            logger.error(f"Error canceling order: {e}")
            return False
    
    async def place_smart_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
    ) -> str:
        """
        Place a smart order with latency-aware execution.
        Starts as a limit order and converts to IOC if not filled within latency budget.
        
        Args:
            symbol: Trading symbol (e.g., 'BTC-USD')
            side: Order side ('BUY' or 'SELL')
            quantity: Order quantity
            price: Order price
            
        Returns:
            str: Client order ID
        """
        try:
            limit_order = Order(
                symbol=symbol,
                side=side,
                order_type="LIMIT",
                quantity=quantity,
                price=price,
                time_in_force="GTC",
            )
            
            client_order_id = await self.place_order(limit_order)
            if not client_order_id:
                return ""
            
            asyncio.create_task(self._monitor_order_latency(client_order_id))
            
            return client_order_id
            
        except Exception as e:
            logger.error(f"Error placing smart order: {e}")
            return ""
    
    async def _monitor_order_latency(self, client_order_id: str) -> None:
        """
        Monitor order latency and convert to IOC if needed.
        
        Args:
            client_order_id: Client order ID
        """
        try:
            await asyncio.sleep(self.latency_budget / 1000)  # Convert to seconds
            
            if client_order_id not in self.active_orders:
                return
            
            order = self.active_orders[client_order_id]
            if not order.is_active():
                return
            
            time_in_market = order.time_in_market()
            if time_in_market >= self.latency_budget:
                logger.info(f"Order {client_order_id} exceeded latency budget ({time_in_market:.2f} ms > {self.latency_budget} ms)")
                
                await self.cancel_order(client_order_id)
                
                ioc_order = Order(
                    symbol=order.symbol,
                    side=order.side,
                    order_type="LIMIT",
                    quantity=order.quantity - order.filled_quantity,
                    price=order.price,
                    time_in_force="IOC",
                )
                
                await self.place_order(ioc_order)
                
        except Exception as e:
            logger.error(f"Error monitoring order latency: {e}")
    
    def _check_risk_limits(self, order: Order) -> bool:
        """
        Check if order passes risk limits.
        
        Args:
            order: Order to check
            
        Returns:
            bool: True if order passes risk limits
        """
        try:
            symbol = order.symbol
            if symbol in self.position_limits:
                position_limit = self.position_limits[symbol]
                
                current_position = 0.0
                
                new_position = current_position
                if order.side == "BUY":
                    new_position += order.quantity
                else:  # SELL
                    new_position -= order.quantity
                
                if abs(new_position) > position_limit:
                    logger.warning(f"Order would exceed position limit: {abs(new_position)} > {position_limit}")
                    return False
            
            if symbol in self.notional_limits:
                notional_limit = self.notional_limits[symbol]
                
                notional_value = order.quantity * (order.price or 0.0)
                
                if notional_value > notional_limit:
                    logger.warning(f"Order would exceed notional limit: {notional_value} > {notional_limit}")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking risk limits: {e}")
            return False
    
    def get_active_orders(self) -> List[Order]:
        """
        Get list of active orders.
        
        Returns:
            List[Order]: List of active orders
        """
        return list(self.active_orders.values())
    
    def get_order(self, client_order_id: str) -> Optional[Order]:
        """
        Get order by client order ID.
        
        Args:
            client_order_id: Client order ID
            
        Returns:
            Optional[Order]: Order or None if not found
        """
        return self.orders.get(client_order_id)
