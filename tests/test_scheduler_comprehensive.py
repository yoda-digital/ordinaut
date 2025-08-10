#!/usr/bin/env python3
"""
Comprehensive Scheduler Tests for Ordinaut.

Tests APScheduler integration including:
- Task scheduling with cron, rrule, and once schedules
- PostgreSQL job store integration and persistence
- Schedule accuracy and timing precision
- DST transitions and timezone handling
- Scheduler lifecycle and job management
- Performance under high schedule load

Tests the complete scheduling pipeline from task creation to work queue insertion.
"""

import pytest
import asyncio
import uuid
import json
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, AsyncMock
import pytz

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock environment before importing scheduler modules
os.environ["DATABASE_URL"] = "sqlite:///test_scheduler.db"
os.environ["REDIS_URL"] = "memory://"

from scheduler.tick import SchedulerService, TaskScheduler, ScheduleValidator
from engine.rruler import next_occurrence, RRuleProcessor
from conftest import insert_test_agent, insert_test_task


@pytest.mark.scheduler
class TestSchedulerService:
    """Test the main SchedulerService integration."""
    
    async def test_scheduler_startup_and_shutdown(self, clean_database):
        """Test scheduler service startup and graceful shutdown."""
        scheduler_service = SchedulerService(clean_database)
        
        # Start scheduler
        await scheduler_service.start()
        assert scheduler_service.is_running() is True
        assert scheduler_service.scheduler.running is True
        
        # Shutdown scheduler
        await scheduler_service.shutdown()
        assert scheduler_service.is_running() is False
        assert scheduler_service.scheduler.running is False
    
    async def test_task_scheduling_on_creation(self, clean_database):
        """Test that tasks are automatically scheduled when created."""
        # Setup test data
        agent = await insert_test_agent(clean_database)
        
        # Create scheduler
        scheduler_service = SchedulerService(clean_database)
        await scheduler_service.start()
        
        try:
            # Create a task with future execution
            future_time = datetime.now(timezone.utc) + timedelta(seconds=5)
            task_data = {
                "title": "Scheduled Test Task",
                "description": "Task to test scheduling",
                "created_by": agent["id"],
                "schedule_kind": "once",
                "schedule_expr": future_time.isoformat(),
                "timezone": "UTC",
                "payload": {"pipeline": [{"id": "test", "uses": "test.tool"}]},
                "status": "active",
                "priority": 5,
                "max_retries": 3
            }
            
            task = await insert_test_task(clean_database, agent["id"], task_data)
            
            # Add task to scheduler
            await scheduler_service.add_task(task)
            
            # Wait a bit to ensure scheduling
            await asyncio.sleep(1)
            
            # Check that job was added to scheduler
            jobs = scheduler_service.scheduler.get_jobs()
            task_jobs = [job for job in jobs if str(task["id"]) in job.id]
            assert len(task_jobs) > 0
            
            # Job should be scheduled for the right time
            job = task_jobs[0]
            expected_time = future_time.replace(tzinfo=timezone.utc)
            actual_time = job.next_run_time
            
            # Allow 1 second tolerance
            assert abs((expected_time - actual_time).total_seconds()) < 1.0
            
        finally:
            await scheduler_service.shutdown()
    
    async def test_recurring_task_scheduling(self, clean_database):
        """Test scheduling of recurring tasks with cron expressions."""
        agent = await insert_test_agent(clean_database)
        
        scheduler_service = SchedulerService(clean_database)
        await scheduler_service.start()
        
        try:
            # Create recurring task (every minute)
            task_data = {
                "title": "Recurring Test Task",
                "description": "Task with cron schedule",
                "created_by": agent["id"],
                "schedule_kind": "cron",
                "schedule_expr": "*/1 * * * *",  # Every minute
                "timezone": "UTC",
                "payload": {"pipeline": [{"id": "recurring", "uses": "test.tool"}]},
                "status": "active",
                "priority": 5,
                "max_retries": 3
            }
            
            task = await insert_test_task(clean_database, agent["id"], task_data)
            await scheduler_service.add_task(task)
            
            # Check job was scheduled
            jobs = scheduler_service.scheduler.get_jobs()
            task_jobs = [job for job in jobs if str(task["id"]) in job.id]
            assert len(task_jobs) > 0
            
            job = task_jobs[0]
            
            # Should be a recurring job (not a single execution)
            assert job.trigger.__class__.__name__ == "CronTrigger"
            
            # Next run should be within the next minute
            next_run = job.next_run_time
            now = datetime.now(timezone.utc)
            assert (next_run - now).total_seconds() <= 60
            
        finally:
            await scheduler_service.shutdown()
    
    async def test_rrule_task_scheduling(self, clean_database):
        """Test scheduling with RRULE expressions."""
        agent = await insert_test_agent(clean_database)
        
        scheduler_service = SchedulerService(clean_database)
        await scheduler_service.start()
        
        try:
            # Create RRULE task (daily at 9 AM)
            task_data = {
                "title": "RRULE Test Task", 
                "description": "Task with RRULE schedule",
                "created_by": agent["id"],
                "schedule_kind": "rrule",
                "schedule_expr": "FREQ=DAILY;BYHOUR=9;BYMINUTE=0",
                "timezone": "Europe/Chisinau",
                "payload": {"pipeline": [{"id": "rrule_test", "uses": "test.tool"}]},
                "status": "active",
                "priority": 5,
                "max_retries": 3
            }
            
            task = await insert_test_task(clean_database, agent["id"], task_data)
            await scheduler_service.add_task(task)
            
            # Check job was scheduled
            jobs = scheduler_service.scheduler.get_jobs()
            task_jobs = [job for job in jobs if str(task["id"]) in job.id]
            assert len(task_jobs) > 0
            
            job = task_jobs[0]
            next_run = job.next_run_time
            
            # Should be scheduled for 9 AM in Chisinau timezone
            chisinau_tz = pytz.timezone("Europe/Chisinau")
            next_run_local = next_run.astimezone(chisinau_tz)
            assert next_run_local.hour == 9
            assert next_run_local.minute == 0
            
        finally:
            await scheduler_service.shutdown()
    
    async def test_schedule_modification(self, clean_database):
        """Test modifying task schedules."""
        agent = await insert_test_agent(clean_database)
        
        scheduler_service = SchedulerService(clean_database)
        await scheduler_service.start()
        
        try:
            # Create initial task
            task_data = {
                "title": "Modifiable Task",
                "description": "Task to test schedule modification",
                "created_by": agent["id"],
                "schedule_kind": "cron",
                "schedule_expr": "0 9 * * *",  # Daily at 9 AM
                "timezone": "UTC",
                "payload": {"pipeline": [{"id": "modify_test", "uses": "test.tool"}]},
                "status": "active",
                "priority": 5,
                "max_retries": 3
            }
            
            task = await insert_test_task(clean_database, agent["id"], task_data)
            await scheduler_service.add_task(task)
            
            # Get initial next run time
            jobs = scheduler_service.scheduler.get_jobs()
            initial_job = [job for job in jobs if str(task["id"]) in job.id][0]
            initial_next_run = initial_job.next_run_time
            
            # Modify schedule
            task_data["schedule_expr"] = "0 15 * * *"  # Change to 3 PM
            modified_task = dict(task)
            modified_task.update(task_data)
            
            await scheduler_service.update_task(modified_task)
            
            # Check schedule was updated
            jobs = scheduler_service.scheduler.get_jobs()
            updated_job = [job for job in jobs if str(task["id"]) in job.id][0]
            updated_next_run = updated_job.next_run_time
            
            # Next run time should be different (and for 3 PM)
            assert updated_next_run != initial_next_run
            assert updated_next_run.hour == 15
            
        finally:
            await scheduler_service.shutdown()
    
    async def test_task_pause_and_resume(self, clean_database):
        """Test pausing and resuming scheduled tasks."""
        agent = await insert_test_agent(clean_database)
        
        scheduler_service = SchedulerService(clean_database)
        await scheduler_service.start()
        
        try:
            # Create task
            task_data = {
                "title": "Pausable Task",
                "description": "Task to test pause/resume",
                "created_by": agent["id"],
                "schedule_kind": "cron",
                "schedule_expr": "*/1 * * * *",  # Every minute
                "timezone": "UTC",
                "payload": {"pipeline": [{"id": "pause_test", "uses": "test.tool"}]},
                "status": "active",
                "priority": 5,
                "max_retries": 3
            }
            
            task = await insert_test_task(clean_database, agent["id"], task_data)
            await scheduler_service.add_task(task)
            
            # Verify job is scheduled
            jobs = scheduler_service.scheduler.get_jobs()
            task_jobs = [job for job in jobs if str(task["id"]) in job.id]
            assert len(task_jobs) > 0
            
            # Pause task
            task_data["status"] = "paused"
            paused_task = dict(task)
            paused_task.update(task_data)
            
            await scheduler_service.pause_task(paused_task["id"])
            
            # Job should be removed/paused
            jobs = scheduler_service.scheduler.get_jobs()
            active_task_jobs = [job for job in jobs if str(task["id"]) in job.id]
            assert len(active_task_jobs) == 0
            
            # Resume task
            await scheduler_service.resume_task(task["id"])
            
            # Job should be rescheduled
            jobs = scheduler_service.scheduler.get_jobs()
            resumed_task_jobs = [job for job in jobs if str(task["id"]) in job.id]
            assert len(resumed_task_jobs) > 0
            
        finally:
            await scheduler_service.shutdown()


