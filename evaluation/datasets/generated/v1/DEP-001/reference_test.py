import sys
import os
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'source'))
from sample_report import *
def test_describe():
    stats = describe([1, 2, 3, 4])
    assert stats["count"] == 4
    assert stats["median"] == 2.5
    assert stats["max"] == 4
