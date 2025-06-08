#!/usr/bin/env python
"""
Minimal test script to verify authentication with Coinbase International Exchange.
This script focuses only on the authentication part of the FIX connection.
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
from fixt11 import FIXT11
from asyncfix.journaler import Journaler
from asyncfix.connection import AsyncFIXConnection, ConnectionState

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('auth_test.log')
    ]
)
logger = logging.getLogger("auth_test")

load_dotenv()

API_KEY = os.getenv("CB_INTX_API_KEY", "")
API_SECRET = os.getenv("CB_INTX_API_SECRET", "")
PASSPHRASE = os.getenv("CB_INTX_PASSPHRASE", "")
SENDER_COMP_ID = os.getenv("CB_INTX_SENDER_COMPID", "")

HOST = "fix.international.coinbase.com"
PORT = 6120
TARGET_COMP_ID = "CBINTL"  # Always use CBINTL
TARGET_SUB_ID = "MD"  # Market Data session

async def get_utc_timestamp():
    """Generate UTC timestamp in FIX format."""
    return time.strftime("%Y%m%d-%H:%M:%S.000", time.gmtime())

async def generate_signature(timestamp, api_key, target_comp_id, passphrase, api_secret):
    """Generate HMAC-SHA256 signature for authentication."""
    message = f"{timestamp}{api_key}CBINTL{passphrase}"
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

async def test_authentication():
    """Test authentication with Coinbase International Exchange."""
    logger.info("=== Authentication Test ===")
    
    if not all([API_KEY, API_SECRET, PASSPHRASE, SENDER_COMP_ID]):
        logger.error("Missing API credentials. Please set environment variables.")
        return
    
    logger.info(f"Using API Key: {API_KEY[:4]}...{API_KEY[-4:]}")
    logger.info(f"Using Sender CompID: {SENDER_COMP_ID}")
    logger.info(f"Using Target CompID: {TARGET_COMP_ID}")
    
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    ssl_context.set_ciphers("DEFAULT:@SECLEVEL=1")  # Fix SSL handshake issues
    
    protocol = FIXT11()
    journaler = Journaler(None)  # In-memory journaler
    
    connection = AsyncFIXConnection(
        protocol=protocol,
        sender_comp_id=SENDER_COMP_ID,
        target_comp_id=TARGET_COMP_ID,
        journaler=journaler,
        host=HOST,
        port=PORT,
        heartbeat_period=30,
        logger=logger
    )
    
    try:
        logger.info(f"Connecting to {HOST}:{PORT}...")
        reader, writer = await asyncio.open_connection(
            HOST, PORT, ssl=ssl_context
        )
        connection._socket_reader = reader
        connection._socket_writer = writer
        await connection._state_set(ConnectionState.NETWORK_CONN_ESTABLISHED)
        logger.info("SSL connection established")
        logger.info("Connection established, sending Logon message...")
        
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
        logon_msg.set(57, TARGET_SUB_ID)  # TargetSubID for Market Data
        # logon_msg.set(8013, "N")  # CancelOrdersOnDisconnect
        # logon_msg.set(8014, "N")  # CancelOrdersOnInternalDisconnect
        
        logger.info(f"Sending Logon message: {logon_msg}")
        
        await connection.send_msg(logon_msg)
        logger.info("Logon message sent, waiting for response...")
        
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
        logger.error(f"Error during authentication test: {e}")
    finally:
        logger.info("Disconnecting...")
        await connection.disconnect(ConnectionState.DISCONNECTED_BROKEN_CONN)
        logger.info("Disconnected")

if __name__ == "__main__":
    asyncio.run(test_authentication())