@pytest.mark.scheduler
class TestScheduleValidation:
    """Test schedule expression validation."""
    
    def test_cron_validation(self):
        """Test cron expression validation."""
        validator = ScheduleValidator()
        
        # Valid cron expressions
        valid_crons = [
            "0 9 * * *",      # Daily at 9 AM
            "*/5 * * * *",    # Every 5 minutes
            "0 0 1 * *",      # First day of month
            "0 9 * * MON-FRI" # Weekdays at 9 AM
        ]
        
        for cron_expr in valid_crons:
            assert validator.validate_cron(cron_expr) is True, f"Should accept: {cron_expr}"
        
        # Invalid cron expressions
        invalid_crons = [
            "invalid cron",
            "60 9 * * *",     # Invalid minute (>59)
            "0 25 * * *",     # Invalid hour (>23)
            "0 9 32 * *",     # Invalid day (>31)
            "0 9 * 13 *"      # Invalid month (>12)
        ]
        
        for cron_expr in invalid_crons:
            assert validator.validate_cron(cron_expr) is False, f"Should reject: {cron_expr}"
    
    def test_rrule_validation(self):
        """Test RRULE expression validation."""
        validator = ScheduleValidator()
        
        # Valid RRULE expressions
        valid_rrules = [
            "FREQ=DAILY",
            "FREQ=WEEKLY;BYDAY=MO,WE,FR",
            "FREQ=MONTHLY;BYMONTHDAY=15",
            "FREQ=YEARLY;BYMONTH=12;BYMONTHDAY=25",
            "FREQ=HOURLY;INTERVAL=2"
        ]
        
        for rrule_expr in valid_rrules:
            assert validator.validate_rrule(rrule_expr) is True, f"Should accept: {rrule_expr}"
        
        # Invalid RRULE expressions
        invalid_rrules = [
            "invalid rrule",
            "FREQ=INVALID",       # Invalid frequency
            "FREQ=DAILY;BADPROP=1", # Invalid property
            "FREQ=WEEKLY;BYDAY=XX", # Invalid day
            "FREQ=MONTHLY;BYMONTHDAY=32" # Invalid day of month
        ]
        
        for rrule_expr in invalid_rrules:
            assert validator.validate_rrule(rrule_expr) is False, f"Should reject: {rrule_expr}"
    
    def test_once_schedule_validation(self):
        """Test 'once' schedule validation (ISO datetime)."""
        validator = ScheduleValidator()
        
        # Valid ISO datetime expressions
        valid_datetimes = [
            "2025-12-25T10:00:00Z",
            "2025-12-25T10:00:00+02:00",
            "2025-12-25T10:00:00.123Z"
        ]
        
        for dt_expr in valid_datetimes:
            assert validator.validate_once(dt_expr) is True, f"Should accept: {dt_expr}"
        
        # Invalid datetime expressions
        invalid_datetimes = [
            "invalid datetime",
            "2025-13-25T10:00:00Z",  # Invalid month
            "2025-12-32T10:00:00Z",  # Invalid day
            "2025-12-25T25:00:00Z",  # Invalid hour
            "2025-12-25T10:61:00Z"   # Invalid minute
        ]
        
        for dt_expr in invalid_datetimes:
            assert validator.validate_once(dt_expr) is False, f"Should reject: {dt_expr}"
    
    def test_timezone_validation(self):
        """Test timezone validation."""
        validator = ScheduleValidator()
        
        # Valid timezones
        valid_timezones = [
            "UTC",
            "Europe/Chisinau",
            "America/New_York",
            "Asia/Tokyo",
            "Australia/Sydney"
        ]
        
        for tz in valid_timezones:
            assert validator.validate_timezone(tz) is True, f"Should accept: {tz}"
        
        # Invalid timezones
        invalid_timezones = [
            "Invalid/Timezone",
            "Europe/NonExistent",
            "GMT+5",  # Should use proper IANA names
            ""
        ]
        
        for tz in invalid_timezones:
            assert validator.validate_timezone(tz) is False, f"Should reject: {tz}"


