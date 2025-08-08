"""
Database module with support for multiple database backends.

Currently supports:
- Neon (PostgreSQL) - Primary database
- Firebase (Firestore) - Legacy, being phased out

Usage:
    # Use Neon (default)
    from services.db import db, notify_user, update_status
    
    # Use specific implementation
    from services.db.neon import NeonDatabase
    from services.db.firebase import FirebaseDB
"""

# Import Neon as the default database
from .neon import db, notify_user, update_status, NeonDatabase

# Make commonly used functions available at package level
__all__ = [
    'db',
    'notify_user', 
    'update_status',
    'NeonDatabase'
]

# Optional: Set the active database backend
# This allows switching between implementations if needed
ACTIVE_BACKEND = 'neon'  # or 'firebase'

def get_database():
    """
    Factory function to get the active database implementation.
    Useful for dependency injection or runtime switching.
    """
    if ACTIVE_BACKEND == 'neon':
        from .neon import db
        return db
    elif ACTIVE_BACKEND == 'firebase':
        from .firebase import get_firebase_db
        return get_firebase_db()
    else:
        raise ValueError(f"Unknown database backend: {ACTIVE_BACKEND}")