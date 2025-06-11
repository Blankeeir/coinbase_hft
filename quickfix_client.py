"""
QuickFIX client for Coinbase International Exchange.
Handles connection, authentication, and message processing.
"""
import os
import ssl
import time
import base64
import hmac
import hashlib
import logging
import uuid
import quickfix as fix
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('coinbase_fix.log')
    ]
)
logger = logging.getLogger("coinbase_hft.quickfix_client")

MSGTYPE_LOGON = "A"
MSGTYPE_HEARTBEAT = "0"
MSGTYPE_TESTREQUEST = "1"
MSGTYPE_REJECT = "3"
MSGTYPE_LOGOUT = "5"
MSGTYPE_BUSINESSREJECT = "j"
MSGTYPE_MARKETDATAREQUEST = "V"
MSGTYPE_MARKETDATASNAPSHOTFULLREFRESH = "W"
MSGTYPE_MARKETDATAINCREMENTALREFRESH = "X"
MSGTYPE_MARKETDATAREQUESTREJECT = "Y"
MSGTYPE_NEWORDERSINGLE = "D"
MSGTYPE_ORDERCANCELREQUEST = "F"
MSGTYPE_ORDERCANCELREJECT = "9"
MSGTYPE_EXECUTIONREPORT = "8"
MSGTYPE_REQUESTFORPOSITIONS = "AN"
MSGTYPE_POSITIONREPORT = "AP"

TAG_ACCOUNT = 1
TAG_CLORDID = 11
TAG_EXECID = 17
TAG_EXECTYPE = 150
TAG_ORDERID = 37
TAG_ORDSTATUS = 39
TAG_ORDTYPE = 40
TAG_PRICE = 44
TAG_SIDE = 54
TAG_SYMBOL = 55
TAG_TEXT = 58
TAG_TIMEINFORCE = 59
TAG_TRANSACTTIME = 60
TAG_ORDERQTY = 38
TAG_TARGETCOMPID = 56
TAG_TARGETSUBID = 57
TAG_SENDERCOMPID = 49
TAG_SENDINGTIME = 52
TAG_MSGTYPE = 35
TAG_BEGINSTRING = 8
TAG_USERNAME = 553
TAG_PASSWORD = 554
TAG_RAWDATA = 96
TAG_RAWDATALENGTH = 95
TAG_RESETSEQNUMFLAG = 141
TAG_ENCRYPTMETHOD = 98
TAG_HEARTBTINT = 108
TAG_DEFAULTAPPVERID = 1137
TAG_CANCELORDERSONDISCONNECT = 8013
TAG_CANCELORDERSONINTERNALDISCONNECT = 8014
TAG_TESTREQUEST = 112

EXECTYPE_NEW = "0"
EXECTYPE_PARTIAL = "1"
EXECTYPE_FILL = "2"
EXECTYPE_DONE = "3"
EXECTYPE_CANCELLED = "4"
EXECTYPE_REPLACED = "5"
EXECTYPE_PENDING_CANCEL = "6"
EXECTYPE_STOPPED = "7"
EXECTYPE_REJECTED = "8"
EXECTYPE_SUSPENDED = "9"
EXECTYPE_PENDING_NEW = "A"
EXECTYPE_CALCULATED = "B"
EXECTYPE_EXPIRED = "C"
EXECTYPE_RESTATED = "D"
EXECTYPE_PENDING_REPLACE = "E"
EXECTYPE_TRADE = "F"
EXECTYPE_TRADE_CORRECT = "G"
EXECTYPE_TRADE_CANCEL = "H"
EXECTYPE_ORDER_STATUS = "I"