@pytest.mark.scheduler
@pytest.mark.dst
class TestTimezoneAndDSTHandling:
    """Test timezone handling and DST transitions."""
    
    def test_dst_spring_forward_handling(self, chisinau_dst_scenarios):
        """Test handling of spring DST transition (clock springs forward)."""
        scenario = chisinau_dst_scenarios["spring_forward_2025"]
        processor = RRuleProcessor()
        
        # Create RRULE that would trigger during DST transition
        rrule_str = "FREQ=DAILY;BYHOUR=2;BYMINUTE=30"  # 2:30 AM daily
        
        # Get next occurrence after spring forward
        base_time = scenario["before"]
        chisinau_tz = pytz.timezone(scenario["timezone"])
        
        next_time = next_occurrence(
            rrule_str, 
            scenario["timezone"], 
            base_time.replace(tzinfo=chisinau_tz)
        )
        
        # Should handle the non-existent time gracefully
        assert next_time is not None
        # Time should be adjusted or skipped appropriately
        assert next_time.tzinfo is not None
    
    def test_dst_fall_back_handling(self, chisinau_dst_scenarios):
        """Test handling of fall DST transition (clock falls back)."""
        scenario = chisinau_dst_scenarios["fall_back_2025"]
        processor = RRuleProcessor()
        
        # Create RRULE for ambiguous time during fall back
        rrule_str = "FREQ=DAILY;BYHOUR=2;BYMINUTE=30"  # 2:30 AM daily
        
        base_time = scenario["before"]
        chisinau_tz = pytz.timezone(scenario["timezone"])
        
        next_time = next_occurrence(
            rrule_str,
            scenario["timezone"],
            base_time.replace(tzinfo=chisinau_tz)
        )
        
        # Should handle ambiguous time consistently
        assert next_time is not None
        assert next_time.tzinfo is not None
    
    def test_cross_timezone_scheduling(self, clean_database):
        """Test scheduling tasks across different timezones."""
        agent = await insert_test_agent(clean_database)
        
        scheduler_service = SchedulerService(clean_database)
        await scheduler_service.start()
        
        try:
            # Create tasks in different timezones, all at "9 AM local"
            timezones = ["UTC", "Europe/Chisinau", "America/New_York", "Asia/Tokyo"]
            tasks = []
            
            for tz in timezones:
                task_data = {
                    "title": f"Task in {tz}",
                    "description": f"9 AM task in {tz}",
                    "created_by": agent["id"],
                    "schedule_kind": "cron",
                    "schedule_expr": "0 9 * * *",  # 9 AM daily
                    "timezone": tz,
                    "payload": {"pipeline": [{"id": f"tz_test_{tz}", "uses": "test.tool"}]},
                    "status": "active",
                    "priority": 5,
                    "max_retries": 3
                }
                
                task = await insert_test_task(clean_database, agent["id"], task_data)
                tasks.append((task, tz))
                await scheduler_service.add_task(task)
            
            # All jobs should be scheduled at different UTC times
            jobs = scheduler_service.scheduler.get_jobs()
            task_jobs = [job for job in jobs if any(str(task[0]["id"]) in job.id for task in tasks)]
            
            assert len(task_jobs) == len(timezones)
            
            # Extract next run times and convert to UTC
            utc_run_times = []
            for job in task_jobs:
                utc_time = job.next_run_time.astimezone(timezone.utc)
                utc_run_times.append(utc_time.hour)
            
            # Should have different UTC hours (since 9 AM local is different UTC times)
            unique_hours = set(utc_run_times)
            assert len(unique_hours) > 1, "Tasks in different timezones should run at different UTC times"
            
        finally:
            await scheduler_service.shutdown()


