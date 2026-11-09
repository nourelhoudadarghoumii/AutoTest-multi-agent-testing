def clamp(value, low, high):
    """Clamp value into [low, high]; inverted bounds raise ValueError."""
    if low > high:
        raise ValueError("low must be <= high")
    return max(low, min(high, value))
