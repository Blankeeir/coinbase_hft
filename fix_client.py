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
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any, Union
import asyncfix
from asyncfix.message import FIXMessage
from asyncfix.protocol import FIXProtocolBase, FIXProtocol44
from asyncfix.session import FIXSession
from asyncfix.connection import AsyncFIXConnection
from asyncfix.journaler import Journaler

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
    ):
        """
        Initialize the FIX client.
        
        Args:
            session_type: Type of FIX session ('order_entry', 'market_data', or 'drop_copy')
            on_execution_report: Callback for execution reports
            on_market_data: Callback for market data messages
            on_position_report: Callback for position reports
        """
        self.session_type = session_type
        self.on_execution_report = on_execution_report
        self.on_market_data = on_market_data
        self.on_position_report = on_position_report
        
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
        self.target_comp_id = config.FIX_TARGET_COMPID
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
        
    async def connect(self) -> bool:
        """
        Establish FIX connection and authenticate.
        
        Returns:
            bool: True if connection and authentication successful
        """
        try:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            self.protocol = FIXProtocol44()  # Using FIX 4.4 protocol as base for FIX 5.0
            
            store_dir = "store"
            import os
            os.makedirs(store_dir, exist_ok=True)
            self.journaler = Journaler(f"{store_dir}/{self.session_type}_session.db")
            
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
            
            await self.connection.connect()
            self.connected = True
            logger.info(f"Connected to {self.host}:{self.port} for {self.session_type} session")
            
            # Authenticate
            await self._authenticate()
            
            return self.authenticated
            
        except Exception as e:
            logger.error(f"Error connecting to FIX server: {e}")
            self.connected = False
            self.authenticated = False
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from FIX server."""
        try:
            if self.connection and self.connected:
                await self.connection.disconnect()
            self.connected = False
            self.authenticated = False
            logger.info(f"Disconnected from {self.session_type} session")
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")
    
    async def _authenticate(self) -> bool:
        """
        Authenticate with the FIX server using HMAC-SHA256.
        
        Returns:
            bool: True if authentication successful
        """
        try:
            timestamp = str(int(time.time()))
            message = f"{timestamp}A{config.CB_INTX_SENDER_COMPID}COINBASE"
            
            signature = hmac.new(
                base64.b64decode(self.api_secret),
                message.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            custom_fields = {
                8013: self.api_key,       # CB API Key
                8014: signature,          # CB API Sign
                8015: timestamp,          # CB API Timestamp
                8016: self.passphrase,    # CB API Passphrase
                1137: 9,                  # DefaultApplVerID = FIX.5.0SP2
            }
            
            await self.connection.send_logon(
                encrypt_method=0,  # No encryption
                heartbeat_interval=config.FIX_HEARTBEAT_INTERVAL,
                reset_seq_num=True,
                custom_fields=custom_fields
            )
            
            auth_timeout = 10  # seconds
            auth_start = time.time()
            while not self.authenticated and time.time() - auth_start < auth_timeout:
                await asyncio.sleep(0.1)
            
            if self.authenticated:
                logger.info(f"Authenticated {self.session_type} session")
            else:
                logger.error(f"Authentication timeout for {self.session_type} session")
            
            return self.authenticated
            
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
            msg_type = message.get_field(35)
            
            if msg_type == "A":
                self.authenticated = True
                logger.info(f"Logon successful for {self.session_type} session")
                return
            
            if msg_type == "5":
                text = message.get_field(58, "No reason provided")
                logger.warning(f"Received Logout: {text}")
                self.authenticated = False
                return
            
            if msg_type == "0":
                return  # Silently process heartbeats
            
            if msg_type == "1":
                self._handle_test_request(message)
                return
            
            if msg_type == "3":
                self._handle_reject(message)
                return
            
            if msg_type == "j":
                self._handle_business_reject(message)
                return
            
            if msg_type == "8" and self.on_execution_report:
                self.on_execution_report(message)
                return
            
            if msg_type == "W" and self.on_market_data:
                self.on_market_data(message)
                return
            
            if msg_type == "X" and self.on_market_data:
                self.on_market_data(message)
                return
            
            if msg_type == "AP" and self.on_position_report:
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
            test_req_id = message.get_field(112, "")
            
            heartbeat = FIXMessage()
            heartbeat.set_field(35, "0")  # MsgType = Heartbeat
            if test_req_id:
                heartbeat.set_field(112, test_req_id)  # TestReqID
            
            asyncio.create_task(self.connection.send_message(heartbeat))
            
        except Exception as e:
            logger.error(f"Error handling test request: {e}")
    
    def _handle_reject(self, message: FIXMessage) -> None:
        """
        Handle FIX Reject message.
        
        Args:
            message: Reject message
        """
        try:
            ref_seq_num = message.get_field(45, "Unknown")
            ref_tag_id = message.get_field(371, "Unknown")
            ref_msg_type = message.get_field(372, "Unknown")
            reason = message.get_field(373, "No reason provided")
            
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
            ref_seq_num = message.get_field(45, "Unknown")
            ref_msg_type = message.get_field(372, "Unknown")
            business_reject_reason = message.get_field(380, "0")
            text = message.get_field(58, "No reason provided")
            
            logger.warning(f"Business Reject: RefSeqNum={ref_seq_num}, "
                          f"RefMsgType={ref_msg_type}, BusinessRejectReason={business_reject_reason}, "
                          f"Text={text}")
            
        except Exception as e:
            logger.error(f"Error handling business reject: {e}")
    
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
        
        try:
            req_id = str(self._get_next_request_id())
            
            mdr = FIXMessage()
            mdr.set_field(35, "V")  # MsgType = Market Data Request
            mdr.set_field(262, req_id)  # MDReqID
            mdr.set_field(263, 1)  # SubscriptionRequestType = Snapshot + Updates
            mdr.set_field(264, 0)  # MarketDepth = Full Book
            mdr.set_field(265, 0)  # MDUpdateType = Full Refresh
            mdr.set_field(266, 1)  # AggregatedBook = Yes
            
            mdr.set_field(267, 2)  # NoMDEntryTypes = 2
            
            mdr.set_field(269, "0")  # MDEntryType = Bid
            
            mdr.set_field(269, "1")  # MDEntryType = Offer
            
            mdr.set_field(146, 1)  # NoRelatedSym = 1
            mdr.set_field(55, symbol)  # Symbol
            
            await self.connection.send_message(mdr)
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
        
        try:
            req_id = str(self._get_next_request_id())
            
            mdr = FIXMessage()
            mdr.set_field(35, "V")  # MsgType = Market Data Request
            mdr.set_field(262, req_id)  # MDReqID
            mdr.set_field(263, 2)  # SubscriptionRequestType = Disable previous subscription
            
            mdr.set_field(146, 1)  # NoRelatedSym = 1
            mdr.set_field(55, symbol)  # Symbol
            
            # Send Market Data Request
            await self.connection.send_message(mdr)
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
        
        try:
            client_order_id = order_id or f"{self.sender_comp_id}-{self._get_next_client_order_id()}"
            
            side_map = {"BUY": "1", "SELL": "2"}
            fix_side = side_map.get(side.upper())
            if not fix_side:
                raise ValueError(f"Invalid side: {side}")
            
            order_type_map = {
                "MARKET": "1",
                "LIMIT": "2",
                "STOP": "3",
                "STOP_LIMIT": "4",
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
            
            nos = FIXMessage()
            nos.set_field(35, "D")  # MsgType = New Order Single
            nos.set_field(11, client_order_id)  # ClOrdID
            nos.set_field(55, symbol)  # Symbol
            nos.set_field(54, fix_side)  # Side
            nos.set_field(60, self._get_utc_timestamp())  # TransactTime
            nos.set_field(40, fix_order_type)  # OrdType
            nos.set_field(38, str(quantity))  # OrderQty
            nos.set_field(59, fix_tif)  # TimeInForce
            
            if order_type.upper() in ["LIMIT", "STOP_LIMIT"] and price is not None:
                nos.set_field(44, str(price))  # Price
            
            if order_type.upper() in ["STOP", "STOP_LIMIT"] and price is not None:
                nos.set_field(99, str(price))  # StopPx
            
            await self.connection.send_message(nos)
            logger.info(f"Placed {order_type} {side} order for {quantity} {symbol} "
                       f"with client order ID {client_order_id}")
            
            return client_order_id
            
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return ""
    
    async def cancel_order(self, client_order_id: str, symbol: str) -> str:
        """
        Cancel an existing order.
        
        Args:
            client_order_id: Client order ID of the order to cancel
            symbol: Trading symbol (e.g., 'BTC-USD')
            
        Returns:
            str: Client order ID of the cancel request
        """
        if not self.authenticated or self.session_type != "order_entry":
            logger.error("Cannot cancel order: Not authenticated or wrong session type")
            return ""
        
        try:
            cancel_client_order_id = f"C-{self._get_next_client_order_id()}"
            
            # Create Order Cancel Request message
            ocr = FIXMessage()
            ocr.set_field(35, "F")  # MsgType = Order Cancel Request
            ocr.set_field(41, client_order_id)  # OrigClOrdID
            ocr.set_field(11, cancel_client_order_id)  # ClOrdID
            ocr.set_field(55, symbol)  # Symbol
            ocr.set_field(60, self._get_utc_timestamp())  # TransactTime
            
            # Send Order Cancel Request message
            await self.connection.send_message(ocr)
            logger.info(f"Sent cancel request for order {client_order_id} with cancel ID {cancel_client_order_id}")
            
            return cancel_client_order_id
            
        except Exception as e:
            logger.error(f"Error canceling order: {e}")
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
        
        try:
            req_id = str(self._get_next_request_id())
            
            rfp = FIXMessage()
            rfp.set_field(35, "AN")  # MsgType = Request For Positions
            rfp.set_field(710, req_id)  # PosReqID
            rfp.set_field(724, "0")  # PosReqType = Positions
            rfp.set_field(263, "1")  # SubscriptionRequestType = Snapshot
            rfp.set_field(60, self._get_utc_timestamp())  # TransactTime
            
            await self.connection.send_message(rfp)
            logger.info("Sent position request")
            return True
            
        except Exception as e:
            logger.error(f"Error requesting positions: {e}")
            return False
    
    def _get_next_client_order_id(self) -> int:
        """
        Generate and return the next client order ID.
        
        Returns:
            int: Next client order ID
        """
        self.next_client_order_id += 1
        return self.next_client_order_id
    
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
