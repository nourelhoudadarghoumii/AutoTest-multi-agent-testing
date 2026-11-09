import os
import re
import hashlib
from datetime import datetime
from typing import List, Optional

class User:
    """User representation."""
    def __init__(self, username: str, email: str):
        self.username = username
        self.email = email
    
    def validate_email(self) -> bool:
        """Validate user email format."""
        return bool(re.match(r"[^@]+@[^@]+\.[^@]+", self.email))
        
    def hash_password(self, password: str) -> str:
        """Hash the user password."""
        return hashlib.sha256(password.encode()).hexdigest()
        
    @staticmethod
    def create_guest():
        """Create a guest user."""
        return User("guest", "guest@example.com")

def process_login(user: Optional[User], login_attempts: int) -> bool:
    """Process user login with basic logic."""
    if not user:
        return False
    elif login_attempts > 3:
        return False
    elif not user.validate_email():
        return False
    else:
        return True
