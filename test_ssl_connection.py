#!/usr/bin/env python
"""
Test script for SSL connection with Coinbase International Exchange.
This script tests the fixed SSLAsyncFIXConnection class.
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
from custom_connection import SSLAsyncFIXConnection
from asyncfix.connection import ConnectionState

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('ssl_connection_test.log')
    ]
)
logger = logging.getLogger("ssl_connection_test")

load_dotenv()

API_KEY = os.getenv("CB_INTX_API_KEY", "")
API_SECRET = os.getenv("CB_INTX_API_SECRET", "")
PASSPHRASE = os.getenv("CB_INTX_PASSPHRASE", "")
SENDER_COMP_ID = os.getenv("CB_INTX_SENDER_COMPID", "")

HOST = "fix.international.coinbase.com"
PORT = 6120
TARGET_COMP_ID = "CBINTLMD"  # Market Data

async def get_utc_timestamp():
    """Generate UTC timestamp in FIX format."""
    return time.strftime("%Y%m%d-%H:%M:%S.000", time.gmtime())

async def generate_signature(timestamp, api_key, target_comp_id, passphrase, api_secret):
    """Generate HMAC-SHA256 signature for authentication."""
    message = f"{timestamp}{api_key}{target_comp_id}{passphrase}"
    
    try:
        decoded_secret = base64.b64decode(api_secret)
        signature = base64.b64encode(
            hmac.new(
                decoded_secret,
                message.encode('utf-8'),
                hashlib.sha256
            ).digest()
        ).decode('utf-8')
        
        return signature
    except Exception as e:
        logger.error(f"Error generating signature: {e}")
        return None

async def on_message(connection, message):
    """Handle incoming FIX messages."""
    msg_type = message.get_or_default(35, "")
    logger.info(f"Received message type: {msg_type}")
    
    if msg_type == "A":  # Logon
        logger.info("Received Logon response (35=A)")
        logger.info(f"Authentication successful!")
    elif msg_type == "3":  # Reject
        logger.warning(f"Received Reject (35=3): {message}")
    elif msg_type == "5":  # Logout
        logger.warning(f"Received Logout (35=5): {message}")
    else:
        logger.info(f"Received message: {message}")

async def test_ssl_connection():
    """Test SSL connection with Coinbase International Exchange."""
    logger.info("=== Testing SSL Connection ===")
    
    if not all([API_KEY, API_SECRET, PASSPHRASE, SENDER_COMP_ID]):
        logger.error("Missing API credentials. Please set environment variables.")
        return
    
    logger.info(f"Using API Key: {API_KEY[:4]}...{API_KEY[-4:]}")
    logger.info(f"Using Sender CompID: {SENDER_COMP_ID}")
    logger.info(f"Using Target CompID: {TARGET_COMP_ID}")
    
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    protocol = FIXProtocol44()
    journaler = Journaler(None)  # In-memory journaler
    
    connection = SSLAsyncFIXConnection(
        protocol=protocol,
        sender_comp_id=SENDER_COMP_ID,
        target_comp_id=TARGET_COMP_ID,
        journaler=journaler,
        host=HOST,
        port=PORT,
        ssl_context=ssl_context,
        heartbeat_period=30,
        logger=logger
    )
    
    connection.on_message = lambda msg: on_message(connection, msg)
    
    try:
        logger.info(f"Connecting to {HOST}:{PORT}...")
        
        logger.info("Testing with ssl parameter...")
        await connection.connect(ssl=ssl_context)
        logger.info("Connection established with ssl parameter")
        
        logger.info("Testing with stored ssl_context...")
        await connection.disconnect(ConnectionState.DISCONNECTED_BROKEN_CONN)
        await asyncio.sleep(1)
        await connection.connect()  # Should use stored ssl_context
        logger.info("Connection established with stored ssl_context")
        
        timestamp = await get_utc_timestamp()
        signature = await generate_signature(timestamp, API_KEY, TARGET_COMP_ID, PASSPHRASE, API_SECRET)
        
        if not signature:
            logger.error("Failed to generate signature")
            return
        
        logon_msg = FIXMessage("A")  # Logon message type
        logon_msg.set(98, "0")  # EncryptMethod: No encryption
        logon_msg.set(108, "30")  # HeartBtInt: 30s
        logon_msg.set(141, "Y")  # ResetSeqNumFlag: Reset sequence numbers
        
        logon_msg.set(553, API_KEY)  # Username: API Key
        logon_msg.set(554, PASSPHRASE)  # Password: Passphrase
        logon_msg.set(95, str(len(signature)))  # RawDataLength: Length of signature
        logon_msg.set(96, signature)  # RawData: HMAC signature
        logon_msg.set(58, timestamp)  # Text: Timestamp used for signature
        logon_msg.set(1137, "9")  # DefaultApplVerID = FIX.5.0SP2
        logon_msg.set(8013, "N")  # CancelOrdersOnDisconnect
        logon_msg.set(8014, "N")  # CancelOrdersOnInternalDisconnect
        
        await connection.send_msg(logon_msg)
        logger.info("Logon message sent, waiting for response...")
        
        for i in range(10):
            await asyncio.sleep(1)
            logger.info(f"Current connection state: {connection.connection_state}")
            if connection.connection_state == 4:  # ESTABLISHED
                logger.info("Authentication successful!")
                break
        
    except Exception as e:
        logger.error(f"Error during SSL connection test: {e}")
    finally:
        logger.info("Disconnecting...")
        await connection.disconnect(ConnectionState.DISCONNECTED_BROKEN_CONN)
        logger.info("Disconnected")

if __name__ == "__main__":
    asyncio.run(test_ssl_connection())
