def merge_intervals(intervals):
    """Merge overlapping [start, end] intervals; input may be unsorted."""
    if not intervals:
        return []
    for start, end in intervals:
        if start > end:
            raise ValueError("invalid interval")
    ordered = sorted(intervals)
    merged = [list(ordered[0])]
    for start, end in ordered[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [tuple(pair) for pair in merged]
