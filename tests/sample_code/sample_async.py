import asyncio
from typing import Dict, Any
from functools import wraps

def validate_input(func):
    """Custom decorator for input validation."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        return await func(*args, **kwargs)
    return wrapper

class AsyncAPIClient:
    """Async API client."""
    def __init__(self, url: str):
        self._url = url
        
    @property
    def base_url(self) -> str:
        """Get base URL."""
        return self._url
        
    @staticmethod
    def parse_response(data: dict) -> dict:
        """Parse the response."""
        return data.get("result", {})
        
    async def fetch(self, url: str, timeout: int = 30) -> dict:
        """Fetch data asynchronously."""
        await asyncio.sleep(0.1)
        return {"status": "ok", "url": url}
        
    async def post(self, url: str, payload: dict) -> bool:
        """Post data asynchronously."""
        await asyncio.sleep(0.1)
        return True

@validate_input
async def validate_user_data(data: Dict[str, Any]) -> bool:
    """Validate user data asynchronously."""
    await asyncio.sleep(0.1)
    return True

async def process_payment(amount: float, currency: str) -> dict:
    """Process payment asynchronously."""
    await asyncio.sleep(0.1)
    return {"status": "success", "amount": amount}
