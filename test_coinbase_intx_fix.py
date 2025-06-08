#!/usr/bin/env python
"""
Test script for Coinbase International Exchange FIX connection fixes.
Tests FIXT11 protocol, correct TargetCompID/TargetSubID, and authentication flow.
"""
import asyncio
import logging
import os
from dotenv import load_dotenv
from fix_client import CoinbaseFIXClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_coinbase_intx_fix")

async def test_market_data_connection():
    """Test market data connection with fixed protocol."""
    logger.info("=== Testing Market Data Connection ===")
    
    client = CoinbaseFIXClient(
        session_type="market_data",
        test_mode=False
    )
    
    logger.info(f"Protocol: {client.protocol.__class__.__name__ if client.protocol else 'Not set'}")
    logger.info(f"TargetCompID: {client.target_comp_id}")
    logger.info(f"TargetSubID: {client.target_sub_id}")
    
    try:
        connected = await client.connect()
        logger.info(f"Connection result: {connected}")
        
        if connected:
            logger.info("Authentication successful! Testing market data subscription...")
            await asyncio.sleep(5)  # Wait for any initial messages
            
            subscribed = await client.subscribe_market_data("BTC-PERP")
            logger.info(f"Market data subscription result: {subscribed}")
            
            logger.info("Waiting for market data (15 seconds)...")
            await asyncio.sleep(15)
            
            await client.disconnect()
            logger.info("Disconnected successfully")
        else:
            logger.error("Connection failed")
            
    except Exception as e:
        logger.error(f"Error during test: {e}")

async def test_order_entry_connection():
    """Test order entry connection with fixed protocol."""
    logger.info("\n=== Testing Order Entry Connection ===")
    
    client = CoinbaseFIXClient(
        session_type="order_entry",
        test_mode=False
    )
    
    logger.info(f"Protocol: {client.protocol.__class__.__name__ if client.protocol else 'Not set'}")
    logger.info(f"TargetCompID: {client.target_comp_id}")
    logger.info(f"TargetSubID: {client.target_sub_id}")
    
    try:
        connected = await client.connect()
        logger.info(f"Connection result: {connected}")
        
        if connected:
            logger.info("Authentication successful!")
            await asyncio.sleep(5)  # Wait for any initial messages
            
            await client.disconnect()
            logger.info("Disconnected successfully")
        else:
            logger.error("Connection failed")
            
    except Exception as e:
        logger.error(f"Error during test: {e}")

if __name__ == "__main__":
    load_dotenv()
    
    if not all([
        os.getenv("CB_INTX_API_KEY"),
        os.getenv("CB_INTX_API_SECRET"), 
        os.getenv("CB_INTX_PASSPHRASE"),
        os.getenv("CB_INTX_SENDER_COMPID")
    ]):
        logger.error("Missing API credentials. Please set environment variables.")
    else:
        asyncio.run(test_market_data_connection())
        asyncio.run(test_order_entry_connection())
