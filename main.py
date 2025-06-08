"""
Main module for Coinbase International Exchange HFT Bot.
Bootstraps the system and coordinates all components.
"""
import asyncio
import logging
import time
import os
import signal
import sys
from typing import Dict, List, Tuple, Optional, Any
import argparse
from asyncfix.message import FIXMessage

import config
from fix_client import CoinbaseFIXClient
from data_handler import DataHandler
from strategy import ChannelBreakoutStrategy
from execution import ExecutionEngine
from portfolio import Portfolio

logger = logging.getLogger("coinbase_hft.main")

class HFTBot:
    """
    High-Frequency Trading Bot for Coinbase International Exchange.
    Coordinates all components and runs the main trading loop.
    """
    def __init__(self, symbol: str, window: int = None, threshold: float = None, test_mode: bool = False):
        """
        Initialize the HFT bot.
        
        Args:
            symbol: Trading symbol (e.g., 'BTC-USD')
            window: Channel window in seconds (overrides config)
            threshold: OBI threshold (overrides config)
            test_mode: Run in test mode without real connection
        """
        self.symbol = symbol
        
        if window is not None:
            config.CHANNEL_WINDOW = window
        if threshold is not None:
            config.OBI_THRESHOLD = threshold
            
        self.test_mode = test_mode
        self.data_handler = DataHandler()
        
        self.market_data_client = CoinbaseFIXClient(
            session_type="market_data",
            on_market_data=self._on_market_data,
            test_mode=self.test_mode,
        )
        
        self.order_entry_client = CoinbaseFIXClient(
            session_type="order_entry",
            on_execution_report=self._on_execution_report,
            on_position_report=self._on_position_report,
            test_mode=self.test_mode,
        )
        
        self.strategy = ChannelBreakoutStrategy(symbol, self.data_handler)
        order_book = self.data_handler.get_or_create_order_book(symbol)
        self.execution = ExecutionEngine(self.order_entry_client, order_book, latency_ms=config.LATENCY_BUDGET)
        self.portfolio = Portfolio(self.order_entry_client)
        
        self.running = False
        self.last_cycle_time = 0.0
        self.cycle_count = 0
        self.trading_enabled = True
        
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
    
    def _handle_signal(self, sig, frame):
        """Handle termination signals."""
        logger.info(f"Received signal {sig}, shutting down...")
        self.running = False
    
    def _on_market_data(self, message: FIXMessage) -> None:
        """
        Process market data message.
        
        Args:
            message: FIX market data message
        """
        try:
            self.data_handler.process_market_data(message)
            
            symbol = message.get_field(55, "")
            if symbol:
                order_book = self.data_handler.get_or_create_order_book(symbol)
                mid_price = order_book.get_mid_price()
                if mid_price > 0:
                    self.portfolio.update_market_prices({symbol: mid_price})
            
        except Exception as e:
            logger.error(f"Error processing market data: {e}")
    
    def _on_execution_report(self, message: FIXMessage) -> None:
        """
        Process execution report.
        
        Args:
            message: FIX execution report message
        """
        try:
            self.execution.on_execution_report(message)
            
            self.portfolio.update_from_execution_report(message)
            
            symbol = message.get_field(55, "")
            if symbol == self.symbol:
                position = self.portfolio.get_position_quantity(symbol)
                position_direction = 1 if position > 0 else (-1 if position < 0 else 0)
                self.strategy.update_position(position_direction)
            
        except Exception as e:
            logger.error(f"Error processing execution report: {e}")
    
    def _on_position_report(self, message: FIXMessage) -> None:
        """
        Process position report.
        
        Args:
            message: FIX position report message
        """
        try:
            self.portfolio.update_from_position_report(message)
            
            symbol = message.get_field(55, "")
            if symbol == self.symbol:
                position = self.portfolio.get_position_quantity(symbol)
                position_direction = 1 if position > 0 else (-1 if position < 0 else 0)
                self.strategy.update_position(position_direction)
            
        except Exception as e:
            logger.error(f"Error processing position report: {e}")
    
    async def connect(self) -> bool:
        """
        Connect to exchange.
        
        Returns:
            bool: True if connection successful
        """
        try:
            md_connected = await self.market_data_client.connect()
            if not md_connected:
                logger.error("Failed to connect market data client")
                return False
            
            oe_connected = await self.order_entry_client.connect()
            if not oe_connected:
                logger.error("Failed to connect order entry client")
                await self.market_data_client.disconnect()
                return False
            
            logger.info("Connected to exchange")
            return True
            
        except Exception as e:
            logger.error(f"Error connecting to exchange: {e}")
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from exchange."""
        try:
            await self.market_data_client.disconnect()
            
            await self.order_entry_client.disconnect()
            
            logger.info("Disconnected from exchange")
            
        except Exception as e:
            logger.error(f"Error disconnecting from exchange: {e}")
    
    async def subscribe_market_data(self) -> bool:
        """
        Subscribe to market data.
        
        Returns:
            bool: True if subscription successful
        """
        try:
            subscribed = await self.market_data_client.subscribe_market_data(self.symbol)
            if not subscribed:
                logger.error(f"Failed to subscribe to market data for {self.symbol}")
                return False
            
            logger.info(f"Subscribed to market data for {self.symbol}")
            return True
            
        except Exception as e:
            logger.error(f"Error subscribing to market data: {e}")
            return False
    
    async def sync_positions(self) -> bool:
        """
        Sync positions with exchange.
        
        Returns:
            bool: True if sync successful
        """
        try:
            synced = await self.portfolio.sync_positions()
            if not synced:
                logger.warning("Failed to sync positions")
                return False
            
            logger.info("Synced positions")
            return True
            
        except Exception as e:
            logger.error(f"Error syncing positions: {e}")
            return False
    
    async def trading_cycle(self) -> None:
        """Run a single trading cycle."""
        try:
            cycle_start = time.time()
            
            if not self.trading_enabled:
                return
            
            if not self.portfolio.check_risk_limits():
                logger.warning("Risk limits exceeded, disabling trading")
                self.trading_enabled = False
                return
            
            signal, price, metadata = self.strategy.generate_signal()
            
            if signal == "BUY":
                logger.info(f"BUY signal generated at {price}: {metadata}")
                
                position_size = config.POSITION_SIZE
                
                await self.execution.place_smart_order(
                    symbol=self.symbol,
                    side="BUY",
                    quantity=position_size,
                    price=price,
                )
                
            elif signal == "SELL":
                logger.info(f"SELL signal generated at {price}: {metadata}")
                
                position_size = config.POSITION_SIZE
                
                await self.execution.place_smart_order(
                    symbol=self.symbol,
                    side="SELL",
                    quantity=position_size,
                    price=price,
                )
            
            should_close, close_metadata = self.strategy.should_close_position()
            if should_close:
                logger.info(f"Position close signal: {close_metadata}")
                
                position = self.portfolio.get_position_quantity(self.symbol)
                
                if position > 0:
                    features = self.data_handler.get_features(self.symbol)
                    current_price = features.get("mid_price", 0)
                    
                    if current_price > 0:
                        await self.execution.place_smart_order(
                            symbol=self.symbol,
                            side="SELL",
                            quantity=abs(position),
                            price=current_price,
                        )
                
                elif position < 0:
                    features = self.data_handler.get_features(self.symbol)
                    current_price = features.get("mid_price", 0)
                    
                    if current_price > 0:
                        await self.execution.place_smart_order(
                            symbol=self.symbol,
                            side="BUY",
                            quantity=abs(position),
                            price=current_price,
                        )
            
            cycle_time = (time.time() - cycle_start) * 1000  # milliseconds
            self.last_cycle_time = cycle_time
            self.cycle_count += 1
            
            if self.cycle_count % 100 == 0:
                portfolio_summary = self.portfolio.get_portfolio_summary()
                logger.info(f"Cycle {self.cycle_count}: {cycle_time:.2f} ms, Portfolio: {portfolio_summary}")
            
        except Exception as e:
            logger.error(f"Error in trading cycle: {e}")
    
    async def run(self) -> None:
        """Run the HFT bot."""
        try:
            logger.info(f"Starting HFT bot for {self.symbol}")
            
            connected = await self.connect()
            if not connected:
                logger.error("Failed to connect, exiting")
                return
            
            subscribed = await self.subscribe_market_data()
            if not subscribed:
                logger.error("Failed to subscribe to market data, exiting")
                await self.disconnect()
                return
            
            await self.sync_positions()
            
            logger.info("Waiting for initial market data...")
            await asyncio.sleep(5)
            
            self.running = True
            logger.info("Starting trading loop")
            
            while self.running:
                await self.trading_cycle()
                
                cycle_time = self.last_cycle_time / 1000  # seconds
                sleep_time = max(0, config.TRADING_CYCLE / 1000 - cycle_time)
                await asyncio.sleep(sleep_time)
            
            await self.disconnect()
            
            logger.info("HFT bot stopped")
            
        except Exception as e:
            logger.error(f"Error running HFT bot: {e}")
            await self.disconnect()

async def main():
    """Main entry point."""
    try:
        parser = argparse.ArgumentParser(description="Coinbase International Exchange HFT Bot")
        parser.add_argument("--symbol", type=str, default=config.TRADING_SYMBOL, help="Trading symbol (e.g., 'BTC-USD')")
        parser.add_argument("--window", type=int, help="Channel window in seconds")
        parser.add_argument("--threshold", type=float, help="OBI threshold")
        parser.add_argument("--test", action="store_true", help="Run in test mode without real connection")
        args = parser.parse_args()
        
        bot = HFTBot(
            symbol=args.symbol,
            window=args.window,
            threshold=args.threshold,
            test_mode=args.test,
        )
        
        await bot.run()
        
    except Exception as e:
        logger.error(f"Error in main: {e}")
        sys.exit(1)

if __name__ == "__main__":
    os.makedirs("log", exist_ok=True)
    os.makedirs("store", exist_ok=True)
    os.makedirs("models", exist_ok=True)
    
    asyncio.run(main())
