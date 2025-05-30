#!/usr/bin/env python
"""
Dashboard runner for Coinbase International Exchange HFT Bot.
Starts the Streamlit dashboard server.
"""
import os
import sys
import subprocess
import logging
import argparse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("dashboard_runner")

def main():
    """Main function to run the dashboard."""
    parser = argparse.ArgumentParser(description="Run HFT Dashboard")
    parser.add_argument("--port", type=int, default=8501, help="Port to run the dashboard on")
    parser.add_argument("--host", type=str, default="localhost", help="Host to run the dashboard on")
    args = parser.parse_args()
    
    data_dir = os.path.join("dashboard", "data")
    os.makedirs(data_dir, exist_ok=True)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    app_path = os.path.join(script_dir, "app.py")
    
    if not os.path.exists(app_path):
        logger.error(f"Dashboard app not found at {app_path}")
        return 1
    
    cmd = [
        "streamlit", "run", app_path,
        "--server.port", str(args.port),
        "--server.address", args.host,
        "--server.headless", "true",
        "--browser.serverAddress", args.host,
        "--theme.base", "light",
    ]
    
    logger.info(f"Starting dashboard on {args.host}:{args.port}")
    logger.info(f"Command: {' '.join(cmd)}")
    
    try:
        process = subprocess.Popen(cmd)
        logger.info(f"Dashboard running at http://{args.host}:{args.port}")
        process.wait()
        return 0
    except KeyboardInterrupt:
        logger.info("Dashboard stopped by user")
        return 0
    except Exception as e:
        logger.error(f"Error running dashboard: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
