#!/usr/bin/env python
"""
Test script for Coinbase International Exchange FIX connection.
Tests the updated protocol, TargetCompID/SubID, and authentication.
"""
import sys
import time
import logging
import quickfix as fix
import quickfix50sp2 as fix50
import hmac, hashlib, base64
from config import *

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("fix_connection_test.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("fix_connection_test")

class TestApplication(fix.Application):
    def __init__(self, session_type):
        super().__init__()
        self.session_type = session_type
        self.session_id = None
        self.connected = False
        self.authenticated = False
        
    def onCreate(self, sessionID):
        logger.info(f"Session created: {sessionID}")
        self.session_id = sessionID
        
    def onLogon(self, sessionID):
        logger.info(f"Logon successful for {self.session_type} session")
        self.authenticated = True
        if self.session_type == "market_data":
            self._subscribe_market_data()
            
    def onLogout(self, sessionID):
        logger.info(f"Logout for {self.session_type} session")
        self.authenticated = False
        
    def toAdmin(self, msg, sessionID):
        msgType = fix.MsgType()
        msg.getHeader().getField(msgType)
        
        if msgType.getValue() == fix.MsgType_Logon:
            logger.info("Preparing Logon message for authentication")
            
            settings = fix.Session.lookupSession(sessionID).getSessionID()
            targetSubID = fix.TargetSubID()
            settings.getField(targetSubID)
            
            utc_timestamp = fix.TransactTime().getString()
            
            msg.setField(fix.Username(API_KEY))
            msg.setField(fix.Password(PASSPHRASE))
            
            message = f"{utc_timestamp}{API_KEY}CBINTL{PASSPHRASE}"
            logger.info(f"Signature message components: timestamp={utc_timestamp}, api_key={API_KEY[:4]}..., target_comp_id=CBINTL, passphrase=***")
            
            hmac_key = base64.b64decode(API_SECRET)
            logger.info(f"Decoded API secret length: {len(hmac_key)} bytes")
            
            signature = hmac.new(hmac_key, message.encode(), hashlib.sha256).digest()
            signature_b64 = base64.b64encode(signature).decode()
            logger.info(f"Generated signature: {signature_b64[:10]}...")
            
            msg.setField(fix.RawDataLength(len(signature_b64)))
            msg.setField(fix.RawData(signature_b64))
            msg.setField(fix.Text(utc_timestamp))
            
            if targetSubID.getValue() == "OE":
                msg.setField(8013, "N")  # CancelOrdersOnDisconnect
                msg.setField(8014, "N")  # CancelOrdersOnInternalDisconnect
            
            logger.info(f"Logon message authenticated with timestamp {utc_timestamp}")
            
    def fromAdmin(self, msg, sessionID):
        msgType = fix.MsgType()
        msg.getHeader().getField(msgType)
        
        if msgType.getValue() == fix.MsgType_Logon:
            logger.info("Received Logon response")
        elif msgType.getValue() == fix.MsgType_Reject:
            refSeqNum = fix.RefSeqNum()
            msg.getField(refSeqNum)
            text = fix.Text()
            if msg.isSetField(text):
                msg.getField(text)
                logger.error(f"Received Reject: {text.getValue()}")
            else:
                logger.error("Received Reject without text")
                
    def toApp(self, msg, sessionID):
        logger.info(f"Sending application message: {msg}")
        
    def fromApp(self, msg, sessionID):
        msgType = fix.MsgType()
        msg.getHeader().getField(msgType)
        
        if msgType.getValue() == fix.MsgType_MarketDataSnapshotFullRefresh:
            logger.info("Received market data snapshot")
        elif msgType.getValue() == fix.MsgType_MarketDataIncrementalRefresh:
            logger.info("Received market data incremental refresh")
            
    def _subscribe_market_data(self):
        logger.info("Subscribing to market data for BTC-USD")
        req = fix50.MarketDataRequest()
        req.setField(fix.MDReqID("BOOK1"))
        req.setField(fix.SubscriptionRequestType(fix.SubscriptionRequestType_SNAPSHOT_PLUS_UPDATES))
        req.setField(fix.MarketDepth(0))   # full depth
        req.setField(fix.MDUpdateType(1))  # incremental
        
        md_entry_types = fix.NoMDEntryTypes()
        for tag in (fix.MDEntryType_BID, fix.MDEntryType_OFFER, fix.MDEntryType_TRADE):
            group = fix50.MarketDataRequest.NoMDEntryTypes()
            group.setField(fix.MDEntryType(tag))
            md_entry_types.addGroup(group)
        req.setField(md_entry_types)
        
        symbols = fix.NoRelatedSym()
        sym_grp = fix50.MarketDataRequest.NoRelatedSym()
        sym_grp.setField(fix.Symbol("BTC-USD"))
        symbols.addGroup(sym_grp)
        req.setField(symbols)
        
        fix.Session.sendToTarget(req, self.session_id)
        logger.info("Market data subscription request sent")

def test_market_data_connection():
    """Test market data connection with fixed protocol."""
    logger.info("=== Testing Market Data Connection ===")
    
    try:
        settings = fix.SessionSettings("coinbase_fix.cfg")
        application = TestApplication("market_data")
        store_factory = fix.FileStoreFactory(settings)
        log_factory = fix.FileLogFactory(settings)
        initiator = fix.SocketInitiator(application, store_factory, settings, log_factory)
        
        logger.info("Starting FIX initiator for market data session")
        initiator.start()
        
        timeout = 30  # seconds
        start_time = time.time()
        while not application.authenticated and time.time() - start_time < timeout:
            logger.info("Waiting for authentication...")
            time.sleep(1)
            
        if application.authenticated:
            logger.info("Authentication successful! Waiting for market data...")
            time.sleep(10)  # Wait for market data
        else:
            logger.error(f"Authentication failed after {timeout} seconds")
            
        logger.info("Stopping FIX initiator")
        initiator.stop()
        return application.authenticated
        
    except Exception as e:
        logger.error(f"Error during test: {e}")
        return False

if __name__ == "__main__":
    if not all([API_KEY, API_SECRET, PASSPHRASE]):
        logger.error("Missing API credentials. Please set environment variables.")
        sys.exit(1)
        
    success = test_market_data_connection()
    
    if success:
        logger.info("FIX connection test PASSED")
        sys.exit(0)
    else:
        logger.error("FIX connection test FAILED")
        sys.exit(1)
