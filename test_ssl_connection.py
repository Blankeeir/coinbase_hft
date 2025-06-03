#!/usr/bin/env python
"""
Test script for SSL connection to Coinbase International Exchange.
This script tests only the SSL connection establishment, not the full FIX protocol.
"""
import asyncio
import ssl
import logging
import socket
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("ssl_connection_test.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("ssl_connection_test")

async def test_ssl_connection(host, port):
    """Test SSL connection to the specified host and port."""
    logger.info(f"Testing SSL connection to {host}:{port}")
    
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    try:
        reader, writer = await asyncio.open_connection(
            host, 
            port,
            ssl=ssl_context
        )
        
        logger.info(f"SSL connection established to {host}:{port}")
        
        peer_cert = writer.get_extra_info('peercert')
        if peer_cert:
            logger.info(f"Peer certificate: {peer_cert}")
        
        writer.close()
        await writer.wait_closed()
        
        logger.info("Connection closed successfully")
        return True
        
    except ssl.SSLError as e:
        logger.error(f"SSL error: {e}")
        return False
    except socket.gaierror as e:
        logger.error(f"Address resolution error: {e}")
        return False
    except ConnectionRefusedError as e:
        logger.error(f"Connection refused: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return False

async def test_all_connections():
    """Test connections to all Coinbase International Exchange endpoints."""
    endpoints = [
        ("fix.international.coinbase.com", 6110),  # Order entry
        ("fix.international.coinbase.com", 6120),  # Market data
        ("fix.international.coinbase.com", 6130),  # Drop copy
    ]
    
    results = []
    for host, port in endpoints:
        success = await test_ssl_connection(host, port)
        results.append((host, port, success))
    
    logger.info("\n=== Connection Test Results ===")
    for host, port, success in results:
        status = "SUCCESS" if success else "FAILED"
        logger.info(f"{host}:{port} - {status}")
    
    return all(success for _, _, success in results)

if __name__ == "__main__":
    logger.info("=== Starting SSL Connection Tests ===")
    
    success = asyncio.run(test_all_connections())
    
    if success:
        logger.info("All SSL connection tests PASSED")
        sys.exit(0)
    else:
        logger.error("Some SSL connection tests FAILED")
        sys.exit(1)
