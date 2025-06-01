#!/usr/bin/env python
"""
Test script for all new FIX message handlers.
"""
import asyncio
import logging
import uuid
from asyncfix.message import FIXMessage
from asyncfix import FTag, FMsg
from fix_client import CoinbaseFIXClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_all_handlers")

def test_order_cancel_reject_callback(message):
    logger.info("Order cancel reject callback triggered")

def test_trade_capture_callback(message):
    logger.info("Trade capture report callback triggered")

def test_quote_request_callback(message):
    logger.info("Quote request callback triggered")

async def test_all_handlers():
    """Test all new message handlers."""
    client = CoinbaseFIXClient(
        session_type='order_entry', 
        test_mode=True,
        on_order_cancel_reject=test_order_cancel_reject_callback,
        on_trade_capture_report=test_trade_capture_callback,
        on_quote_request=test_quote_request_callback
    )
    client.authenticated = True
    
    logger.info("\n=== Testing OrderMassCancelReport ===")
    mass_cancel_report = FIXMessage("r")
    mass_cancel_report.set(FTag.ClOrdID, str(uuid.uuid4()))
    mass_cancel_report.set(1369, "12345")  # MassActionReportID
    mass_cancel_report.set(FTag.Symbol, "BTC-USD")
    mass_cancel_report.set(FTag.Side, "1")  # Buy
    mass_cancel_report.set(531, "7")  # Cancel All Orders
    mass_cancel_report.set(533, "5")  # Total affected orders
    client._handle_order_mass_cancel_report(mass_cancel_report)
    
    mass_cancel_reject = FIXMessage("r")
    mass_cancel_reject.set(FTag.ClOrdID, str(uuid.uuid4()))
    mass_cancel_reject.set(531, "0")  # Cancel Request Rejected
    mass_cancel_reject.set(532, "1")  # Invalid or unknown Security
    client._handle_order_mass_cancel_report(mass_cancel_reject)
    
    logger.info("\n=== Testing OrderCancelReject ===")
    cancel_reject = FIXMessage("9")
    cancel_reject.set(FTag.ClOrdID, str(uuid.uuid4()))
    cancel_reject.set(FTag.OrigClOrdID, str(uuid.uuid4()))
    cancel_reject.set(FTag.OrderID, "12345")
    cancel_reject.set(102, "1")  # Unknown order
    cancel_reject.set(434, "1")  # Order Cancel Request
    cancel_reject.set(FTag.Text, "Order not found")
    client._handle_order_cancel_reject(cancel_reject)
    
    logger.info("\n=== Testing TradeCaptureReport ===")
    trade_capture = FIXMessage("AE")
    trade_capture.set(828, "0")  # Regular trade
    trade_capture.set(FTag.ExecID, str(uuid.uuid4()))
    trade_capture.set(FTag.Symbol, "BTC-USD")
    trade_capture.set(32, "0.1")  # LastQty
    trade_capture.set(31, "50000")  # LastPx
    trade_capture.set(552, "1")  # NoSides
    trade_capture.set(FTag.Side, "1")  # Buy
    client._handle_trade_capture_report(trade_capture)
    
    transfer_capture = FIXMessage("AE")
    transfer_capture.set(828, "3")  # Transfer
    transfer_capture.set(830, "LIQUIDATED")  # TransferReason
    transfer_capture.set(FTag.ExecID, str(uuid.uuid4()))
    transfer_capture.set(FTag.Symbol, "BTC-USD")
    transfer_capture.set(32, "0.5")  # LastQty
    transfer_capture.set(31, "49000")  # LastPx
    transfer_capture.set(552, "1")  # NoSides
    transfer_capture.set(FTag.Side, "2")  # Sell
    client._handle_trade_capture_report(transfer_capture)
    
    logger.info("\n=== Testing PreFill Messages ===")
    prefill_success = FIXMessage("F7")
    prefill_success.set(22007, str(uuid.uuid4()))  # PreFillRequestID
    client._handle_prefill_request_success(prefill_success)
    
    prefill_report = FIXMessage("F8")
    prefill_report.set(FTag.ClOrdID, str(uuid.uuid4()))
    prefill_report.set(FTag.OrderID, "12345")
    prefill_report.set(FTag.Symbol, "BTC-USD")
    prefill_report.set(FTag.Side, "1")  # Buy
    prefill_report.set(32, "0.1")  # LastQty
    prefill_report.set(31, "50000")  # LastPx
    prefill_report.set(851, "1")  # Added liquidity
    client._handle_prefill_report(prefill_report)
    
    logger.info("\n=== Testing Quote Request ===")
    quote_request = FIXMessage("R")
    quote_request.set(131, str(uuid.uuid4()))  # QuoteReqID
    quote_request.set(FTag.Symbol, "BTC-USD")
    quote_request.set(FTag.OrderQty, "1.0")
    quote_request.set(62, "20250601-18:30:00")  # ValidUntilTime
    quote_request.set(126, "20250601-19:00:00")  # ExpireTime
    client._handle_quote_request(quote_request)
    
    logger.info("\n=== Testing Quote Status Report ===")
    quote_status_active = FIXMessage("AI")
    quote_status_active.set(131, str(uuid.uuid4()))  # QuoteReqID
    quote_status_active.set(117, str(uuid.uuid4()))  # QuoteID
    quote_status_active.set(FTag.Symbol, "BTC-USD")
    quote_status_active.set(297, "16")  # Active
    client._handle_quote_status_report(quote_status_active)
    
    quote_status_rejected = FIXMessage("AI")
    quote_status_rejected.set(131, str(uuid.uuid4()))  # QuoteReqID
    quote_status_rejected.set(117, str(uuid.uuid4()))  # QuoteID
    quote_status_rejected.set(FTag.Symbol, "BTC-USD")
    quote_status_rejected.set(297, "5")  # Rejected
    quote_status_rejected.set(FTag.Text, "Invalid price")
    client._handle_quote_status_report(quote_status_rejected)
    
    logger.info("\n=== Testing Send Methods ===")
    prefill_id = await client.send_prefill_request()
    logger.info(f"PreFill Request sent with ID: {prefill_id}")
    
    rfq_id = await client.send_rfq_request()
    logger.info(f"RFQ Request sent with ID: {rfq_id}")
    
    quote_id = await client.send_quote(
        quote_req_id=str(uuid.uuid4()),
        symbol="BTC-USD",
        bid_px=49900,
        bid_size="1.0",
        offer_px=50100,
        offer_size="1.0",
        portfolio_id="test-portfolio-uuid"
    )
    logger.info(f"Quote sent with ID: {quote_id}")
    
    logger.info("\n=== All tests completed successfully ===")

if __name__ == "__main__":
    asyncio.run(test_all_handlers())
