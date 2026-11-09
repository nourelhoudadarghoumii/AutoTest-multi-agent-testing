import sys
import os
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'source'))
from sample_bank import *
def test_flow():
    acc = BankAccount("Ada", 100)
    assert acc.deposit(50) == 150
    assert acc.withdraw(30) == 120
    assert len(acc.history) == 2
