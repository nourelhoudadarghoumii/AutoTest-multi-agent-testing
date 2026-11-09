import sys
import os
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'source'))
from sample_debug_ports import *


def test_parse_port_string_raises_value_error():
    with pytest.raises(ValueError):
        parse_port("8080")


def test_parse_port_valid():
    assert parse_port(8080) == 8080
