#!/usr/bin/env python
"""
Test script for Take Profit Stop Loss (TPSL) order functionality.
"""
import asyncio
import logging
from fix_client import CoinbaseFIXClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_tpsl")

async def test_tpsl_orders():
    """Test TPSL order functionality."""
    client = CoinbaseFIXClient(session_type='order_entry', test_mode=True)
    client.authenticated = True
    
    logger.info("=== Testing Valid TPSL Sell Order ===")
    sell_order_id = await client.place_order(
        symbol='BTC-USD',
        side='SELL', 
        order_type='TAKE_PROFIT_STOP_LOSS',
        quantity=0.1,
        price=60000,  # Take profit price
        stop_price=55000,  # Stop loss trigger
        stop_limit_price=54000,  # Stop loss limit
        time_in_force='GTC'
    )
    logger.info(f"TPSL Sell order placed: {sell_order_id}")
    
    logger.info("=== Testing Valid TPSL Buy Order ===")
    buy_order_id = await client.place_order(
        symbol='BTC-USD',
        side='BUY',
        order_type='TAKE_PROFIT_STOP_LOSS', 
        quantity=0.1,
        price=50000,  # Take profit price
        stop_price=55000,  # Stop loss trigger
        stop_limit_price=56000,  # Stop loss limit
        time_in_force='GTC'
    )
    logger.info(f"TPSL Buy order placed: {buy_order_id}")
    
    logger.info("=== Testing TPSL Validation Errors ===")
    
    try:
        await client.place_order(
            symbol='BTC-USD',
            side='SELL',
            order_type='TAKE_PROFIT_STOP_LOSS',
            quantity=0.1,
            price=60000,
            stop_price=55000,
            stop_limit_price=54000,
            time_in_force='IOC'  # Invalid for TPSL
        )
    except ValueError as e:
        logger.info(f"Expected validation error: {e}")
    
    try:
        await client.place_order(
            symbol='BTC-USD',
            side='SELL',
            order_type='TAKE_PROFIT_STOP_LOSS',
            quantity=0.1,
            price=60000,
            stop_price=55000,
            stop_limit_price=54000,
            post_only=True  # Not supported for TPSL
        )
    except ValueError as e:
        logger.info(f"Expected validation error: {e}")
    
    try:
        await client.place_order(
            symbol='BTC-USD',
            side='SELL',
            order_type='TAKE_PROFIT_STOP_LOSS',
            quantity=0.1,
            price=50000,  # Should be > stop_price
            stop_price=55000,
            stop_limit_price=54000
        )
    except ValueError as e:
        logger.info(f"Expected validation error: {e}")
    
    logger.info("=== Testing TPSL Order Modification ===")
    modified_order_id = await client.modify_order(
        original_client_order_id=sell_order_id,
        symbol='BTC-USD',
        price=61000,  # New take profit
        stop_price=56000,  # New stop trigger  
        stop_limit_price=55000  # New stop limit
    )
    logger.info(f"TPSL order modified: {modified_order_id}")

if __name__ == "__main__":
    asyncio.run(test_tpsl_orders())
