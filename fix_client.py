"""
FIX Client for Coinbase International Exchange.
Handles FIX connectivity, authentication, and message processing.
"""
import asyncio
import hmac
import hashlib
import base64
import time
import logging
import ssl
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any, Union
import asyncfix
from asyncfix.message import FIXMessage
from asyncfix.protocol import FIXProtocolBase, FIXProtocol44
from asyncfix.session import FIXSession
from asyncfix.connection import AsyncFIXConnection, ConnectionState
from asyncfix.journaler import Journaler
from asyncfix import FTag, FMsg

import config

logger = logging.getLogger("coinbase_hft.fix_client")

class CoinbaseFIXClient:
    """
    FIX client for Coinbase International Exchange.
    Handles connection, authentication, and message processing.
    """
    def __init__(
        self,
        session_type: str,
        on_execution_report: Optional[Callable[[FIXMessage], None]] = None,
        on_market_data: Optional[Callable[[FIXMessage], None]] = None,
        on_position_report: Optional[Callable[[FIXMessage], None]] = None,
        test_mode: bool = False,
    ):
        """
        Initialize the FIX client.
        
        Args:
            session_type: Type of FIX session ('order_entry', 'market_data', or 'drop_copy')
            on_execution_report: Callback for execution reports
            on_market_data: Callback for market data messages
            on_position_report: Callback for position reports
            test_mode: Run in test mode without real connection
        """
        self.session_type = session_type
        self.on_execution_report = on_execution_report
        self.on_market_data = on_market_data
        self.on_position_report = on_position_report
        self.test_mode = test_mode
        
        if session_type == "order_entry":
            self.host = config.FIX_ORDER_ENTRY_HOST
            self.port = config.FIX_ORDER_ENTRY_PORT
        elif session_type == "market_data":
            self.host = config.FIX_MARKET_DATA_HOST
            self.port = config.FIX_MARKET_DATA_PORT
        elif session_type == "drop_copy":
            self.host = config.FIX_DROP_COPY_HOST
            self.port = config.FIX_DROP_COPY_PORT
        else:
            raise ValueError(f"Invalid session type: {session_type}")
        
        self.sender_comp_id = config.CB_INTX_SENDER_COMPID
        
        if session_type == "order_entry":
            self.target_comp_id = config.FIX_TARGET_COMPID_ORDER_ENTRY
        elif session_type == "market_data":
            self.target_comp_id = config.FIX_TARGET_COMPID_MARKET_DATA
        elif session_type == "drop_copy":
            self.target_comp_id = config.FIX_TARGET_COMPID_DROP_COPY
        else:
            raise ValueError(f"Invalid session type: {session_type}")
        self.api_key = config.CB_INTX_API_KEY
        self.api_secret = config.CB_INTX_API_SECRET
        self.passphrase = config.CB_INTX_PASSPHRASE
        
        self.protocol = None
        self.connection = None
        self.journaler = None
        self.connected = False
        self.authenticated = False
        
        self.next_client_order_id = int(time.time())
        self.next_request_id = int(time.time())
        
    async def connect(self, max_retries: int = None) -> bool:
        """
        Establish FIX connection and authenticate with retry mechanism.
        
        Args:
            max_retries: Maximum number of connection attempts (defaults to config.FIX_MAX_RETRIES)
            
        Returns:
            bool: True if connection and authentication successful
        """
        if self.test_mode:
            logger.info(f"Test mode enabled for {self.session_type} session")
            self.connected = True
            self.authenticated = True
            return True
            
        network_timeout = config.FIX_NETWORK_TIMEOUT  # seconds
        auth_timeout = config.FIX_AUTH_TIMEOUT  # seconds
        max_retries = max_retries if max_retries is not None else config.FIX_MAX_RETRIES
        retry_delay = 2  # Initial delay in seconds
        
        for attempt in range(1, max_retries + 1):
            try:
                if attempt > 1:
                    logger.info(f"Connection attempt {attempt}/{max_retries} for {self.session_type} session")
                
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                ssl_context.set_ciphers('ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-SHA256:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-SHA384')
                
                self.protocol = FIXProtocol44()  # Using FIX 4.4 protocol as base for FIX 5.0
                
                store_dir = "store"
                import os
                os.makedirs(store_dir, exist_ok=True)
                
                timestamp = int(time.time())
                db_path = f"{store_dir}/{self.session_type}_{timestamp}_session.db"
                
                if self.journaler:
                    try:
                        if hasattr(self.journaler, 'conn') and self.journaler.conn:
                            self.journaler.conn.close()
                    except Exception as e:
                        logger.warning(f"Error closing previous journaler connection: {e}")
                
                self.journaler = Journaler(db_path)
                logger.debug(f"Created new journaler with database: {db_path}")
                
                # Create AsyncFIXConnection
                self.connection = AsyncFIXConnection(
                    protocol=self.protocol,
                    sender_comp_id=self.sender_comp_id,
                    target_comp_id=self.target_comp_id,
                    journaler=self.journaler,
                    host=self.host,
                    port=self.port,
                    heartbeat_period=config.FIX_HEARTBEAT_INTERVAL,
                    logger=logger,
                )
                
                self.connection.on_message = self._on_message
                
                try:
                    if self.test_mode:
                        self.connected = True
                        logger.info(f"[TEST MODE] Simulated connection to {self.host}:{self.port} for {self.session_type} session")
                    else:
                        await self.connection.connect()
                        self.connected = True
                        logger.info(f"Connected to {self.host}:{self.port} for {self.session_type} session")
                except Exception as e:
                    logger.error(f"Connection error details: {str(e)}")
                    if "SSL" in str(e) or "TLS" in str(e):
                        logger.error("SSL/TLS handshake failed. Check your certificates.")
                    if "Connection refused" in str(e):
                        logger.error("Connection refused. Your IP may not be whitelisted.")
                    if "timeout" in str(e).lower():
                        logger.error("Connection timeout. Your IP may not be whitelisted or there may be network issues.")
                    raise
                
                if self.test_mode:
                    # In test mode, simulate successful connection
                    self.authenticated = True
                    logger.info(f"[TEST MODE] Simulated successful authentication for {self.session_type} session")
                    return True
                else:
                    connection_start = time.time()
                    while (self.connection.connection_state < ConnectionState.NETWORK_CONN_ESTABLISHED and 
                           time.time() - connection_start < network_timeout):
                        await asyncio.sleep(0.1)
                        
                    if self.connection.connection_state < ConnectionState.NETWORK_CONN_ESTABLISHED:
                        logger.error(f"Network connection timeout: state={self.connection.connection_state}")
                        self.connected = False
                        
                        if attempt < max_retries:
                            backoff = retry_delay * (2 ** (attempt - 1))
                            logger.info(f"Retrying in {backoff} seconds...")
                            await asyncio.sleep(backoff)
                        continue
                
                # Authenticate
                auth_success = await self._authenticate()
                if not auth_success:
                    logger.error("Failed to send authentication request")
                    if attempt < max_retries:
                        backoff = retry_delay * (2 ** (attempt - 1))
                        logger.info(f"Retrying in {backoff} seconds...")
                        await asyncio.sleep(backoff)
                    continue
                
                auth_start = time.time()
                while (not self.authenticated and 
                       time.time() - auth_start < auth_timeout):
                    await asyncio.sleep(0.1)
                
                if not self.authenticated:
                    logger.error(f"Authentication timeout after {auth_timeout} seconds")
                    
                    if attempt < max_retries:
                        backoff = retry_delay * (2 ** (attempt - 1))
                        logger.info(f"Retrying in {backoff} seconds...")
                        await asyncio.sleep(backoff)
                    continue
                
                logger.info(f"Successfully authenticated {self.session_type} session")
                return True
                
            except Exception as e:
                logger.error(f"Error connecting to FIX server (attempt {attempt}/{max_retries}): {e}")
                self.connected = False
                self.authenticated = False
                
                if attempt < max_retries:
                    backoff = retry_delay * (2 ** (attempt - 1))
                    logger.info(f"Retrying in {backoff} seconds...")
                    await asyncio.sleep(backoff)
        
        logger.error(f"Failed to connect after {max_retries} attempts")
        return False
    
    async def disconnect(self) -> None:
        """Disconnect from FIX server and clean up resources."""
        try:
            if self.connection and self.connected:
                await self.connection.disconnect()
            
            if self.journaler and hasattr(self.journaler, 'conn') and self.journaler.conn:
                try:
                    self.journaler.conn.close()
                    logger.debug(f"Closed journaler connection for {self.session_type} session")
                except Exception as e:
                    logger.warning(f"Error closing journaler connection: {e}")
            
            self.connected = False
            self.authenticated = False
            logger.info(f"Disconnected from {self.session_type} session")
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")
    
    async def _authenticate(self) -> bool:
        """
        Authenticate with the FIX server using HMAC-SHA256.
        
        Returns:
            bool: True if authentication request was sent successfully
        """
        try:
            # In test mode, simulate successful authentication
            if self.test_mode:
                logger.info(f"[TEST MODE] Simulated authentication for {self.session_type} session")
                return True
                
            if not all([self.api_key, self.api_secret, self.passphrase]):
                logger.error("Cannot authenticate: Missing API credentials")
                return False
                
            # Generate UTC timestamp in milliseconds format
            utc_timestamp = self._get_utc_timestamp()
            
            # Signature format: Time + Client API Key + Session + Passphrase
            message = f"{utc_timestamp}{self.api_key}{self.target_comp_id}{self.passphrase}"
            
            signature = hmac.new(
                base64.b64decode(self.api_secret),
                message.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            logon_msg = FIXMessage(FMsg.LOGON)
            logon_msg.set(FTag.EncryptMethod, "0")  # No encryption
            logon_msg.set(FTag.HeartBtInt, str(config.FIX_HEARTBEAT_INTERVAL))
            logon_msg.set(FTag.ResetSeqNumFlag, "Y")  # Reset sequence numbers
            logon_msg.set(FTag.Username, self.api_key)  # Tag 553: API Key
            logon_msg.set(FTag.Password, self.passphrase)  # Tag 554: Passphrase
            logon_msg.set(FTag.Text, signature)  # Tag 58: HMAC signature
            logon_msg.set(1137, "9")  # DefaultApplVerID = FIX.5.0SP2
            
            logon_msg.set(8001, "Q")  # DefaultSelfTradePreventionStrategy: Cancel both orders
            logon_msg.set(8013, "Y")  # CancelOrdersOnDisconnect: Only cancel orders from this session
            logon_msg.set(8014, "Y")  # CancelOrdersOnInternalDisconnect: Cancel on internal disconnect
            
            logger.debug(f"Sending authentication request for {self.session_type} session")
            await self.connection.send_msg(logon_msg)
            
            # Return True to indicate the authentication request was sent successfully
            return True
            
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return False
    
    def _on_message(self, message: FIXMessage) -> None:
        """
        Process incoming FIX messages.
        
        Args:
            message: FIX message
        """
        try:
            msg_type = message.get(FTag.MsgType)
            
            if msg_type == FMsg.LOGON:
                self.authenticated = True
                logger.info(f"Logon successful for {self.session_type} session")
                return
            
            if msg_type == FMsg.LOGOUT:
                text = message.get(FTag.Text, "No reason provided")
                logger.warning(f"Received Logout: {text}")
                self.authenticated = False
                return
            
            if msg_type == FMsg.HEARTBEAT:
                return  # Silently process heartbeats
            
            if msg_type == FMsg.TESTREQUEST:
                self._handle_test_request(message)
                return
            
            if msg_type == FMsg.REJECT:
                self._handle_reject(message)
                return
            
            if msg_type == FMsg.BUSINESSMESSAGEREJECT:
                self._handle_business_reject(message)
                return
            
            if msg_type == FMsg.EXECUTIONREPORT and self.on_execution_report:
                self._log_execution_report(message)
                self.on_execution_report(message)
                return
            
            if msg_type == FMsg.MARKETDATASNAPSHOTFULLREFRESH and self.on_market_data:
                self.on_market_data(message)
                return
            
            if msg_type == FMsg.MARKETDATAINCREMENTALREFRESH and self.on_market_data:
                self.on_market_data(message)
                return
            
            if msg_type == FMsg.POSITIONREPORT and self.on_position_report:
                self.on_position_report(message)
                return
            
            logger.debug(f"Received unhandled message type: {msg_type}")
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    def _handle_test_request(self, message: FIXMessage) -> None:
        """
        Handle FIX Test Request message.
        
        Args:
            message: Test Request message
        """
        try:
            test_req_id = message.get(FTag.TestReqID, "")
            
            heartbeat = FIXMessage(FMsg.HEARTBEAT)
            if test_req_id:
                heartbeat.set(FTag.TestReqID, test_req_id)
            
            asyncio.create_task(self.connection.send_msg(heartbeat))
            
        except Exception as e:
            logger.error(f"Error handling test request: {e}")
    
    def _handle_reject(self, message: FIXMessage) -> None:
        """
        Handle FIX Reject message.
        
        Args:
            message: Reject message
        """
        try:
            ref_seq_num = message.get(FTag.RefSeqNum, "Unknown")
            ref_tag_id = message.get(FTag.RefTagID, "Unknown")
            ref_msg_type = message.get(FTag.RefMsgType, "Unknown")
            reason = message.get(FTag.SessionRejectReason, "No reason provided")
            
            logger.warning(f"Session level Reject: RefSeqNum={ref_seq_num}, "
                          f"RefTagID={ref_tag_id}, RefMsgType={ref_msg_type}, "
                          f"Reason={reason}")
            
        except Exception as e:
            logger.error(f"Error handling reject: {e}")
    
    def _handle_business_reject(self, message: FIXMessage) -> None:
        """
        Handle FIX Business Message Reject.
        
        Args:
            message: Business Message Reject
        """
        try:
            ref_seq_num = message.get(FTag.RefSeqNum, "Unknown")
            ref_msg_type = message.get(FTag.RefMsgType, "Unknown")
            business_reject_reason = message.get(FTag.BusinessRejectReason, "0")
            text = message.get(FTag.Text, "No reason provided")
            
            logger.warning(f"Business Reject: RefSeqNum={ref_seq_num}, "
                          f"RefMsgType={ref_msg_type}, BusinessRejectReason={business_reject_reason}, "
                          f"Text={text}")
            
        except Exception as e:
            logger.error(f"Error handling business reject: {e}")
    
    def _log_execution_report(self, message: FIXMessage) -> None:
        """
        Log execution report details for debugging.
        
        Args:
            message: FIX execution report message
        """
        try:
            clord_id = message.get(FTag.ClOrdID, "")
            exec_type = message.get(150, "")
            ord_status = message.get(FTag.OrdStatus, "")
            symbol = message.get(FTag.Symbol, "")
            side = message.get(FTag.Side, "")
            
            exec_type_map = {
                "0": "New", "1": "Partial Fill", "2": "Fill", 
                "4": "Canceled", "5": "Replaced", "8": "Rejected",
                "C": "Expired", "L": "Stop Triggered"
            }
            
            ord_status_map = {
                "0": "New", "1": "Partially Filled", "2": "Filled",
                "4": "Canceled", "5": "Replaced", "8": "Rejected", "C": "Expired"
            }
            
            exec_desc = exec_type_map.get(exec_type, exec_type)
            status_desc = ord_status_map.get(ord_status, ord_status)
            
            logger.info(f"ExecutionReport: {clord_id} {symbol} {side} - {exec_desc} ({status_desc})")
            
            if exec_type == "8":
                reject_reason = message.get(103, "Unknown")
                text = message.get(FTag.Text, "")
                logger.warning(f"Order rejected: {reject_reason} - {text}")
            
        except Exception as e:
            logger.error(f"Error logging execution report: {e}")
    
    async def subscribe_market_data(self, symbol: str, depth: int = 10) -> bool:
        """
        Subscribe to market data for a symbol.
        
        Args:
            symbol: Trading symbol (e.g., 'BTC-USD')
            depth: Order book depth
            
        Returns:
            bool: True if subscription request sent successfully
        """
        if not self.authenticated or self.session_type != "market_data":
            logger.error("Cannot subscribe to market data: Not authenticated or wrong session type")
            return False
            
        if self.test_mode:
            logger.info(f"Test mode: Simulating market data subscription for {symbol}")
            return True
        
        try:
            req_id = str(self._get_next_request_id())
            
            mdr = FIXMessage(FMsg.MARKETDATAREQUEST)
            mdr.set(FTag.MDReqID, req_id)
            mdr.set(FTag.SubscriptionRequestType, "1")  # Snapshot + Updates
            mdr.set(FTag.MarketDepth, "0")  # Full Book
            mdr.set(FTag.MDUpdateType, "0")  # Full Refresh
            mdr.set(FTag.AggregatedBook, "1")  # Yes
            
            mdr.set(FTag.NoMDEntryTypes, "2")
            
            mdr.set(FTag.MDEntryType, "0")  # Bid
            
            mdr.set(FTag.MDEntryType, "1")  # Offer
            
            mdr.set(FTag.NoRelatedSym, "1")
            mdr.set(FTag.Symbol, symbol)
            
            await self.connection.send_msg(mdr)
            logger.info(f"Sent market data subscription request for {symbol}")
            return True
            
        except Exception as e:
            logger.error(f"Error subscribing to market data: {e}")
            return False
    
    async def unsubscribe_market_data(self, symbol: str) -> bool:
        """
        Unsubscribe from market data for a symbol.
        
        Args:
            symbol: Trading symbol (e.g., 'BTC-USD')
            
        Returns:
            bool: True if unsubscription request sent successfully
        """
        if not self.authenticated or self.session_type != "market_data":
            logger.error("Cannot unsubscribe from market data: Not authenticated or wrong session type")
            return False
            
        if self.test_mode:
            logger.info(f"Test mode: Simulating market data unsubscription for {symbol}")
            return True
        
        try:
            req_id = str(self._get_next_request_id())
            
            mdr = FIXMessage(FMsg.MARKETDATAREQUEST)
            mdr.set(FTag.MDReqID, req_id)
            mdr.set(FTag.SubscriptionRequestType, "2")  # Disable previous subscription
            
            mdr.set(FTag.NoRelatedSym, "1")
            mdr.set(FTag.Symbol, symbol)
            
            # Send Market Data Request
            await self.connection.send_msg(mdr)
            logger.info(f"Sent market data unsubscription request for {symbol}")
            return True
            
        except Exception as e:
            logger.error(f"Error unsubscribing from market data: {e}")
            return False
    
    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float] = None,
        time_in_force: str = "GTC",
        order_id: Optional[str] = None,
        portfolio_id: Optional[str] = None,
        post_only: bool = False,
        self_trade_prevention: str = "Q",  # Default: Cancel both orders
    ) -> str:
        """
        Place a new order.
        
        Args:
            symbol: Trading symbol (e.g., 'BTC-USD')
            side: Order side ('BUY' or 'SELL')
            order_type: Order type ('LIMIT', 'MARKET', 'STOP', 'STOP_LIMIT')
            quantity: Order quantity
            price: Order price (required for LIMIT and STOP_LIMIT orders)
            time_in_force: Time in force ('GTC', 'IOC', 'FOK', 'GTD')
            order_id: Custom order ID (generated if not provided)
            
        Returns:
            str: Client order ID
        """
        if not self.authenticated or self.session_type != "order_entry":
            logger.error("Cannot place order: Not authenticated or wrong session type")
            return ""
            
        if self.test_mode:
            client_order_id = order_id or f"TEST-{self._get_next_client_order_id()}"
            logger.info(f"Test mode: Simulating {order_type} {side} order for {quantity} {symbol} at price {price}")
            return client_order_id
        
        try:
            # Generate UUID for client order ID if not provided
            if not order_id:
                client_order_id = str(uuid.uuid4())
            else:
                client_order_id = order_id
            
            side_map = {"BUY": "1", "SELL": "2"}
            fix_side = side_map.get(side.upper())
            if not fix_side:
                raise ValueError(f"Invalid side: {side}")
            
            order_type_map = {
                "MARKET": "1",
                "LIMIT": "2",
                "STOP": "3",
                "STOP_LIMIT": "4",
                "TAKE_PROFIT_STOP_LOSS": "O",  # TP/SL order type
            }
            fix_order_type = order_type_map.get(order_type.upper())
            if not fix_order_type:
                raise ValueError(f"Invalid order type: {order_type}")
            
            tif_map = {
                "DAY": "0",
                "GTC": "1",  # Good Till Cancel
                "IOC": "3",  # Immediate or Cancel
                "FOK": "4",  # Fill or Kill
                "GTD": "6",  # Good Till Date
            }
            fix_tif = tif_map.get(time_in_force.upper())
            if not fix_tif:
                raise ValueError(f"Invalid time in force: {time_in_force}")
            
            nos = FIXMessage(FMsg.NEWORDERSINGLE)
            nos.set(FTag.ClOrdID, client_order_id)
            nos.set(FTag.Symbol, symbol)
            nos.set(FTag.Side, fix_side)
            nos.set(FTag.TransactTime, self._get_utc_timestamp())
            nos.set(FTag.OrdType, fix_order_type)
            nos.set(FTag.OrderQty, str(quantity))
            nos.set(FTag.TimeInForce, fix_tif)
            
            if portfolio_id:
                nos.set(453, "1")  # NoPartyIDs = 1
                nos.set(448, portfolio_id)  # PartyID = portfolio UUID
                nos.set(452, "24")  # PartyRole = 24 (Customer account)
            
            nos.set(8000, self_trade_prevention)  # SelfTradePreventionStrategy
            
            if post_only:
                nos.set(18, "6")  # ExecInst = 6 (Post only)
            
            if order_type.upper() in ["LIMIT", "STOP_LIMIT"] and price is not None:
                nos.set(FTag.Price, str(price))
            
            if order_type.upper() in ["STOP", "STOP_LIMIT", "TAKE_PROFIT_STOP_LOSS"] and price is not None:
                nos.set(FTag.StopPx, str(price))
            
            await self.connection.send_msg(nos)
            logger.info(f"Placed {order_type} {side} order for {quantity} {symbol} "
                       f"with client order ID {client_order_id}")
            
            return client_order_id
            
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return ""
    
    async def cancel_order(self, client_order_id: str, symbol: str, portfolio_id: Optional[str] = None) -> str:
        """
        Cancel an existing order.
        
        Args:
            client_order_id: Client order ID of the order to cancel
            symbol: Trading symbol (e.g., 'BTC-USD')
            portfolio_id: Portfolio UUID (optional)
            
        Returns:
            str: Client order ID of the cancel request
        """
        if not self.authenticated or self.session_type != "order_entry":
            logger.error("Cannot cancel order: Not authenticated or wrong session type")
            return ""
            
        if self.test_mode:
            cancel_client_order_id = str(uuid.uuid4())
            logger.info(f"Test mode: Simulating cancel for order {client_order_id} with cancel ID {cancel_client_order_id}")
            return cancel_client_order_id
        
        try:
            # Generate UUID for cancel order ID
            cancel_client_order_id = str(uuid.uuid4())
            
            # Create Order Cancel Request message
            ocr = FIXMessage(FMsg.ORDERCANCELREQUEST)
            ocr.set(FTag.OrigClOrdID, client_order_id)
            ocr.set(FTag.ClOrdID, cancel_client_order_id)
            ocr.set(FTag.Symbol, symbol)
            ocr.set(FTag.TransactTime, self._get_utc_timestamp())
            
            if portfolio_id:
                ocr.set(453, "1")  # NoPartyIDs = 1
                ocr.set(448, portfolio_id)  # PartyID = portfolio UUID
                ocr.set(452, "24")  # PartyRole = 24 (Customer account)
            
            # Send Order Cancel Request message
            await self.connection.send_msg(ocr)
            logger.info(f"Sent cancel request for order {client_order_id} with cancel ID {cancel_client_order_id}")
            
            return cancel_client_order_id
            
        except Exception as e:
            logger.error(f"Error canceling order: {e}")
            return ""
    
    async def modify_order(
        self,
        original_client_order_id: str,
        symbol: str,
        quantity: Optional[float] = None,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        stop_limit_price: Optional[float] = None,
        portfolio_id: Optional[str] = None,
    ) -> str:
        """
        Modify an existing order using OrderCancelReplaceRequest.
        
        Args:
            original_client_order_id: Client order ID of the order to modify
            symbol: Trading symbol (e.g., 'BTC-USD')
            quantity: New order quantity (optional)
            price: New order price (optional)
            stop_price: New stop price for stop orders (optional)
            stop_limit_price: New stop limit price for TP/SL orders (optional)
            portfolio_id: Portfolio UUID (optional)
            
        Returns:
            str: New client order ID
        """
        if not self.authenticated or self.session_type != "order_entry":
            logger.error("Cannot modify order: Not authenticated or wrong session type")
            return ""
            
        if self.test_mode:
            new_client_order_id = str(uuid.uuid4())
            logger.info(f"Test mode: Simulating modify for order {original_client_order_id} with new ID {new_client_order_id}")
            return new_client_order_id
        
        try:
            # Generate UUID for new client order ID
            new_client_order_id = str(uuid.uuid4())
            
            # Create Order Cancel Replace Request message
            ocrr = FIXMessage(FMsg.ORDERCANCELREPLACEREQUEST)
            ocrr.set(FTag.OrigClOrdID, original_client_order_id)
            ocrr.set(FTag.ClOrdID, new_client_order_id)
            ocrr.set(FTag.Symbol, symbol)
            ocrr.set(FTag.TransactTime, self._get_utc_timestamp())
            
            if portfolio_id:
                ocrr.set(453, "1")  # NoPartyIDs = 1
                ocrr.set(448, portfolio_id)  # PartyID = portfolio UUID
                ocrr.set(452, "24")  # PartyRole = 24 (Customer account)
            
            if quantity is not None:
                ocrr.set(FTag.OrderQty, str(quantity))
                
            if price is not None:
                ocrr.set(FTag.Price, str(price))
                
            if stop_price is not None:
                ocrr.set(FTag.StopPx, str(stop_price))
                
            if stop_limit_price is not None:
                ocrr.set(3040, str(stop_limit_price))  # StopLimitPx
            
            # Send Order Cancel Replace Request message
            await self.connection.send_msg(ocrr)
            logger.info(f"Sent modify request for order {original_client_order_id} with new ID {new_client_order_id}")
            
            return new_client_order_id
            
        except Exception as e:
            logger.error(f"Error modifying order: {e}")
            return ""
            
    async def mass_cancel_orders(
        self,
        symbol: Optional[str] = None,
        side: Optional[str] = None,
        portfolio_id: Optional[str] = None,
    ) -> str:
        """
        Cancel multiple orders using OrderMassCancelRequest.
        
        Args:
            symbol: Trading symbol (e.g., 'BTC-USD'). If not provided, cancels all symbols.
            side: Order side ('BUY' or 'SELL'). If not provided, cancels all sides.
            portfolio_id: Portfolio UUID (optional)
            
        Returns:
            str: Client order ID for the mass cancel request
        """
        if not self.authenticated or self.session_type != "order_entry":
            logger.error("Cannot mass cancel orders: Not authenticated or wrong session type")
            return ""
            
        if self.test_mode:
            client_order_id = str(uuid.uuid4())
            logger.info(f"Test mode: Simulating mass cancel with ID {client_order_id}")
            return client_order_id
        
        try:
            # Generate UUID for client order ID
            client_order_id = str(uuid.uuid4())
            
            # Create Order Mass Cancel Request message
            omcr = FIXMessage("q")  # OrderMassCancelRequest msgtype
            omcr.set(FTag.ClOrdID, client_order_id)
            omcr.set(FTag.TransactTime, self._get_utc_timestamp())
            
            if side:
                fix_side = "1" if side.upper() == "BUY" else "2"
                omcr.set(FTag.Side, fix_side)
            
            if symbol:
                omcr.set(FTag.Symbol, symbol)
            
            if portfolio_id:
                omcr.set(453, "1")  # NoPartyIDs = 1
                omcr.set(448, portfolio_id)  # PartyID = portfolio UUID
                omcr.set(452, "24")  # PartyRole = 24 (Customer account)
            
            # Send Order Mass Cancel Request message
            await self.connection.send_msg(omcr)
            logger.info(f"Sent mass cancel request with ID {client_order_id}")
            
            return client_order_id
            
        except Exception as e:
            logger.error(f"Error sending mass cancel request: {e}")
            return ""
            
    async def request_positions(self) -> bool:
        """
        Request current positions.
        
        Returns:
            bool: True if request sent successfully
        """
        if not self.authenticated or self.session_type != "order_entry":
            logger.error("Cannot request positions: Not authenticated or wrong session type")
            return False
            
        if self.test_mode:
            logger.info("Test mode: Simulating position request")
            return True
        
        try:
            req_id = str(self._get_next_request_id())
            
            rfp = FIXMessage(FMsg.REQUESTFORPOSITIONS)
            rfp.set(FTag.PosReqID, req_id)
            rfp.set(FTag.PosReqType, "0")  # Positions
            rfp.set(FTag.SubscriptionRequestType, "1")  # Snapshot
            rfp.set(FTag.TransactTime, self._get_utc_timestamp())
            
            await self.connection.send_msg(rfp)
            logger.info("Sent position request")
            return True
            
        except Exception as e:
            logger.error(f"Error requesting positions: {e}")
            return False
    
    def _get_next_client_order_id(self) -> str:
        """
        Generate and return the next client order ID.
        
        Returns:
            str: Next client order ID in UUID format
        """
        return str(uuid.uuid4())
    
    def _get_next_request_id(self) -> int:
        """
        Generate and return the next request ID.
        
        Returns:
            int: Next request ID
        """
        self.next_request_id += 1
        return self.next_request_id
    
    def _get_utc_timestamp(self) -> str:
        """
        Generate UTC timestamp in FIX format.
        
        Returns:
            str: UTC timestamp in format YYYYMMDD-HH:MM:SS.sss
        """
        return datetime.utcnow().strftime("%Y%m%d-%H:%M:%S.%f")[:-3]
