import pytest
from asyncfix.message import FIXMessage


@pytest.fixture
def message():
    """Provide a dummy FIXMessage for tests."""
    return FIXMessage("0")


@pytest.fixture
def securities():
    """Dummy list of securities for handler tests."""
    return [{"symbol": "BTC-USD", "security_type": "FXSPOT"}]


@pytest.fixture
def security_def():
    """Dummy security definition for handler tests."""
    return {
        "symbol": "BTC-USD",
        "update_action": "A",
        "security_type": "FXSPOT",
    }
