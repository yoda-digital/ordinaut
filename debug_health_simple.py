#!/usr/bin/env python3

import asyncio
import os

os.environ['DATABASE_URL'] = 'postgresql://orchestrator:orchestrator_pw@localhost:5432/orchestrator'

from observability.health import SystemHealthMonitor

async def debug_individual_health_checks():
    """Debug individual health checks to see what they return."""
    print("=== DEBUGGING INDIVIDUAL HEALTH CHECKS ===")
    
    monitor = SystemHealthMonitor()
    
    # Test each health check individually
    health_checks = [
        ("API", monitor.check_api_health),
        ("Database", monitor.check_database_health),
        ("Redis", monitor.check_redis_health),
        ("Workers", monitor.check_worker_health),
        ("Scheduler", monitor.check_scheduler_health),
    ]
    
    for name, check_func in health_checks:
        print(f"\n--- Testing {name} health check ---")
        try:
            result = await check_func()
            print(f"Result type: {type(result)}")
            print(f"Result: {result}")
            if hasattr(result, 'to_dict'):
                print(f"Result dict: {result.to_dict()}")
        except Exception as e:
            print(f"Exception: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_individual_health_checks())