"""
Data collector for the HFT dashboard.
Collects trading metrics and historical data.
"""
import os
import time
import logging
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
import pandas as pd
import numpy as np

from portfolio import Portfolio
from fix_client import CoinbaseFIXClient
import config

logger = logging.getLogger("coinbase_hft.dashboard.data_collector")

class DataCollector:
    """
    Collects and stores trading metrics for the dashboard.
    """
    def __init__(self, portfolio: Portfolio, symbols: List[str]):
        """
        Initialize the data collector.
        
        Args:
            portfolio: Portfolio instance
            symbols: List of trading symbols
        """
        self.portfolio = portfolio
        self.symbols = symbols
        self.data_dir = os.path.join("dashboard", "data")
        os.makedirs(self.data_dir, exist_ok=True)
        
        self.metrics = {
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
        
        self.last_update = time.time()
        self.update_interval = 60  # seconds
        
        self._initialize_metrics_files()
    
    def _initialize_metrics_files(self):
        """Initialize metrics files with empty data."""
        metrics_file = os.path.join(self.data_dir, "metrics.json")
        if not os.path.exists(metrics_file):
            with open(metrics_file, "w") as f:
                json.dump(self.metrics, f)
        
        equity_file = os.path.join(self.data_dir, "equity_curve.csv")
        if not os.path.exists(equity_file):
            df = pd.DataFrame(columns=["timestamp", "equity"])
            df.to_csv(equity_file, index=False)
        
        trades_file = os.path.join(self.data_dir, "trades.csv")
        if not os.path.exists(trades_file):
            df = pd.DataFrame(columns=[
                "timestamp", "symbol", "side", "quantity", 
                "price", "pnl", "duration"
            ])
            df.to_csv(trades_file, index=False)
    
    async def update_metrics(self):
        """Update trading metrics."""
        try:
            current_time = time.time()
            if current_time - self.last_update < self.update_interval:
                return
            
            self.last_update = current_time
            
            portfolio_summary = self.portfolio.get_portfolio_summary()
            
            balance = portfolio_summary.get("balance", 0.0)
            equity = portfolio_summary.get("equity", 0.0)
            
            timestamp = datetime.now().isoformat()
            
            self.metrics["balance"].append((timestamp, balance))
            self.metrics["equity"].append((timestamp, equity))
            
            today = datetime.now().date()
            today_start = datetime.combine(today, datetime.min.time())
            
            daily_pnl = self.portfolio.get_pnl_since(today_start.timestamp())
            self.metrics["pnl_daily"].append((timestamp, daily_pnl))
            
            total_pnl = portfolio_summary.get("total_pnl", 0.0)
            self.metrics["pnl_total"].append((timestamp, total_pnl))
            
            equity_series = [e[1] for e in self.metrics["equity"]]
            if equity_series:
                peak = max(equity_series)
                current_drawdown = (peak - equity) / peak if peak > 0 else 0.0
                self.metrics["drawdown"].append((timestamp, current_drawdown))
                
                self.metrics["max_drawdown"] = max(
                    self.metrics["max_drawdown"], 
                    current_drawdown
                )
            
            for symbol in self.symbols:
                position = self.portfolio.get_position_quantity(symbol)
                avg_price = self.portfolio.get_position_avg_price(symbol)
                unrealized_pnl = self.portfolio.get_position_unrealized_pnl(symbol)
                
                self.metrics["positions"][symbol] = {
                    "quantity": position,
                    "avg_price": avg_price,
                    "unrealized_pnl": unrealized_pnl,
                    "timestamp": timestamp,
                }
            
            for symbol in self.symbols:
                daily_volume = self.portfolio.get_volume_since(
                    symbol, today_start.timestamp()
                )
                self.metrics["volume_daily"][symbol] = daily_volume
                
                week_start = (datetime.now() - timedelta(days=7)).timestamp()
                weekly_volume = self.portfolio.get_volume_since(symbol, week_start)
                self.metrics["volume_7d"][symbol] = weekly_volume
                
                month_start = (datetime.now() - timedelta(days=30)).timestamp()
                monthly_volume = self.portfolio.get_volume_since(symbol, month_start)
                self.metrics["volume_30d"][symbol] = monthly_volume
            
            if len(self.metrics["equity"]) > 30:
                returns = self._calculate_returns()
                if len(returns) > 0:
                    sharpe = self._calculate_sharpe(returns)
                    self.metrics["sharpe"] = sharpe
            
            trades = self.portfolio.get_closed_trades()
            if trades:
                winning_trades = sum(1 for t in trades if t.get("pnl", 0) > 0)
                self.metrics["win_rate"] = winning_trades / len(trades)
                self.metrics["trade_count"] = len(trades)
                
                for trade in trades:
                    if trade not in self.metrics["trades"]:
                        self.metrics["trades"].append(trade)
            
            await self._save_metrics()
            
        except Exception as e:
            logger.error(f"Error updating metrics: {e}")
    
    def _calculate_returns(self) -> List[float]:
        """
        Calculate daily returns from equity curve.
        
        Returns:
            List[float]: List of daily returns
        """
        equity_values = [e[1] for e in self.metrics["equity"]]
        if len(equity_values) < 2:
            return []
        
        returns = []
        for i in range(1, len(equity_values)):
            if equity_values[i-1] > 0:
                ret = (equity_values[i] - equity_values[i-1]) / equity_values[i-1]
                returns.append(ret)
        
        return returns
    
    def _calculate_sharpe(self, returns: List[float], risk_free_rate: float = 0.0) -> float:
        """
        Calculate Sharpe ratio.
        
        Args:
            returns: List of returns
            risk_free_rate: Risk-free rate
            
        Returns:
            float: Sharpe ratio
        """
        if not returns:
            return 0.0
        
        mean_return = np.mean(returns)
        std_return = np.std(returns)
        
        if std_return == 0:
            return 0.0
        
        sharpe = (mean_return - risk_free_rate) / std_return * np.sqrt(252)
        
        return sharpe
    
    async def _save_metrics(self):
        """Save metrics to files."""
        try:
            metrics_file = os.path.join(self.data_dir, "metrics.json")
            with open(metrics_file, "w") as f:
                metrics_copy = self.metrics.copy()
                json.dump(metrics_copy, f, default=str)
            
            equity_file = os.path.join(self.data_dir, "equity_curve.csv")
            equity_df = pd.DataFrame(
                self.metrics["equity"], 
                columns=["timestamp", "equity"]
            )
            equity_df.to_csv(equity_file, index=False)
            
            trades_file = os.path.join(self.data_dir, "trades.csv")
            if self.metrics["trades"]:
                trades_df = pd.DataFrame(self.metrics["trades"])
                trades_df.to_csv(trades_file, index=False)
            
        except Exception as e:
            logger.error(f"Error saving metrics: {e}")
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get current metrics.
        
        Returns:
            Dict[str, Any]: Current metrics
        """
        return self.metrics
    
    def get_equity_curve(self) -> pd.DataFrame:
        """
        Get equity curve as DataFrame.
        
        Returns:
            pd.DataFrame: Equity curve
        """
        try:
            equity_file = os.path.join(self.data_dir, "equity_curve.csv")
            if os.path.exists(equity_file):
                return pd.read_csv(equity_file)
            else:
                return pd.DataFrame(columns=["timestamp", "equity"])
        except Exception as e:
            logger.error(f"Error loading equity curve: {e}")
            return pd.DataFrame(columns=["timestamp", "equity"])
    
    def get_trades(self) -> pd.DataFrame:
        """
        Get trades as DataFrame.
        
        Returns:
            pd.DataFrame: Trades
        """
        try:
            trades_file = os.path.join(self.data_dir, "trades.csv")
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
