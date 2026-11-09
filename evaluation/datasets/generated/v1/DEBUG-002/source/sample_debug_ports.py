def parse_port(text):
    """Parse a port number (1-65535). Raises TypeError on non-int input."""
    if not isinstance(text, int):
        raise TypeError("port must be an integer")
    if not 1 <= text <= 65535:
        raise ValueError("port out of range")
    return text
