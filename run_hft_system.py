#!/usr/bin/env python
"""
Combined runner script for Coinbase International Exchange HFT Bot.
Starts both the trading system and dashboard.
"""
import os
import sys
import argparse
import asyncio
import logging
import subprocess
import signal
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("hft_system_runner")

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Run Coinbase International Exchange HFT Bot")
    parser.add_argument("--symbol", type=str, default="BTC-USD", help="Trading symbol")
    parser.add_argument("--window", type=int, help="Channel window in seconds")
    parser.add_argument("--threshold", type=float, help="OBI threshold")
    parser.add_argument("--dashboard", action="store_true", help="Start dashboard")
    parser.add_argument("--dashboard-port", type=int, default=8501, help="Dashboard port")
    parser.add_argument("--dashboard-host", type=str, default="localhost", help="Dashboard host")
    parser.add_argument("--test", action="store_true", help="Run in test mode (no trading)")
    return parser.parse_args()

async def run_trading_system(args):
    """Run the trading system."""
    try:
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from main import main as trading_main
        
        logger.info(f"Starting trading system for {args.symbol}")
        await trading_main()
        
    except KeyboardInterrupt:
        logger.info("Trading system stopped by user")
    except Exception as e:
        logger.error(f"Error running trading system: {e}")
        return False
    
    return True

def run_dashboard(args):
    """Run the dashboard."""
    try:
        dashboard_script = os.path.join("dashboard", "run_dashboard.py")
        
        if not os.path.exists(dashboard_script):
            logger.error(f"Dashboard script not found at {dashboard_script}")
            return False
        
        cmd = [
            sys.executable, dashboard_script,
            "--port", str(args.dashboard_port),
            "--host", args.dashboard_host,
        ]
        
        logger.info(f"Starting dashboard on {args.dashboard_host}:{args.dashboard_port}")
        process = subprocess.Popen(cmd)
        
        return process
        
    except Exception as e:
        logger.error(f"Error starting dashboard: {e}")
        return None

def run_test_setup():
    """Run test setup script."""
    try:
        test_script = "test_setup.py"
        
        if not os.path.exists(test_script):
            logger.error(f"Test script not found at {test_script}")
            return False
        
        logger.info("Running test setup")
        result = subprocess.run([sys.executable, test_script], capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info("Test setup successful")
            return True
        else:
            logger.error(f"Test setup failed: {result.stderr}")
            return False
        
    except Exception as e:
        logger.error(f"Error running test setup: {e}")
        return False

def check_env_file():
    """Check if .env file exists and API credentials are set."""
    try:
        env_file = ".env"
        
        if not os.path.exists(env_file):
            logger.error(f".env file not found. Please create it from .env.example")
            return False
        
        with open(env_file, "r") as f:
            env_content = f.read()
        
        required_vars = [
            "CB_INTX_API_KEY=",
            "CB_INTX_API_SECRET=",
            "CB_INTX_PASSPHRASE=",
            "CB_INTX_SENDER_COMPID=",
        ]
        
        for var in required_vars:
            if var in env_content:
                logger.error(f"API credentials not fully configured in .env file. Please set {var.strip('=')}")
                return False
        
        return True
        
    except Exception as e:
        logger.error(f"Error checking .env file: {e}")
        return False

def create_required_directories():
    """Create required directories."""
    required_dirs = ["log", "store", "models", "dashboard/data"]
    
    for directory in required_dirs:
        os.makedirs(directory, exist_ok=True)
        logger.info(f"Created directory: {directory}")

async def main():
    """Main function."""
    args = parse_args()
    
    create_required_directories()
    
    if not run_test_setup():
        logger.error("Test setup failed. Please fix the issues before running the system.")
        return 1
    
    if not args.test and not check_env_file():
        logger.error("Environment not properly configured. Please set API credentials in .env file.")
        return 1
    elif args.test:
        logger.info("Running in test mode, skipping API credential check")
    
    dashboard_process = None
    if args.dashboard:
        dashboard_process = run_dashboard(args)
        if not dashboard_process:
            logger.error("Failed to start dashboard")
            return 1
        
        logger.info("Waiting for dashboard to start...")
        time.sleep(3)
    
    if not args.test:
        def signal_handler(sig, frame):
            logger.info(f"Received signal {sig}, shutting down...")
            if dashboard_process:
                dashboard_process.terminate()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        await run_trading_system(args)
    else:
        logger.info("Running in test mode, not starting trading system")
        
        if dashboard_process:
            logger.info("Press Ctrl+C to exit")
            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                logger.info("Stopped by user")
                if dashboard_process:
                    dashboard_process.terminate()
    
    return 0

if __name__ == "__main__":
    asyncio.run(main())
