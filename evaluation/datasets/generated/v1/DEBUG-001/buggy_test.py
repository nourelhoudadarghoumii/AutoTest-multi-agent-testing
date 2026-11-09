import sys
import os
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'source'))
from sample_debug_add import *


def test_add():
    assert add(2, 3) == 6


def test_add_negative():
    assert add(-1, -2) == -3


def test_multiply():
    assert multiply(3, 4) == 12
