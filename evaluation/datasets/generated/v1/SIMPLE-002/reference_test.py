import sys
import os
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'source'))
from sample_greet import *
def test_greet_name():
    assert greet("Ada") == "Hello, Ada!"


def test_greet_empty():
    assert greet("") == "Hello, world!"
