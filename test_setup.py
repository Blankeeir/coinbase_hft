"""
Test script to verify that the HFT system is properly set up.
This script checks that all required files and directories exist
and that the system can initialize without errors.
"""
import os
import sys
import importlib
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("setup_test")

def check_file_exists(filepath, required=True):
    """Check if a file exists and log the result."""
    exists = os.path.isfile(filepath)
    if exists:
        logger.info(f"✓ Found {filepath}")
    elif required:
        logger.error(f"✗ Missing required file: {filepath}")
    else:
        logger.warning(f"! Missing optional file: {filepath}")
    return exists

def check_directory_exists(dirpath, required=True):
    """Check if a directory exists and log the result."""
    exists = os.path.isdir(dirpath)
    if exists:
        logger.info(f"✓ Found directory {dirpath}")
    elif required:
        logger.error(f"✗ Missing required directory: {dirpath}")
    else:
        logger.warning(f"! Missing optional directory: {dirpath}")
    return exists

def check_module_imports():
    """Try to import all required modules."""
    modules = [
        "config", 
        "fix_client", 
        "data_handler", 
        "strategy", 
        "execution", 
        "portfolio", 
        "main"
    ]
    
    all_imported = True
    for module_name in modules:
        try:
            module = importlib.import_module(module_name)
            logger.info(f"✓ Successfully imported {module_name}")
        except ImportError as e:
            logger.error(f"✗ Failed to import {module_name}: {e}")
            all_imported = False
    
    return all_imported

def main():
    """Run all setup checks."""
    logger.info("Starting HFT system setup verification")
    
    required_files = [
        "requirements.txt",
        "config.py",
        "coinbase_fix.cfg",
        "fix_client.py",
        "data_handler.py",
        "strategy.py",
        "execution.py",
        "portfolio.py",
        "main.py",
        "spec/FIXT11.xml",
        "spec/FIX50SP2.xml",
    ]
    
    optional_files = [
        ".env",
        ".env.example",
        "README.md",
    ]
    
    required_dirs = [
        "spec",
        "log",
        "store",
        "models",
    ]
    
    all_required_files_exist = all(check_file_exists(f) for f in required_files)
    all_optional_files_checked = all(check_file_exists(f, required=False) for f in optional_files)
    all_required_dirs_exist = all(check_directory_exists(d) for d in required_dirs)
    
    all_modules_import = check_module_imports()
    
    if not os.path.isfile(".env") and os.path.isfile(".env.example"):
        logger.info("No .env file found. You should create one from .env.example before running the system.")
        logger.info("Example command: cp .env.example .env")
    
    if all_required_files_exist and all_required_dirs_exist and all_modules_import:
        logger.info("✅ Setup verification completed successfully!")
        logger.info("The system is ready to run once you fill in your API credentials in the .env file.")
        logger.info("To run the system: python main.py --symbol BTC-USD")
        return 0
    else:
        logger.error("❌ Setup verification failed. Please fix the issues above before running the system.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
