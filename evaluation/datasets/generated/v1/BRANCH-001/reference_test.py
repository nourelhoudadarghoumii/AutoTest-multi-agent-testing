import sys
import os
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'source'))
from sample_grades import *
def test_grades():
    assert classify_grade(95) == "A"
    assert classify_grade(85) == "B"
    assert classify_grade(75) == "C"
    assert classify_grade(65) == "D"
    assert classify_grade(10) == "F"


def test_invalid():
    import pytest
    with pytest.raises(ValueError):
        classify_grade(-1)
