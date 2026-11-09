import sys
import os
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'source'))
from sample_simple import *
def test_add():
    assert add(2, 3) == 5


def test_sub():
    assert sub(5, 2) == 3
