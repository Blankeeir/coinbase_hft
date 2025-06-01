#!/usr/bin/env python
"""
Test script for drop copy message handlers.
"""
import asyncio
import logging
import uuid
from asyncfix.message import FIXMessage
from asyncfix import FTag, FMsg
from fix_client import CoinbaseFIXClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_drop_copy")

def test_execution_report_callback(message):
    """Test callback for execution reports."""
    try:
        no_misc_fees = int(message.get(136, "0"))
        if no_misc_fees > 0:
            fees = []
            fee_amt = message.get(137, "0")
            fee_curr = message.get(138, "")
            fee_type = message.get(139, "")
            
            fee_type_map = {
                "4": "Exchange fees",
                "7": "Other",
                "14": "Security lending"
            }
            
            fee_type_desc = fee_type_map.get(fee_type, f"Unknown ({fee_type})")
            
            fees.append({
                "amount": fee_amt,
                "currency": fee_curr,
                "type": fee_type_desc
            })
            
            logger.info(f"Execution with fees: {fees}")
        
        no_party_ids = int(message.get(453, "0"))
        if no_party_ids > 0:
            portfolio_id = None
            client_id = None
            
            for i in range(no_party_ids):
                party_id = message.get(448, "")
                party_role = message.get(452, "")
                
                if party_role == "24":  # Customer account
                    portfolio_id = party_id
                elif party_role == "3":  # Client ID
                    client_id = party_id
            
            if portfolio_id:
                logger.info(f"Portfolio ID: {portfolio_id}")
            if client_id:
                logger.info(f"Client ID: {client_id}")
    
    except Exception as e:
        logger.error(f"Error in execution report callback: {e}")

def test_trade_capture_callback(message):
    """Test callback for trade capture reports."""
    try:
        trd_type = message.get(828, "")
        trd_match_id = message.get(880, "")
        
        if trd_type == "3":  # Transfer
            transfer_reason = message.get(830, "")
            logger.info(f"Transfer trade: {trd_match_id}, Reason: {transfer_reason}")
        else:
            logger.info(f"Regular trade: {trd_match_id}")
        
        no_sides = int(message.get(552, "0"))
        if no_sides > 0:
            no_party_ids = int(message.get(453, "0"))
            if no_party_ids > 0:
                portfolio_id = None
                
                party_id = message.get(448, "")
                party_role = message.get(452, "")
                
                if party_role == "24":  # Customer account
                    portfolio_id = party_id
                
                if portfolio_id:
                    logger.info(f"Portfolio ID: {portfolio_id}")
        
        no_misc_fees = int(message.get(136, "0"))
        if no_misc_fees > 0:
            fees = []
            fee_amt = message.get(137, "0")
            fee_curr = message.get(138, "")
            fee_type = message.get(139, "")
            
            fees.append({
                "amount": fee_amt,
                "currency": fee_curr,
                "type": fee_type
            })
            
            logger.info(f"Trade with fees: {fees}")
    
    except Exception as e:
        logger.error(f"Error in trade capture callback: {e}")

def test_quote_status_callback(message):
    """Test callback for quote status reports."""
    try:
        quote_req_id = message.get(131, "")
        quote_id = message.get(117, "")
        quote_status = message.get(297, "")
        
        status_map = {
            "5": "Rejected",
            "7": "Expired",
            "16": "Active",
            "17": "Canceled",
            "19": "Pending End Trade"
        }
        
        status_desc = status_map.get(quote_status, quote_status)
        logger.info(f"Quote status: {status_desc} for Quote ID: {quote_id}")
        
        if quote_status == "19":  # Pending End Trade
            side = message.get(FTag.Side, "")
            side_desc = "Buy" if side == "1" else "Sell" if side == "2" else "Unknown"
            logger.info(f"Quote selected for execution: {side_desc}")
    
    except Exception as e:
        logger.error(f"Error in quote status callback: {e}")

