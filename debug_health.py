#!/usr/bin/env python3

import asyncio
import os
import time
from datetime import datetime
from sqlalchemy import text

os.environ['DATABASE_URL'] = 'postgresql://orchestrator:orchestrator_pw@localhost:5432/orchestrator'

from api.dependencies import get_database

async def minimal_database_health_check():
    """Minimal database health check to identify the exact issue."""
    print("=== MINIMAL DATABASE HEALTH CHECK ===")
    start_time = time.time()
    timestamp = datetime.utcnow().isoformat() + 'Z'
    
    try:
        print("Step 1: Getting database connection...")
        async with get_database() as session:
            print("Step 2: Connected, executing query...")
            
            # Simple connectivity test
            result = await session.execute(text("SELECT 1 as health_check"))
            print(f"Step 3: Query executed, result type: {type(result)}")
            
            row = result.fetchone()  # This should NOT be awaited
            print(f"Step 4: fetchone() called, row type: {type(row)}, value: {row}")
            
            if row and row[0] == 1:
                print("Step 5: Health check passed!")
                return True
            else:
                print(f"Step 5: Unexpected result: {row}")
                return False
    
    except Exception as e:
        print(f"ERROR in health check: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    result = asyncio.run(minimal_database_health_check())
    print(f"Health check result: {result}")