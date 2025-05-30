#!/usr/bin/env python
"""
Test script to verify the Coinbase International Exchange HFT Bot.
This script initializes all components and runs a simple test to ensure everything works.
"""
import asyncio
import logging
import os
import sys
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("test")

async def run_test():
    """Run a simple test of the HFT bot."""
    try:
        from main import HFTBot
        
        symbol = os.getenv("TEST_SYMBOL", "BTC-USD")
        window = int(os.getenv("TEST_WINDOW", "120"))
        threshold = float(os.getenv("TEST_THRESHOLD", "0.15"))
        
        logger.info(f"Initializing HFT bot with symbol={symbol}, window={window}, threshold={threshold}")
        bot = HFTBot(symbol=symbol, window=window, threshold=threshold)
        
        logger.info("Testing component initialization...")
        assert bot.data_handler is not None, "Data handler not initialized"
        assert bot.market_data_client is not None, "Market data client not initialized"
        assert bot.order_entry_client is not None, "Order entry client not initialized"
        assert bot.strategy is not None, "Strategy not initialized"
        assert bot.execution is not None, "Execution engine not initialized"
        assert bot.portfolio is not None, "Portfolio not initialized"
        
        logger.info("Checking API credentials...")
        import config
        if not all([config.CB_INTX_API_KEY, config.CB_INTX_API_SECRET, 
                   config.CB_INTX_PASSPHRASE, config.CB_INTX_SENDER_COMPID]):
            logger.warning("API credentials not set. Skipping connection test.")
            logger.info("To run a full test, set the following environment variables:")
            logger.info("  CB_INTX_API_KEY, CB_INTX_API_SECRET, CB_INTX_PASSPHRASE, CB_INTX_SENDER_COMPID")
            logger.info("Test completed successfully (initialization only)")
            return
        
        logger.info("Testing connection to exchange...")
        connected = await bot.connect()
        if connected:
            logger.info("Successfully connected to exchange")
            
            logger.info("Testing market data subscription...")
            subscribed = await bot.subscribe_market_data()
            if subscribed:
                logger.info("Successfully subscribed to market data")
                
                logger.info("Waiting for initial market data (5 seconds)...")
                await asyncio.sleep(5)
                
                logger.info("Running a test trading cycle...")
                await bot.trading_cycle()
                
                logger.info("Testing position sync...")
                await bot.sync_positions()
            
            logger.info("Disconnecting from exchange...")
            await bot.disconnect()
        
        logger.info("Test completed successfully")
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False
    
    return True

def check_directories():
    """Check if required directories exist and create them if needed."""
    required_dirs = ["log", "store", "models", "spec"]
    for directory in required_dirs:
        if not os.path.exists(directory):
            logger.info(f"Creating directory: {directory}")
            os.makedirs(directory, exist_ok=True)

def check_files():
    """Check if required files exist."""
    required_files = [
        "config.py", 
        "fix_client.py", 
        "data_handler.py", 
        "strategy.py", 
        "execution.py", 
        "portfolio.py", 
        "main.py",
        "coinbase_fix.cfg",
        "spec/FIX50SP2.xml",
        "spec/FIXT11.xml"
    ]
    
    missing_files = []
    for file in required_files:
        if not os.path.exists(file):
            missing_files.append(file)
    
    if missing_files:
        logger.error(f"Missing required files: {', '.join(missing_files)}")
        return False
    
    return True

if __name__ == "__main__":
    load_dotenv()
    
    check_directories()
    if not check_files():
        sys.exit(1)
    
    if asyncio.run(run_test()):
        logger.info("All tests passed!")
        sys.exit(0)
    else:
        logger.error("Tests failed!")
        sys.exit(1)
