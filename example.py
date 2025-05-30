"""
Example script for Coinbase International Exchange HFT Bot.
This script demonstrates how to use the HFT bot with minimal configuration.
"""
import asyncio
import logging
import os
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("example")

async def run_example():
    """Run the HFT bot example."""
    try:
        from main import HFTBot
        
        bot = HFTBot(
            symbol="BTC-USD",  # Trading symbol
            window=120,        # Channel window in seconds
            threshold=0.15,    # OBI threshold
        )
        
        logger.info("Connecting to exchange...")
        connected = await bot.connect()
        if not connected:
            logger.error("Failed to connect to exchange")
            return
        
        logger.info("Subscribing to market data...")
        subscribed = await bot.subscribe_market_data()
        if not subscribed:
            logger.error("Failed to subscribe to market data")
            await bot.disconnect()
            return
        
        logger.info("Syncing positions...")
        await bot.sync_positions()
        
        logger.info("Waiting for initial market data...")
        await asyncio.sleep(5)
        
        logger.info("Running trading cycles...")
        for _ in range(10):
            await bot.trading_cycle()
            await asyncio.sleep(1)
        
        logger.info("Disconnecting from exchange...")
        await bot.disconnect()
        
        logger.info("Example completed successfully")
        
    except Exception as e:
        logger.error(f"Error in example: {e}")

if __name__ == "__main__":
    load_dotenv()
    
    required_env_vars = [
        "CB_INTX_API_KEY",
        "CB_INTX_API_SECRET",
        "CB_INTX_PASSPHRASE",
        "CB_INTX_SENDER_COMPID",
    ]
    
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        logger.error("Please set these variables in .env file or environment")
        logger.error("Run: cp .env.example .env && nano .env")
        exit(1)
    
    asyncio.run(run_example())
