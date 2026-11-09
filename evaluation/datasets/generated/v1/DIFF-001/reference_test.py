import sys
import os
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'source'))
from sample_intervals import *
def test_merge():
    assert merge_intervals([(1, 3), (2, 6), (8, 10)]) == [(1, 6), (8, 10)]
    assert merge_intervals([]) == []
    assert merge_intervals([(5, 5)]) == [(5, 5)]
