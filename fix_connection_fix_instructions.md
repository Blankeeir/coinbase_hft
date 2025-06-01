# Coinbase International Exchange FIX Connection Fix

This document provides instructions for fixing the FIX connection issues with Coinbase International Exchange.

## Key Issues Identified

1. **SSL Context Not Passed to Connection Method**
   - The SSL context is created but not passed to the `connect()` method
   - Fix: Pass the SSL context to the connect method: `await connection.connect(ssl=ssl_context)`

2. **Incorrect TargetCompID Values**
   - Ensure you're using the correct TargetCompID values:
     - Market Data: `CBINTLMD`
     - Order Entry: `CBINTLOE`
     - Drop Copy: `CBINTLDC`

3. **Authentication Message Format**
   - The authentication message must include specific fields in the correct order
   - Ensure all required fields are included in the Logon message

## How to Apply the Fix

### 1. Update the `connect()` method in `fix_client.py`

Find this code:
```python
await self.connection.connect()
```

Replace with:
```python
await self.connection.connect(ssl=self.ssl_context)
```

### 2. Verify TargetCompID Values in `config.py`

Ensure these values are set correctly:
```python
FIX_TARGET_COMPID_MARKET_DATA = "CBINTLMD"
FIX_TARGET_COMPID_ORDER_ENTRY = "CBINTLOE"
FIX_TARGET_COMPID_DROP_COPY = "CBINTLDC"
```

### 3. Ensure Authentication Message Format is Correct

The Logon message should include these fields:
```python
logon_msg = FIXMessage("A")  # Logon message type
logon_msg.set(98, "0")  # EncryptMethod: No encryption
logon_msg.set(108, "30")  # HeartBtInt: 30s
logon_msg.set(141, "Y")  # ResetSeqNumFlag: Reset sequence numbers

# Authentication fields
logon_msg.set(553, api_key)  # Username: API Key
logon_msg.set(554, passphrase)  # Password: Passphrase
logon_msg.set(95, str(len(signature)))  # RawDataLength: Length of signature
logon_msg.set(96, signature)  # RawData: HMAC signature
logon_msg.set(58, timestamp)  # Text: Timestamp used for signature
logon_msg.set(1137, "9")  # DefaultApplVerID = FIX.5.0SP2

# Coinbase-specific fields
logon_msg.set(8013, "N")  # CancelOrdersOnDisconnect
logon_msg.set(8014, "N")  # CancelOrdersOnInternalDisconnect
```

## Testing the Fix

1. Copy the `fix_connection_fix.py` script to your server
2. Set your API credentials in the `.env` file:
   ```
   CB_INTX_API_KEY=your_api_key
   CB_INTX_API_SECRET=your_api_secret
   CB_INTX_PASSPHRASE=your_passphrase
   CB_INTX_SENDER_COMPID=your_sender_compid
   ```
3. Run the test script:
   ```
   python fix_connection_fix.py
   ```

The script will attempt to connect to the market data session and authenticate. If successful, you should see "Authentication successful!" in the logs.

## Troubleshooting

If you still encounter issues:

1. **Check API Credentials**
   - Ensure your API key, secret, passphrase, and sender CompID are correct
   - Verify your IP is whitelisted in the Coinbase International Exchange dashboard

2. **Verify SSL/TLS Configuration**
   - If you see SSL/TLS errors, try adding:
     ```python
     ssl_context.set_ciphers("DEFAULT:@SECLEVEL=1")
     ```

3. **Check Connection State**
   - State 1: NETWORK_CONN_INITIATED (initial state)
   - State 2: NETWORK_CONN_ESTABLISHED (TLS handshake complete)
   - State 3: LOGON_SENT (Logon message sent)
   - State 4: ESTABLISHED (Logon acknowledged)
   - State 7: LOGON_INITIAL_SENT (Initial Logon sent)

4. **Packet Capture**
   - If all else fails, capture packets to see what's happening:
     ```
     sudo tcpdump -n -s0 -A host fix.international.coinbase.com and port 6120
     ```

## Additional Resources

- [Coinbase International Exchange FIX API Documentation](https://docs.cloud.coinbase.com/intx/docs)
- [AsyncFIX Documentation](https://github.com/nkaz001/asyncfix)
