#!/bin/bash

echo "Installing Coinbase International Exchange HFT Bot dependencies..."

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python -m venv .venv
fi

echo "Activating virtual environment..."
source .venv/bin/activate

echo "Installing dependencies..."
pip install -r requirements.txt

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    echo "Creating .env file from .env.example..."
    cp .env.example .env
    echo "Please edit .env file with your API credentials."
fi

echo "Creating required directories..."
mkdir -p log store models

echo "Installation complete!"
echo ""
echo "To run the HFT bot:"
echo "1. Edit .env file with your API credentials"
echo "2. Activate the virtual environment: source .venv/bin/activate"
echo "3. Run the bot: python main.py --symbol BTC-USD"
echo ""
echo "For more options, run: python main.py --help"
