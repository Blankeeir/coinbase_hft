"""
Configuration settings for Coinbase International Exchange HFT Bot.
Handles API keys, trading parameters, and environment settings.
"""
import os
import logging
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

CB_INTX_API_KEY = os.getenv("CB_INTX_API_KEY", "")
CB_INTX_API_SECRET = os.getenv("CB_INTX_API_SECRET", "")
CB_INTX_PASSPHRASE = os.getenv("CB_INTX_PASSPHRASE", "")
CB_INTX_SENDER_COMPID = os.getenv("CB_INTX_SENDER_COMPID", "")

ENVIRONMENT = os.getenv("ENVIRONMENT", "sandbox").lower()  # 'sandbox' or 'production'

if ENVIRONMENT == "sandbox":
    FIX_ORDER_ENTRY_HOST = "n5e2.coinbase.com"
    FIX_ORDER_ENTRY_PORT = 6110
    FIX_MARKET_DATA_HOST = "n5e2.coinbase.com"
    FIX_MARKET_DATA_PORT = 6120
    FIX_DROP_COPY_HOST = "n5e2.coinbase.com"
    FIX_DROP_COPY_PORT = 6130
    REST_API_URL = "https://api-n5e1.coinbase.com"
    WS_API_URL = "wss://ws-md.n5e2.coinbase.com"
else:  # production
    FIX_ORDER_ENTRY_HOST = "fix.international.coinbase.com"
    FIX_ORDER_ENTRY_PORT = 6110
    FIX_MARKET_DATA_HOST = "fix.international.coinbase.com"
    FIX_MARKET_DATA_PORT = 6120
    FIX_DROP_COPY_HOST = "fix.international.coinbase.com"
    FIX_DROP_COPY_PORT = 6130
    REST_API_URL = "https://api.exchange.coinbase.com"
    WS_API_URL = "wss://ws-feed.exchange.coinbase.com"

FIX_VERSION = "FIXT.1.1"
FIX_APP_VERSION = "FIX.5.0SP2"
FIX_TARGET_COMPID = "COINBASE"
FIX_HEARTBEAT_INTERVAL = 30  # seconds
FIX_NETWORK_TIMEOUT = int(os.getenv("FIX_NETWORK_TIMEOUT", "10"))  # seconds
FIX_AUTH_TIMEOUT = int(os.getenv("FIX_AUTH_TIMEOUT", "20"))  # seconds
FIX_MAX_RETRIES = int(os.getenv("FIX_MAX_RETRIES", "3"))  # retry attempts

TRADING_SYMBOL = os.getenv("TRADING_SYMBOL", "BTC-USD")
POSITION_SIZE = float(os.getenv("POSITION_SIZE", "0.01"))  # BTC
MAX_POSITION = float(os.getenv("MAX_POSITION", "0.05"))  # BTC
MAX_NOTIONAL_VALUE = float(os.getenv("MAX_NOTIONAL_VALUE", "10000"))  # USD

CHANNEL_WINDOW = int(os.getenv("CHANNEL_WINDOW", "120"))  # seconds
OBI_THRESHOLD = float(os.getenv("OBI_THRESHOLD", "0.15"))  # Order book imbalance threshold
OBI_LEVELS = int(os.getenv("OBI_LEVELS", "5"))  # Number of levels to use for OBI calculation
LATENCY_BUDGET = float(os.getenv("LATENCY_BUDGET", "200"))  # milliseconds
TRADING_CYCLE = float(os.getenv("TRADING_CYCLE", "50"))  # milliseconds

USE_STOP_LOSS = os.getenv("USE_STOP_LOSS", "True").lower() == "true"
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "0.5"))  # Percentage
TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", "1.0"))  # Percentage
MAX_DRAWDOWN_PCT = float(os.getenv("MAX_DRAWDOWN_PCT", "5.0"))  # Percentage
DAILY_LOSS_LIMIT_PCT = float(os.getenv("DAILY_LOSS_LIMIT_PCT", "2.0"))  # Percentage

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", f"coinbase_hft_{datetime.now().strftime('%Y%m%d')}.log")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("coinbase_hft")

if not all([CB_INTX_API_KEY, CB_INTX_API_SECRET, CB_INTX_PASSPHRASE, CB_INTX_SENDER_COMPID]):
    logger.warning("API credentials not fully configured. Set environment variables or update .env file.")
