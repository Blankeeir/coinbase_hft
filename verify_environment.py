#!/usr/bin/env python
"""
Environment verification script for Coinbase International Exchange HFT Bot.
This script checks that Python 3.12 is installed and all required packages are accessible.
"""
import sys
import os
import importlib
import logging
import subprocess
import platform

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("verify_environment")

def check_python_version():
    """Check Python version."""
    version = sys.version_info
    logger.info(f"Python version: {sys.version}")
    
    if version.major == 3 and version.minor >= 10:
        logger.info("✓ Python version is 3.10 or higher")
        return True
    else:
        logger.error(f"✗ Python version is {version.major}.{version.minor}, but 3.10+ is required")
        return False

def check_package_imports():
    """Check if required packages can be imported."""
    packages = [
        "asyncfix",
        "pandas",
        "numpy",
        "sklearn",
        "dotenv",
        "aiohttp",
        "websockets",
        "matplotlib",
        "pytz",
        "cryptography",
        "pydantic",
        "streamlit",
        "plotly",
    ]
    
    all_imported = True
    for package in packages:
        try:
            importlib.import_module(package)
            logger.info(f"✓ Successfully imported {package}")
        except ImportError as e:
            logger.error(f"✗ Failed to import {package}: {e}")
            all_imported = False
    
    return all_imported

def check_system_info():
    """Check system information."""
    logger.info(f"Platform: {platform.platform()}")
    logger.info(f"Processor: {platform.processor()}")
    logger.info(f"Python executable: {sys.executable}")
    
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        logger.info("✓ Running in a virtual environment")
    else:
        logger.warning("! Not running in a virtual environment")
    
    logger.info(f"PYTHONPATH: {os.environ.get('PYTHONPATH', 'Not set')}")
    logger.info(f"sys.path: {sys.path}")

def check_pip_packages():
    """Check installed pip packages."""
    try:
        result = subprocess.run([sys.executable, "-m", "pip", "list"], capture_output=True, text=True)
        logger.info("Installed packages:")
        for line in result.stdout.splitlines()[:10]:  # Show first 10 packages
            logger.info(f"  {line}")
        logger.info(f"  ... and {len(result.stdout.splitlines()) - 10} more")
        return True
    except Exception as e:
        logger.error(f"✗ Failed to list pip packages: {e}")
        return False

def main():
    """Main function."""
    logger.info("Starting environment verification")
    
    check_system_info()
    
    python_version_ok = check_python_version()
    packages_ok = check_package_imports()
    pip_packages_ok = check_pip_packages()
    
    if python_version_ok and packages_ok:
        logger.info("✅ Environment verification successful!")
        logger.info("The system is ready to run.")
        logger.info("To run the system in test mode: python run_hft_system.py --test --dashboard")
        return 0
    else:
        logger.error("❌ Environment verification failed. Please fix the issues above before running the system.")
        logger.error("See INSTALL_PYTHON.md for instructions on setting up Python 3.12 and the required packages.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
