def greet(name):
    """Return a greeting; empty name falls back to 'world'."""
    if not name:
        name = "world"
    return f"Hello, {name}!"
