def parse_positive_int(text):
    """Parse a strictly positive integer; raise ValueError on bad input."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    value = int(text)
    if value <= 0:
        raise ValueError(f"expected a positive integer, got {value}")
    return value
