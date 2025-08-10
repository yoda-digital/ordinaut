#!/usr/bin/env python3

import asyncio
import os
import time
from datetime import datetime
from sqlalchemy import text

os.environ['DATABASE_URL'] = 'postgresql://orchestrator:orchestrator_pw@localhost:5432/orchestrator'

from api.dependencies import get_database
from observability.health import HealthCheck, HealthStatus

async def simple_database_health_check():
    """Simple database health check without any extra dependencies."""
    start_time = time.time()
    timestamp = datetime.utcnow().isoformat() + 'Z'
    
    try:
        print("Starting simple database health check...")
        
        async with get_database() as session:
            print("Got database session")
            
            # Simple connectivity test  
            result = await session.execute(text("SELECT 1 as health_check"))
            print("Executed query")
            
            row = result.fetchone()  # Should NOT be awaited
            print(f"Got row: {row}")
            
            if row and row[0] == 1:
                print("Row check passed")
                
                # Test orchestrator-specific functionality
                result = await session.execute(text("SELECT COUNT(*) as task_count FROM task"))
                print("Executed task count query")
                
                task_row = result.fetchone()  # Should NOT be awaited
                print(f"Got task row: {task_row}")
                
                duration = (time.time() - start_time) * 1000
                
                return HealthCheck(
                    name="database",
                    status=HealthStatus.HEALTHY,
                    message="Database connection successful",
                    duration_ms=duration,
                    timestamp=timestamp,
                    details={
                        "connection_test": "passed",
                        "schema_test": "passed", 
                        "task_table_accessible": True
                    }
                )
            else:
                raise Exception("Health check query returned unexpected result")
                
    except Exception as e:
        print(f"Exception in health check: {e}")
        duration = (time.time() - start_time) * 1000
        
        return HealthCheck(
            name="database",
            status=HealthStatus.UNHEALTHY,
            message="Database health check failed",
            duration_ms=duration,
            timestamp=timestamp,
            error=str(e),
            details={"connection_test": "failed"}
        )

if __name__ == "__main__":
    result = asyncio.run(simple_database_health_check())
    print(f"\nFinal result type: {type(result)}")
    print(f"Final result: {result}")
    if hasattr(result, 'to_dict'):
        print(f"Result dict: {result.to_dict()}")