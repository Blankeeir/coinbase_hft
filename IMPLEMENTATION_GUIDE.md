# Coinbase International Exchange FIX Connection Implementation Guide

This guide provides detailed instructions for implementing the FIX connection fix for the Coinbase International Exchange HFT system.

## Overview of the Issue

The main issue with the FIX connection is that the SSL context is not being passed to the `connect()` method in the `SSLAsyncFIXConnection` class. This results in the following error:

```
SSLAsyncFIXConnection.connect() got an unexpected keyword argument 'ssl'
```

## Implementation Options

You have three options to fix this issue:

### Option 1: Apply the Patch Script (Recommended)

The patch script automatically applies all necessary changes to your existing code.

1. Copy the `fix_client_patch.py` file to your server
2. Run the patch script:
   ```bash
   python fix_client_patch.py
   ```
3. The script will:
   - Create a backup of your `fix_client.py` file
   - Add the `_wait_for_network_connection` method
   - Update the `connect()` method to pass the SSL context
   - Fix the connection state check

### Option 2: Use the Comprehensive Fix

The comprehensive fix provides a complete replacement for the `fix_client.py` file with all issues fixed.

1. Copy the `fix_client_comprehensive_fix.py` file to your server
2. Rename it to replace your existing `fix_client.py`:
   ```bash
   mv fix_client_comprehensive_fix.py fix_client.py
   ```

### Option 3: Manual Fixes

If you prefer to make the changes manually:

1. Update the `SSLAsyncFIXConnection.connect()` method in `custom_connection.py`:
   ```python
   async def connect(self, ssl=None):
       """Connect with SSL support."""
       try:
           ssl_context = ssl if ssl is not None else self.ssl_context
           
           self._socket_reader, self._socket_writer = await asyncio.open_connection(
               self._host, 
               self._port,
               ssl=ssl_context
           )
           
           if not self._aio_task_socket_read:
               self._aio_task_socket_read = asyncio.create_task(self.socket_read_task())
           if not self._aio_task_heartbeat:
               self._aio_task_heartbeat = asyncio.create_task(self.heartbeat_timer_task())
               
           await self._state_set(ConnectionState.NETWORK_CONN_ESTABLISHED)
           
           logger.info(f"SSL connection established to {self._host}:{self._port}")
           
       except Exception as e:
           logger.error(f"SSL connection error: {e}")
           raise
   ```

2. Add a helper method to wait for network connection in `fix_client.py`:
   ```python
   async def _wait_for_network_connection(self, timeout: int = 10) -> bool:
       """Wait for network connection to be established."""
       start_time = time.time()
       while time.time() - start_time < timeout:
           if self.connection.connection_state == ConnectionState.NETWORK_CONN_ESTABLISHED:
               return True
           await asyncio.sleep(0.1)
       return False
   ```

3. Update the connection state check in `fix_client.py`:
   ```python
   # Before:
   if self.connection.connection_state != ConnectionState.NETWORK_CONN_ESTABLISHED:
       logger.error("Failed to establish network connection")
       continue
   
   # After:
   if not await self._wait_for_network_connection():
       logger.error("Timed out waiting for network connection")
       continue
   ```

## Testing the Fix

1. Copy the `test_ssl_connection.py` file to your server
2. Run the test script:
   ```bash
   python test_ssl_connection.py
   ```

The script will test both ways of passing the SSL context:
- Explicitly via the `ssl` parameter
- Using the stored `ssl_context` in the connection instance

If the test is successful, you should see "Connection established" messages in the logs.

## Market Data Message Handlers

We've also implemented comprehensive market data message handlers for:
- SecurityListRequest (35=x)
- SecurityList (35=y)
- SecurityDefinition (35=d)
- MarketDataRequest (35=V)
- MarketDataRequestReject (35=Y)

To test these handlers:
1. Copy the `test_market_data_handlers.py` file to your server
2. Run the test script:
   ```bash
   python test_market_data_handlers.py
   ```

## Troubleshooting

If you still encounter issues:

1. **Check API Credentials**
   - Verify your API key, secret, passphrase, and sender CompID are correct
   - Ensure your IP is whitelisted in the Coinbase International Exchange dashboard

2. **Verify SSL/TLS Configuration**
   - If you see SSL/TLS errors, try adding:
     ```python
     ssl_context.set_ciphers("DEFAULT:@SECLEVEL=1")
     ```

3. **Check Connection State Transitions**
   - State 1: NETWORK_CONN_INITIATED (initial state)
   - State 2: NETWORK_CONN_ESTABLISHED (TLS handshake complete)
   - State 3: LOGON_SENT (Logon message sent)
   - State 4: ESTABLISHED (Logon acknowledged)

4. **Enable Debug Logging**
   - Set logging level to DEBUG for more detailed information:
     ```python
     logging.basicConfig(level=logging.DEBUG)
     ```

5. **Verify Target CompID Values**
   - Market Data: `CBINTLMD`
   - Order Entry: `CBINTLOE`
   - Drop Copy: `CBINTLDC`

## Running the Full System

After applying the fix, you can run the full system:

```bash
python main.py
```

## Additional Resources

- [Coinbase International Exchange FIX API Documentation](https://docs.cloud.coinbase.com/intx/docs)
- [AsyncFIX Documentation](https://github.com/nkaz001/asyncfix)
