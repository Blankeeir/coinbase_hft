import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from data_handler import LimitOrderBook


def test_update_and_top_levels_sorted():
    lob = LimitOrderBook()
    # Insert bids and asks in unsorted order
    lob.update('B', 100, 1)
    lob.update('B', 102, 1)
    lob.update('B', 101, 1)

    lob.update('S', 200, 1)
    lob.update('S', 198, 1)
    lob.update('S', 199, 1)

    bids, asks = lob.top_levels(3)
    assert bids == [(102, 1), (101, 1), (100, 1)]
    assert asks == [(198, 1), (199, 1), (200, 1)]


def test_mid_price_empty_and_after_updates():
    lob = LimitOrderBook()
    assert lob.mid_price() is None

    # populate book
    lob.update('B', 100, 1)
    lob.update('S', 200, 1)
    assert lob.mid_price() == (100 + 200) / 2


def test_obi_computation():
    lob = LimitOrderBook()
    lob.update('B', 100, 2)
    lob.update('B', 99, 2)
    lob.update('S', 101, 1)
    lob.update('S', 102, 1)

    # bid volume = 2+2=4, ask volume = 1+1=2
    expected = (4 - 2) / (4 + 2)
    assert lob.obi() == pytest.approx(expected)
