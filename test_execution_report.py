#!/usr/bin/env python
"""
Test script for ExecutionReport handling with fee information.
"""
import logging
import uuid
import time
from asyncfix.message import FIXMessage
from asyncfix import FTag, FMsg
from portfolio import Position

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_execution_report")

def test_position_fee_handling():
    """Test position fee handling directly."""
    position = Position("BTC-USD")
    
    fill = {
        "symbol": "BTC-USD",
        "side": "BUY",
        "quantity": 0.1,
        "price": 50000,
        "timestamp": time.time(),
        "fees": [
            {
                "amount": 5.0,
                "currency": "USD",
                "type": "4",  # Exchange fees
            }
        ]
    }
    
    position.update_from_fill(fill)
    
    print(f"Position: {position}")
    print(f"Last trade: {position.trades[-1]}")
    print(f"Fees: {position.trades[-1].get('fees', [])}")

def test_execution_report_parsing():
    """Test execution report fee parsing."""
    exec_report = FIXMessage("8")  # ExecutionReport
    exec_report.set(FTag.ClOrdID, str(uuid.uuid4()))
    exec_report.set(150, "1")  # ExecType = Partial Fill
    exec_report.set(FTag.Symbol, "BTC-USD")
    exec_report.set(FTag.Side, "1")  # Buy
    exec_report.set(32, "0.1")  # LastQty
    exec_report.set(31, "50000")  # LastPx
    
    exec_report.set(136, "2")  # NoMiscFees = 2
    exec_report.set(137, "5.0")  # MiscFeeAmt
    exec_report.set(138, "USD")  # MiscFeeCurr
    exec_report.set(139, "4")  # MiscFeeType = Exchange fees
    
    fees = []
    try:
        no_misc_fees = int(exec_report.get(136, "0"))
        print(f"NoMiscFees: {no_misc_fees}")
        
        for i in range(no_misc_fees):
            fee_amt = float(exec_report.get(137, "0"))
            fee_curr = exec_report.get(138, "")
            fee_type = exec_report.get(139, "")
            
            fees.append({
                "amount": fee_amt,
                "currency": fee_curr,
                "type": fee_type,
            })
            
        print(f"Extracted fees: {fees}")
    except Exception as e:
        print(f"Error extracting fees: {e}")

if __name__ == "__main__":
    test_position_fee_handling()
    print("\n---\n")
    test_execution_report_parsing()
