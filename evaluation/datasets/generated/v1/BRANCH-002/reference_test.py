import sys
import os
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'source'))
from sample_shipping import *
def test_tiers():
    assert shipping_cost(0.5, False) == 5.0
    assert shipping_cost(3, False) == 10.0
    assert shipping_cost(10, False) == 25.0
    assert shipping_cost(30, False) == 50.0


def test_express():
    assert shipping_cost(3, True) == 20.0
