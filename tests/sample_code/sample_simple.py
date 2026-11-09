import math
import os

def calculate_tax(amount: float, rate: float, country: str) -> float:
    """Calculate tax for a given amount and rate."""
    return amount + (amount * rate)

def format_price(amount: float, currency: str) -> str:
    """Format the price with currency symbol."""
    return f"{amount:.2f} {currency}"
