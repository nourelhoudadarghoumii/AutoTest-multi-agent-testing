import json


def encode_payload(data):
    """Serialize data to a compact JSON string."""
    return json.dumps(data, separators=(",", ":"))
