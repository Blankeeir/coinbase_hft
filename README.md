# Coinbase International Exchange HFT Bot

A modular Python implementation of a **smart channel–breakout** strategy with an **order‑book‑imbalance (OBI) machine‑learning factor**.  
The stack is engineered for the **FIX 5.0 SP2 gateway** exposed by *Coinbase International Exchange* (INTX).

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
├── requirements.txt          # Dependencies
├── install.sh                # Installation script
├── run_test.py               # Test script
├── STRATEGY_GUIDE.md         # Detailed strategy documentation
└── spec/                     # FIX data dictionaries
    ├── FIXT11.xml            # Transport data dictionary
    └── FIX50SP2.xml          # Application data dictionary
```

## Quick start

```bash
# 1.  Install deps (needs Python ≥ 3.10)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2.  Export creds (or create .env file)
export CB_INTX_API_KEY=...
export CB_INTX_API_SECRET=...
export CB_INTX_PASSPHRASE=...
export CB_INTX_SENDER_COMPID=YOUR_COMP_ID

# 3.  Launch
python main.py --symbol BTC-USD --window 120 --threshold 0.15
```

## Configuration

The system can be configured through environment variables or a `.env` file. Key configuration parameters:

- `CB_INTX_API_KEY`: Coinbase International API key
- `CB_INTX_API_SECRET`: Coinbase International API secret
- `CB_INTX_PASSPHRASE`: Coinbase International API passphrase
- `CB_INTX_SENDER_COMPID`: Your FIX SenderCompID
- `ENVIRONMENT`: `sandbox` or `production` (default: `sandbox`)
- `TRADING_SYMBOL`: Trading symbol (default: `BTC-USD`)
- `POSITION_SIZE`: Position size in base currency (default: `0.01` BTC)
- `MAX_POSITION`: Maximum position size (default: `0.05` BTC)
- `CHANNEL_WINDOW`: Channel window in seconds (default: `120`)
- `OBI_THRESHOLD`: Order book imbalance threshold (default: `0.15`)
- `LATENCY_BUDGET`: Latency budget in milliseconds (default: `200`)

See `config.py` for all available configuration options.

## Strategy

The system implements a smart channel breakout strategy with an order book imbalance (OBI) machine learning factor:

1. **Channel breakout** – Detects price escaping a rolling high/low band (default: 2‑minute window).  
2. **Order‑Book Imbalance (OBI)** –  
   \[
     \text{OBI} = \frac{\sum_{i=1}^{k} B_i - \sum_{i=1}^{k} A_i}{\sum_{i=1}^{k} B_i + \sum_{i=1}^{k} A_i}
   \]
   where \(B_i\) and \(A_i\) are size at the \(i\)‑th bid/ask level.  
   A lightweight **SGDClassifier** learns to predict the breakout's direction using live OBI, short‑horizon returns and volatility.

3. **Advanced Features** – The system includes additional features for improved prediction accuracy:
   - Short-term volatility
   - Trade imbalance
   - VWAP distance
   - Hawkes-based order flow intensity

Orders are first posted passively at the top of book. If passive fills lag beyond the latency budget (defaults to 200 ms), they are converted to IOC aggressions.

## Components

- **FIX Client**: Handles connectivity to Coinbase International Exchange using FIX 5.0 SP2 protocol
- **Data Handler**: Reconstructs the order book and calculates features for the ML model
- **Strategy**: Implements the channel breakout strategy with OBI ML factor
- **Execution Engine**: Handles smart order placement with latency monitoring
- **Portfolio Manager**: Tracks positions and P&L

## Getting Started

### Prerequisites

- Python 3.10 or higher
- Coinbase International Exchange account with FIX API access
- API credentials (key, secret, passphrase, and SenderCompID)

### Installation

1. **Clone the repository**

```bash
git clone https://github.com/yourusername/coinbase_hft.git
cd coinbase_hft
```

2. **Create a virtual environment and install dependencies**

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

3. **Configure your API credentials**

Copy the example environment file and edit it with your credentials:

```bash
cp .env.example .env
nano .env  # Or use any text editor
```

Fill in the following fields:
```
CB_INTX_API_KEY=your_api_key_here
CB_INTX_API_SECRET=your_api_secret_here
CB_INTX_PASSPHRASE=your_passphrase_here
CB_INTX_SENDER_COMPID=your_sender_compid_here
```

4. **Verify your setup**

Run the test setup script to verify that everything is configured correctly:

```bash
python test_setup.py
```

This will check that all required files and directories exist and that the system can initialize properly.

### Running the System

1. **Run with dashboard (recommended)**

The combined runner script starts both the trading system and dashboard:

```bash
python run_hft_system.py --symbol BTC-USD --dashboard
```

Access the dashboard at http://localhost:8501 to monitor your trading performance.

2. **Run in test mode (no trading)**

To test the system without actual trading:

```bash
python run_hft_system.py --test --dashboard
```

This mode bypasses API credential checks and doesn't connect to the exchange.

3. **Run only the trading system**

```bash
python run_hft_system.py --symbol BTC-USD
```

4. **Customize parameters**

```bash
python run_hft_system.py --symbol ETH-USD --window 180 --threshold 0.2 --dashboard
```

### Dashboard

The system includes a real-time dashboard built with Streamlit for monitoring trading performance:

- **Real-time metrics**: Balance, equity, daily PnL, win rate, and Sharpe ratio
- **Performance charts**: Equity curve, PnL, drawdown, and trading volume
- **Position monitoring**: Current positions with unrealized PnL
- **Trade history**: Recent trades with execution details

To start the dashboard:

```bash
python run_hft_system.py --dashboard
```

Or run only the dashboard:

```bash
cd dashboard
python run_dashboard.py
```

### Monitoring and Logs

- Logs are stored in the `log` directory
- Check `coinbase_hft.log` for detailed operation logs
- The bot outputs portfolio summary every 100 trading cycles
- Dashboard metrics are stored in `dashboard/data/` for persistence

### Troubleshooting

1. **Connection Issues**
   - Verify your API credentials in the .env file
   - Check that you have the correct permissions on your Coinbase International account
   - Ensure your IP is whitelisted in the Coinbase International settings

2. **Market Data Issues**
   - Verify that the symbol you're trading is supported
   - Check the log files for any subscription errors

3. **Order Placement Issues**
   - Verify that you have sufficient funds in your account
   - Check position and notional limits in config.py

4. **Performance Optimization**
   - Adjust the TRADING_CYCLE parameter for faster/slower execution
   - Tune the ML model parameters in strategy.py
   - Adjust the LATENCY_BUDGET for your network conditions

For more detailed information on the strategy implementation, see the [Strategy Guide](STRATEGY_GUIDE.md).

## Notes

* As of **June 3 2025** Coinbase deprecates the legacy *FIX 4.2* order‑entry gateway—this client speaks **FIX 5.0 SP2** by default.
* Market‑data snapshots (`35=W`) and incremental updates (`35=X`) follow the spec in the INTX docs.
* Strategy inspiration: recent studies on deep order‑flow imbalance forecasting.

---  
**DISCLAIMER** This codebase is educational and shipped *as‑is*. Run it on a paper account and understand the risks before deploying real capital.
