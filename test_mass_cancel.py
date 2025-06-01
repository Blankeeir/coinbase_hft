#!/usr/bin/env python
"""
Test script for OrderMassCancelRequest implementation.
"""
import asyncio
import logging
from fix_client import CoinbaseFIXClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_mass_cancel")

async def test_mass_cancel():
    """Test mass cancel orders functionality."""
    client = CoinbaseFIXClient(session_type='order_entry', test_mode=True)
    client.authenticated = True
    
    cancel_id = await client.mass_cancel_orders(symbol='BTC-USD', side='BUY', portfolio_id='test-portfolio')
    print(f'Mass cancel request sent with ID: {cancel_id}')
    
    cancel_all_id = await client.mass_cancel_orders()
    print(f'Mass cancel all request sent with ID: {cancel_all_id}')

if __name__ == "__main__":
    asyncio.run(test_mass_cancel())
