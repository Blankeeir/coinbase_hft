"""
Custom AsyncFIX connection class with SSL support.
"""
import asyncio
import logging
import ssl
from asyncfix.connection import AsyncFIXConnection, ConnectionState
from asyncfix.protocol import FIXProtocolBase
from asyncfix.journaler import Journaler

logger = logging.getLogger(__name__)

class SSLAsyncFIXConnection(AsyncFIXConnection):
    """AsyncFIX connection with SSL support."""
    
    def __init__(
        self,
        protocol: FIXProtocolBase,
        sender_comp_id: str,
        target_comp_id: str,
        journaler: Journaler,
        host: str,
        port: int,
        ssl_context: ssl.SSLContext = None,
        heartbeat_period: int = 30,
        logger: logging.Logger = None,
    ):
        """Initialize with SSL context."""
        super().__init__(
            protocol=protocol,
            sender_comp_id=sender_comp_id,
            target_comp_id=target_comp_id,
            journaler=journaler,
            host=host,
            port=port,
            heartbeat_period=heartbeat_period,
            logger=logger,
        )
        self.ssl_context = ssl_context
    
    async def connect(self, ssl=None):
        """Connect with SSL support.
        
        Args:
            ssl: Optional SSL context. If provided, overrides the stored ssl_context.
        """
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
