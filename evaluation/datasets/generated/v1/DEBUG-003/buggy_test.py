import sys
import os
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'source'))
from sample_debug_payload import *


from unittest.mock import patch


def test_encode_uses_json_dumps():
    with patch("sample_debug_payload.json.tool") as dumps_mock:
        dumps_mock.return_value = "{}"
        assert encode_payload({"a": 1}) == "{}"
