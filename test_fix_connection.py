#!/usr/bin/env python
"""
Test script to verify FIX connection with Coinbase International Exchange.
This script tests the fixed connection logic that sends Logon immediately after socket connection.
"""
import asyncio
import logging
import os
import sys
import time
from dotenv import load_dotenv
import config
from fix_client import CoinbaseFIXClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_fix_connection")

async def test_connection():
    """Test FIX connection with different configurations."""
    load_dotenv()
    
    logger.info("=== FIX Connection Test ===")
    logger.info(f"Environment: {config.ENVIRONMENT}")
    logger.info(f"Market Data Host: {config.FIX_MARKET_DATA_HOST}")
    logger.info(f"Market Data Port: {config.FIX_MARKET_DATA_PORT}")
    logger.info(f"Target CompID (Market Data): {config.FIX_TARGET_COMPID_MARKET_DATA}")
    
    logger.info("\n=== Testing with test_mode=True ===")
    test_client = CoinbaseFIXClient(
        session_type="market_data",
        test_mode=True
    )
    connected = await test_client.connect()
    logger.info(f"Test mode connection result: {connected}")
    
    if not all([config.CB_INTX_API_KEY, config.CB_INTX_API_SECRET, 
                config.CB_INTX_PASSPHRASE, config.CB_INTX_SENDER_COMPID]):
        logger.warning("API credentials not fully configured. Skipping real connection test.")
        logger.info("To test with real credentials, set the following environment variables:")
        logger.info("  CB_INTX_API_KEY")
        logger.info("  CB_INTX_API_SECRET")
        logger.info("  CB_INTX_PASSPHRASE")
        logger.info("  CB_INTX_SENDER_COMPID")
        return
    
    logger.info("\n=== Testing with real connection ===")
    client = CoinbaseFIXClient(
        session_type="market_data",
        test_mode=False
    )
    
    logger.info(f"Client host: {client.host}")
    logger.info(f"Client port: {client.port}")
    logger.info(f"Client sender_comp_id: {client.sender_comp_id}")
    logger.info(f"Client target_comp_id: {client.target_comp_id}")
    
    try:
        connected = await client.connect()
        logger.info(f"Real connection result: {connected}")
        
        if connected:
            logger.info("Connection successful! Testing market data subscription...")
            subscribed = await client.subscribe_market_data("BTC-USD")
            logger.info(f"Market data subscription result: {subscribed}")
            
            logger.info("Waiting for market data (10 seconds)...")
            await asyncio.sleep(10)
            
            logger.info("Disconnecting...")
            await client.disconnect()
            logger.info("Disconnected successfully")
    except Exception as e:
        logger.error(f"Error during connection test: {e}")
    
    logger.info("\n=== Connection test completed ===")

if __name__ == "__main__":
    asyncio.run(test_connection())
