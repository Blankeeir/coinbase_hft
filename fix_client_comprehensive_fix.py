#!/usr/bin/env python
"""
Comprehensive fix for Coinbase International Exchange FIX client.
This file provides a drop-in replacement for the fix_client.py file.

Key fixes:
1. SSL context handling in connect() method
2. Proper authentication message format
3. Correct connection state management
4. Comprehensive error handling
"""
import asyncio
import base64
import hashlib
import hmac
import logging
import os
import ssl
import time
import uuid
from typing import Dict, List, Optional, Callable, Any, Union

from asyncfix.connection import ConnectionState
from asyncfix.journaler import Journaler
from asyncfix.message import FIXMessage
from asyncfix.protocol import FIXProtocol44
from dotenv import load_dotenv

from custom_connection import SSLAsyncFIXConnection

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('coinbase_hft.log')
    ]
)
logger = logging.getLogger("coinbase_hft.fix_client")

load_dotenv()

class CoinbaseFIXClient:
    """
    FIX client for Coinbase International Exchange.
    Handles connection, authentication, and message processing.
    """
    
    def __init__(
        self,
        session_type: str = 'market_data',
        test_mode: bool = False,
        on_order_book_update: Optional[Callable] = None,
        on_trade: Optional[Callable] = None,
        on_execution_report: Optional[Callable] = None,
        on_order_cancel_reject: Optional[Callable] = None,
        on_security_list: Optional[Callable] = None,
        on_security_definition: Optional[Callable] = None,
        on_market_data_request_reject: Optional[Callable] = None,
    ):
        """
        Initialize FIX client.
        
        Args:
            session_type: Type of FIX session ('market_data', 'order_entry', or 'drop_copy')
            test_mode: Whether to use test mode (no real orders)
            on_order_book_update: Callback for order book updates
            on_trade: Callback for trade updates
            on_execution_report: Callback for execution reports
            on_order_cancel_reject: Callback for order cancel rejects
            on_security_list: Callback for security list messages
            on_security_definition: Callback for security definition messages
            on_market_data_request_reject: Callback for market data request rejects
        """
        self.session_type = session_type
        self.test_mode = test_mode
        self.authenticated = False
        self.connection = None
        self.session = None
        self.request_id_counter = 0
        
        self.api_key = os.getenv("CB_INTX_API_KEY", "")
        self.api_secret = os.getenv("CB_INTX_API_SECRET", "")
        self.passphrase = os.getenv("CB_INTX_PASSPHRASE", "")
        self.sender_comp_id = os.getenv("CB_INTX_SENDER_COMPID", "")
        
        self.host = "fix.international.coinbase.com"
        self.port = self._get_port_for_session_type(session_type)
        self.target_comp_id = self._get_target_comp_id_for_session_type(session_type)
        
        self.ssl_context = None
        
        self.on_order_book_update = on_order_book_update
        self.on_trade = on_trade
        self.on_execution_report = on_execution_report
        self.on_order_cancel_reject = on_order_cancel_reject
        self.on_security_list = on_security_list
        self.on_security_definition = on_security_definition
        self.on_market_data_request_reject = on_market_data_request_reject
        
        if not all([self.api_key, self.api_secret, self.passphrase, self.sender_comp_id]):
            logger.error("Missing API credentials. Please set environment variables.")
            raise ValueError("Missing API credentials")
    
    def _get_port_for_session_type(self, session_type: str) -> int:
        """Get port for session type."""
        port_map = {
            'market_data': 6120,
            'order_entry': 6121,
            'drop_copy': 6122
        }
        return port_map.get(session_type, 6120)
    
    def _get_target_comp_id_for_session_type(self, session_type: str) -> str:
        """Get target CompID for session type."""
        target_comp_id_map = {
            'market_data': "CBINTLMD",
            'order_entry': "CBINTLOE",
            'drop_copy': "CBINTLDC"
        }
        return target_comp_id_map.get(session_type, "CBINTLMD")
    
    async def _get_utc_timestamp(self) -> str:
        """Generate UTC timestamp in FIX format."""
        return time.strftime("%Y%m%d-%H:%M:%S.000", time.gmtime())
    
    async def _generate_signature(self, timestamp: str) -> str:
        """Generate HMAC-SHA256 signature for authentication."""
        message = f"{timestamp}{self.api_key}{self.target_comp_id}{self.passphrase}"
        
        try:
            decoded_secret = base64.b64decode(self.api_secret)
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
            raise
    
    async def _send_logon_message(self) -> None:
        """Send Logon message with authentication."""
        timestamp = await self._get_utc_timestamp()
        signature = await self._generate_signature(timestamp)
        
        logon_msg = FIXMessage("A")  # Logon message type
        logon_msg.set(98, "0")  # EncryptMethod: No encryption
        logon_msg.set(108, "30")  # HeartBtInt: 30s
        logon_msg.set(141, "Y")  # ResetSeqNumFlag: Reset sequence numbers
        
        logon_msg.set(553, self.api_key)  # Username: API Key
        logon_msg.set(554, self.passphrase)  # Password: Passphrase
        logon_msg.set(95, str(len(signature)))  # RawDataLength: Length of signature
        logon_msg.set(96, signature)  # RawData: HMAC signature
        logon_msg.set(58, timestamp)  # Text: Timestamp used for signature
        logon_msg.set(1137, "9")  # DefaultApplVerID = FIX.5.0SP2
        
        logon_msg.set(8013, "N")  # CancelOrdersOnDisconnect
        logon_msg.set(8014, "N")  # CancelOrdersOnInternalDisconnect
        
        logger.info(f"Sending Logon message")
        await self.connection.send_msg(logon_msg)
        logger.info("Logon message sent")
    
    async def _wait_for_network_connection(self, timeout: int = 10) -> bool:
        """Wait for network connection to be established."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.connection.connection_state == ConnectionState.NETWORK_CONN_ESTABLISHED:
                return True
            await asyncio.sleep(0.1)
        return False
    
    async def connect(self, max_attempts: int = 3) -> bool:
        """
        Connect to FIX server and authenticate.
        
        Args:
            max_attempts: Maximum number of connection attempts
            
        Returns:
            bool: True if connection and authentication successful, False otherwise
        """
        logger.info(f"Connecting to {self.session_type} session at {self.host}:{self.port}")
        
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        
        protocol = FIXProtocol44()
        journaler = Journaler(None)  # In-memory journaler
        
        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(f"Connection attempt {attempt}/{max_attempts} for {self.session_type} session")
                
                self.connection = SSLAsyncFIXConnection(
                    protocol=protocol,
                    sender_comp_id=self.sender_comp_id,
                    target_comp_id=self.target_comp_id,
                    journaler=journaler,
                    host=self.host,
                    port=self.port,
                    ssl_context=self.ssl_context,
                    heartbeat_period=30,
                    logger=logger
                )
                
                self.connection.on_message = self._on_message
                
                await self.connection.connect()
                
                if not await self._wait_for_network_connection():
                    logger.error("Timed out waiting for network connection")
                    continue
                
                await self._send_logon_message()
                
                for i in range(10):
                    await asyncio.sleep(1)
                    if self.authenticated:
                        logger.info(f"Successfully connected and authenticated to {self.session_type} session")
                        return True
                
                logger.error(f"Authentication failed for {self.session_type} session")
                
            except Exception as e:
                logger.error(f"Connection error details: {e}")
                if "SSL/TLS" in str(e):
                    logger.error("SSL/TLS handshake failed. Check your certificates.")
                
                logger.error(f"Error connecting to FIX server (attempt {attempt}/{max_attempts}): {e}")
                
                if attempt < max_attempts:
                    retry_delay = 2 ** (attempt - 1)  # Exponential backoff
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
        
        logger.error(f"Failed to connect after {max_attempts} attempts")
        return False
    
    async def disconnect(self) -> None:
        """Disconnect from FIX server."""
        if self.connection:
            logger.info("Disconnecting from FIX server")
            await self.connection.disconnect(ConnectionState.DISCONNECTED_BROKEN_CONN)
            logger.info("Disconnected from FIX server")
    
    async def _on_message(self, message: FIXMessage) -> None:
        """
        Process incoming FIX messages.
        
        Args:
            message: FIX message
        """
        try:
            msg_type = message.get_or_default(35, "")
            
            logger.debug(f"Received message type: {msg_type}")
            
            if msg_type == "A":  # Logon
                self._handle_logon(message)
            elif msg_type == "5":  # Logout
                self._handle_logout(message)
            elif msg_type == "3":  # Reject
                self._handle_reject(message)
            elif msg_type == "W":  # Market Data Snapshot
                self._handle_market_data_snapshot(message)
            elif msg_type == "X":  # Market Data Incremental Refresh
                self._handle_market_data_incremental(message)
            elif msg_type == "8":  # Execution Report
                self._handle_execution_report(message)
            elif msg_type == "9":  # Order Cancel Reject
                self._handle_order_cancel_reject(message)
            elif msg_type == "y":  # Security List
                self._handle_security_list(message)
            elif msg_type == "d":  # Security Definition
                self._handle_security_definition(message)
            elif msg_type == "Y":  # Market Data Request Reject
                self._handle_market_data_request_reject(message)
            else:
                logger.info(f"Unhandled message type: {msg_type}")
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    def _handle_logon(self, message: FIXMessage) -> None:
        """Handle Logon (35=A) message."""
        logger.info("Received Logon response (35=A)")
        self.authenticated = True
    
    def _handle_logout(self, message: FIXMessage) -> None:
        """Handle Logout (35=5) message."""
        text = message.get_or_default(58, "")
        logger.warning(f"Received Logout (35=5): {text}")
        self.authenticated = False
    
    def _handle_reject(self, message: FIXMessage) -> None:
        """Handle Reject (35=3) message."""
        text = message.get_or_default(58, "")
        logger.warning(f"Received Reject (35=3): {text}")
    
    def _handle_market_data_snapshot(self, message: FIXMessage) -> None:
        """Handle Market Data Snapshot (35=W) message."""
        try:
            symbol = message.get_or_default(55, "")
            md_req_id = message.get_or_default(262, "")
            
            logger.info(f"Received Market Data Snapshot for {symbol} (ReqID: {md_req_id})")
            
            if self.on_order_book_update:
                self.on_order_book_update(message)
                
        except Exception as e:
            logger.error(f"Error handling Market Data Snapshot: {e}")
    
    def _handle_market_data_incremental(self, message: FIXMessage) -> None:
        """Handle Market Data Incremental Refresh (35=X) message."""
        try:
            md_req_id = message.get_or_default(262, "")
            
            logger.debug(f"Received Market Data Incremental Refresh (ReqID: {md_req_id})")
            
            if self.on_order_book_update:
                self.on_order_book_update(message)
                
        except Exception as e:
            logger.error(f"Error handling Market Data Incremental Refresh: {e}")
    
    def _handle_execution_report(self, message: FIXMessage) -> None:
        """Handle Execution Report (35=8) message."""
        try:
            order_id = message.get_or_default(37, "")
            exec_type = message.get_or_default(150, "")
            
            logger.info(f"Received Execution Report for Order {order_id} (ExecType: {exec_type})")
            
            if self.on_execution_report:
                self.on_execution_report(message)
                
        except Exception as e:
            logger.error(f"Error handling Execution Report: {e}")
    
    def _handle_order_cancel_reject(self, message: FIXMessage) -> None:
        """Handle Order Cancel Reject (35=9) message."""
        try:
            order_id = message.get_or_default(37, "")
            cl_ord_id = message.get_or_default(11, "")
            reason = message.get_or_default(58, "")
            
            logger.warning(f"Order Cancel Reject for Order {order_id} (ClOrdID: {cl_ord_id}): {reason}")
            
            if self.on_order_cancel_reject:
                self.on_order_cancel_reject(message)
                
        except Exception as e:
            logger.error(f"Error handling Order Cancel Reject: {e}")
    
    def _handle_security_list(self, message: FIXMessage) -> None:
        """Handle SecurityList (35=y) message."""
        try:
            security_req_id = message.get_or_default(320, "")
            security_request_result = message.get_or_default(560, "")
            no_related_sym = int(message.get_or_default(146, "0"))
            
            securities = []
            for i in range(no_related_sym):
                symbol = message.get_or_default(55, "", i)
                security_type = message.get_or_default(167, "", i)
                security_sub_type = message.get_or_default(762, "", i)
                min_price_increment = message.get_or_default(969, "", i)
                margin_ratio = message.get_or_default(898, "", i)
                currency = message.get_or_default(15, "", i)
                min_trade_vol = message.get_or_default(562, "", i)
                position_limit = message.get_or_default(970, "", i)
                trading_status = message.get_or_default(1682, "", i)
                
                security = {
                    'symbol': symbol,
                    'security_type': security_type,
                    'security_sub_type': security_sub_type,
                    'min_price_increment': min_price_increment,
                    'margin_ratio': margin_ratio,
                    'currency': currency,
                    'min_trade_vol': min_trade_vol,
                    'position_limit': position_limit,
                    'trading_status': trading_status
                }
                securities.append(security)
            
            logger.info(f"SecurityList: ID={security_req_id}, Result={security_request_result}, "
                       f"Securities={len(securities)}")
            
            if self.on_security_list:
                self.on_security_list(message, securities)
                
        except Exception as e:
            logger.error(f"Error handling SecurityList: {e}")
    
    def _handle_security_definition(self, message: FIXMessage) -> None:
        """Handle SecurityDefinition (35=d) message."""
        try:
            security_update_action = message.get_or_default(980, "")
            last_update_time = message.get_or_default(779, "")
            symbol = message.get_or_default(55, "")
            security_type = message.get_or_default(167, "")
            security_sub_type = message.get_or_default(762, "")
            min_price_increment = message.get_or_default(969, "")
            margin_ratio = message.get_or_default(898, "")
            currency = message.get_or_default(15, "")
            min_trade_vol = message.get_or_default(562, "")
            position_limit = message.get_or_default(970, "")
            trading_status = message.get_or_default(1682, "")
            
            security_def = {
                'update_action': security_update_action,
                'last_update_time': last_update_time,
                'symbol': symbol,
                'security_type': security_type,
                'security_sub_type': security_sub_type,
                'min_price_increment': min_price_increment,
                'margin_ratio': margin_ratio,
                'currency': currency,
                'min_trade_vol': min_trade_vol,
                'position_limit': position_limit,
                'trading_status': trading_status
            }
            
            logger.info(f"SecurityDefinition: {symbol} - {security_update_action}")
            
            if self.on_security_definition:
                self.on_security_definition(message, security_def)
                
        except Exception as e:
            logger.error(f"Error handling SecurityDefinition: {e}")
    
    def _handle_market_data_request_reject(self, message: FIXMessage) -> None:
        """Handle MarketDataRequestReject (35=Y) message."""
        try:
            md_req_id = message.get_or_default(262, "")
            md_req_rej_reason = message.get_or_default(281, "")
            text = message.get_or_default(58, "")
            
            reason_map = {
                "0": "Unknown symbol",
                "1": "Duplicate MDReqID", 
                "5": "Unsupported market depth",
                "7": "Other"
            }
            
            reason_desc = reason_map.get(md_req_rej_reason, f"Unknown ({md_req_rej_reason})")
            
            logger.warning(f"MarketDataRequestReject: ID={md_req_id}, Reason={reason_desc}, Text={text}")
            
            if self.on_market_data_request_reject:
                self.on_market_data_request_reject(message)
                
        except Exception as e:
            logger.error(f"Error handling MarketDataRequestReject: {e}")
    
    def _get_next_request_id(self) -> str:
        """Generate a unique request ID."""
        self.request_id_counter += 1
        return f"{self.session_type}_{int(time.time())}_{self.request_id_counter}"
    
    async def request_security_list(self, security_list_request_type: str = "0") -> str:
        """
        Send SecurityListRequest (35=x) message.
        
        Args:
            security_list_request_type: Type of security list request
                "0" = All securities
                "1" = Symbol
                "2" = SecurityType
                "3" = Product
                "4" = TradingSessionID
                
        Returns:
            str: Request ID
        """
        security_req_id = self._get_next_request_id()
        
        message = FIXMessage("x")
        message.set(320, security_req_id)  # SecurityReqID
        message.set(559, security_list_request_type)  # SecurityListRequestType
        
        await self.connection.send_msg(message)
        logger.info(f"SecurityListRequest sent: ID={security_req_id}")
        return security_req_id
    
    async def send_market_data_request(
        self, 
        symbols: List[str], 
        market_depth: int = 10, 
        subscription_type: str = "1"
    ) -> str:
        """
        Send MarketDataRequest (35=V) message.
        
        Args:
            symbols: List of symbols to subscribe to
            market_depth: Market depth (number of levels)
            subscription_type: Subscription type
                "0" = Snapshot
                "1" = Subscribe
                "2" = Unsubscribe
                
        Returns:
            str: Request ID
        """
        md_req_id = self._get_next_request_id()
        
        message = FIXMessage("V")
        message.set(262, md_req_id)  # MDReqID
        message.set(263, subscription_type)  # SubscriptionRequestType
        message.set(264, str(market_depth))  # MarketDepth
        message.set(146, str(len(symbols)))  # NoRelatedSym
        
        for i, symbol in enumerate(symbols):
            message.set(55, symbol, i)  # Symbol
            message.set(167, "FXSPOT", i)  # SecurityType
        
        await self.connection.send_msg(message)
        logger.info(f"MarketDataRequest sent: ID={md_req_id}, Symbols={symbols}")
        return md_req_id
    
    async def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float] = None,
        time_in_force: str = "GTC",
        stop_price: Optional[float] = None,
        client_order_id: Optional[str] = None
    ) -> str:
        """
        Create a new order.
        
        Args:
            symbol: Trading symbol (e.g., "BTC-USD")
            side: Order side ("1" = Buy, "2" = Sell)
            order_type: Order type ("1" = Market, "2" = Limit, "3" = Stop, "4" = Stop Limit)
            quantity: Order quantity
            price: Order price (required for Limit and Stop Limit orders)
            time_in_force: Time in force
                "GTC" = Good Till Cancel
                "IOC" = Immediate or Cancel
                "FOK" = Fill or Kill
                "GTD" = Good Till Date
            stop_price: Stop price (required for Stop and Stop Limit orders)
            client_order_id: Client-assigned order ID (generated if not provided)
            
        Returns:
            str: Client order ID
        """
        if self.session_type != 'order_entry':
            logger.error("Cannot create order: not connected to order entry session")
            raise ValueError("Not connected to order entry session")
        
        if not self.authenticated:
            logger.error("Cannot create order: not authenticated")
            raise ValueError("Not authenticated")
        
        if order_type in ["2", "4"] and price is None:
            logger.error("Price is required for Limit and Stop Limit orders")
            raise ValueError("Price is required for Limit and Stop Limit orders")
        
        if order_type in ["3", "4"] and stop_price is None:
            logger.error("Stop price is required for Stop and Stop Limit orders")
            raise ValueError("Stop price is required for Stop and Stop Limit orders")
        
        if client_order_id is None:
            client_order_id = f"order_{uuid.uuid4().hex[:16]}"
        
        message = FIXMessage("D")  # New Order Single
        
        message.set(11, client_order_id)  # ClOrdID
        message.set(55, symbol)  # Symbol
        message.set(54, side)  # Side
        message.set(60, await self._get_utc_timestamp())  # TransactTime
        message.set(40, order_type)  # OrdType
        message.set(38, str(quantity))  # OrderQty
        
        if price is not None:
            message.set(44, str(price))  # Price
        
        if stop_price is not None:
            message.set(99, str(stop_price))  # StopPx
        
        tif_map = {
            "GTC": "1",  # Good Till Cancel
            "IOC": "3",  # Immediate or Cancel
            "FOK": "4",  # Fill or Kill
            "GTD": "6"   # Good Till Date
        }
        message.set(59, tif_map.get(time_in_force, "1"))  # TimeInForce
        
        await self.connection.send_msg(message)
        logger.info(f"Order created: {symbol} {side} {quantity} @ {price} (ID: {client_order_id})")
        
        return client_order_id
    
    async def cancel_order(self, client_order_id: str, original_client_order_id: str, symbol: str) -> str:
        """
        Cancel an existing order.
        
        Args:
            client_order_id: New client order ID for this cancel request
            original_client_order_id: Client order ID of the order to cancel
            symbol: Trading symbol
            
        Returns:
            str: Client order ID of the cancel request
        """
        if self.session_type != 'order_entry':
            logger.error("Cannot cancel order: not connected to order entry session")
            raise ValueError("Not connected to order entry session")
        
        if not self.authenticated:
            logger.error("Cannot cancel order: not authenticated")
            raise ValueError("Not authenticated")
        
        message = FIXMessage("F")  # Order Cancel Request
        
        message.set(11, client_order_id)  # ClOrdID
        message.set(41, original_client_order_id)  # OrigClOrdID
        message.set(55, symbol)  # Symbol
        message.set(60, await self._get_utc_timestamp())  # TransactTime
        
        await self.connection.send_msg(message)
        logger.info(f"Cancel request sent for order {original_client_order_id} (ID: {client_order_id})")
        
        return client_order_id
    
    async def modify_order(
        self,
        client_order_id: str,
        original_client_order_id: str,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float] = None
    ) -> str:
        """
        Modify an existing order.
        
        Args:
            client_order_id: New client order ID for this modify request
            original_client_order_id: Client order ID of the order to modify
            symbol: Trading symbol
            side: Order side ("1" = Buy, "2" = Sell)
            order_type: Order type ("1" = Market, "2" = Limit, "3" = Stop, "4" = Stop Limit)
            quantity: New order quantity
            price: New order price
            
        Returns:
            str: Client order ID of the modify request
        """
        if self.session_type != 'order_entry':
            logger.error("Cannot modify order: not connected to order entry session")
            raise ValueError("Not connected to order entry session")
        
        if not self.authenticated:
            logger.error("Cannot modify order: not authenticated")
            raise ValueError("Not authenticated")
        
        message = FIXMessage("G")  # Order Cancel/Replace Request
        
        message.set(11, client_order_id)  # ClOrdID
        message.set(41, original_client_order_id)  # OrigClOrdID
        message.set(55, symbol)  # Symbol
        message.set(54, side)  # Side
        message.set(60, await self._get_utc_timestamp())  # TransactTime
        message.set(40, order_type)  # OrdType
        message.set(38, str(quantity))  # OrderQty
        
        if price is not None:
            message.set(44, str(price))  # Price
        
        await self.connection.send_msg(message)
        logger.info(f"Modify request sent for order {original_client_order_id} (ID: {client_order_id})")
        
        return client_order_id
