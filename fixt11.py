"""FIXT 1.1 Protocol module for Coinbase International Exchange."""
from asyncfix.protocol.protocol_base import FIXProtocolBase

class FIXT11(FIXProtocolBase):
    """FIXT 1.1 protocol definition class for Coinbase INTX."""
    
    beginstring = "FIXT.1.1"
    
    session_message_types = {
        "0", "1", "2", "3", "4", "5", "A", "1", "2", "3", "4", "5"
    }
    
    default_appl_ver_id = "9"
