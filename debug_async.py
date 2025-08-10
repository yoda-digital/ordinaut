#!/usr/bin/env python3

import asyncio
import os
from sqlalchemy import text

async def debug_database_connection():
    """Debug database connection to understand the Row await issue."""
    print("=== DEBUGGING DATABASE CONNECTION ===")
    
    try:
        print("1. Testing get_database()...")
        db_context = get_database()
        print(f"   get_database() returned: {type(db_context)}")
        
        print("2. Testing async context manager...")
        async with db_context as session:
            print(f"   Session type: {type(session)}")
            
            print("3. Testing execute...")
            result = await session.execute(text("SELECT 1 as test_value"))
            print(f"   Result type: {type(result)}")
            
            print("4. Testing fetchone...")
            row = result.fetchone()  # NOT awaited
            print(f"   Row type: {type(row)}")
            print(f"   Row value: {row}")
            
            if row:
                print(f"   Row[0]: {row[0]}")
                
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Set environment BEFORE importing
    os.environ['DATABASE_URL'] = 'postgresql://orchestrator:orchestrator_pw@localhost:5432/orchestrator'
    
    # Import after setting env
    from api.dependencies import get_database
    
    # Run debug
    asyncio.run(debug_database_connection())