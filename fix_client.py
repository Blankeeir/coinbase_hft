"""Thin wrapper around QuickFIX for Coinbase INTX."""
import quickfix as fix
import quickfix50sp2 as fix50
import threading, time, logging
import hmac, hashlib, base64
from config import *
from data_handler import LimitOrderBook

logger = logging.getLogger('FIX')
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')

class IntxApp(fix.Application):
    def __init__(self, symbol, book:LimitOrderBook):
        super().__init__()
        self.symbol = symbol
        self.book = book
        self.sessionID = None

    # --- session events ----------------------------------------------------
    def onCreate(self, sessionID):    self.sessionID = sessionID
    def onLogon(self, sessionID):
        logger.info('Logon')
        self._subscribe_market_data()
    def onLogout(self, sessionID):    logger.warning('Logout')
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
            hmac_key = base64.b64decode(API_SECRET)
            signature = hmac.new(hmac_key, message.encode(), hashlib.sha256).digest()
            signature_b64 = base64.b64encode(signature).decode()
            
            msg.setField(fix.RawDataLength(len(signature_b64)))
            msg.setField(fix.RawData(signature_b64))
            msg.setField(fix.Text(utc_timestamp))
            
            if targetSubID.getValue() == "OE":
                msg.setField(8013, "N")  # CancelOrdersOnDisconnect
                msg.setField(8014, "N")  # CancelOrdersOnInternalDisconnect
            
            logger.info(f"Logon message authenticated with timestamp {utc_timestamp}")
    def fromAdmin(self, msg, sessionID): pass
    def toApp(self, msg, sessionID):   pass
    def fromApp(self, msg, sessionID):
        self._route(msg)

    # --- helpers -----------------------------------------------------------
    def _subscribe_market_data(self):
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
        sym_grp.setField(fix.Symbol(self.symbol))
        symbols.addGroup(sym_grp)
        req.setField(symbols)
        fix.Session.sendToTarget(req, self.sessionID)

    def _route(self, msg):
        msg_type = fix.MsgType()
        msg.getHeader().getField(msg_type)
        if msg_type.getValue() == fix.MsgType_MarketDataIncrementalRefresh:
            self._handle_incremental(msg)
        elif msg_type.getValue() == fix.MsgType_MarketDataSnapshotFullRefresh:
            self._handle_snapshot(msg)

    # --- book handlers -----------------------------------------------------
    def _handle_snapshot(self, msg):
        group = fix50.MarketDataSnapshotFullRefresh.NoMDEntries()
        i = 1
        while msg.hasGroup(i, group.getFieldTag()):
            msg.getGroup(i, group)
            side = 'B' if group.getField(fix.MDEntryType()) == fix.MDEntryType_BID else 'A'
            price = float(group.getField(fix.MDEntryPx()))
            size  = float(group.getField(fix.MDEntrySize()))
            self.book.update(side, price, size)
            i += 1
        self.book.on_tick()

    def _handle_incremental(self, msg):
        group = fix50.MarketDataIncrementalRefresh.NoMDEntries()
        i = 1
        while msg.hasGroup(i, group.getFieldTag()):
            msg.getGroup(i, group)
            side_tag = int(group.getField(fix.MDEntryType()))
            if side_tag not in (fix.MDEntryType_BID, fix.MDEntryType_OFFER):
                i += 1; continue
            side = 'B' if side_tag == fix.MDEntryType_BID else 'A'
            price = float(group.getField(fix.MDEntryPx()))
            size  = float(group.getField(fix.MDEntrySize()))
            self.book.update(side, price, size)
            i += 1
        self.book.on_tick()

    # --- order helpers -----------------------------------------------------
    def place_limit_order(self, cloid, side, qty, price):
        logger.info(f'LIMIT {side} {qty}@{price}')
        msg = fix50.NewOrderSingle(
            fix.ClOrdID(cloid),
            fix.Side(fix.Side_BUY if side=='BUY' else fix.Side_SELL),
            fix.TransactTime(),
            fix.OrdType(fix.OrdType_LIMIT)
        )
        msg.setField(fix.OrderQty(qty))
        msg.setField(fix.Price(price))
        msg.setField(fix.Symbol(self.symbol))
        fix.Session.sendToTarget(msg, self.sessionID)

    def place_market_order(self, side, qty):
        logger.info(f'MARKET {side} {qty}')
        msg = fix50.NewOrderSingle(
            fix.ClOrdID(str(int(time.time()*1000))),
            fix.Side(fix.Side_BUY if side=='BUY' else fix.Side_SELL),
            fix.TransactTime(),
            fix.OrdType(fix.OrdType_MARKET)
        )
        msg.setField(fix.OrderQty(qty))
        msg.setField(fix.Symbol(self.symbol))
        fix.Session.sendToTarget(msg, self.sessionID)

    def cancel_order(self, cloid):
        logger.info(f'Cancel {cloid}')
        msg = fix50.OrderCancelRequest(
            fix.OrigClOrdID(cloid),
            fix.ClOrdID(str(int(time.time()*1000))),
            fix.Side(fix.Side_BUY)
        )
        msg.setField(fix.Symbol(self.symbol))
        fix.Session.sendToTarget(msg, self.sessionID)

# ---------------------------------------------------------------------------
def start_fix(symbol, book):
    settings = fix.SessionSettings("coinbase_fix.cfg")
    app = IntxApp(symbol, book)
    store_factory = fix.FileStoreFactory(settings)
    log_factory   = fix.FileLogFactory(settings)
    initiator = fix.SocketInitiator(app, store_factory, settings, log_factory)
    initiator.start()
    return initiator, app
