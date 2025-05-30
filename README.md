# Coinbase International Exchange HFT Bot

A modular Python implementation of a **smart channel–breakout** strategy with an **order‑book‑imbalance (OBI) machine‑learning factor**.  
The stack is engineered for the **FIX 5.0 gateway** exposed by *Coinbase International Exchange* (INTX).

## Project structure

```
coinbase_hft/
├── config.py                 # API keys and constants
├── coinbase_fix.cfg          # QuickFIX session settings
├── fix_client.py             # Low‑level FIX connectivity & callbacks
├── data_handler.py           # Order‑book reconstruction & feature calc
├── strategy.py               # Channel‑breakout + OBI ML model
├── execution.py              # Smart order‑placement / risk layer
├── portfolio.py              # Position & PnL tracking
├── main.py                   # Bootstrapper
└── requirements.txt
```

## Quick start

```bash
# 1.  Install deps (needs Python ≥ 3.10)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2.  Export creds (or edit config.py)
export CB_INTX_API_KEY=...
export CB_INTX_API_SECRET=...
export CB_INTX_PASSPHRASE=...
export CB_INTX_SENDER_COMPID=YOUR_COMP_ID

# 3.  Launch
python main.py --symbol BTC-USD --window 120 --threshold 0.15
```

### Notes

* As of **June 3 2025** Coinbase deprecates the legacy *FIX 4.2* order‑entry gateway—this client speaks **FIX 5.0 SP2** by default.︱citeturn0search8  
* Market‑data snapshots (`35=W`) and incremental updates (`35=X`) follow the spec in the INTX docs.︱citeturn0search1  
* Strategy inspiration: recent studies on deep order‑flow imbalance forecasting︱citeturn0search6turn0search9.

## Strategy

1. **Channel breakout** – Detects price escaping a rolling high/low band (default: 2‑minute window).  
2. **Order‑Book Imbalance (OBI)** –  
   \[
     \text{OBI} = \frac{\sum_{i=1}^{k} B_i - \sum_{i=1}^{k} A_i}{\sum_{i=1}^{k} B_i + \sum_{i=1}^{k} A_i}
   \]
   where \(B_i\) and \(A_i\) are size at the \(i\)‑th bid/ask level.  
   A lightweight **SGDClassifier** learns to predict the breakout’s direction using live OBI, short‑horizon returns and volatility.

Orders are first posted passively at the top of book.  If passive fills lag beyond the latency budget (defaults to 200 ms), they are converted to IOC aggressions.

---  
**DISCLAIMER** This codebase is educational and shipped *as‑is*. Run it on a paper account and understand the risks before deploying real capital.

---
**Very Important Updates for Next Steps**
Next steps & suggestions
Feature-engineering – add short-term volatility, trade-imbalance, VWAP distance, and Hawkes-based OFI forecasts for richer inputs.

Risk controls – plug your internal position limits & kill-switches into execution.py.

** Correct any issues occured


comprehensive references for hft strategy:

strategy need to be further improved
