def shipping_cost(weight_kg, express):
    """Compute shipping cost with weight tiers and an express surcharge."""
    if weight_kg <= 0:
        raise ValueError("weight must be positive")
    if weight_kg <= 1:
        cost = 5.0
    elif weight_kg <= 5:
        cost = 10.0
    elif weight_kg <= 20:
        cost = 25.0
    else:
        cost = 50.0
    if express:
        cost = cost * 2
    return cost
