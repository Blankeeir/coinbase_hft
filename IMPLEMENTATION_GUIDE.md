# Coinbase International Exchange FIX Connection Implementation Guide

This guide provides detailed instructions for implementing the fixes required to connect to Coinbase International Exchange using the FIX 5.0 SP2 protocol.

## Issue Summary

The Coinbase International Exchange FIX gateway expects specific session-level headers and authentication parameters:

1. **BeginString**: Must be `FIXT.1.1` (not `FIX.4.4`)
2. **TargetCompID**: Must be `CBINTL` (not `CBINTLMD` or `CBINTLOE`)
3. **TargetSubID**: Required field with values `MD` (market data), `OE` (order entry), or `DC` (drop copy)
4. **HMAC Signature**: Must use `CBINTL` in the pre-hash string
5. **Cancel-on-disconnect flags**: Only for order entry sessions

## Implementation Steps

### 1. Update QuickFIX Configuration (coinbase_fix.cfg)

```
[DEFAULT]
ConnectionType=initiator
FileStorePath=./store
FileLogPath=./log
StartTime=00:00:00
EndTime=23:59:59
UseDataDictionary=Y
DataDictionary=spec/FIX50SP2.xml
TransportDataDictionary=spec/FIXT11.xml
HeartBtInt=30
ResetOnLogout=Y
ResetOnLogon=Y
ReconnectInterval=60
SSLEnable=Y
SSLValidateCertificates=N

# Market Data Session
[SESSION]
BeginString=FIXT.1.1
SenderCompID=CLIENT1
TargetCompID=CBINTL
TargetSubID=MD
ApplVerID=9              # FIX 5.0 SP2
SocketConnectHost=fix.international.coinbase.com
SocketConnectPort=6120
FileLogPath=log/market_data
FileStorePath=store/market_data

# Order Entry Session
[SESSION]
BeginString=FIXT.1.1
SenderCompID=CLIENT1
TargetCompID=CBINTL
TargetSubID=OE
ApplVerID=9              # FIX 5.0 SP2
SocketConnectHost=fix.international.coinbase.com
SocketConnectPort=6110
FileLogPath=log/order_entry
FileStorePath=store/order_entry
```

### 2. Create FIX Data Dictionary Files

Create the directory structure:
```bash
mkdir -p spec log/market_data log/order_entry store/market_data store/order_entry
```

Create `spec/FIXT11.xml` and `spec/FIX50SP2.xml` with the appropriate definitions.

### 3. Update Authentication in fix_client.py

Update the `toAdmin` method to properly authenticate Logon messages:

```python
def toAdmin(self, msg, sessionID):
    msgType = fix.MsgType()
    msg.getHeader().getField(msgType)
    
    # Only authenticate Logon messages
    if msgType.getValue() == fix.MsgType_Logon:
        logger.info("Preparing Logon message for authentication")
        
        # Get session settings
        settings = fix.Session.lookupSession(sessionID).getSessionID()
        targetSubID = fix.TargetSubID()
        settings.getField(targetSubID)
        
        # Generate timestamp for signature
        utc_timestamp = fix.TransactTime().getString()
        
        # Set authentication fields
        msg.setField(fix.Username(API_KEY))
        msg.setField(fix.Password(PASSPHRASE))
        
        # Create signature
        # Signature format: timestamp + api_key + "CBINTL" + passphrase
        message = f"{utc_timestamp}{API_KEY}CBINTL{PASSPHRASE}"
        hmac_key = base64.b64decode(API_SECRET)
        signature = hmac.new(hmac_key, message.encode(), hashlib.sha256).digest()
        signature_b64 = base64.b64encode(signature).decode()
        
        # Set signature fields
        msg.setField(fix.RawDataLength(len(signature_b64)))
        msg.setField(fix.RawData(signature_b64))
        msg.setField(fix.Text(utc_timestamp))
        
        # Only add cancel-on-disconnect flags for order entry sessions
        if targetSubID.getValue() == "OE":
            msg.setField(8013, "N")  # CancelOrdersOnDisconnect
            msg.setField(8014, "N")  # CancelOrdersOnInternalDisconnect
        
        logger.info(f"Logon message authenticated with timestamp {utc_timestamp}")
```

### 4. Create Custom SSL Connection Handler (for AsyncFIX)

If using AsyncFIX, create a custom connection handler in `custom_connection.py`:

```python
class SSLAsyncFIXConnection(AsyncFIXConnection):
    """SSL-enabled AsyncFIXConnection for Coinbase International Exchange."""
    
    def __init__(self, protocol, sender_comp_id, target_comp_id, journaler, 
                 host, port, ssl_context=None, heartbeat_period=30, logger=None):
        """Initialize SSL connection with required parameters."""
        super().__init__(protocol, sender_comp_id, target_comp_id, journaler, 
                         host, port, heartbeat_period, logger)
        
        # Store SSL context for connection
        self.ssl_context = ssl_context if ssl_context else self._create_default_ssl_context()
        
    def _create_default_ssl_context(self):
        """Create a default SSL context if none is provided."""
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context
        
    async def connect(self, ssl=None):
        """Connect with SSL support."""
        try:
            # Use provided SSL context or fall back to stored one
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

### 5. Testing the Connection

Use the provided test script to verify the connection works:

```bash
python test_fix_connection.py
```

The test script will:
1. Connect to the Coinbase International Exchange FIX gateway
2. Authenticate using the correct protocol and CompID/SubID values
3. Subscribe to market data (for market data sessions)
4. Log the results for verification

## Troubleshooting

### Common Issues

1. **Authentication Failures**
   - Verify API credentials are correct
   - Check that the HMAC signature uses "CBINTL" in the pre-hash string
   - Ensure the timestamp format is correct (YYYYMMDD-HH:MM:SS.sss)

2. **Connection Issues**
   - Verify SSL settings are correct
   - Check that you're using the correct host and port
   - Ensure your IP is whitelisted in the Coinbase International settings

3. **Message Routing Issues**
   - Verify TargetSubID is set correctly ("MD", "OE", or "DC")
   - Check that BeginString is "FIXT.1.1"
   - Ensure ApplVerID is set to "9" (FIX 5.0 SP2)

### Logs to Check

- `fix_connection_test.log` - Test script logs
- `log/market_data/` - Market data session logs
- `log/order_entry/` - Order entry session logs

## Next Steps

After implementing these fixes, you should be able to:
1. Connect to the Coinbase International Exchange FIX gateway
2. Authenticate successfully
3. Subscribe to market data
4. Place and manage orders

For additional assistance, refer to the Coinbase International Exchange FIX API documentation.
