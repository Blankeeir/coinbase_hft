"""Lightweight REST helper for positions / collateral."""
import time, hmac, hashlib, base64, json, requests
from config import *

def _sign(ts, method, path, body=''):
    message = f'{ts}{method}{path}{body}'.encode()
    hmac_key = base64.b64decode(API_SECRET)
    sig = hmac.new(hmac_key, message, hashlib.sha256).digest()
    return base64.b64encode(sig).decode()

def _headers(method, path, body=''):
    ts = str(int(time.time()))
    return {
        "CB-ACCESS-KEY": API_KEY,
        "CB-ACCESS-SIGN": _sign(ts, method, path, body),
        "CB-ACCESS-TIMESTAMP": ts,
        "CB-ACCESS-PASSPHRASE": PASSPHRASE,
        "Content-Type": "application/json"
    }

def get_positions():
    path = "/api/v1/positions"
    url  = REST_BASE + path
    r = requests.get(url, headers=_headers('GET', path))
    r.raise_for_status()
    return r.json()