class FixSession:
    """FIX Session for Coinbase International Exchange"""
    
    def __init__(self, session_id, portfolio_id=None):
        """Initialize the FIX session."""
        self.session_id = session_id
        self.portfolio_id = portfolio_id
    
    def send_message(self, message):
        """Send a FIX message to the target."""
        fix.Session.sendToTarget(message, self.session_id)
        
    def on_message(self, message):
        """Process application messages."""
        msg_type = message.getHeader().getField(TAG_MSGTYPE)
        
        if msg_type == MSGTYPE_EXECUTIONREPORT:
            self.handle_execution_report(message)
        elif msg_type == MSGTYPE_REJECT:
            self.handle_reject(message)
        elif msg_type == MSGTYPE_MARKETDATASNAPSHOTFULLREFRESH:
            self.handle_market_data_snapshot(message)
        elif msg_type == MSGTYPE_MARKETDATAINCREMENTALREFRESH:
            self.handle_market_data_incremental(message)
        elif msg_type == MSGTYPE_POSITIONREPORT:
            self.handle_position_report(message)
    
    def handle_execution_report(self, message):
        """Handle execution report messages."""
        if not message.isSetField(TAG_EXECTYPE):
            logger.warning("Execution report missing ExecType")
            return
            
        exec_type = message.getField(TAG_EXECTYPE)
        
        if message.isSetField(TAG_TEXT):
            reason = message.getField(TAG_TEXT)
        else:
            reason = 'Not Returned'
            
        if message.isSetField(TAG_ORDERID):
            order_id = message.getField(TAG_ORDERID)
        else:
            order_id = 'Unknown'
            
        if message.isSetField(TAG_SYMBOL):
            symbol = message.getField(TAG_SYMBOL)
        else:
            symbol = 'Unknown'
            
        if message.isSetField(TAG_ORDERQTY):
            filled_qty = message.getField(TAG_ORDERQTY)
        else:
            filled_qty = '0'
        
        handlers = {
            EXECTYPE_NEW: lambda: logger.info(f'New Order for Symbol {symbol} with Order ID {order_id}: Order Not Filled'),
            EXECTYPE_PARTIAL: lambda: logger.info(f'Order for Symbol {symbol} with Order ID {order_id}: Partial fill of {filled_qty}'),
            EXECTYPE_FILL: lambda: logger.info(f'Order for Symbol {symbol} with Order ID {order_id}: Filled with quantity {filled_qty}'),
            EXECTYPE_DONE: lambda: logger.info(f'Order {order_id} Done'),
            EXECTYPE_CANCELLED: lambda: logger.info(f'Order {order_id} Cancelled, Reason: {reason}'),
            EXECTYPE_STOPPED: lambda: logger.info(f'Order {order_id} Stopped, Reason: {reason}'),
            EXECTYPE_REJECTED: lambda: logger.info(f'Order {order_id} Rejected, Reason: {reason}'),
            EXECTYPE_RESTATED: lambda: logger.info(f'Order {order_id} Restated, Reason: {reason}'),
            EXECTYPE_ORDER_STATUS: lambda: logger.info(f'Order Status for {order_id}'),
        }
        
        handler = handlers.get(exec_type)
        if handler:
            handler()
        else:
            logger.warning(f"Unknown execution type: {exec_type}")
    
    def handle_reject(self, message):
        """Handle reject messages."""
        if message.isSetField(TAG_TEXT):
            reason = message.getField(TAG_TEXT)
            logger.warning(f'Message Rejected, Reason: {reason}')
        else:
            logger.warning('Message Rejected, Reason: Not Returned')
    
    def handle_market_data_snapshot(self, message):
        """Handle market data snapshot messages."""
        logger.info("Received market data snapshot")
    
    def handle_market_data_incremental(self, message):
        """Handle market data incremental refresh messages."""
        logger.info("Received market data incremental refresh")
    
    def handle_position_report(self, message):
        """Handle position report messages."""
        logger.info("Received position report")

