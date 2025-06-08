"""
Data Handler for Coinbase International Exchange HFT Bot.
Handles order book reconstruction and feature calculation.
"""

import logging
import time
from typing import Dict, List, Tuple, Optional, Any, Union
from collections import OrderedDict, deque
import numpy as np
import pandas as pd
from asyncfix.message import FIXMessage

import config

logger = logging.getLogger("coinbase_hft.data_handler")


class OrderBookLevel:
    """Represents a single level in the order book."""

    def __init__(self, price: float, size: float, side: str):
        self.price = price
        self.size = size
        self.side = side  # 'bid' or 'ask'

    def __repr__(self) -> str:
        return f"OrderBookLevel(price={self.price}, size={self.size}, side={self.side})"


class OrderBook:
    """
    Order book for a trading symbol.
    Maintains bids and asks sorted by price.
    """

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.bids: Dict[float, float] = {}  # price -> size
        self.asks: Dict[float, float] = {}  # price -> size
        self.last_update_time = 0.0
        self.last_trade_price = 0.0
        self.last_trade_size = 0.0
        self.last_trade_side = ""  # 'buy' or 'sell'

        self.price_history: List[Tuple[float, float]] = []  # (timestamp, price)
        self.trade_history: List[Tuple[float, float, str]] = (
            []
        )  # (timestamp, size, side)

        self.obi_history: List[Tuple[float, float]] = []  # (timestamp, OBI)
        self.volatility_history: List[Tuple[float, float]] = (
            []
        )  # (timestamp, volatility)
        self.trade_imbalance_history: List[Tuple[float, float]] = (
            []
        )  # (timestamp, trade_imbalance)
        self.vwap_distance_history: List[Tuple[float, float]] = (
            []
        )  # (timestamp, vwap_distance)

    def update_from_snapshot(self, message: FIXMessage) -> None:
        """
        Update order book from a market data snapshot message.

        Args:
            message: Market Data Snapshot Full Refresh (W) message
        """
        try:
            self.bids.clear()
            self.asks.clear()

            no_md_entries = int(message.get_field(268, "0"))

            for i in range(no_md_entries):
                entry_type = message.get_field(269, "", i)
                price = float(message.get_field(270, "0", i))
                size = float(message.get_field(271, "0", i))

                if entry_type == "0":  # Bid
                    self.bids[price] = size
                elif entry_type == "1":  # Ask
                    self.asks[price] = size
                elif entry_type == "2":  # Trade
                    self.last_trade_price = price
                    self.last_trade_size = size
                    self.last_trade_side = "buy"  # Assume buy for simplicity
                    self._add_trade(price, size, "buy")

            self.last_update_time = time.time()
            self._add_mid_price()
            self._calculate_features()

            logger.debug(
                f"Updated order book for {self.symbol} from snapshot with "
                f"{len(self.bids)} bids and {len(self.asks)} asks"
            )

        except Exception as e:
            logger.error(f"Error updating order book from snapshot: {e}")

    def update_from_incremental(self, message: FIXMessage) -> None:
        """
        Update order book from an incremental market data message.

        Args:
            message: Market Data Incremental Refresh (X) message
        """
        try:
            no_md_entries = int(message.get_field(268, "0"))

            for i in range(no_md_entries):
                entry_type = message.get_field(269, "", i)
                price = float(message.get_field(270, "0", i))
                size = float(message.get_field(271, "0", i))
                update_action = message.get_field(279, "", i)

                if entry_type == "0":  # Bid
                    if update_action == "0":  # New
                        self.bids[price] = size
                    elif update_action == "1":  # Change
                        self.bids[price] = size
                    elif update_action == "2":  # Delete
                        if price in self.bids:
                            del self.bids[price]

                elif entry_type == "1":  # Ask
                    if update_action == "0":  # New
                        self.asks[price] = size
                    elif update_action == "1":  # Change
                        self.asks[price] = size
                    elif update_action == "2":  # Delete
                        if price in self.asks:
                            del self.asks[price]

                elif entry_type == "2":  # Trade
                    self.last_trade_price = price
                    self.last_trade_size = size

                    if price <= self.get_best_bid():
                        self.last_trade_side = "sell"
                    else:
                        self.last_trade_side = "buy"

                    self._add_trade(price, size, self.last_trade_side)

            self.last_update_time = time.time()
            self._add_mid_price()
            self._calculate_features()

            logger.debug(
                f"Updated order book for {self.symbol} incrementally with "
                f"{len(self.bids)} bids and {len(self.asks)} asks"
            )

        except Exception as e:
            logger.error(f"Error updating order book incrementally: {e}")

    def get_best_bid(self) -> float:
        """
        Get the best (highest) bid price.

        Returns:
            float: Best bid price or 0 if no bids
        """
        return max(self.bids.keys()) if self.bids else 0.0

    def get_best_ask(self) -> float:
        """
        Get the best (lowest) ask price.

        Returns:
            float: Best ask price or 0 if no asks
        """
        return min(self.asks.keys()) if self.asks else 0.0

    def get_mid_price(self) -> float:
        """
        Get the mid price (average of best bid and best ask).

        Returns:
            float: Mid price or 0 if order book is empty
        """
        best_bid = self.get_best_bid()
        best_ask = self.get_best_ask()

        if best_bid > 0 and best_ask > 0:
            return (best_bid + best_ask) / 2

        return 0.0

    def get_spread(self) -> float:
        """
        Get the bid-ask spread.

        Returns:
            float: Bid-ask spread or 0 if order book is empty
        """
        best_bid = self.get_best_bid()
        best_ask = self.get_best_ask()

        if best_bid > 0 and best_ask > 0:
            return best_ask - best_bid

        return 0.0

    def get_order_book_imbalance(self, levels: int = 5) -> float:
        """
        Calculate order book imbalance (OBI).

        OBI = (sum(bid_sizes) - sum(ask_sizes)) / (sum(bid_sizes) + sum(ask_sizes))

        Args:
            levels: Number of price levels to include

        Returns:
            float: Order book imbalance in range [-1, 1]
        """
        try:
            sorted_bids = sorted(self.bids.items(), key=lambda x: x[0], reverse=True)
            sorted_asks = sorted(self.asks.items(), key=lambda x: x[0])

            top_bids = sorted_bids[:levels]
            top_asks = sorted_asks[:levels]

            sum_bid_sizes = sum(size for _, size in top_bids)
            sum_ask_sizes = sum(size for _, size in top_asks)

            if sum_bid_sizes + sum_ask_sizes > 0:
                obi = (sum_bid_sizes - sum_ask_sizes) / (sum_bid_sizes + sum_ask_sizes)
                return obi

            return 0.0

        except Exception as e:
            logger.error(f"Error calculating order book imbalance: {e}")
            return 0.0

    def get_weighted_mid_price(self, levels: int = 5) -> float:
        """
        Calculate volume-weighted mid price.

        Args:
            levels: Number of price levels to include

        Returns:
            float: Volume-weighted mid price
        """
        try:
            sorted_bids = sorted(self.bids.items(), key=lambda x: x[0], reverse=True)
            sorted_asks = sorted(self.asks.items(), key=lambda x: x[0])

            top_bids = sorted_bids[:levels]
            top_asks = sorted_asks[:levels]

            weighted_bid = sum(price * size for price, size in top_bids)
            weighted_ask = sum(price * size for price, size in top_asks)

            total_bid_size = sum(size for _, size in top_bids)
            total_ask_size = sum(size for _, size in top_asks)

            if total_bid_size > 0 and total_ask_size > 0:
                weighted_mid = (
                    weighted_bid / total_bid_size + weighted_ask / total_ask_size
                ) / 2
                return weighted_mid

            return self.get_mid_price()

        except Exception as e:
            logger.error(f"Error calculating weighted mid price: {e}")
            return self.get_mid_price()

    def get_volatility(self, window: int = 20) -> float:
        """
        Calculate price volatility over a window of recent prices.

        Args:
            window: Number of recent prices to include

        Returns:
            float: Price volatility (standard deviation of returns)
        """
        try:
            if len(self.price_history) < window + 1:
                return 0.0

            recent_prices = [price for _, price in self.price_history[-window:]]

            returns = np.diff(recent_prices) / recent_prices[:-1]

            volatility = np.std(returns)

            return volatility

        except Exception as e:
            logger.error(f"Error calculating volatility: {e}")
            return 0.0

    def get_trade_imbalance(self, window: int = 20) -> float:
        """
        Calculate trade imbalance over a window of recent trades.

        Trade imbalance = (buy_volume - sell_volume) / (buy_volume + sell_volume)

        Args:
            window: Number of recent trades to include

        Returns:
            float: Trade imbalance in range [-1, 1]
        """
        try:
            if len(self.trade_history) < window:
                return 0.0

            recent_trades = self.trade_history[-window:]

            buy_volume = sum(size for _, size, side in recent_trades if side == "buy")
            sell_volume = sum(size for _, size, side in recent_trades if side == "sell")

            if buy_volume + sell_volume > 0:
                trade_imbalance = (buy_volume - sell_volume) / (
                    buy_volume + sell_volume
                )
                return trade_imbalance

            return 0.0

        except Exception as e:
            logger.error(f"Error calculating trade imbalance: {e}")
            return 0.0

    def get_vwap(self, window: int = 100) -> float:
        """
        Calculate Volume-Weighted Average Price (VWAP).

        Args:
            window: Number of recent trades to include

        Returns:
            float: VWAP
        """
        try:
            if len(self.trade_history) < window:
                return self.get_mid_price()

            recent_trades = self.trade_history[-window:]

            volume_price_sum = sum(
                size * self.get_mid_price() for _, size, _ in recent_trades
            )
            total_volume = sum(size for _, size, _ in recent_trades)

            if total_volume > 0:
                vwap = volume_price_sum / total_volume
                return vwap

            return self.get_mid_price()

        except Exception as e:
            logger.error(f"Error calculating VWAP: {e}")
            return self.get_mid_price()

    def get_vwap_distance(self) -> float:
        """
        Calculate distance of current mid price from VWAP.

        Returns:
            float: VWAP distance as percentage
        """
        try:
            vwap = self.get_vwap()
            mid_price = self.get_mid_price()

            if vwap > 0 and mid_price > 0:
                return (mid_price - vwap) / vwap

            return 0.0

        except Exception as e:
            logger.error(f"Error calculating VWAP distance: {e}")
            return 0.0

    def get_recent_return(self, lookback: int = 5) -> float:
        """Return percentage change over a lookback in seconds."""
        try:
            if len(self.price_history) < 2:
                return 0.0

            now = time.time()
            past_prices = [
                price for t, price in self.price_history if now - t <= lookback
            ]
            if len(past_prices) < 2:
                return 0.0
            return (past_prices[-1] - past_prices[0]) / past_prices[0]
        except Exception as e:
            logger.error(f"Error calculating recent return: {e}")
            return 0.0

    def get_hawkes_intensity(self, window: int = 50, decay: float = 0.1) -> float:
        """
        Calculate Hawkes process intensity for order flow imbalance.

        Args:
            window: Number of recent trades to include
            decay: Exponential decay factor

        Returns:
            float: Hawkes process intensity
        """
        try:
            if len(self.trade_history) < window:
                return 0.0

            recent_trades = self.trade_history[-window:]
            current_time = time.time()

            intensity = 0.0
            for trade_time, size, side in recent_trades:
                direction = 1 if side == "buy" else -1

                time_diff = current_time - trade_time
                decay_factor = np.exp(-decay * time_diff)

                intensity += direction * size * decay_factor

            total_size = sum(size for _, size, _ in recent_trades)
            if total_size > 0:
                intensity /= total_size

            return intensity

        except Exception as e:
            logger.error(f"Error calculating Hawkes intensity: {e}")
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
        best_bid = next(iter(self.bids.items()))[0]
        best_ask = next(iter(self.asks.items()))[0]
        return (best_bid + best_ask) / 2
        
    def get_mid_price(self):
        """
        Alias for mid_price() to maintain compatibility with OrderBook interface.
        
        Returns:
            float: Mid price or None if order book is empty
        """
        return self.mid_price()
        
    def get_spread(self):
        """
        Calculate the bid-ask spread.
        
        Returns:
            float: Bid-ask spread or 0 if order book is empty
        """
        if not self.bids or not self.asks:
            return 0.0
        best_bid = next(iter(self.bids.items()))[0]
        best_ask = next(iter(self.asks.items()))[0]
        return best_ask - best_bid
        
    def get_order_book_imbalance(self, levels=5):
        """
        Alias for obi() to maintain compatibility with OrderBook interface.
        
        Args:
            levels: Number of price levels to consider
            
        Returns:
            float: Order book imbalance in range [-1, 1]
        """
        return self.obi(levels)
        
    def get_volatility(self, window=20):
        """
        Calculate price volatility over a window of recent prices.
        
        Args:
            window: Number of price points to consider
            
        Returns:
            float: Volatility (standard deviation of returns)
        """
        if len(self.mid_history) < 2:
            return 0.0
            
        prices = list(self.mid_history)[-min(window, len(self.mid_history)):]
        
        if len(prices) < 2:
            return 0.0
            
        # Calculate returns
        returns = [prices[i] / prices[i-1] - 1 for i in range(1, len(prices))]
        
        # Calculate standard deviation
        if not returns:
            return 0.0
            
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / len(returns)
        
        return (variance ** 0.5) * 100  # Convert to percentage

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
        
    def get_features(self) -> Dict[str, float]:
        """
        Get all features for ML model.
        
        Returns:
            Dict[str, float]: Dictionary of features
        """
        try:
            mid = self.mid_price()
            if mid is None:
                return {}
                
            high, low = self.channel()
            if high is None or low is None:
                high = mid * 1.01
                low = mid * 0.99
                
            features = {
                "mid_price": mid,
                "spread": next(iter(self.asks.items()))[0] - next(iter(self.bids.items()))[0] if self.bids and self.asks else 0.0,
                "obi": self.obi(k=config.OBI_LEVELS),
                "upper_bound": high,
                "lower_bound": low,
                "channel_width": high - low,
                "channel_position": (mid - low) / (high - low) if high > low else 0.5,
            }
            
            return features
            
        except Exception as e:
            logger.error(f"Error getting features: {e}")
            return {}

    def get_donchian_channel(self, window: int = 120) -> Tuple[float, float]:
        """
        Calculate Donchian channel (highest high and lowest low) over a window.

        Args:
            window: Window size in seconds

        Returns:
            Tuple[float, float]: Upper and lower bounds of the channel
        """
        try:
            high, low = self.channel()
            if high is None or low is None:
                mid = self.get_mid_price()
                if mid is None or mid <= 0:
                    return 1.0, 1.0  # Default values if no valid price
                return mid * 1.01, mid * 0.99
            return high, low

        except Exception as e:
            logger.error(f"Error calculating Donchian channel: {e}")
            mid = self.get_mid_price()
            if mid is None or mid <= 0:
                return 1.0, 1.0  # Default values if no valid price
            return mid, mid

    def get_features(self) -> Dict[str, float]:
        """
        Get all features for ML model.
        
        Returns:
            Dict[str, float]: Dictionary of features
        """
        try:
            mid_price = self.get_mid_price()
            
            if mid_price is None or mid_price <= 0:
                return {
                    "mid_price": 0.0,
                    "spread": 0.0,
                    "obi": 0.0,
                    "volatility": 0.0,
                    "upper_bound": 1.01,
                    "lower_bound": 0.99,
                    "channel_width": 0.02,
                    "channel_position": 0.5,
                }
                
            features = {
                "mid_price": mid_price,
                "spread": self.get_spread() or 0.0,
                "obi": self.get_order_book_imbalance(levels=config.OBI_LEVELS) or 0.0,
                "volatility": self.get_volatility() or 0.0,
            }

            high, low = self.channel()
            if high is None or low is None:
                high = mid_price * 1.01
                low = mid_price * 0.99
                
            features["upper_bound"] = high
            features["lower_bound"] = low
            features["channel_width"] = high - low
            
            if high > low:
                features["channel_position"] = (mid_price - low) / (high - low)
            else:
                features["channel_position"] = 0.5

            return features

        except Exception as e:
            logger.error(f"Error getting features: {e}")
            return {
                "mid_price": 0.0,
                "spread": 0.0,
                "obi": 0.0,
                "volatility": 0.0,
                "upper_bound": 1.01,
                "lower_bound": 0.99,
                "channel_width": 0.02,
                "channel_position": 0.5,
            }

    def _add_mid_price(self) -> None:
        """Add current mid price to price history."""
        try:
            mid_price = self.get_mid_price()
            if mid_price > 0:
                self.price_history.append((time.time(), mid_price))

                max_history = 1000
                if len(self.price_history) > max_history:
                    self.price_history = self.price_history[-max_history:]

        except Exception as e:
            logger.error(f"Error adding mid price: {e}")

    def _add_trade(self, price: float, size: float, side: str) -> None:
        """
        Add trade to trade history.

        Args:
            price: Trade price
            size: Trade size
            side: Trade side ('buy' or 'sell')
        """
        try:
            self.trade_history.append((time.time(), size, side))

            max_history = 1000
            if len(self.trade_history) > max_history:
                self.trade_history = self.trade_history[-max_history:]

        except Exception as e:
            logger.error(f"Error adding trade: {e}")

    def _calculate_features(self) -> None:
        """Calculate and store features for ML model."""
        try:
            current_time = time.time()

            obi = self.get_order_book_imbalance(levels=config.OBI_LEVELS)
            volatility = self.get_volatility()
            
            mid_price = self.get_mid_price()
            if mid_price is not None:
                self.mid_history.append(mid_price)

        except Exception as e:
            logger.error(f"Error calculating features: {e}")


