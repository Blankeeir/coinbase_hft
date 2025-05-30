"""
Portfolio module for Coinbase International Exchange HFT Bot.
Handles position tracking and P&L calculations.
"""
import logging
import time
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime
import pandas as pd
import numpy as np

import config
from fix_client import CoinbaseFIXClient

logger = logging.getLogger("coinbase_hft.portfolio")

class Position:
    """Represents a position in a trading symbol."""
    def __init__(self, symbol: str):
        """
        Initialize a position.
        
        Args:
            symbol: Trading symbol (e.g., 'BTC-USD')
        """
        self.symbol = symbol
        self.quantity = 0.0
        self.average_entry_price = 0.0
        self.realized_pnl = 0.0
        self.unrealized_pnl = 0.0
        self.last_price = 0.0
        self.last_update_time = time.time()
        self.trades: List[Dict[str, Any]] = []
    
    def __repr__(self) -> str:
        return (f"Position(symbol={self.symbol}, quantity={self.quantity}, "
                f"avg_entry={self.average_entry_price}, "
                f"realized_pnl={self.realized_pnl}, "
                f"unrealized_pnl={self.unrealized_pnl})")
    
    def update_from_fill(self, fill: Dict[str, Any]) -> None:
        """
        Update position from a fill.
        
        Args:
            fill: Fill dictionary with keys:
                - side: 'BUY' or 'SELL'
                - quantity: Fill quantity
                - price: Fill price
                - timestamp: Fill timestamp
        """
        try:
            side = fill["side"]
            quantity = fill["quantity"]
            price = fill["price"]
            timestamp = fill.get("timestamp", time.time())
            
            pnl = 0.0
            
            if side == "BUY":
                if self.quantity < 0:
                    cover_quantity = min(abs(self.quantity), quantity)
                    pnl = cover_quantity * (self.average_entry_price - price)
                    self.realized_pnl += pnl
                    
                    self.quantity += quantity
                    if self.quantity > 0:
                        self.average_entry_price = price
                    elif self.quantity == 0:
                        self.average_entry_price = 0.0
                    else:
                        pass
                else:
                    old_value = self.quantity * self.average_entry_price
                    new_value = quantity * price
                    self.quantity += quantity
                    self.average_entry_price = (old_value + new_value) / self.quantity if self.quantity > 0 else 0.0
            
            else:  # SELL
                if self.quantity > 0:
                    close_quantity = min(self.quantity, quantity)
                    pnl = close_quantity * (price - self.average_entry_price)
                    self.realized_pnl += pnl
                    
                    self.quantity -= quantity
                    if self.quantity < 0:
                        self.average_entry_price = price
                    elif self.quantity == 0:
                        self.average_entry_price = 0.0
                    else:
                        pass
                else:
                    old_value = abs(self.quantity) * self.average_entry_price
                    new_value = quantity * price
                    self.quantity -= quantity
                    self.average_entry_price = (old_value + new_value) / abs(self.quantity) if self.quantity < 0 else 0.0
            
            trade = {
                "timestamp": timestamp,
                "side": side,
                "quantity": quantity,
                "price": price,
                "pnl": pnl,
            }
            self.trades.append(trade)
            
            self.last_price = price
            self.last_update_time = time.time()
            
            logger.info(f"Updated position for {self.symbol}: {self}")
            
        except Exception as e:
            logger.error(f"Error updating position from fill: {e}")
    
    def update_from_position_report(self, report: Dict[str, Any]) -> None:
        """
        Update position from a position report.
        
        Args:
            report: Position report dictionary with keys:
                - quantity: Position quantity
                - avg_price: Average entry price
                - realized_pnl: Realized P&L
        """
        try:
            self.quantity = report.get("quantity", self.quantity)
            self.average_entry_price = report.get("avg_price", self.average_entry_price)
            self.realized_pnl = report.get("realized_pnl", self.realized_pnl)
            self.last_update_time = time.time()
            
            logger.info(f"Updated position from report for {self.symbol}: {self}")
            
        except Exception as e:
            logger.error(f"Error updating position from report: {e}")
    
    def update_market_price(self, price: float) -> None:
        """
        Update position with current market price.
        
        Args:
            price: Current market price
        """
        try:
            if price <= 0:
                return
            
            self.last_price = price
            
            if self.quantity != 0 and self.average_entry_price > 0:
                if self.quantity > 0:
                    self.unrealized_pnl = self.quantity * (price - self.average_entry_price)
                else:
                    self.unrealized_pnl = abs(self.quantity) * (self.average_entry_price - price)
            else:
                self.unrealized_pnl = 0.0
            
            self.last_update_time = time.time()
            
        except Exception as e:
            logger.error(f"Error updating market price: {e}")
    
    def get_position_value(self) -> float:
        """
        Get current position value.
        
        Returns:
            float: Position value in quote currency
        """
        return abs(self.quantity) * self.last_price
    
    def get_total_pnl(self) -> float:
        """
        Get total P&L (realized + unrealized).
        
        Returns:
            float: Total P&L
        """
        return self.realized_pnl + self.unrealized_pnl
    
    def get_daily_pnl(self) -> float:
        """
        Get daily P&L.
        
        Returns:
            float: Daily P&L
        """
        try:
            today = datetime.now().date()
            today_trades = [
                trade for trade in self.trades
                if datetime.fromtimestamp(trade["timestamp"]).date() == today
            ]
            
            daily_realized_pnl = sum(trade["pnl"] for trade in today_trades)
            
            daily_pnl = daily_realized_pnl + self.unrealized_pnl
            
            return daily_pnl
            
        except Exception as e:
            logger.error(f"Error calculating daily P&L: {e}")
            return 0.0

