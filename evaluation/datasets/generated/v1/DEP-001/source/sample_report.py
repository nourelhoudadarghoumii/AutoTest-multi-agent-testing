import math

from helpers import median


def describe(values):
    """Basic descriptive statistics; delegates the median to helpers."""
    if not values:
        raise ValueError("empty data")
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "mean": sum(values) / len(values),
        "median": median(values),
        "stdev": math.sqrt(sum((v - sum(values) / len(values)) ** 2 for v in values) / len(values)),
    }
