def moving_average(values, window):
    """Moving average over `window`-sized slices; window must fit the data."""
    if window <= 0:
        raise ValueError("window must be positive")
    if window > len(values):
        raise ValueError("window larger than data")
    if not values:
        return []
    return [sum(values[i:i + window]) / window for i in range(len(values) - window + 1)]
