import sys
import os
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'source'))
from sample_flatten import *
def test_flatten():
    assert flatten_dict({"a": {"b": 1}}) == {"a.b": 1}
    assert flatten_dict({}) == {}
    assert flatten_dict({"x": 1}) == {"x": 1}
