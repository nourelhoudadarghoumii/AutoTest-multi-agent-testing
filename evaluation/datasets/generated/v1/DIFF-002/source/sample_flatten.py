def flatten_dict(nested, prefix=""):
    """Flatten a nested dict into {'a.b.c': value} pairs."""
    items = {}
    for key, value in nested.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            items.update(flatten_dict(value, prefix=path))
        else:
            items[path] = value
    return items
