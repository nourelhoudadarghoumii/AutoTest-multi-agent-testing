def median(values):
    """Median of a non-empty list of numbers."""
    if not values:
        raise ValueError("empty data")
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2
