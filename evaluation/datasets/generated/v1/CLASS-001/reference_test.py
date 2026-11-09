import sys
import os
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'source'))
from sample_rect import *
def test_rect():
    r = Rectangle(3, 4)
    assert r.area() == 12
    assert r.perimeter() == 14


def test_scale():
    r = Rectangle(2, 3).scale(2)
    assert r.area() == 24