class Portfolio:
    """
    Portfolio manager for tracking positions and P&L.
    """
    def __init__(self, fix_client: CoinbaseFIXClient):
        """
        Initialize the portfolio.
        
        Args:
            fix_client: FIX client for position requests
        """
        self.fix_client = fix_client
        self.positions: Dict[str, Position] = {}
        self.last_sync_time = 0.0
        self.sync_interval = 300.0  # seconds (5 minutes)
    
    def get_or_create_position(self, symbol: str) -> Position:
        """
        Get or create position for a symbol.
        
        Args:
            symbol: Trading symbol (e.g., 'BTC-USD')
            
        Returns:
            Position: Position for the symbol
        """
        if symbol not in self.positions:
            self.positions[symbol] = Position(symbol)
        
        return self.positions[symbol]
    
    def update_from_fill(self, fill: Dict[str, Any]) -> None:
        """
        Update portfolio from a fill.
        
        Args:
            fill: Fill dictionary with keys:
                - symbol: Trading symbol
                - side: 'BUY' or 'SELL'
                - quantity: Fill quantity
                - price: Fill price
                - timestamp: Fill timestamp
        """
        try:
            symbol = fill["symbol"]
            position = self.get_or_create_position(symbol)
            position.update_from_fill(fill)
            
        except Exception as e:
            logger.error(f"Error updating portfolio from fill: {e}")
    
    def update_from_execution_report(self, message: Any) -> None:
        """
        Update portfolio from an execution report.
        
        Args:
            message: FIX execution report message
        """
        try:
            exec_type = message.get_field(150, "")
            
            if exec_type not in ["F", "1"]:  # Fill or Partial Fill
                return
            
            symbol = message.get_field(55, "")
            side = message.get_field(54, "")
            last_qty = float(message.get_field(32, "0"))
            last_px = float(message.get_field(31, "0"))
            
            side_map = {"1": "BUY", "2": "SELL"}
            side = side_map.get(side, side)
            
            fill = {
                "symbol": symbol,
                "side": side,
                "quantity": last_qty,
                "price": last_px,
                "timestamp": time.time(),
            }
            
            self.update_from_fill(fill)
            
        except Exception as e:
            logger.error(f"Error updating portfolio from execution report: {e}")
    
    def update_from_position_report(self, message: Any) -> None:
        """
        Update portfolio from a position report.
        
        Args:
            message: FIX position report message
        """
        try:
            symbol = message.get_field(55, "")
            position_qty = float(message.get_field(702, "0"))
            avg_px = float(message.get_field(704, "0"))
            realized_pnl = float(message.get_field(730, "0"))
            
            report = {
                "quantity": position_qty,
                "avg_price": avg_px,
                "realized_pnl": realized_pnl,
            }
            
            position = self.get_or_create_position(symbol)
            position.update_from_position_report(report)
            
            self.last_sync_time = time.time()
            
        except Exception as e:
            logger.error(f"Error updating portfolio from position report: {e}")
    
    def update_market_prices(self, prices: Dict[str, float]) -> None:
        """
        Update portfolio with current market prices.
        
        Args:
            prices: Dictionary of symbol -> price
        """
        try:
            for symbol, price in prices.items():
                if symbol in self.positions:
                    position = self.positions[symbol]
                    position.update_market_price(price)
            
        except Exception as e:
            logger.error(f"Error updating market prices: {e}")
    
    async def sync_positions(self) -> bool:
        """
        Sync positions with exchange.
        
        Returns:
            bool: True if sync request sent successfully
        """
        try:
            current_time = time.time()
            if current_time - self.last_sync_time < self.sync_interval:
                return True
            
            success = await self.fix_client.request_positions()
            if success:
                logger.info("Sent position sync request")
            else:
                logger.error("Failed to send position sync request")
            
            return success
            
        except Exception as e:
            logger.error(f"Error syncing positions: {e}")
            return False
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """
        Get position for a symbol.
        
        Args:
            symbol: Trading symbol (e.g., 'BTC-USD')
            
        Returns:
            Optional[Position]: Position or None if not found
        """
        return self.positions.get(symbol)
    
    def get_position_quantity(self, symbol: str) -> float:
        """
        Get position quantity for a symbol.
        
        Args:
            symbol: Trading symbol (e.g., 'BTC-USD')
            
        Returns:
            float: Position quantity (positive for long, negative for short, 0 for flat)
        """
        position = self.get_position(symbol)
        return position.quantity if position else 0.0
    
    def get_total_value(self) -> float:
        """
        Get total portfolio value.
        
        Returns:
            float: Total portfolio value in quote currency
        """
        return sum(position.get_position_value() for position in self.positions.values())
    
    def get_total_pnl(self) -> float:
        """
        Get total portfolio P&L.
        
        Returns:
            float: Total P&L
        """
        return sum(position.get_total_pnl() for position in self.positions.values())
    
    def get_daily_pnl(self) -> float:
        """
        Get daily portfolio P&L.
        
        Returns:
            float: Daily P&L
        """
        return sum(position.get_daily_pnl() for position in self.positions.values())
    
    def check_risk_limits(self) -> bool:
        """
        Check if portfolio is within risk limits.
        
        Returns:
            bool: True if within limits
        """
        try:
            daily_pnl = self.get_daily_pnl()
            daily_loss_limit = -config.DAILY_LOSS_LIMIT_PCT * self.get_total_value() / 100.0
            
            if daily_pnl < daily_loss_limit:
                logger.warning(f"Daily loss limit exceeded: {daily_pnl} < {daily_loss_limit}")
                return False
            
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking risk limits: {e}")
            return False
    
    def get_portfolio_summary(self) -> Dict[str, Any]:
        """
        Get portfolio summary.
        
        Returns:
            Dict[str, Any]: Portfolio summary
        """
        try:
            summary = {
                "total_value": self.get_total_value(),
                "total_pnl": self.get_total_pnl(),
                "daily_pnl": self.get_daily_pnl(),
                "positions": {
                    symbol: {
                        "quantity": position.quantity,
                        "avg_entry": position.average_entry_price,
                        "last_price": position.last_price,
                        "value": position.get_position_value(),
                        "realized_pnl": position.realized_pnl,
                        "unrealized_pnl": position.unrealized_pnl,
                    }
                    for symbol, position in self.positions.items()
                    if position.quantity != 0
                },
            }
            
            return summary
            
        except Exception as e:
            logger.error(f"Error getting portfolio summary: {e}")
            return {}
