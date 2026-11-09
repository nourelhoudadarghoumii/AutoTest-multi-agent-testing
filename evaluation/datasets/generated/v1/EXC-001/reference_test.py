import sys
import os
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'source'))
from sample_parser import *
def test_valid():
    assert parse_positive_int("42") == 42


def test_errors():
    import pytest
    with pytest.raises(TypeError):
        parse_positive_int(12)
    with pytest.raises(ValueError):
        parse_positive_int("-5")