class CoinbaseQuickFIXClient(fix.Application):
    """QuickFIX client for Coinbase International Exchange."""
    
    def __init__(self, session_type="order_entry"):
        """
        Initialize the QuickFIX client.
        
        Args:
            session_type: Type of FIX session ("order_entry", "market_data", or "drop_copy")
        """
        super().__init__()
        self.session_type = session_type
        
        if session_type == "order_entry":
            self.host = "fix-international.coinbase.com"
            self.port = 6110
            self.target_sub_id = "OE"
        elif session_type == "market_data":
            self.host = "fix-international.coinbase.com"
            self.port = 6120
            self.target_sub_id = "MD"
        elif session_type == "drop_copy":
            self.host = "fix-international.coinbase.com"
            self.port = 6130
            self.target_sub_id = "DC"
        else:
            raise ValueError(f"Invalid session type: {session_type}")
        
        self.api_key = os.getenv("CB_INTX_API_KEY", "")
        self.api_secret = os.getenv("CB_INTX_API_SECRET", "")
        self.passphrase = os.getenv("CB_INTX_PASSPHRASE", "")
        self.sender_comp_id = os.getenv("CB_INTX_SENDER_COMPID", "")
        self.target_comp_id = "CBINTL"  # Always use CBINTL
        
        self.session_id = None
        self.fix_session = None
        self.authenticated = False
        self.connected = False
        self.next_client_order_id = int(time.time())
        self.next_request_id = int(time.time())
        
        self.on_execution_report_callback = None
        self.on_market_data_callback = None
        self.on_position_report_callback = None
    
    def onCreate(self, session_id):
        """Called when a new FIX session is created."""
        logger.info(f"Session created: {session_id.toString()}")
        self.session_id = session_id
        self.fix_session = FixSession(self.session_id)
    
    def onLogon(self, session_id):
        """Called when a successful logon occurs."""
        logger.info(f"Logon successful for session: {session_id.toString()}")
        self.authenticated = True
        self.connected = True
    
    def onLogout(self, session_id):
        """Called when a logout occurs."""
        logger.info(f"Logout for session: {session_id.toString()}")
        self.authenticated = False
        self.connected = False
    
    def toAdmin(self, message, session_id):
        """Called before sending an administrative message."""
        msg_type = message.getHeader().getField(TAG_MSGTYPE)
        
        if msg_type == MSGTYPE_LOGON:
            message.setField(fix.StringField(TAG_USERNAME, self.api_key))
            message.setField(fix.StringField(TAG_PASSWORD, self.passphrase))
            message.setField(fix.StringField(TAG_RESETSEQNUMFLAG, "Y"))
            message.setField(fix.StringField(TAG_DEFAULTAPPVERID, "9"))  # FIX.5.0SP2
            message.setField(fix.StringField(TAG_TARGETSUBID, self.target_sub_id))
            
            if self.session_type == "order_entry":
                message.setField(fix.StringField(TAG_CANCELORDERSONDISCONNECT, "N"))
                message.setField(fix.StringField(TAG_CANCELORDERSONINTERNALDISCONNECT, "N"))
            
            sending_time = message.getHeader().getField(TAG_SENDINGTIME)
            signature = self.sign(sending_time, self.api_key, self.target_comp_id, self.passphrase, self.api_secret)
            
            message.setField(fix.StringField(TAG_TEXT, signature))
            
            logger.info("Added authentication to Logon message")
    
    def fromAdmin(self, message, session_id):
        """Called when an administrative message is received."""
        msg_type = message.getHeader().getField(TAG_MSGTYPE)
        
        if msg_type == MSGTYPE_REJECT:
            self.handle_session_level_reject(message)
        elif msg_type == MSGTYPE_TESTREQUEST:
            self.handle_test_request(message)
    
    def toApp(self, message, session_id):
        """Called before sending an application message."""
        logger.info(f"Sending application message: {message}")
    
    def fromApp(self, message, session_id):
        """Called when an application message is received."""
        msg_type = message.getHeader().getField(TAG_MSGTYPE)
        
        if msg_type == MSGTYPE_EXECUTIONREPORT:
            if self.on_execution_report_callback:
                self.on_execution_report_callback(message)
            self.fix_session.handle_execution_report(message)
        elif msg_type == MSGTYPE_MARKETDATASNAPSHOTFULLREFRESH:
            if self.on_market_data_callback:
                self.on_market_data_callback(message)
            self.fix_session.handle_market_data_snapshot(message)
        elif msg_type == MSGTYPE_MARKETDATAINCREMENTALREFRESH:
            if self.on_market_data_callback:
                self.on_market_data_callback(message)
            self.fix_session.handle_market_data_incremental(message)
        elif msg_type == MSGTYPE_POSITIONREPORT:
            if self.on_position_report_callback:
                self.on_position_report_callback(message)
            self.fix_session.handle_position_report(message)
        elif msg_type == MSGTYPE_BUSINESSREJECT:
            self.handle_business_reject(message)
        elif msg_type == MSGTYPE_ORDERCANCELREJECT:
            self.handle_order_cancel_reject(message)
    
    def sign(self, sending_time, api_key, target_comp_id, passphrase, api_secret):
        """Generate HMAC-SHA256 signature for authentication."""
        message = f"{sending_time}{api_key}{target_comp_id}{passphrase}".encode("utf-8")
        hmac_key = base64.b64decode(api_secret)
        signature = hmac.new(hmac_key, message, hashlib.sha256)
        sign_b64 = base64.b64encode(signature.digest()).decode()
        return sign_b64
    
    def handle_session_level_reject(self, message):
        """Handle session level reject messages."""
        if message.isSetField(TAG_TEXT):
            reason = message.getField(TAG_TEXT)
            logger.warning(f"Session level reject: {reason}")
        else:
            logger.warning("Session level reject with no reason")
    
    def handle_business_reject(self, message):
        """Handle business reject messages."""
        if message.isSetField(TAG_TEXT):
            reason = message.getField(TAG_TEXT)
            logger.warning(f"Business reject: {reason}")
        else:
            logger.warning("Business reject with no reason")
    
    def handle_order_cancel_reject(self, message):
        """Handle order cancel reject messages."""
        if message.isSetField(TAG_TEXT):
            reason = message.getField(TAG_TEXT)
            logger.warning(f"Order cancel reject: {reason}")
        else:
            logger.warning("Order cancel reject with no reason")
    
    def handle_test_request(self, message):
        """Handle test request messages."""
        if message.isSetField(TAG_TESTREQUEST):
            test_req_id = message.getField(TAG_TESTREQUEST)
            
            heartbeat = fix.Message()
            header = heartbeat.getHeader()
            header.setField(fix.MsgType(MSGTYPE_HEARTBEAT))
            
            if test_req_id:
                heartbeat.setField(fix.TestReqID(test_req_id))
            
            self.fix_session.send_message(heartbeat)
            logger.info(f"Sent heartbeat in response to test request: {test_req_id}")
    
    def _get_next_client_order_id(self):
        """Get the next client order ID."""
        self.next_client_order_id += 1
        return self.next_client_order_id
    
    def _get_next_request_id(self):
        """Get the next request ID."""
        self.next_request_id += 1
        return self.next_request_id
    
    def subscribe_market_data(self, symbol):
        """
        Subscribe to market data for a symbol.
        
        Args:
            symbol: Trading symbol (e.g., "BTC-PERP")
            
        Returns:
            bool: True if subscription request was sent successfully
        """
        if not self.authenticated or self.session_type != "market_data":
            logger.error("Cannot subscribe to market data: Not authenticated or wrong session type")
            return False
        
        try:
            req_id = str(self._get_next_request_id())
            
            mdr = fix.Message()
            header = mdr.getHeader()
            header.setField(fix.MsgType(MSGTYPE_MARKETDATAREQUEST))
            
            mdr.setField(fix.MDReqID(req_id))
            mdr.setField(fix.SubscriptionRequestType('1'))  # Snapshot + Updates
            mdr.setField(fix.MarketDepth(0))  # Full book
            
            group = fix.NoRelatedSym()
            group.setField(fix.Symbol(symbol))
            mdr.addGroup(group)
            
            mdr.setField(fix.NoMDEntryTypes(2))
            
            bid_group = fix.MDEntryType()
            bid_group.setField(fix.MDEntryType('0'))  # Bid
            mdr.addGroup(bid_group)
            
            ask_group = fix.MDEntryType()
            ask_group.setField(fix.MDEntryType('1'))  # Offer
            mdr.addGroup(ask_group)
            
            self.fix_session.send_message(mdr)
            logger.info(f"Sent market data subscription request for {symbol}")
            return True
            
        except Exception as e:
            logger.error(f"Error subscribing to market data: {e}")
            return False
    
    def unsubscribe_market_data(self, symbol):
        """
        Unsubscribe from market data for a symbol.
        
        Args:
            symbol: Trading symbol (e.g., "BTC-PERP")
            
        Returns:
            bool: True if unsubscription request was sent successfully
        """
        if not self.authenticated or self.session_type != "market_data":
            logger.error("Cannot unsubscribe from market data: Not authenticated or wrong session type")
            return False
        
        try:
            req_id = str(self._get_next_request_id())
            
            mdr = fix.Message()
            header = mdr.getHeader()
            header.setField(fix.MsgType(MSGTYPE_MARKETDATAREQUEST))
            
            mdr.setField(fix.MDReqID(req_id))
            mdr.setField(fix.SubscriptionRequestType('2'))  # Unsubscribe
            mdr.setField(fix.MarketDepth(0))
            
            group = fix.NoRelatedSym()
            group.setField(fix.Symbol(symbol))
            mdr.addGroup(group)
            
            self.fix_session.send_message(mdr)
            logger.info(f"Sent market data unsubscription request for {symbol}")
            return True
            
        except Exception as e:
            logger.error(f"Error unsubscribing from market data: {e}")
            return False
    
    def place_order(self, symbol, side, quantity, order_type="LIMIT", price=None, time_in_force="GTC", order_id=None):
        """
        Place a new order.
        
        Args:
            symbol: Trading symbol (e.g., "BTC-PERP")
            side: Order side ("BUY" or "SELL")
            quantity: Order quantity
            order_type: Order type ("LIMIT" or "MARKET")
            price: Limit price (required for LIMIT orders)
            time_in_force: Time in force ("GTC", "IOC", "FOK")
            order_id: Optional client order ID
            
        Returns:
            str: Client order ID if order was sent successfully, empty string otherwise
        """
        if not self.authenticated or self.session_type != "order_entry":
            logger.error("Cannot place order: Not authenticated or wrong session type")
            return ""
        
        try:
            client_order_id = order_id or f"{self.sender_comp_id}-{self._get_next_client_order_id()}"
            
            nos = fix.Message()
            header = nos.getHeader()
            header.setField(fix.MsgType(MSGTYPE_NEWORDERSINGLE))
            
            nos.setField(fix.ClOrdID(client_order_id))
            nos.setField(fix.Symbol(symbol))
            
            if side == "BUY":
                nos.setField(fix.Side(fix.Side_BUY))
            elif side == "SELL":
                nos.setField(fix.Side(fix.Side_SELL))
            else:
                raise ValueError(f"Invalid side: {side}")
            
            if order_type == "LIMIT":
                nos.setField(fix.OrdType(fix.OrdType_LIMIT))
                if price is None:
                    raise ValueError("Price is required for LIMIT orders")
                nos.setField(fix.Price(float(price)))
            elif order_type == "MARKET":
                nos.setField(fix.OrdType(fix.OrdType_MARKET))
            else:
                raise ValueError(f"Invalid order type: {order_type}")
            
            nos.setField(fix.OrderQty(float(quantity)))
            
            if time_in_force == "GTC":
                nos.setField(fix.TimeInForce(fix.TimeInForce_GOOD_TILL_CANCEL))
            elif time_in_force == "IOC":
                nos.setField(fix.TimeInForce(fix.TimeInForce_IMMEDIATE_OR_CANCEL))
            elif time_in_force == "FOK":
                nos.setField(fix.TimeInForce(fix.TimeInForce_FILL_OR_KILL))
            else:
                raise ValueError(f"Invalid time in force: {time_in_force}")
            
            nos.setField(fix.TransactTime())
            
            self.fix_session.send_message(nos)
            logger.info(f"Placed {order_type} {side} order for {quantity} {symbol} "
                       f"with client order ID {client_order_id}")
            
            return client_order_id
            
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return ""
    
    def cancel_order(self, client_order_id, order_id=None, symbol=None, side=None):
        """
        Cancel an existing order.
        
        Args:
            client_order_id: Original client order ID
            order_id: Optional exchange order ID
            symbol: Optional trading symbol
            side: Optional order side
            
        Returns:
            str: Cancel client order ID if cancel request was sent successfully, empty string otherwise
        """
        if not self.authenticated or self.session_type != "order_entry":
            logger.error("Cannot cancel order: Not authenticated or wrong session type")
            return ""
        
        try:
            cancel_client_order_id = f"C-{self._get_next_client_order_id()}"
            
            ocr = fix.Message()
            header = ocr.getHeader()
            header.setField(fix.MsgType(MSGTYPE_ORDERCANCELREQUEST))
            
            ocr.setField(fix.ClOrdID(cancel_client_order_id))
            ocr.setField(fix.OrigClOrdID(client_order_id))
            
            if order_id:
                ocr.setField(fix.OrderID(order_id))
            
            if symbol:
                ocr.setField(fix.Symbol(symbol))
            
            if side:
                if side == "BUY":
                    ocr.setField(fix.Side(fix.Side_BUY))
                elif side == "SELL":
                    ocr.setField(fix.Side(fix.Side_SELL))
            
            ocr.setField(fix.TransactTime())
            
            self.fix_session.send_message(ocr)
            logger.info(f"Sent cancel request for order {client_order_id} with cancel ID {cancel_client_order_id}")
            
            return cancel_client_order_id
            
        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
            return ""
    
    def request_positions(self):
        """
        Request current positions.
        
        Returns:
            bool: True if position request was sent successfully
        """
        if not self.authenticated or self.session_type != "order_entry":
            logger.error("Cannot request positions: Not authenticated or wrong session type")
            return False
        
        try:
            req_id = str(self._get_next_request_id())
            
            rfp = fix.Message()
            header = rfp.getHeader()
            header.setField(fix.MsgType(MSGTYPE_REQUESTFORPOSITIONS))
            
            rfp.setField(fix.PosReqID(req_id))
            rfp.setField(fix.PosReqType(0))  # Positions
            rfp.setField(fix.AccountType(1))  # Account
            rfp.setField(fix.Account(self.sender_comp_id))
            rfp.setField(fix.TransactTime())
            rfp.setField(fix.ClearingBusinessDate(time.strftime("%Y%m%d")))
            
            self.fix_session.send_message(rfp)
            logger.info("Sent position request")
            
            return True
            
        except Exception as e:
            logger.error(f"Error requesting positions: {e}")
            return False
