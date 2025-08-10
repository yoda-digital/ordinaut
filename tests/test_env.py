#!/usr/bin/env python3
"""
Test environment setup for Ordinaut.

Sets up environment variables and configurations needed for testing.
"""

import os
import tempfile
from pathlib import Path

def setup_test_environment():
    """Set up environment variables for testing."""
    
    # Create temporary database for testing
    temp_dir = Path(tempfile.mkdtemp())
    test_db_path = temp_dir / "test_orchestrator.db"
    
    # Set database URL for testing
    if not os.getenv("DATABASE_URL"):
        os.environ["DATABASE_URL"] = f"sqlite:///{test_db_path}"
    
    # Set Redis URL for testing (optional)
    if not os.getenv("REDIS_URL"):
        os.environ["REDIS_URL"] = "memory://"
    
    # Set other test environment variables
    os.environ["TESTING"] = "true"
    os.environ["LOG_LEVEL"] = "WARNING"  # Reduce log noise during testing
    
    return {
        "database_url": os.environ["DATABASE_URL"],
        "redis_url": os.environ["REDIS_URL"],
        "temp_dir": temp_dir,
        "test_db_path": test_db_path
    }

# Set up test environment when module is imported
TEST_ENV = setup_test_environment()