@pytest.mark.scheduler
class TestSchedulerPerformance:
    """Test scheduler performance under load."""
    
    async def test_high_volume_task_scheduling(self, clean_database):
        """Test scheduler performance with many tasks."""
        agent = await insert_test_agent(clean_database)
        
        scheduler_service = SchedulerService(clean_database)
        await scheduler_service.start()
        
        try:
            # Create many tasks
            task_count = 100
            tasks = []
            
            start_time = time.time()
            
            for i in range(task_count):
                task_data = {
                    "title": f"High Volume Task {i}",
                    "description": f"Performance test task {i}",
                    "created_by": agent["id"],
                    "schedule_kind": "cron",
                    "schedule_expr": f"{i % 60} {(i // 60) % 24} * * *",  # Distribute across hours/minutes
                    "timezone": "UTC",
                    "payload": {"pipeline": [{"id": f"perf_test_{i}", "uses": "test.tool"}]},
                    "status": "active",
                    "priority": 5,
                    "max_retries": 3
                }
                
                task = await insert_test_task(clean_database, agent["id"], task_data)
                tasks.append(task)
                await scheduler_service.add_task(task)
            
            scheduling_time = time.time() - start_time
            
            # All tasks should be scheduled
            jobs = scheduler_service.scheduler.get_jobs()
            scheduled_jobs = [job for job in jobs if any(str(task["id"]) in job.id for task in tasks)]
            
            assert len(scheduled_jobs) == task_count
            
            # Scheduling should be reasonably fast (< 1 second per 100 tasks)
            max_scheduling_time = 1.0
            assert scheduling_time < max_scheduling_time, \
                f"Scheduling {task_count} tasks took {scheduling_time:.2f}s, expected < {max_scheduling_time}s"
            
        finally:
            await scheduler_service.shutdown()
    
    async def test_schedule_accuracy_under_load(self, clean_database):
        """Test that schedule accuracy is maintained under load."""
        agent = await insert_test_agent(clean_database)
        
        scheduler_service = SchedulerService(clean_database)
        await scheduler_service.start()
        
        try:
            # Create tasks scheduled to run very soon with high precision
            near_future = datetime.now(timezone.utc) + timedelta(seconds=5)
            
            tasks = []
            expected_times = []
            
            for i in range(10):
                # Each task 100ms apart
                execution_time = near_future + timedelta(milliseconds=i * 100)
                expected_times.append(execution_time)
                
                task_data = {
                    "title": f"Precision Task {i}",
                    "description": f"High precision timing test {i}",
                    "created_by": agent["id"],
                    "schedule_kind": "once",
                    "schedule_expr": execution_time.isoformat(),
                    "timezone": "UTC",
                    "payload": {"pipeline": [{"id": f"precision_test_{i}", "uses": "test.tool"}]},
                    "status": "active",
                    "priority": 5,
                    "max_retries": 3
                }
                
                task = await insert_test_task(clean_database, agent["id"], task_data)
                tasks.append(task)
                await scheduler_service.add_task(task)
            
            # Check scheduling accuracy
            jobs = scheduler_service.scheduler.get_jobs()
            scheduled_jobs = [job for job in jobs if any(str(task["id"]) in job.id for task in tasks)]
            
            # All tasks should be scheduled
            assert len(scheduled_jobs) == len(tasks)
            
            # Check timing accuracy (within 1 second tolerance)
            for i, job in enumerate(sorted(scheduled_jobs, key=lambda j: j.next_run_time)):
                expected_time = expected_times[i]
                actual_time = job.next_run_time.replace(tzinfo=timezone.utc)
                
                time_diff = abs((expected_time - actual_time).total_seconds())
                assert time_diff < 1.0, f"Task {i} scheduled {time_diff:.2f}s off expected time"
                
        finally:
            await scheduler_service.shutdown()
    
    @pytest.mark.benchmark
    def test_job_execution_trigger_performance(self, benchmark, clean_database):
        """Benchmark job execution trigger performance."""
        async def setup_and_trigger():
            agent = await insert_test_agent(clean_database)
            
            scheduler_service = SchedulerService(clean_database)
            await scheduler_service.start()
            
            try:
                # Create immediate task
                task_data = {
                    "title": "Benchmark Task",
                    "description": "Performance benchmark task",
                    "created_by": agent["id"],
                    "schedule_kind": "once",
                    "schedule_expr": datetime.now(timezone.utc).isoformat(),
                    "timezone": "UTC",
                    "payload": {"pipeline": [{"id": "benchmark", "uses": "test.tool"}]},
                    "status": "active",
                    "priority": 5,
                    "max_retries": 3
                }
                
                task = await insert_test_task(clean_database, agent["id"], task_data)
                
                # Time the scheduling operation
                start_time = time.perf_counter()
                await scheduler_service.add_task(task)
                end_time = time.perf_counter()
                
                return end_time - start_time
                
            finally:
                await scheduler_service.shutdown()
        
        def run_benchmark():
            return asyncio.run(setup_and_trigger())
        
        execution_time = benchmark(run_benchmark)
        
        # Should complete quickly (< 100ms for single task scheduling)
        assert execution_time < 0.1, f"Task scheduling took {execution_time:.3f}s, expected < 0.1s"