class DataHandler:
    """
    Handles market data processing and feature calculation.
    Maintains order books for multiple symbols.
    """

    def __init__(self):
        self.order_books: Dict[str, OrderBook] = {}

    def get_or_create_order_book(self, symbol: str) -> LimitOrderBook:
        """
        Get or create order book for a symbol.

        Args:
            symbol: Trading symbol (e.g., 'BTC-USD')

        Returns:
            LimitOrderBook: Order book for the symbol
        """
        if symbol not in self.order_books:
            self.order_books[symbol] = LimitOrderBook(symbol)

        return self.order_books[symbol]

    def process_market_data(self, message: FIXMessage) -> None:
        """
        Process market data message.

        Args:
            message: FIX market data message
        """
        try:
            msg_type = message.get_field(35)
            symbol = message.get_field(55)

            order_book = self.get_or_create_order_book(symbol)

            if msg_type == "W":  # Market Data Snapshot Full Refresh
                order_book.update_from_snapshot(message)
            elif msg_type == "X":  # Market Data Incremental Refresh
                order_book.update_from_incremental(message)

        except Exception as e:
            logger.error(f"Error processing market data: {e}")

    def get_features(self, symbol: str) -> Dict[str, float]:
        """
        Get features for a symbol.

        Args:
            symbol: Trading symbol (e.g., 'BTC-USD')

        Returns:
            Dict[str, float]: Dictionary of features
        """
        try:
            order_book = self.get_or_create_order_book(symbol)
            return order_book.get_features()

        except Exception as e:
            logger.error(f"Error getting features: {e}")
            return {}

    def is_breakout(self, symbol: str) -> Tuple[bool, str]:
        """
        Check if price has broken out of the Donchian channel.

        Args:
            symbol: Trading symbol (e.g., 'BTC-USD')

        Returns:
            Tuple[bool, str]: (is_breakout, direction)
                is_breakout: True if breakout detected
                direction: 'up' or 'down'
        """
        try:
            order_book = self.get_or_create_order_book(symbol)

            current_price = order_book.get_mid_price()
            upper_bound, lower_bound = order_book.get_donchian_channel(
                window=config.CHANNEL_WINDOW
            )

            if current_price > upper_bound:
                return True, "up"
            elif current_price < lower_bound:
                return True, "down"

            return False, ""

        except Exception as e:
            logger.error(f"Error checking breakout: {e}")
            return False, ""
