"""Centralised configuration for the INTX HFT bot."""
import os

API_KEY    = os.getenv("CB_INTX_API_KEY")
API_SECRET = os.getenv("CB_INTX_API_SECRET")
PASSPHRASE = os.getenv("CB_INTX_PASSPHRASE")

# FIX connectivity
FIX_HOST   = os.getenv("CB_INTX_FIX_HOST", "fix-gateway-int.exchange.coinbase.com")
FIX_PORT   = int(os.getenv("CB_INTX_FIX_PORT", 4198))
SENDER_COMPID = os.getenv("CB_INTX_SENDER_COMPID", "CLIENT1")
TARGET_COMPID = "COINBASE"

# Trading
DEFAULT_SYMBOL = os.getenv("CB_INTX_SYMBOL", "BTC-USD")
LATENCY_BUDGET_MS = int(os.getenv("CB_INTX_LATENCY_MS", 200))
CHANNEL_WINDOW_SEC = int(os.getenv("CB_INTX_CH_WINDOW", 120))
OBI_DEPTH = int(os.getenv("CB_INTX_OBI_DEPTH", 10))
OBI_THRESHOLD = float(os.getenv("CB_INTX_OBI_THRESHOLD", 0.15))

REST_BASE = "https://api-int.exchange.coinbase.com"