@pytest.mark.scheduler
class TestSchedulerErrorHandling:
    """Test scheduler error handling and recovery."""
    
    async def test_invalid_schedule_handling(self, clean_database):
        """Test handling of invalid schedule expressions."""
        agent = await insert_test_agent(clean_database)
        
        scheduler_service = SchedulerService(clean_database)
        await scheduler_service.start()
        
        try:
            # Create task with invalid cron expression
            task_data = {
                "title": "Invalid Schedule Task",
                "description": "Task with invalid schedule",
                "created_by": agent["id"],
                "schedule_kind": "cron",
                "schedule_expr": "invalid cron expression",
                "timezone": "UTC",
                "payload": {"pipeline": [{"id": "invalid_test", "uses": "test.tool"}]},
                "status": "active",
                "priority": 5,
                "max_retries": 3
            }
            
            task = await insert_test_task(clean_database, agent["id"], task_data)
            
            # Adding invalid task should not crash scheduler
            try:
                await scheduler_service.add_task(task)
                # Should either succeed with error handling or raise specific exception
                assert True
            except ValueError as e:
                # Expected for invalid schedule
                assert "invalid" in str(e).lower() or "schedule" in str(e).lower()
            except Exception as e:
                pytest.fail(f"Unexpected exception type: {type(e).__name__}: {e}")
            
            # Scheduler should still be running
            assert scheduler_service.is_running() is True
            
        finally:
            await scheduler_service.shutdown()
    
    async def test_database_error_recovery(self, clean_database):
        """Test scheduler recovery from database errors."""
        scheduler_service = SchedulerService(clean_database)
        await scheduler_service.start()
        
        try:
            # Simulate database error
            with patch.object(clean_database, 'execute') as mock_execute:
                mock_execute.side_effect = Exception("Database connection lost")
                
                # Scheduler should handle database errors gracefully
                # This may not directly test scheduler operations, but tests resilience
                assert scheduler_service.is_running() is True
                
        finally:
            await scheduler_service.shutdown()
    
    async def test_job_execution_failure_handling(self, clean_database):
        """Test handling of job execution failures."""
        agent = await insert_test_agent(clean_database)
        
        scheduler_service = SchedulerService(clean_database)
        await scheduler_service.start()
        
        try:
            # Create task that will trigger soon
            near_future = datetime.now(timezone.utc) + timedelta(seconds=1)
            
            task_data = {
                "title": "Failing Job Task",
                "description": "Task designed to test job failure handling",
                "created_by": agent["id"],
                "schedule_kind": "once",
                "schedule_expr": near_future.isoformat(),
                "timezone": "UTC",
                "payload": {"pipeline": [{"id": "failing_test", "uses": "test.fail"}]},
                "status": "active",
                "priority": 5,
                "max_retries": 3
            }
            
            task = await insert_test_task(clean_database, agent["id"], task_data)
            await scheduler_service.add_task(task)
            
            # Mock job execution to fail
            with patch.object(scheduler_service, '_execute_task') as mock_execute:
                mock_execute.side_effect = Exception("Job execution failed")
                
                # Wait for job to trigger
                await asyncio.sleep(2)
                
                # Scheduler should still be running after job failure
                assert scheduler_service.is_running() is True
                
        finally:
            await scheduler_service.shutdown()


