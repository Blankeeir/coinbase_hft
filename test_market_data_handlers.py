#!/usr/bin/env python
"""
Test script for market data message handlers.
"""
import asyncio
import logging
import uuid
from asyncfix.message import FIXMessage
from asyncfix import FTag, FMsg
from fix_client import CoinbaseFIXClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_market_data")

def test_security_list_callback(message, securities):
    logger.info(f"Security list callback triggered with {len(securities)} securities")
    for i, security in enumerate(securities[:3]):  # Show first 3 for brevity
        logger.info(f"  Security {i+1}: {security['symbol']} ({security['security_type']})")

def test_security_definition_callback(message, security_def):
    logger.info(f"Security definition callback triggered for {security_def['symbol']}")
    logger.info(f"  Action: {security_def['update_action']}, Type: {security_def['security_type']}")

def test_market_data_request_reject_callback(message):
    logger.info("Market data request reject callback triggered")

async def test_market_data_handlers():
    """Test all market data message handlers."""
    client = CoinbaseFIXClient(
        session_type='market_data', 
        test_mode=True,
        on_security_list=test_security_list_callback,
        on_security_definition=test_security_definition_callback,
        on_market_data_request_reject=test_market_data_request_reject_callback
    )
    client.authenticated = True
    
    logger.info("\n=== Testing SecurityListRequest ===")
    security_list_req = FIXMessage("x")
    security_list_req.set(320, str(uuid.uuid4()))  # SecurityReqID
    security_list_req.set(559, "0")  # All Securities
    client._handle_security_list_request(security_list_req)
    
    logger.info("\n=== Testing SecurityList ===")
    security_list = FIXMessage("y")
    security_list.set(320, str(uuid.uuid4()))  # SecurityReqID
    security_list.set(560, "0")  # Valid request
    security_list.set(146, "2")  # NoRelatedSym = 2
    
    security_list.set(55, "BTC-USD", 0)  # Symbol
    security_list.set(167, "FXSPOT", 0)  # SecurityType
    security_list.set(762, "STANDARD", 0)  # SecuritySubType
    security_list.set(969, "0.01", 0)  # MinPriceIncrement
    security_list.set(898, "0.50", 0)  # MarginRatio
    security_list.set(15, "USD", 0)  # Currency
    security_list.set(562, "1", 0)  # MinTradeVol
    security_list.set(1682, "17", 0)  # Ready to trade
    
    security_list.set(55, "ETH-USD", 1)  # Symbol
    security_list.set(167, "FXSPOT", 1)  # SecurityType
    security_list.set(762, "STANDARD", 1)  # SecuritySubType
    security_list.set(969, "0.01", 1)  # MinPriceIncrement
    security_list.set(898, "0.75", 1)  # MarginRatio
    security_list.set(15, "USD", 1)  # Currency
    security_list.set(562, "1", 1)  # MinTradeVol
    security_list.set(1682, "17", 1)  # Ready to trade
    
    client._handle_security_list(security_list)
    
    logger.info("\n=== Testing SecurityDefinition ===")
    security_def_add = FIXMessage("d")
    security_def_add.set(980, "A")  # Add
    security_def_add.set(779, "20250530-18:00:00")  # LastUpdateTime
    security_def_add.set(55, "SOL-USD")  # Symbol
    security_def_add.set(167, "FXSPOT")  # SecurityType
    security_def_add.set(762, "STANDARD")  # SecuritySubType
    security_def_add.set(969, "0.001")  # MinPriceIncrement
    security_def_add.set(898, "0.85")  # MarginRatio
    security_def_add.set(15, "USD")  # Currency
    security_def_add.set(562, "1")  # MinTradeVol
    security_def_add.set(1682, "17")  # Ready to trade
    client._handle_security_definition(security_def_add)
    
    security_def_modify = FIXMessage("d")
    security_def_modify.set(980, "M")  # Modify
    security_def_modify.set(55, "SOL-USD")  # Symbol
    security_def_modify.set(898, "0.90")  # Updated MarginRatio
    client._handle_security_definition(security_def_modify)
    
    logger.info("\n=== Testing MarketDataRequest ===")
    md_request = FIXMessage("V")
    md_request.set(262, str(uuid.uuid4()))  # MDReqID
    md_request.set(263, "1")  # Subscribe
    md_request.set(264, "10")  # MarketDepth
    md_request.set(146, "2")  # NoRelatedSym
    md_request.set(55, "BTC-USD", 0)  # Symbol
    md_request.set(167, "FXSPOT", 0)  # SecurityType
    md_request.set(55, "ETH-USD", 1)  # Symbol
    md_request.set(167, "FXSPOT", 1)  # SecurityType
    client._handle_market_data_request(md_request)
    
    logger.info("\n=== Testing MarketDataRequestReject ===")
    md_reject = FIXMessage("Y")
    md_reject.set(262, str(uuid.uuid4()))  # MDReqID
    md_reject.set(281, "0")  # Unknown symbol
    md_reject.set(58, "Symbol XYZ-USD not found")  # Text
    client._handle_market_data_request_reject(md_reject)
    
    logger.info("\n=== Testing Send Methods ===")
    security_req_id = await client.request_security_list()
    logger.info(f"SecurityListRequest sent with ID: {security_req_id}")
    
    md_req_id = await client.send_market_data_request(["BTC-USD", "ETH-USD"], market_depth=10)
    logger.info(f"MarketDataRequest sent with ID: {md_req_id}")
    
    logger.info("\n=== All market data tests completed successfully ===")

if __name__ == "__main__":
    asyncio.run(test_market_data_handlers())
