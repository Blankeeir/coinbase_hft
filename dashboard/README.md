# Coinbase International Exchange HFT Dashboard

This dashboard provides real-time monitoring and visualization of the HFT trading system's performance metrics.

## Features

- Real-time equity curve visualization
- Performance metrics (returns, drawdown, Sharpe ratio)
- Trading volume statistics (daily, 7-day, 30-day)
- Position monitoring with risk metrics
- Trade history and analytics

## Components

- `app.py` - Streamlit dashboard application
- `data_collector.py` - Collects and processes trading metrics
- `run_dashboard.py` - Script to start the dashboard server
- `data/` - Directory for storing metrics data

## Running the Dashboard

To start the dashboard:

```bash
# From the project root directory
python dashboard/run_dashboard.py --port 8501 --host localhost
```

This will start the Streamlit server and make the dashboard available at http://localhost:8501.

## Dashboard Sections

1. **Overview** - Key performance metrics including balance, daily PnL, win rate, and Sharpe ratio
2. **Performance Charts** - Interactive charts for equity curve, PnL, drawdown, and trading volume
3. **Positions** - Current open positions with unrealized PnL
4. **Recent Trades** - Table of recent trades with execution details
5. **Trading Statistics** - Summary statistics including total trades, max drawdown, and total PnL

## Data Collection

The dashboard collects data from the trading system in real-time through the `DataCollector` class, which:

- Tracks portfolio balance and equity
- Calculates performance metrics (PnL, drawdown, Sharpe ratio)
- Monitors trading volume across different time periods
- Records trade history and position information

Data is stored in CSV and JSON files in the `data/` directory for persistence between dashboard sessions.

## Customization

You can customize the dashboard by:

- Modifying the Streamlit theme in `run_dashboard.py`
- Adding new visualization components in `app.py`
- Extending the metrics collection in `data_collector.py`
- Adjusting the update frequency in the `DataCollector` class

## Requirements

- Streamlit
- Plotly
- Pandas
- NumPy

These dependencies are included in the main project's `requirements.txt` file.
