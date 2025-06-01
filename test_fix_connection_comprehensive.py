#!/usr/bin/env python
"""
Comprehensive test script for Coinbase International Exchange FIX connection.
Tests SSL context handling, authentication, and message processing.
"""
import asyncio
import logging
import os
import sys
import time
from dotenv import load_dotenv
import config
from fix_client import CoinbaseFIXClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('fix_connection_test.log')
    ]
)
logger = logging.getLogger("fix_connection_test")

async def test_connection_comprehensive():
    """Test FIX connection with comprehensive checks."""
    load_dotenv()
    
    logger.info("=" * 80)
    logger.info("COINBASE INTERNATIONAL EXCHANGE FIX CONNECTION TEST")
    logger.info("=" * 80)
    logger.info(f"Environment: {config.ENVIRONMENT}")
    logger.info(f"API Key: {config.CB_INTX_API_KEY[:4]}...{config.CB_INTX_API_KEY[-4:]}")
    logger.info(f"Sender CompID: {config.CB_INTX_SENDER_COMPID}")
    
    logger.info("\n=== Testing Market Data Connection ===")
    logger.info(f"Host: {config.FIX_MARKET_DATA_HOST}")
    logger.info(f"Port: {config.FIX_MARKET_DATA_PORT}")
    logger.info(f"Target CompID: {config.FIX_TARGET_COMPID_MARKET_DATA}")
    
    market_data_client = CoinbaseFIXClient(
        session_type="market_data",
        test_mode=False
    )
    
    try:
        logger.info("Connecting to market data session...")
        connected = await market_data_client.connect()
        logger.info(f"Market data connection result: {connected}")
        
        if connected:
            logger.info("Connection successful! Testing market data subscription...")
            
            logger.info("Requesting security list...")
            security_req_id = await market_data_client.request_security_list()
            logger.info(f"Security list request sent with ID: {security_req_id}")
            
            logger.info("Waiting for security list response (5 seconds)...")
            await asyncio.sleep(5)
            
            logger.info("Subscribing to BTC-USD market data...")
            subscribed = await market_data_client.subscribe_market_data("BTC-USD")
            logger.info(f"Market data subscription result: {subscribed}")
            
            logger.info("Waiting for market data (10 seconds)...")
            await asyncio.sleep(10)
            
            logger.info("Unsubscribing from market data...")
            unsubscribed = await market_data_client.unsubscribe_market_data("BTC-USD")
            logger.info(f"Market data unsubscription result: {unsubscribed}")
            
            logger.info("Disconnecting market data session...")
            await market_data_client.disconnect()
            logger.info("Market data session disconnected successfully")
    except Exception as e:
        logger.error(f"Error during market data connection test: {e}")
    
    logger.info("\n=== Testing Order Entry Connection ===")
    logger.info(f"Host: {config.FIX_ORDER_ENTRY_HOST}")
    logger.info(f"Port: {config.FIX_ORDER_ENTRY_PORT}")
    logger.info(f"Target CompID: {config.FIX_TARGET_COMPID_ORDER_ENTRY}")
    
    order_entry_client = CoinbaseFIXClient(
        session_type="order_entry",
        test_mode=False
    )
    
    try:
        logger.info("Connecting to order entry session...")
        connected = await order_entry_client.connect()
        logger.info(f"Order entry connection result: {connected}")
        
        if connected:
            logger.info("Connection successful! Testing position request...")
            
            logger.info("Requesting positions...")
            position_req_id = await order_entry_client.request_positions()
            logger.info(f"Position request sent with ID: {position_req_id}")
            
            logger.info("Waiting for position response (5 seconds)...")
            await asyncio.sleep(5)
            
            logger.info("Disconnecting order entry session...")
            await order_entry_client.disconnect()
            logger.info("Order entry session disconnected successfully")
    except Exception as e:
        logger.error(f"Error during order entry connection test: {e}")
    
    logger.info("\n=== Connection test completed ===")

if __name__ == "__main__":
    asyncio.run(test_connection_comprehensive())
