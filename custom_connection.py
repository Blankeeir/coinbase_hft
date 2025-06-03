"""Custom SSL connection handler for Coinbase International Exchange FIX API."""
import asyncio
import ssl
import logging
from asyncfix.connection import AsyncFIXConnection, ConnectionState

logger = logging.getLogger("custom_connection")

class SSLAsyncFIXConnection(AsyncFIXConnection):
    """
    SSL-enabled AsyncFIXConnection for Coinbase International Exchange.
    
    This class extends AsyncFIXConnection to properly handle SSL connections
    with the Coinbase International Exchange FIX gateway.
    """
    
    def __init__(self, protocol, sender_comp_id, target_comp_id, journaler, 
                 host, port, ssl_context=None, heartbeat_period=30, logger=None):
        """Initialize SSL connection with required parameters."""
        super().__init__(protocol, sender_comp_id, target_comp_id, journaler, 
                         host, port, heartbeat_period, logger)
        
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
            
    async def _wait_for_network_connection(self, timeout=10):
        """Wait for network connection to be established."""
        start_time = asyncio.get_event_loop().time()
        while self.connection_state != ConnectionState.NETWORK_CONN_ESTABLISHED:
            if asyncio.get_event_loop().time() - start_time > timeout:
                raise TimeoutError("Timeout waiting for network connection")
            await asyncio.sleep(0.1)
