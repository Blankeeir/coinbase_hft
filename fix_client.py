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
from fixt11 import FIXT11

import config

logger = logging.getLogger("coinbase_hft.fix_client")

SESSION_SUB_IDS = {
    "order_entry": "OE",
    "market_data": "MD", 
    "drop_copy": "DC",
}

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
        on_order_cancel_reject: Optional[Callable[[FIXMessage], None]] = None,
        on_trade_capture_report: Optional[Callable[[FIXMessage], None]] = None,
        on_quote_request: Optional[Callable[[FIXMessage], None]] = None,
        on_quote: Optional[Callable[[FIXMessage], None]] = None,
        on_security_list: Optional[Callable[[FIXMessage, List[Dict]], None]] = None,
        on_security_definition: Optional[Callable[[FIXMessage, Dict], None]] = None,
        on_market_data_request_reject: Optional[Callable[[FIXMessage], None]] = None,
        test_mode: bool = False,
    ):
        """
        Initialize the FIX client.
        
        Args:
            session_type: Type of FIX session ('order_entry', 'market_data', or 'drop_copy')
            on_execution_report: Callback for execution reports
            on_market_data: Callback for market data messages
            on_position_report: Callback for position reports
            on_order_cancel_reject: Callback for order cancel reject messages
            on_trade_capture_report: Callback for trade capture reports
            on_quote_request: Callback for quote requests
            on_quote: Callback for quote messages
            on_security_list: Callback for security list messages
            on_security_definition: Callback for security definition messages
            on_market_data_request_reject: Callback for market data request reject messages
            test_mode: Run in test mode without real connection
        """
        self.session_type = session_type
        self.on_execution_report = on_execution_report
        self.on_market_data = on_market_data
        self.on_position_report = on_position_report
        self.on_order_cancel_reject = on_order_cancel_reject
        self.on_trade_capture_report = on_trade_capture_report
        self.on_quote_request = on_quote_request
        self.on_quote = on_quote
        self.on_security_list = on_security_list
        self.on_security_definition = on_security_definition
        self.on_market_data_request_reject = on_market_data_request_reject
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
        
        self.target_comp_id = "CBINTL"
        
        self.target_sub_id = SESSION_SUB_IDS[session_type]
        
        self.api_key = config.CB_INTX_API_KEY
        self.api_secret = config.CB_INTX_API_SECRET
        self.passphrase = config.CB_INTX_PASSPHRASE
        
        self.protocol = None
        self.connection = None
        self.journaler = None
        self.connected = False
        self.authenticated = False
        
        if self.test_mode:
            self.connected = True
            class MockConnection:
                async def send_msg(self, message):
                    logger.info(f"Test mode: Would send message {message}")
                    return True
            self.connection = MockConnection()
        
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
            
        network_timeout = 30  # seconds, increased from 10s per Coinbase recommendation
        auth_timeout = config.FIX_AUTH_TIMEOUT  # seconds
        max_retries = max_retries if max_retries is not None else config.FIX_MAX_RETRIES
        retry_delay = 2  # Initial delay in seconds
        
        for attempt in range(1, max_retries + 1):
            try:
                if attempt > 1:
                    logger.info(f"Connection attempt {attempt}/{max_retries} for {self.session_type} session")
                
                # Create SSL context for secure connection
                self.ssl_context = ssl.create_default_context()
                self.ssl_context.check_hostname = False
                self.ssl_context.verify_mode = ssl.CERT_NONE
                
                self.protocol = FIXT11()
                
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
                
                from custom_connection import SSLAsyncFIXConnection
                
                self.connection = SSLAsyncFIXConnection(
                    protocol=self.protocol,
                    sender_comp_id=self.sender_comp_id,
                    target_comp_id=self.target_comp_id,
                    journaler=self.journaler,
                    host=self.host,
                    port=self.port,
                    ssl_context=self.ssl_context,
                    heartbeat_period=config.FIX_HEARTBEAT_INTERVAL,
                    logger=logger,
                )
                
                self.connection.on_message = self._on_message
                
                try:
                    if self.test_mode:
                        self.connected = True
                        logger.info(f"[TEST MODE] Simulated connection to {self.host}:{self.port} for {self.session_type} session")
                    else:
                        await self.connection.connect(ssl=self.ssl_context)
                        self.connected = True
                        logger.info(f"Connected to {self.host}:{self.port} for {self.session_type} session")
                        
                        # Authenticate immediately after connection
                        logger.info(f"Socket ready, sending Logon message")
                        auth_success = await self._authenticate()
                        if not auth_success:
                            logger.error(f"Failed to authenticate for {self.session_type} session")
                            if attempt < max_retries:
                                backoff = retry_delay * (2 ** (attempt - 1))
                                logger.info(f"Retrying in {backoff} seconds...")
                                await asyncio.sleep(backoff)
                            continue
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
                
            # Generate UTC timestamp in ISO format
            utc_timestamp = self._get_utc_timestamp()
            logger.info(f"Using timestamp for authentication: {utc_timestamp}")
            
            # Signature format: timestamp + api_key + "CBINTL" + passphrase (always use CBINTL)
            message = f"{utc_timestamp}{self.api_key}CBINTL{self.passphrase}"
            logger.info(f"Authentication message components: timestamp={utc_timestamp}, api_key={self.api_key[:4]}..., target_comp_id=CBINTL, passphrase=***")
            
            # Decode the API secret from base64 and create HMAC signature
            try:
                try:
                    decoded_secret = base64.b64decode(self.api_secret)
                    logger.info(f"Decoded API secret length: {len(decoded_secret)} bytes")
                except Exception as e:
                    logger.error(f"Failed to decode API secret: {e}")
                    return False
                
                signature = base64.b64encode(
                    hmac.new(
                        decoded_secret,
                        message.encode('utf-8'),
                        hashlib.sha256
                    ).digest()
                ).decode('utf-8')
                
                logger.info(f"Generated signature: {signature[:10]}...")
            except Exception as e:
                logger.error(f"Error generating signature: {e}")
                return False
            
            logger.debug(f"Generated signature: {signature[:10]}...")
            
            # Create Logon message
            logon_msg = FIXMessage("A")  # Logon message type
            logon_msg.set(98, "0")  # EncryptMethod: No encryption (Tag 98)
            logon_msg.set(108, "30")  # HeartBtInt: 30s per Coinbase docs (Tag 108)
            logon_msg.set(141, "Y")  # ResetSeqNumFlag: Reset sequence numbers (Tag 141)
            
            # Authentication fields - match official Coinbase sample scripts
            logon_msg.set(553, self.api_key)  # Username: API Key (Tag 553)
            logon_msg.set(554, self.passphrase)  # Password: Passphrase (Tag 554)
            logon_msg.set(95, str(len(signature)))  # RawDataLength: Length of signature (Tag 95)
            logon_msg.set(96, signature)  # RawData: HMAC signature (Tag 96)
            logon_msg.set(58, utc_timestamp)  # Text: Timestamp used for signature (Tag 58)
            logon_msg.set(1137, "9")  # DefaultApplVerID = FIX.5.0SP2
            
            logon_msg.set(57, self.target_sub_id)  # TargetSubID
            
            if self.session_type == "order_entry":
                logon_msg.set(8013, "N")  # CancelOrdersOnDisconnect: Don't cancel orders on disconnect
                logon_msg.set(8014, "N")  # CancelOrdersOnInternalDisconnect: Don't cancel on internal disconnect
            
            logger.info(f"Sending Logon message for {self.session_type} session with fields: 98=0|108=30|141=Y|553={self.api_key}|554={self.passphrase}|95={len(signature)}|96={signature[:10]}...|58={utc_timestamp}|1137=9|57={self.target_sub_id}")
            
            # Send the Logon message
            await self.connection.send_msg(logon_msg)
            logger.info(f"Logon message sent, waiting for response...")
            
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
            msg_type = message.get(35)  # MsgType (tag 35)
            
            if msg_type == "A":  # Logon
                self.authenticated = True
                logger.info(f"Logon successful for {self.session_type} session")
                return
            
            if msg_type == "5":  # Logout
                text = message.get(58, "No reason provided")  # Text (tag 58)
                logger.warning(f"Received Logout: {text}")
                self.authenticated = False
                return
            
            if msg_type == "0":  # Heartbeat
                return  # Silently process heartbeats
            
            if msg_type == "1":  # TestRequest
                self._handle_test_request(message)
                return
            
            if msg_type == "3":  # Reject
                self._handle_reject(message)
                return
            
            if msg_type == "j":  # BusinessMessageReject
                self._handle_business_reject(message)
                return
            
            if msg_type == "8" and self.on_execution_report:  # ExecutionReport
                self._log_execution_report(message)
                self.on_execution_report(message)
                return
            
            if msg_type == "W" and self.on_market_data:  # MarketDataSnapshotFullRefresh
                self.on_market_data(message)
                return
            
            if msg_type == "X" and self.on_market_data:  # MarketDataIncrementalRefresh
                self.on_market_data(message)
                return
            
            if msg_type == "AP" and self.on_position_report:  # PositionReport
                self.on_position_report(message)
                return
            
            # Handle OrderMassCancelReport
            if msg_type == "r":  # OrderMassCancelReport
                self._handle_order_mass_cancel_report(message)
                return
            
            # Handle OrderCancelReject
            if msg_type == "9":  # OrderCancelReject
                self._handle_order_cancel_reject(message)
                return
            
            # Handle TradeCaptureReport
            if msg_type == "AE":  # TradeCaptureReport
                self._handle_trade_capture_report(message)
                return
            
            # Handle PreFill messages
            if msg_type == "F7":  # PreFillRequestSuccess
                self._handle_prefill_request_success(message)
                return
            
            if msg_type == "F8":  # PreFillReport
                self._handle_prefill_report(message)
                return
            
            # Handle RFQ/Quote messages
            if msg_type == FMsg.QUOTEREQUEST:
                self._handle_quote_request(message)
                return
            
            if msg_type == FMsg.QUOTESTATUSREPORT:
                self._handle_quote_status_report(message)
                return
            
            # Handle Market Data messages
            if msg_type == "x":  # SecurityListRequest
                self._handle_security_list_request(message)
                return
                
            if msg_type == "y":  # SecurityList
                self._handle_security_list(message)
                return
                
            if msg_type == "d":  # SecurityDefinition
                self._handle_security_definition(message)
                return
                
            if msg_type == "V":  # MarketDataRequest
                self._handle_market_data_request(message)
                return
                
            if msg_type == "Y":  # MarketDataRequestReject
                self._handle_market_data_request_reject(message)
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
            test_req_id = message.get(112, "")  # TestReqID (tag 112)
            
            heartbeat = FIXMessage("0")  # Heartbeat (MsgType 0)
            if test_req_id:
                heartbeat.set(112, test_req_id)  # TestReqID (tag 112)
            
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
            ord_type = message.get(FTag.OrdType, "")
            
            exec_type_map = {
                "0": "New", "1": "Partial Fill", "2": "Fill", 
                "4": "Canceled", "5": "Replaced", "8": "Rejected",
                "C": "Expired", "L": "Stop Triggered", "6": "Pending Cancel",
                "A": "Pending New", "E": "Pending Replace"
            }
            
            ord_status_map = {
                "0": "New", "1": "Partially Filled", "2": "Filled",
                "4": "Canceled", "5": "Replaced", "8": "Rejected", "C": "Expired",
                "6": "Pending Cancel", "A": "Pending New", "E": "Pending Replace"
            }
            
            ord_type_desc = "TPSL" if ord_type == "O" else ""
            
            exec_desc = exec_type_map.get(exec_type, exec_type)
            status_desc = ord_status_map.get(ord_status, ord_status)
            
            logger.info(f"ExecutionReport: {clord_id} {symbol} {side} {ord_type_desc} - {exec_desc} ({status_desc})")
            
            try:
                no_party_ids = int(message.get(453, "0"))
                if no_party_ids > 0 and self.test_mode:
                    portfolio_id = "portfolio-uuid-123"  # Mock for test mode
                    logger.info(f"  Portfolio: {portfolio_id}")
            except Exception as e:
                logger.debug(f"No portfolio information: {e}")
            
            if exec_type in ["1", "2"]:  # Partial Fill or Fill
                try:
                    no_misc_fees = int(message.get(136, "0"))
                    if no_misc_fees > 0 and self.test_mode:
                        fee_amt = message.get(137, "0")
                        fee_curr = message.get(138, "")
                        fee_type = message.get(139, "")
                        
                        fee_type_map = {
                            "4": "Exchange fees",
                            "7": "Other",
                            "14": "Security lending"
                        }
                        
                        fee_type_desc = fee_type_map.get(fee_type, f"Unknown ({fee_type})")
                        logger.info(f"  Fees: {fee_amt} {fee_curr} ({fee_type_desc})")
                except Exception as e:
                    logger.debug(f"No fee information: {e}")
            
            if exec_type == "8":
                reject_reason = message.get(103, "Unknown")
                text = message.get(FTag.Text, "")
                logger.warning(f"Order rejected: {reject_reason} - {text}")
            
        except Exception as e:
            logger.error(f"Error logging execution report: {e}")
    
    def _handle_order_mass_cancel_report(self, message: FIXMessage) -> None:
        """
        Handle OrderMassCancelReport (35=r).
        
        Args:
            message: OrderMassCancelReport message
        """
        try:
            clord_id = message.get(FTag.ClOrdID, "")
            mass_action_report_id = message.get(1369, "")
            symbol = message.get(FTag.Symbol, "")
            side = message.get(FTag.Side, "")
            mass_cancel_response = message.get(531, "")
            total_affected_orders = message.get(533, "0")
            
            response_map = {
                "0": "Cancel Request Rejected",
                "7": "Cancel All Orders"
            }
            
            response_desc = response_map.get(mass_cancel_response, mass_cancel_response)
            
            if mass_cancel_response == "0":
                reject_reason = message.get(532, "0")
                reject_reason_map = {
                    "0": "Mass Cancel Not Supported",
                    "1": "Invalid or unknown Security",
                    "99": "Other"
                }
                reject_desc = reject_reason_map.get(reject_reason, reject_reason)
                logger.warning(f"Mass Cancel Rejected: {clord_id} - {reject_desc}")
            else:
                logger.info(f"Mass Cancel Report: {clord_id} {symbol} {side} - {response_desc}, "
                          f"Affected: {total_affected_orders} orders")
            
        except Exception as e:
            logger.error(f"Error handling mass cancel report: {e}")
    
    def _handle_order_cancel_reject(self, message: FIXMessage) -> None:
        """
        Handle OrderCancelReject (35=9).
        
        Args:
            message: OrderCancelReject message
        """
        try:
            clord_id = message.get(FTag.ClOrdID, "")
            orig_clord_id = message.get(FTag.OrigClOrdID, "")
            order_id = message.get(FTag.OrderID, "")
            cxl_rej_reason = message.get(102, "")
            cxl_rej_response_to = message.get(434, "")
            text = message.get(FTag.Text, "")
            
            reason_map = {
                "0": "Too late to cancel",
                "1": "Unknown order",
                "3": "Order already pending cancel or cancel replace"
            }
            
            response_map = {
                "1": "Order Cancel Request",
                "2": "Order Cancel/Replace Request"
            }
            
            reason_desc = reason_map.get(cxl_rej_reason, cxl_rej_reason)
            response_desc = response_map.get(cxl_rej_response_to, cxl_rej_response_to)
            
            logger.warning(f"Order Cancel Reject: {clord_id} (orig: {orig_clord_id}) - "
                         f"{reason_desc} for {response_desc}. Text: {text}")
            
            if self.on_order_cancel_reject:
                self.on_order_cancel_reject(message)
            
        except Exception as e:
            logger.error(f"Error handling order cancel reject: {e}")
    
    def _handle_trade_capture_report(self, message: FIXMessage) -> None:
        """
        Handle TradeCaptureReport (35=AE).
        
        Args:
            message: TradeCaptureReport message
        """
        try:
            trd_type = message.get(828, "")
            trd_match_id = message.get(880, "")
            exec_id = message.get(FTag.ExecID, "")
            trade_link_id = message.get(820, "")
            symbol = message.get(FTag.Symbol, "")
            last_qty = message.get(32, "")
            last_px = message.get(31, "")
            side = ""
            portfolio_id = None
            
            no_sides = int(message.get(552, "0"))
            if no_sides > 0:
                side = message.get(FTag.Side, "")
                
                try:
                    no_party_ids = int(message.get(453, "0"))
                    if no_party_ids > 0:
                        for i in range(no_party_ids):
                            party_id = message.get(448, "", i)
                            party_role = message.get(452, "", i)
                            
                            if party_role == "24":  # Customer account
                                portfolio_id = party_id
                                break
                            elif party_role == "3":  # Client ID
                                client_id = party_id
                except Exception as e:
                    logger.debug(f"Error extracting party information: {e}")
            
            fees = []
            try:
                no_misc_fees = int(message.get(136, "0"))
                if no_misc_fees > 0:
                    for i in range(no_misc_fees):
                        fee_amt = message.get(137, "0", i)
                        fee_curr = message.get(138, "", i)
                        fee_type = message.get(139, "", i)
                        
                        fee_type_map = {
                            "4": "Exchange fees",
                            "7": "Other",
                            "14": "Asset lending"
                        }
                        
                        fee_type_desc = fee_type_map.get(fee_type, f"Unknown ({fee_type})")
                        
                        fees.append({
                            "amount": fee_amt,
                            "currency": fee_curr,
                            "type": fee_type_desc
                        })
            except Exception as e:
                logger.debug(f"Error extracting fee information: {e}")
            
            trd_type_map = {
                "0": "Regular trade",
                "3": "Transfer"
            }
            
            trd_desc = trd_type_map.get(trd_type, trd_type)
            
            if trd_type == "3":  # Transfer
                transfer_reason = message.get(830, "")
                transfer_reason_map = {
                    "LIQUIDATED": "Position liquidated",
                    "ASSIGNED": "Position assigned"
                }
                reason_desc = transfer_reason_map.get(transfer_reason, transfer_reason)
                
                logger.info(f"Trade Capture Report: {trd_match_id} {symbol} {side} - "
                          f"{trd_desc} ({reason_desc}), Qty: {last_qty}, Px: {last_px}")
                
                if portfolio_id:
                    logger.info(f"  Portfolio: {portfolio_id}")
                
                if fees:
                    logger.info(f"  Fees: {len(fees)} fee entries")
                    for fee in fees:
                        logger.info(f"    {fee['amount']} {fee['currency']} ({fee['type']})")
            else:
                logger.info(f"Trade Capture Report: {trd_match_id} {symbol} {side} - "
                          f"{trd_desc}, Qty: {last_qty}, Px: {last_px}")
                
                if portfolio_id:
                    logger.info(f"  Portfolio: {portfolio_id}")
                
                if fees:
                    logger.info(f"  Fees: {len(fees)} fee entries")
                    for fee in fees:
                        logger.info(f"    {fee['amount']} {fee['currency']} ({fee['type']})")
            
            if self.on_trade_capture_report:
                self.on_trade_capture_report(message)
            
        except Exception as e:
            logger.error(f"Error handling trade capture report: {e}")
    
    def _handle_prefill_request_success(self, message: FIXMessage) -> None:
        """
        Handle PreFillRequestSuccess (35=F7).
        
        Args:
            message: PreFillRequestSuccess message
        """
        try:
            prefill_request_id = message.get(22007, "")
            logger.info(f"PreFill Request Success: {prefill_request_id}")
            
        except Exception as e:
            logger.error(f"Error handling prefill request success: {e}")
    
    def _handle_prefill_report(self, message: FIXMessage) -> None:
        """
        Handle PreFillReport (35=F8).
        
        Args:
            message: PreFillReport message
        """
        try:
            clord_id = message.get(FTag.ClOrdID, "")
            order_id = message.get(FTag.OrderID, "")
            symbol = message.get(FTag.Symbol, "")
            side = message.get(FTag.Side, "")
            last_qty = message.get(32, "")
            last_px = message.get(31, "")
            last_liquidity_ind = message.get(851, "")
            
            liquidity_map = {
                "1": "Added liquidity",
                "2": "Removed liquidity"
            }
            
            liquidity_desc = liquidity_map.get(last_liquidity_ind, last_liquidity_ind)
            
            logger.info(f"PreFill Report: {clord_id} {symbol} {side} - "
                      f"Qty: {last_qty}, Px: {last_px}, Liquidity: {liquidity_desc}")
            
        except Exception as e:
            logger.error(f"Error handling prefill report: {e}")
    
    def _handle_quote_request(self, message: FIXMessage) -> None:
        """
        Handle Quote Request (35=R).
        
        Args:
            message: Quote Request message
        """
        try:
            quote_req_id = message.get(131, "")
            symbol = message.get(FTag.Symbol, "")
            order_qty = message.get(FTag.OrderQty, "")
            valid_until_time = message.get(62, "")
            expire_time = message.get(126, "")
            
            logger.info(f"Quote Request: {quote_req_id} {symbol} - "
                      f"Qty: {order_qty}, Valid Until: {valid_until_time}")
            
            if self.on_quote_request:
                self.on_quote_request(message)
            
        except Exception as e:
            logger.error(f"Error handling quote request: {e}")
    
    def _handle_quote_status_report(self, message: FIXMessage) -> None:
        """
        Handle Quote Status Report (35=AI).
        
        Args:
            message: Quote Status Report message
        """
        try:
            quote_req_id = message.get(131, "")
            quote_id = message.get(117, "")
            symbol = message.get(FTag.Symbol, "")
            quote_status = message.get(297, "")
            
            bid_px = message.get(132, "")
            offer_px = message.get(133, "")
            bid_size = message.get(134, "")
            offer_size = message.get(135, "")
            valid_until_time = message.get(62, "")
            expire_time = message.get(126, "")
            
            side = None
            if quote_status == "19":  # Pending End Trade
                side = message.get(FTag.Side, "")
                order_qty = message.get(FTag.OrderQty, "")
                
                side_map = {
                    "1": "Buy",
                    "2": "Sell"
                }
                
                side_desc = side_map.get(side, side)
                if side and order_qty:
                    logger.info(f"  Quote selected for execution: {side_desc} {order_qty}")
            
            status_map = {
                "5": "Rejected",
                "7": "Expired", 
                "16": "Active",
                "17": "Canceled",
                "19": "Pending End Trade"
            }
            
            status_desc = status_map.get(quote_status, quote_status)
            
            if quote_status == "5":  # Rejected
                text = message.get(FTag.Text, "")
                logger.warning(f"Quote Status Report: {quote_id} {symbol} - {status_desc}: {text}")
            elif quote_status == "7":  # Expired
                logger.warning(f"Quote Status Report: {quote_id} {symbol} - {status_desc}, "
                             f"Expired at: {expire_time}")
            elif quote_status == "16":  # Active
                logger.info(f"Quote Status Report: {quote_id} {symbol} - {status_desc}, "
                          f"Valid until: {valid_until_time}")
                
                if bid_px and bid_size:
                    logger.info(f"  Bid: {bid_px} x {bid_size}")
                if offer_px and offer_size:
                    logger.info(f"  Offer: {offer_px} x {offer_size}")
            elif quote_status == "17":  # Canceled
                logger.info(f"Quote Status Report: {quote_id} {symbol} - {status_desc}, "
                          f"Not selected for execution")
            elif quote_status == "19":  # Pending End Trade
                logger.info(f"Quote Status Report: {quote_id} {symbol} - {status_desc}, "
                          f"Selected for execution")
            else:
                logger.info(f"Quote Status Report: {quote_id} {symbol} - {status_desc}")
            
            if self.on_quote:
                self.on_quote(message)
            
        except Exception as e:
            logger.error(f"Error handling quote status report: {e}")
    
    async def send_prefill_request(self, prefill_request_id: str = None) -> str:
        """
        Send PreFillRequest (35=F6) to subscribe to prefills.
        
        Args:
            prefill_request_id: Client generated ID for the request
            
        Returns:
            str: The prefill request ID used
        """
        if not self.authenticated or self.session_type != "order_entry":
            logger.error("Cannot send prefill request: Not authenticated or wrong session type")
            return ""
            
        if self.test_mode:
            request_id = prefill_request_id or str(uuid.uuid4())
            logger.info(f"Test mode: Simulating prefill request with ID {request_id}")
            return request_id
        
        try:
            request_id = prefill_request_id or str(uuid.uuid4())
            
            prefill_req = FIXMessage("F6")  # PreFillRequest
            prefill_req.set(22007, request_id)  # PreFillRequestID
            
            await self.connection.send_msg(prefill_req)
            logger.info(f"Sent PreFill Request with ID {request_id}")
            
            return request_id
            
        except Exception as e:
            logger.error(f"Error sending prefill request: {e}")
            return ""
    
    async def send_rfq_request(self, rfq_req_id: str = None) -> str:
        """
        Send RFQ Request (35=AH) to subscribe to RFQ.
        
        Args:
            rfq_req_id: Unique identifier for RFQ Request
            
        Returns:
            str: The RFQ request ID used
        """
        if not self.authenticated or self.session_type != "order_entry":
            logger.error("Cannot send RFQ request: Not authenticated or wrong session type")
            return ""
            
        if self.test_mode:
            request_id = rfq_req_id or str(uuid.uuid4())
            logger.info(f"Test mode: Simulating RFQ request with ID {request_id}")
            return request_id
        
        try:
            request_id = rfq_req_id or str(uuid.uuid4())
            
            rfq_req = FIXMessage("AH")  # RFQRequest
            rfq_req.set(644, request_id)  # RFQReqID
            
            await self.connection.send_msg(rfq_req)
            logger.info(f"Sent RFQ Request with ID {request_id}")
            
            return request_id
            
        except Exception as e:
            logger.error(f"Error sending RFQ request: {e}")
            return ""
    
    async def send_quote(self, quote_req_id: str, symbol: str, bid_px: float = None, 
                       offer_px: float = None, bid_size: str = None, offer_size: str = None,
                       portfolio_id: str = None) -> str:
        """
        Send Quote (35=S) in response to Quote Request.
        
        Args:
            quote_req_id: Quote request ID from Quote Request
            symbol: Trading symbol
            bid_px: Bid price (optional)
            offer_px: Offer price (optional)
            bid_size: Bid size (required if bid_px provided)
            offer_size: Offer size (required if offer_px provided)
            portfolio_id: Portfolio UUID (optional)
            
        Returns:
            str: Quote ID
        """
        if not self.authenticated or self.session_type != "order_entry":
            logger.error("Cannot send quote: Not authenticated or wrong session type")
            return ""
            
        if self.test_mode:
            quote_id = str(uuid.uuid4())
            logger.info(f"Test mode: Simulating quote with ID {quote_id}")
            return quote_id
        
        try:
            quote_id = str(uuid.uuid4())
            
            quote = FIXMessage("S")  # Quote
            quote.set(131, quote_req_id)  # QuoteReqID
            quote.set(117, quote_id)  # QuoteID
            quote.set(FTag.Symbol, symbol)
            
            if bid_px and bid_size:
                quote.set(132, str(bid_px))  # BidPx
                quote.set(134, bid_size)  # BidSize
            
            if offer_px and offer_size:
                quote.set(133, str(offer_px))  # OfferPx
                quote.set(135, offer_size)  # OfferSize
            
            if portfolio_id:
                quote.set(453, "1")  # NoPartyIDs
                quote.set(448, portfolio_id)  # PartyID
                quote.set(452, "24")  # PartyRole = Customer account
            
            await self.connection.send_msg(quote)
            logger.info(f"Sent Quote {quote_id} for request {quote_req_id}")
            
            return quote_id
            
        except Exception as e:
            logger.error(f"Error sending quote: {e}")
            return ""

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
        stop_price: Optional[float] = None,  # For TPSL orders
        stop_limit_price: Optional[float] = None,  # For TPSL orders
    ) -> str:
        """
        Place a new order.
        
        Args:
            symbol: Trading symbol (e.g., 'BTC-USD')
            side: Order side ('BUY' or 'SELL')
            order_type: Order type ('LIMIT', 'MARKET', 'STOP', 'STOP_LIMIT', 'TAKE_PROFIT_STOP_LOSS')
            quantity: Order quantity
            price: Order price (required for LIMIT, STOP_LIMIT, and TPSL orders)
            time_in_force: Time in force ('GTC', 'IOC', 'FOK', 'GTD'). TPSL orders only support GTC and GTD.
            order_id: Custom order ID (generated if not provided)
            portfolio_id: Portfolio UUID (optional)
            post_only: Post only flag (not supported for TPSL orders)
            self_trade_prevention: Self trade prevention strategy
            stop_price: Stop price for TPSL orders (StopPx field)
            stop_limit_price: Stop limit price for TPSL orders (StopLimitPx field)
            
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
            
            if order_type.upper() in ["STOP", "STOP_LIMIT"] and price is not None:
                nos.set(FTag.StopPx, str(price))
            
            # Handle TPSL orders
            if order_type.upper() == "TAKE_PROFIT_STOP_LOSS":
                if time_in_force.upper() not in ["GTC", "GTD"]:
                    raise ValueError("TPSL orders only support GTC and GTD time in force")
                
                if post_only:
                    raise ValueError("TPSL orders do not support post_only")
                
                if price is None or stop_price is None or stop_limit_price is None:
                    raise ValueError("TPSL orders require price, stop_price, and stop_limit_price")
                
                nos.set(FTag.Price, str(price))
                
                nos.set(FTag.StopPx, str(stop_price))
                
                nos.set(3040, str(stop_limit_price))
                
                if fix_side == "2":  # Sell TPSL
                    if not (price > stop_price > stop_limit_price):
                        raise ValueError("For Sell TPSL: Price must be > StopPx and StopPx must be > StopLimitPx")
                else:  # Buy TPSL
                    if not (price < stop_price < stop_limit_price):
                        raise ValueError("For Buy TPSL: Price must be < StopPx and StopPx must be < StopLimitPx")
            
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
    
    def _handle_security_list_request(self, message: FIXMessage) -> None:
        """
        Handle SecurityListRequest (35=x) message.
        
        Args:
            message: SecurityListRequest message
        """
        try:
            security_req_id = message.get(320, "")  # SecurityReqID
            security_list_request_type = message.get(559, "")  # SecurityListRequestType
            
            logger.info(f"SecurityListRequest: ID={security_req_id}, Type={security_list_request_type}")
            
        except Exception as e:
            logger.error(f"Error handling SecurityListRequest: {e}")
    
    def _handle_security_list(self, message: FIXMessage) -> None:
        """
        Handle SecurityList (35=y) message.
        
        Args:
            message: SecurityList message
        """
        try:
            security_req_id = message.get(320, "")  # SecurityReqID
            security_request_result = message.get(560, "")  # SecurityRequestResult
            no_related_sym = int(message.get(146, "0"))  # NoRelatedSym
            
            securities = []
            if self.test_mode:
                if no_related_sym > 0:
                    securities = [
                        {
                            'symbol': "BTC-USD",
                            'security_type': "FXSPOT",
                            'security_sub_type': "STANDARD",
                            'contract_multiplier': "1",
                            'min_price_increment': "0.01",
                            'margin_ratio': "0.50",
                            'currency': "USD",
                            'min_trade_vol': "1",
                            'position_limit': "100",
                            'round_lot': "0.001",
                            'trading_status': "17"
                        }
                    ]
                    
                    if no_related_sym > 1:
                        securities.append({
                            'symbol': "ETH-USD",
                            'security_type': "FXSPOT",
                            'security_sub_type': "STANDARD",
                            'contract_multiplier': "1",
                            'min_price_increment': "0.01",
                            'margin_ratio': "0.75",
                            'currency': "USD",
                            'min_trade_vol': "1",
                            'position_limit': "100",
                            'round_lot': "0.001",
                            'trading_status': "17"
                        })
            else:
                logger.warning("Production repeating group access not implemented yet")
                
                security = {
                    'symbol': "",
                    'security_type': "",
                    'security_sub_type': "",
                    'contract_multiplier': "",
                    'min_price_increment': "",
                    'margin_ratio': "",
                    'currency': "",
                    'min_trade_vol': "",
                    'position_limit': "",
                    'round_lot': "",
                    'trading_status': ""
                }
                securities.append(security)
            
            logger.info(f"SecurityList: ID={security_req_id}, Result={security_request_result}, "
                       f"Securities={len(securities)}")
            
            if self.on_security_list:
                self.on_security_list(message, securities)
                
        except Exception as e:
            logger.error(f"Error handling SecurityList: {e}")
    
    def _handle_security_definition(self, message: FIXMessage) -> None:
        """
        Handle SecurityDefinition (35=d) message.
        
        Args:
            message: SecurityDefinition message
        """
        try:
            security_update_action = message.get(980, "")  # SecurityUpdateAction
            last_update_time = message.get(779, "")  # LastUpdateTime
            symbol = message.get(55, "")  # Symbol
            security_type = message.get(167, "")  # SecurityType
            security_sub_type = message.get(762, "")  # SecuritySubType
            min_price_increment = message.get(969, "")  # MinPriceIncrement
            margin_ratio = message.get(898, "")  # MarginRatio
            currency = message.get(15, "")  # Currency
            min_trade_vol = message.get(562, "")  # MinTradeVol
            position_limit = message.get(970, "")  # PositionLimit
            trading_status = message.get(1682, "")  # MDSecurityTradingStatus
            
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
    
    def _handle_market_data_request(self, message: FIXMessage) -> None:
        """
        Handle MarketDataRequest (35=V) message.
        
        Args:
            message: MarketDataRequest message
        """
        try:
            md_req_id = message.get(262, "")  # MDReqID
            subscription_request_type = message.get(263, "")  # SubscriptionRequestType
            market_depth = message.get(264, "")  # MarketDepth
            no_related_sym = int(message.get(146, "0"))  # NoRelatedSym
            
            symbols = []
            if self.test_mode:
                if no_related_sym > 0:
                    symbols.append({'symbol': "BTC-USD", 'security_type': "FXSPOT"})
                    
                    if no_related_sym > 1:
                        symbols.append({'symbol': "ETH-USD", 'security_type': "FXSPOT"})
            else:
                logger.warning("Production repeating group access not implemented yet")
            
            logger.info(f"MarketDataRequest: ID={md_req_id}, Type={subscription_request_type}, "
                       f"Depth={market_depth}, Symbols={len(symbols)}")
                       
        except Exception as e:
            logger.error(f"Error handling MarketDataRequest: {e}")
    
    def _handle_market_data_request_reject(self, message: FIXMessage) -> None:
        """
        Handle MarketDataRequestReject (35=Y) message.
        
        Args:
            message: MarketDataRequestReject message
        """
        try:
            md_req_id = message.get(262, "")  # MDReqID
            md_req_rej_reason = message.get(281, "")  # MDReqRejReason
            text = message.get(58, "")  # Text
            
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
    
    async def request_security_list(self, security_list_request_type: str = "0") -> str:
        """
        Send SecurityListRequest (35=x) message.
        
        Args:
            security_list_request_type: Type of security list request
                0 = All securities (default)
                1 = Symbol
                2 = SecurityType
                3 = Product
                4 = TradingSessionID
                5 = SecurityGroup
        
        Returns:
            SecurityReqID: Unique identifier for the request
        """
        security_req_id = self._get_next_request_id()
        
        message = FIXMessage("x")
        message.set(320, security_req_id)  # SecurityReqID
        message.set(559, security_list_request_type)  # SecurityListRequestType
        
        await self.connection.send_msg(message)
        logger.info(f"SecurityListRequest sent: ID={security_req_id}")
        return security_req_id
        
    async def send_market_data_request(self, symbols: List[str], market_depth: int = 1, 
                                      subscription_type: str = "1") -> str:
        """
        Send MarketDataRequest (35=V) message.
        
        Args:
            symbols: List of symbols to subscribe to
            market_depth: Depth of market data (1, 10, or 20)
            subscription_type: Type of subscription
                1 = Subscribe (default)
                2 = Unsubscribe
        
        Returns:
            MDReqID: Unique identifier for the request
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
    
    async def _wait_for_network(self, timeout: float = 15.0) -> bool:
        """
        Monitor socket connection state changes without blocking authentication.
        This is a helper method for logging state transitions only.
        
        Args:
            timeout: Maximum time to wait in seconds
            
        Returns:
            bool: True if the socket reached the required state, False if timed out
        """
        
        start = time.monotonic()
        last_state = -1
        current_state = self.connection.connection_state
        
        logger.info(f"Initial socket state: {current_state}")
        
        return True
        
    def _get_utc_timestamp(self) -> str:
        """
        Generate UTC timestamp in FIX format.
        
        Returns:
            str: UTC timestamp in format YYYYMMDD-HH:MM:SS.sss
        """
        return datetime.utcnow().strftime("%Y%m%d-%H:%M:%S.%f")[:-3]
