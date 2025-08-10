#!/usr/bin/env python3
"""
Development script to run the Ordinaut API locally.

This script starts the FastAPI application with uvicorn in development mode
with hot reloading and detailed logging.
"""

import os
import sys
import uvicorn
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def main():
    """Run the FastAPI application in development mode."""
    # Set development environment variables
    os.environ.setdefault("ENVIRONMENT", "development")
    os.environ.setdefault("DEBUG", "true")
    os.environ.setdefault("VERSION", "1.0.0")
    
    # Database URL - use environment or default to local PostgreSQL
    os.environ.setdefault(
        "DATABASE_URL", 
        "postgresql://orchestrator:orchestrator_pw@localhost:5432/orchestrator"
    )
    
    # Redis URL - use environment or default to local Redis
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    
    print("🚀 Starting Ordinaut API")
    print(f"   Environment: {os.environ.get('ENVIRONMENT')}")
    print(f"   Database: {os.environ.get('DATABASE_URL')}")
    print(f"   Redis: {os.environ.get('REDIS_URL')}")
    print("   Documentation: http://localhost:8080/docs")
    print("   API Health: http://localhost:8080/health")
    print()
    
    # Run the application
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8080,
        reload=True,  # Enable hot reloading for development
        log_level="info",
        access_log=True,
        reload_dirs=[str(project_root / "api")]  # Only reload on API changes
    )

if __name__ == "__main__":
    main()