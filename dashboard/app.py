"""
Streamlit dashboard for Coinbase International Exchange HFT Bot.
Displays real-time trading metrics and performance statistics.
"""
import os
import sys
import time
import json
import logging
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dashboard.data_collector import DataCollector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("coinbase_hft.dashboard")

st.set_page_config(
    page_title="Coinbase HFT Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        color: #1E88E5;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.5rem;
        font-weight: 600;
        color: #424242;
        margin-bottom: 0.5rem;
    }
    .metric-card {
        background-color: #f5f5f5;
        border-radius: 5px;
        padding: 1rem;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    }
    .positive {
        color: #4CAF50;
    }
    .negative {
        color: #F44336;
    }
    .neutral {
        color: #757575;
    }
    .stPlotlyChart {
        height: 400px;
    }
</style>
""", unsafe_allow_html=True)

def load_metrics():
    """Load metrics from file."""
    try:
        metrics_file = os.path.join("dashboard", "data", "metrics.json")
        if os.path.exists(metrics_file):
            with open(metrics_file, "r") as f:
                return json.load(f)
        else:
            return {
                "balance": [],
                "equity": [],
                "pnl_daily": [],
                "pnl_total": [],
                "drawdown": [],
                "sharpe": None,
                "max_drawdown": 0.0,
                "win_rate": 0.0,
                "trade_count": 0,
                "volume_daily": {},
                "volume_7d": {},
                "volume_30d": {},
                "positions": {},
                "trades": [],
            }
    except Exception as e:
        logger.error(f"Error loading metrics: {e}")
        return {}

def load_equity_curve():
    """Load equity curve from file."""
    try:
        equity_file = os.path.join("dashboard", "data", "equity_curve.csv")
        if os.path.exists(equity_file):
            return pd.read_csv(equity_file)
        else:
            return pd.DataFrame(columns=["timestamp", "equity"])
    except Exception as e:
        logger.error(f"Error loading equity curve: {e}")
        return pd.DataFrame(columns=["timestamp", "equity"])

def load_trades():
    """Load trades from file."""
    try:
        trades_file = os.path.join("dashboard", "data", "trades.csv")
        if os.path.exists(trades_file):
            return pd.read_csv(trades_file)
        else:
            return pd.DataFrame(columns=[
                "timestamp", "symbol", "side", "quantity", 
                "price", "pnl", "duration"
            ])
    except Exception as e:
        logger.error(f"Error loading trades: {e}")
        return pd.DataFrame(columns=[
                "timestamp", "symbol", "side", "quantity", 
                "price", "pnl", "duration"
            ])

def format_number(value, precision=2, prefix="", suffix=""):
    """Format number with prefix and suffix."""
    if value is None:
        return "N/A"
    
    formatted = f"{prefix}{value:.{precision}f}{suffix}"
    return formatted

def create_equity_chart(equity_df):
    """Create equity curve chart."""
    if equity_df.empty:
        return go.Figure()
    
    equity_df["timestamp"] = pd.to_datetime(equity_df["timestamp"])
    
    fig = go.Figure()
    
    fig.add_trace(
        go.Scatter(
            x=equity_df["timestamp"],
            y=equity_df["equity"],
            mode="lines",
            name="Equity",
            line=dict(color="#1E88E5", width=2),
        )
    )
    
    fig.update_layout(
        title="Equity Curve",
        xaxis_title="Time",
        yaxis_title="Equity",
        height=400,
        margin=dict(l=0, r=0, t=40, b=0),
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
        ),
    )
    
    return fig

def create_pnl_chart(metrics):
    """Create PnL chart."""
    if not metrics.get("pnl_daily"):
        return go.Figure()
    
    pnl_df = pd.DataFrame(metrics["pnl_daily"], columns=["timestamp", "pnl"])
    pnl_df["timestamp"] = pd.to_datetime(pnl_df["timestamp"])
    
    fig = go.Figure()
    
    fig.add_trace(
        go.Bar(
            x=pnl_df["timestamp"],
            y=pnl_df["pnl"],
            name="Daily PnL",
            marker_color=["#4CAF50" if p >= 0 else "#F44336" for p in pnl_df["pnl"]],
        )
    )
    
    fig.update_layout(
        title="Daily PnL",
        xaxis_title="Date",
        yaxis_title="PnL",
        height=400,
        margin=dict(l=0, r=0, t=40, b=0),
        hovermode="x unified",
    )
    
    return fig

def create_drawdown_chart(metrics):
    """Create drawdown chart."""
    if not metrics.get("drawdown"):
        return go.Figure()
    
    dd_df = pd.DataFrame(metrics["drawdown"], columns=["timestamp", "drawdown"])
    dd_df["timestamp"] = pd.to_datetime(dd_df["timestamp"])
    dd_df["drawdown"] = dd_df["drawdown"] * 100  # Convert to percentage
    
    fig = go.Figure()
    
    fig.add_trace(
        go.Scatter(
            x=dd_df["timestamp"],
            y=dd_df["drawdown"],
            mode="lines",
            name="Drawdown",
            line=dict(color="#F44336", width=2),
            fill="tozeroy",
        )
    )
    
    fig.update_layout(
        title="Drawdown",
        xaxis_title="Time",
        yaxis_title="Drawdown (%)",
        height=400,
        margin=dict(l=0, r=0, t=40, b=0),
        hovermode="x unified",
    )
    
    return fig

def create_volume_chart(metrics):
    """Create trading volume chart."""
    if not metrics.get("volume_daily"):
        return go.Figure()
    
    symbols = list(metrics["volume_daily"].keys())
    
    data = []
    for symbol in symbols:
        data.append({
            "symbol": symbol,
            "daily": metrics["volume_daily"].get(symbol, 0),
            "weekly": metrics["volume_7d"].get(symbol, 0),
            "monthly": metrics["volume_30d"].get(symbol, 0),
        })
    
    volume_df = pd.DataFrame(data)
    
    fig = go.Figure()
    
    for period in ["daily", "weekly", "monthly"]:
        fig.add_trace(
            go.Bar(
                x=volume_df["symbol"],
                y=volume_df[period],
                name=period.capitalize(),
            )
        )
    
    fig.update_layout(
        title="Trading Volume",
        xaxis_title="Symbol",
        yaxis_title="Volume",
        height=400,
        margin=dict(l=0, r=0, t=40, b=0),
        hovermode="x unified",
        barmode="group",
    )
    
    return fig

def create_trades_table(trades_df):
    """Create trades table."""
    if trades_df.empty:
        return None
    
    trades_df["timestamp"] = pd.to_datetime(trades_df["timestamp"])
    
    trades_df = trades_df.sort_values("timestamp", ascending=False)
    
    trades_df["timestamp"] = trades_df["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
    trades_df["price"] = trades_df["price"].apply(lambda x: f"${x:.2f}")
    trades_df["pnl"] = trades_df["pnl"].apply(
        lambda x: f"<span class='positive'>${x:.2f}</span>" if x >= 0 
        else f"<span class='negative'>${x:.2f}</span>"
    )
    
    trades_df = trades_df.rename(columns={
        "timestamp": "Time",
        "symbol": "Symbol",
        "side": "Side",
        "quantity": "Quantity",
        "price": "Price",
        "pnl": "PnL",
        "duration": "Duration (ms)",
    })
    
    trades_df = trades_df.head(20)
    
    return trades_df

def main():
    """Main dashboard function."""
    st.markdown("<div class='main-header'>Coinbase International Exchange HFT Dashboard</div>", unsafe_allow_html=True)
    
    last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.markdown(f"Last updated: {last_update}")
    
    metrics = load_metrics()
    equity_df = load_equity_curve()
    trades_df = load_trades()
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown("<div class='sub-header'>Balance</div>", unsafe_allow_html=True)
        balance = metrics.get("balance", [])
        current_balance = balance[-1][1] if balance else 0
        st.markdown(f"<div class='metric-card'>${current_balance:.2f}</div>", unsafe_allow_html=True)
    
    with col2:
        st.markdown("<div class='sub-header'>Daily PnL</div>", unsafe_allow_html=True)
        daily_pnl = metrics.get("pnl_daily", [])
        current_pnl = daily_pnl[-1][1] if daily_pnl else 0
        pnl_class = "positive" if current_pnl >= 0 else "negative"
        st.markdown(f"<div class='metric-card'><span class='{pnl_class}'>${current_pnl:.2f}</span></div>", unsafe_allow_html=True)
    
    with col3:
        st.markdown("<div class='sub-header'>Win Rate</div>", unsafe_allow_html=True)
        win_rate = metrics.get("win_rate", 0) * 100
        st.markdown(f"<div class='metric-card'>{win_rate:.1f}%</div>", unsafe_allow_html=True)
    
    with col4:
        st.markdown("<div class='sub-header'>Sharpe Ratio</div>", unsafe_allow_html=True)
        sharpe = metrics.get("sharpe", 0)
        sharpe_class = "positive" if sharpe > 1 else ("neutral" if sharpe > 0 else "negative")
        st.markdown(f"<div class='metric-card'><span class='{sharpe_class}'>{sharpe:.2f}</span></div>", unsafe_allow_html=True)
    
    st.markdown("<div class='sub-header'>Performance Charts</div>", unsafe_allow_html=True)
    
    tab1, tab2, tab3, tab4 = st.tabs(["Equity", "PnL", "Drawdown", "Volume"])
    
    with tab1:
        equity_chart = create_equity_chart(equity_df)
        st.plotly_chart(equity_chart, use_container_width=True)
    
    with tab2:
        pnl_chart = create_pnl_chart(metrics)
        st.plotly_chart(pnl_chart, use_container_width=True)
    
    with tab3:
        drawdown_chart = create_drawdown_chart(metrics)
        st.plotly_chart(drawdown_chart, use_container_width=True)
    
    with tab4:
        volume_chart = create_volume_chart(metrics)
        st.plotly_chart(volume_chart, use_container_width=True)
    
    st.markdown("<div class='sub-header'>Current Positions</div>", unsafe_allow_html=True)
    
    positions = metrics.get("positions", {})
    if positions:
        position_data = []
        for symbol, pos in positions.items():
            position_data.append({
                "Symbol": symbol,
                "Quantity": pos.get("quantity", 0),
                "Avg Price": f"${pos.get('avg_price', 0):.2f}",
                "Unrealized PnL": pos.get("unrealized_pnl", 0),
            })
        
        position_df = pd.DataFrame(position_data)
        position_df["Unrealized PnL"] = position_df["Unrealized PnL"].apply(
            lambda x: f"<span class='positive'>${x:.2f}</span>" if x >= 0 
            else f"<span class='negative'>${x:.2f}</span>"
        )
        
        st.markdown(position_df.to_html(escape=False, index=False), unsafe_allow_html=True)
    else:
        st.info("No active positions")
    
    st.markdown("<div class='sub-header'>Recent Trades</div>", unsafe_allow_html=True)
    
    trades_table = create_trades_table(trades_df)
    if trades_table is not None:
        st.markdown(trades_table.to_html(escape=False, index=False), unsafe_allow_html=True)
    else:
        st.info("No trades recorded yet")
    
    st.markdown("<div class='sub-header'>Trading Statistics</div>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
        st.markdown("**Total Trades**", unsafe_allow_html=True)
        st.markdown(f"{metrics.get('trade_count', 0)}", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    
    with col2:
        st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
        st.markdown("**Max Drawdown**", unsafe_allow_html=True)
        max_dd = metrics.get("max_drawdown", 0) * 100
        st.markdown(f"<span class='negative'>{max_dd:.2f}%</span>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    
    with col3:
        st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
        st.markdown("**Total PnL**", unsafe_allow_html=True)
        total_pnl = metrics.get("pnl_total", [])
        current_total_pnl = total_pnl[-1][1] if total_pnl else 0
        pnl_class = "positive" if current_total_pnl >= 0 else "negative"
        st.markdown(f"<span class='{pnl_class}'>${current_total_pnl:.2f}</span>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
