#!/usr/bin/env python
"""
Comprehensive fix for Coinbase International Exchange FIX connection issues.
This script demonstrates the correct way to establish a FIX connection with SSL.

Key fixes:
1. Pass SSL context to connect() method: await connection.connect(ssl=ssl_context)
2. Use correct TargetCompID values: CBINTLMD (market data), CBINTLOE (order entry)
3. Ensure authentication message format matches Coinbase requirements
"""
import asyncio
import logging
import os
import ssl
import base64
import hmac
import hashlib
import time
from dotenv import load_dotenv
from asyncfix.message import FIXMessage
from asyncfix.protocol import FIXProtocol44
from asyncfix.journaler import Journaler
from asyncfix.connection import AsyncFIXConnection, ConnectionState

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('fix_connection_fix.log')
    ]
)
logger = logging.getLogger("fix_connection_fix")

load_dotenv()

API_KEY = os.getenv("CB_INTX_API_KEY", "")
API_SECRET = os.getenv("CB_INTX_API_SECRET", "")
PASSPHRASE = os.getenv("CB_INTX_PASSPHRASE", "")
SENDER_COMP_ID = os.getenv("CB_INTX_SENDER_COMPID", "")

HOST = "fix.international.coinbase.com"
PORT_MARKET_DATA = 6120
PORT_ORDER_ENTRY = 6121
TARGET_COMP_ID_MARKET_DATA = "CBINTLMD"
TARGET_COMP_ID_ORDER_ENTRY = "CBINTLOE"

async def get_utc_timestamp():
    """Generate UTC timestamp in FIX format."""
    return time.strftime("%Y%m%d-%H:%M:%S.000", time.gmtime())

async def generate_signature(timestamp, api_key, target_comp_id, passphrase, api_secret):
    """Generate HMAC-SHA256 signature for authentication."""
    message = f"{timestamp}{api_key}{target_comp_id}{passphrase}"
    logger.info(f"Signature message components: timestamp={timestamp}, api_key={api_key[:4]}..., target_comp_id={target_comp_id}, passphrase=***")
    
    try:
        decoded_secret = base64.b64decode(api_secret)
        logger.info(f"Decoded API secret length: {len(decoded_secret)} bytes")
        
        signature = base64.b64encode(
            hmac.new(
                decoded_secret,
                message.encode('utf-8'),
                hashlib.sha256
            ).digest()
        ).decode('utf-8')
        
        logger.info(f"Generated signature: {signature[:10]}...")
        return signature
    except Exception as e:
        logger.error(f"Error generating signature: {e}")
        return None

async def send_logon_message(connection, api_key, passphrase, target_comp_id, api_secret):
    """Send Logon message with authentication."""
    timestamp = await get_utc_timestamp()
    signature = await generate_signature(timestamp, api_key, target_comp_id, passphrase, api_secret)
    
    if not signature:
        logger.error("Failed to generate signature")
        return False
    
    logon_msg = FIXMessage("A")  # Logon message type
    logon_msg.set(98, "0")  # EncryptMethod: No encryption
    logon_msg.set(108, "30")  # HeartBtInt: 30s
    logon_msg.set(141, "Y")  # ResetSeqNumFlag: Reset sequence numbers
    
    logon_msg.set(553, api_key)  # Username: API Key
    logon_msg.set(554, passphrase)  # Password: Passphrase
    logon_msg.set(95, str(len(signature)))  # RawDataLength: Length of signature
    logon_msg.set(96, signature)  # RawData: HMAC signature
    logon_msg.set(58, timestamp)  # Text: Timestamp used for signature
    logon_msg.set(1137, "9")  # DefaultApplVerID = FIX.5.0SP2
    
    logon_msg.set(8013, "N")  # CancelOrdersOnDisconnect: Don't cancel orders on disconnect
    logon_msg.set(8014, "N")  # CancelOrdersOnInternalDisconnect: Don't cancel on internal disconnect
    
    logger.info(f"Sending Logon message: {logon_msg}")
    
    await connection.send_msg(logon_msg)
    logger.info("Logon message sent, waiting for response...")
    return True

async def on_message(self, message):
    """Handle incoming FIX messages."""
    msg_type = message.get_or_default(35, "")
    logger.info(f"Received message type: {msg_type}")
    
    if msg_type == "A":  # Logon
        logger.info("Received Logon response (35=A)")
        logger.info(f"Authentication successful!")
        self.authenticated = True
    elif msg_type == "3":  # Reject
        logger.warning(f"Received Reject (35=3): {message}")
    elif msg_type == "5":  # Logout
        logger.warning(f"Received Logout (35=5): {message}")
    else:
        logger.info(f"Received message: {message}")

async def test_market_data_connection():
    """Test connection to market data session."""
    logger.info("=== Testing Market Data Connection ===")
    
    if not all([API_KEY, API_SECRET, PASSPHRASE, SENDER_COMP_ID]):
        logger.error("Missing API credentials. Please set environment variables.")
        return
    
    logger.info(f"Using API Key: {API_KEY[:4]}...{API_KEY[-4:]}")
    logger.info(f"Using Sender CompID: {SENDER_COMP_ID}")
    logger.info(f"Using Target CompID: {TARGET_COMP_ID_MARKET_DATA}")
    
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    protocol = FIXProtocol44()
    journaler = Journaler(None)  # In-memory journaler
    
    connection = AsyncFIXConnection(
        protocol=protocol,
        sender_comp_id=SENDER_COMP_ID,
        target_comp_id=TARGET_COMP_ID_MARKET_DATA,
        journaler=journaler,
        host=HOST,
        port=PORT_MARKET_DATA,
        heartbeat_period=30,
        logger=logger
    )
    
    connection.on_message = on_message
    
    try:
        logger.info(f"Connecting to {HOST}:{PORT_MARKET_DATA}...")
        
        await connection.connect(ssl=ssl_context)
        logger.info("Connection established, sending Logon message...")
        
        auth_sent = await send_logon_message(
            connection, 
            API_KEY, 
            PASSPHRASE, 
            TARGET_COMP_ID_MARKET_DATA, 
            API_SECRET
        )
        
        if not auth_sent:
            logger.error("Failed to send authentication message")
            return
        
        logger.info("Waiting for 30 seconds to receive response...")
        for i in range(30):
            await asyncio.sleep(1)
            if connection.connection_state == 4:  # ESTABLISHED
                logger.info("Authentication successful!")
                break
            logger.info(f"Current connection state: {connection.connection_state}")
        
        if connection.connection_state != 4:
            logger.error(f"Authentication failed, final state: {connection.connection_state}")
        
    except Exception as e:
        logger.error(f"Error during connection test: {e}")
    finally:
        logger.info("Disconnecting...")
        await connection.disconnect(ConnectionState.DISCONNECTED_BROKEN_CONN)
        logger.info("Disconnected")

async def main():
    """Run connection tests."""
    logger.info("=== Coinbase International Exchange FIX Connection Fix ===")
    await test_market_data_connection()
    logger.info("=== Connection test completed ===")

if __name__ == "__main__":
    asyncio.run(main())
