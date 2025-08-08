#!/usr/bin/env python3
"""
Validation script for the Personal Agent Orchestrator Scheduler.

This script validates that the scheduler service can be imported and initialized
without runtime errors, and demonstrates the key functionality.
"""

import os
import sys
from datetime import datetime, timezone, timedelta

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def validate_imports():
    """Validate all required imports work correctly."""
    print("Validating imports...")
    
    try:
        from scheduler.tick import SchedulerService
        print("✓ SchedulerService imported successfully")
        
        from engine.rruler import next_occurrence
        print("✓ RRULE processor imported successfully")
        
        from engine.registry import load_active_tasks
        print("✓ Task registry imported successfully")
        
        # Test APScheduler imports
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
        print("✓ APScheduler components imported successfully")
        
        return True
        
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False


def validate_rrule_processing():
    """Validate RRULE processing functionality."""
    print("\nValidating RRULE processing...")
    
    try:
        from engine.rruler import next_occurrence, validate_rrule_syntax
        
        # Test common RRULE patterns
        test_cases = [
            "FREQ=DAILY;BYHOUR=9;BYMINUTE=0",
            "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=30",
            "FREQ=MONTHLY;BYDAY=1MO;BYHOUR=10;BYMINUTE=0",
            "FREQ=YEARLY;BYMONTH=1;BYMONTHDAY=1;BYHOUR=0;BYMINUTE=0"
        ]
        
        for rrule_expr in test_cases:
            next_time = next_occurrence(rrule_expr, "Europe/Chisinau")
            if next_time:
                print(f"✓ RRULE '{rrule_expr}' -> next: {next_time}")
            else:
                print(f"✗ RRULE '{rrule_expr}' produced no future occurrences")
                return False
        
        # Test validation
        validation = validate_rrule_syntax("FREQ=DAILY;BYHOUR=9")
        if validation['valid']:
            print("✓ RRULE validation working correctly")
        else:
            print(f"✗ RRULE validation failed: {validation['errors']}")
            return False
        
        return True
        
    except Exception as e:
        print(f"✗ RRULE processing error: {e}")
        return False


def validate_scheduler_initialization():
    """Validate scheduler service can be initialized."""
    print("\nValidating scheduler initialization...")
    
    try:
        # Mock database URL for testing
        test_db_url = "postgresql://test:test@localhost:5432/test"
        
        # Import with mocked database
        from unittest.mock import patch, Mock
        
        with patch('scheduler.tick.create_engine') as mock_engine:
            mock_engine.return_value = Mock()
            
            from scheduler.tick import SchedulerService
            
            service = SchedulerService(test_db_url, "Europe/Chisinau")
            
            # Validate initialization
            assert service.database_url == test_db_url
            assert service.timezone == "Europe/Chisinau"
            assert service.scheduler is not None
            print("✓ Scheduler service initialized successfully")
            
            # Test task scheduling methods exist
            assert hasattr(service, 'schedule_task_job')
            assert hasattr(service, 'enqueue_due_work')
            assert hasattr(service, 'load_and_schedule_tasks')
            print("✓ Scheduler methods available")
            
            return True
            
    except Exception as e:
        print(f"✗ Scheduler initialization error: {e}")
        return False


def validate_task_scheduling_logic():
    """Validate task scheduling dispatch logic."""
    print("\nValidating task scheduling logic...")
    
    try:
        from unittest.mock import patch, Mock
        
        with patch('scheduler.tick.create_engine') as mock_engine:
            mock_engine.return_value = Mock()
            
            from scheduler.tick import SchedulerService
            
            service = SchedulerService("postgresql://test:test@localhost:5432/test", "UTC")
            
            # Mock the internal scheduling methods
            service._schedule_cron_task = Mock()
            service._schedule_once_task = Mock()  
            service._schedule_rrule_task = Mock()
            
            # Test different task types
            test_tasks = [
                {
                    'id': 'task-1',
                    'title': 'Cron Task',
                    'schedule_kind': 'cron',
                    'schedule_expr': '0 9 * * *',
                    'timezone': 'UTC'
                },
                {
                    'id': 'task-2', 
                    'title': 'Once Task',
                    'schedule_kind': 'once',
                    'schedule_expr': '2025-12-25T09:00:00Z',
                    'timezone': 'UTC'
                },
                {
                    'id': 'task-3',
                    'title': 'RRULE Task', 
                    'schedule_kind': 'rrule',
                    'schedule_expr': 'FREQ=DAILY;BYHOUR=10',
                    'timezone': 'UTC'
                },
                {
                    'id': 'task-4',
                    'title': 'Event Task',
                    'schedule_kind': 'event',
                    'schedule_expr': 'user.notification',
                    'timezone': 'UTC'
                }
            ]
            
            for task in test_tasks:
                service.schedule_task_job(task)
            
            # Verify correct methods were called
            assert service._schedule_cron_task.call_count == 1
            assert service._schedule_once_task.call_count == 1
            assert service._schedule_rrule_task.call_count == 1
            
            print("✓ Task scheduling dispatch logic working correctly")
            return True
            
    except Exception as e:
        print(f"✗ Task scheduling validation error: {e}")
        return False


def main():
    """Run all validation checks."""
    print("Personal Agent Orchestrator Scheduler Validation")
    print("=" * 50)
    
    checks = [
        validate_imports,
        validate_rrule_processing,
        validate_scheduler_initialization,
        validate_task_scheduling_logic
    ]
    
    passed = 0
    total = len(checks)
    
    for check in checks:
        if check():
            passed += 1
        print()  # Add spacing between checks
    
    print("=" * 50)
    print(f"Validation Results: {passed}/{total} checks passed")
    
    if passed == total:
        print("✓ All validations passed! Scheduler is ready for deployment.")
        return 0
    else:
        print("✗ Some validations failed. Please check the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())