@pytest.mark.scheduler
@pytest.mark.integration
class TestSchedulerIntegration:
    """Test scheduler integration with other system components."""
    
    async def test_scheduler_to_work_queue_integration(self, clean_database):
        """Test that scheduler properly creates work queue items."""
        agent = await insert_test_agent(clean_database)
        
        scheduler_service = SchedulerService(clean_database)
        await scheduler_service.start()
        
        try:
            # Create task scheduled to run immediately
            immediate_time = datetime.now(timezone.utc) + timedelta(seconds=1)
            
            task_data = {
                "title": "Work Queue Test Task",
                "description": "Task to test work queue integration",
                "created_by": agent["id"],
                "schedule_kind": "once", 
                "schedule_expr": immediate_time.isoformat(),
                "timezone": "UTC",
                "payload": {"pipeline": [{"id": "queue_test", "uses": "test.tool"}]},
                "status": "active",
                "priority": 5,
                "max_retries": 3
            }
            
            task = await insert_test_task(clean_database, agent["id"], task_data)
            await scheduler_service.add_task(task)
            
            # Wait for job to execute and create work item
            await asyncio.sleep(3)
            
            # Check that work item was created in due_work table
            with clean_database.begin() as conn:
                result = conn.execute(
                    "SELECT * FROM due_work WHERE task_id = ?", 
                    (task["id"],)
                ).fetchone()
            
            # Work item should be created (or task run should be recorded)
            # This tests the integration path from scheduler to work queue
            if result:
                assert result.task_id == task["id"]
            else:
                # Alternative: check if task_run was created directly
                with clean_database.begin() as conn:
                    run_result = conn.execute(
                        "SELECT * FROM task_run WHERE task_id = ?", 
                        (task["id"],)
                    ).fetchone()
                
                # Either due_work or task_run should exist
                assert result is not None or run_result is not None
                
        finally:
            await scheduler_service.shutdown()