async def test_drop_copy_handlers():
    """Test all drop copy message handlers."""
    client = CoinbaseFIXClient(
        session_type='drop_copy', 
        test_mode=True,
        on_execution_report=test_execution_report_callback,
        on_trade_capture_report=test_trade_capture_callback,
        on_quote=test_quote_status_callback
    )
    client.authenticated = True
    
    logger.info("\n=== Testing ExecutionReport with Fees ===")
    exec_report = FIXMessage("8")
    exec_report.set(FTag.ClOrdID, str(uuid.uuid4()))
    exec_report.set(150, "1")  # ExecType = Partial Fill
    exec_report.set(FTag.OrdStatus, "1")  # Partially Filled
    exec_report.set(FTag.Symbol, "BTC-USD")
    exec_report.set(FTag.Side, "1")  # Buy
    exec_report.set(32, "0.1")  # LastQty
    exec_report.set(31, "50000")  # LastPx
    exec_report.set(14, "0.1")  # CumQty
    exec_report.set(151, "0.9")  # LeavesQty
    exec_report.set(6, "50000")  # AvgPx
    
    exec_report.set(136, "2")  # NoMiscFees = 2
    exec_report.set(137, "5.0")  # MiscFeeAmt
    exec_report.set(138, "USD")  # MiscFeeCurr
    exec_report.set(139, "4")  # MiscFeeType = Exchange fees
    
    exec_report.set(453, "1")  # NoPartyIDs = 1
    exec_report.set(448, "portfolio-uuid-123", 0)  # PartyID
    exec_report.set(452, "24", 0)  # PartyRole = Customer account
    
    client._log_execution_report(exec_report)
    if client.on_execution_report:
        client.on_execution_report(exec_report)
    
    logger.info("\n=== Testing TradeCaptureReport with Transfer ===")
    trade_capture = FIXMessage("AE")
    trade_capture.set(828, "3")  # Transfer
    trade_capture.set(830, "LIQUIDATED")  # TransferReason
    trade_capture.set(880, str(uuid.uuid4()))  # TrdMatchID
    trade_capture.set(FTag.ExecID, str(uuid.uuid4()))
    trade_capture.set(FTag.Symbol, "BTC-USD")
    trade_capture.set(32, "0.5")  # LastQty
    trade_capture.set(31, "49000")  # LastPx
    
    trade_capture.set(552, "1")  # NoSides = 1
    trade_capture.set(FTag.Side, "2")  # Sell
    trade_capture.set(453, "1")  # NoPartyIDs = 1
    trade_capture.set(448, "portfolio-uuid-456", 0)  # PartyID
    trade_capture.set(452, "24", 0)  # PartyRole = Customer account
    
    trade_capture.set(136, "1")  # NoMiscFees = 1
    trade_capture.set(137, "10.0")  # MiscFeeAmt
    trade_capture.set(138, "USD")  # MiscFeeCurr
    trade_capture.set(139, "14")  # MiscFeeType = Security lending
    
    client._handle_trade_capture_report(trade_capture)
    
    logger.info("\n=== Testing Quote Status Report ===")
    quote_status_pending = FIXMessage("AI")
    quote_status_pending.set(131, str(uuid.uuid4()))  # QuoteReqID
    quote_status_pending.set(117, str(uuid.uuid4()))  # QuoteID
    quote_status_pending.set(FTag.Symbol, "BTC-USD")
    quote_status_pending.set(297, "19")  # Pending End Trade
    quote_status_pending.set(FTag.Side, "1")  # Buy
    quote_status_pending.set(FTag.OrderQty, "1.0")
    quote_status_pending.set(132, "49900")  # BidPx
    quote_status_pending.set(133, "50100")  # OfferPx
    quote_status_pending.set(134, "1.0")  # BidSize
    quote_status_pending.set(135, "1.0")  # OfferSize
    quote_status_pending.set(62, "20250601-19:30:00")  # ValidUntilTime
    quote_status_pending.set(126, "20250601-20:00:00")  # ExpireTime
    
    client._handle_quote_status_report(quote_status_pending)
    
    logger.info("\n=== All drop copy tests completed successfully ===")

if __name__ == "__main__":
    asyncio.run(test_drop_copy_handlers())
