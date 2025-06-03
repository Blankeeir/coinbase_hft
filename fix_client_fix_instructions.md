# Coinbase International Exchange FIX Client Fix

This document provides instructions for fixing the FIX client connection issues with Coinbase International Exchange.

## Issue: SSLAsyncFIXConnection.connect() Parameter Error

The error message indicates that the `connect()` method in `SSLAsyncFIXConnection` doesn't accept the `ssl` parameter:

```
SSLAsyncFIXConnection.connect() got an unexpected keyword argument 'ssl'
```

## Solution

### 1. Update SSLAsyncFIXConnection.connect() Method

In `custom_connection.py`, update the `connect()` method to accept the `ssl` parameter:

```python
async def connect(self, ssl=None):
    """Connect with SSL support.
    
    Args:
        ssl: Optional SSL context. If provided, overrides the stored ssl_context.
    """
    try:
        # Use provided SSL context or fall back to the one stored in the instance
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

### 2. Alternative: Update fix_client.py to Not Pass ssl Parameter

If you prefer not to modify the `SSLAsyncFIXConnection` class, you can update the `fix_client.py` file to not pass the `ssl` parameter:

```python
# Before:
await self.connection.connect(ssl=self.ssl_context)

# After:
await self.connection.connect()
```

Since the SSL context is already stored in the connection instance during initialization, this should work as well.

### 3. Verify TargetCompID Values

Ensure these values are set correctly in `config.py`:

```python
FIX_TARGET_COMPID_MARKET_DATA = "CBINTLMD"
FIX_TARGET_COMPID_ORDER_ENTRY = "CBINTLOE"
FIX_TARGET_COMPID_DROP_COPY = "CBINTLDC"
```

## Testing the Fix

1. Run the test script to verify the SSL connection works:
   ```
   python test_ssl_connection.py
   ```

2. If the test is successful, run the main application:
   ```
   python main.py
   ```

## Troubleshooting

If you still encounter issues:

1. Check the connection state transitions:
   - State 1: NETWORK_CONN_INITIATED
   - State 2: NETWORK_CONN_ESTABLISHED (TLS handshake complete)
   - State 3: LOGON_SENT
   - State 4: ESTABLISHED

2. Verify the SSL context configuration:
   ```python
   ssl_context = ssl.create_default_context()
   ssl_context.check_hostname = False
   ssl_context.verify_mode = ssl.CERT_NONE
   ```

3. Ensure the authentication message format is correct:
   ```python
   logon_msg = FIXMessage("A")  # Logon message type
   logon_msg.set(98, "0")  # EncryptMethod: No encryption
   logon_msg.set(108, "30")  # HeartBtInt: 30s
   logon_msg.set(141, "Y")  # ResetSeqNumFlag: Reset sequence numbers
   
   logon_msg.set(553, API_KEY)  # Username: API Key
   logon_msg.set(554, PASSPHRASE)  # Password: Passphrase
   logon_msg.set(95, str(len(signature)))  # RawDataLength: Length of signature
   logon_msg.set(96, signature)  # RawData: HMAC signature
   logon_msg.set(58, timestamp)  # Text: Timestamp used for signature
   logon_msg.set(1137, "9")  # DefaultApplVerID = FIX.5.0SP2
   logon_msg.set(8013, "N")  # CancelOrdersOnDisconnect
   logon_msg.set(8014, "N")  # CancelOrdersOnInternalDisconnect
   ```
