#!/usr/bin/env python3
"""
Test suite for the Personal Agent Orchestrator Scheduler Service.

Tests the APScheduler integration, timezone handling, RRULE processing,
and due_work table creation functionality.
"""

import os
import sys
import pytest
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch
import uuid

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scheduler.tick import SchedulerService
from engine.rruler import next_occurrence


class TestSchedulerService:
    """Test suite for SchedulerService functionality."""
    
    @pytest.fixture
    def mock_db_url(self):
        """Mock database URL for testing."""
        return "postgresql://test:test@localhost:5432/test"
    
    @pytest.fixture
    def scheduler_service(self, mock_db_url):
        """Create scheduler service instance for testing."""
        with patch('scheduler.tick.create_engine') as mock_engine:
            mock_engine.return_value = Mock()
            service = SchedulerService(mock_db_url, "Europe/Chisinau")
            return service
    
    def test_scheduler_initialization(self, mock_db_url):
        """Test scheduler service initialization."""
        with patch('scheduler.tick.create_engine') as mock_engine:
            mock_engine.return_value = Mock()
            
            service = SchedulerService(mock_db_url, "Europe/Chisinau")
            
            assert service.database_url == mock_db_url
            assert service.timezone == "Europe/Chisinau"
            assert service.scheduler is not None
            assert service.engine is not None
    
    def test_enqueue_due_work(self, scheduler_service):
        """Test due_work row creation."""
        task_id = str(uuid.uuid4())
        scheduled_time = datetime.now(timezone.utc)
        
        # Mock database connection
        mock_conn = Mock()
        scheduler_service.engine.begin.return_value.__enter__.return_value = mock_conn
        
        # Mock task lookup to avoid RRULE rescheduling
        mock_conn.execute.return_value.fetchone.return_value = None
        
        scheduler_service.enqueue_due_work(task_id, scheduled_time)
        
        # Verify database insert was called
        mock_conn.execute.assert_called()
        call_args = mock_conn.execute.call_args
        
        # Check SQL contains INSERT INTO due_work
        assert "INSERT INTO due_work" in str(call_args[0][0])
        assert call_args[1]["task_id"] == task_id
        assert call_args[1]["run_at"] == scheduled_time
    
    def test_cron_task_scheduling(self, scheduler_service):
        """Test cron expression parsing and job scheduling."""
        task_id = str(uuid.uuid4())
        cron_expr = "30 8 * * 1-5"  # 8:30 AM weekdays
        timezone_name = "Europe/Chisinau"
        
        # Mock scheduler add_job
        scheduler_service.scheduler.add_job = Mock()
        
        scheduler_service._schedule_cron_task(task_id, cron_expr, timezone_name)
        
        # Verify job was scheduled
        scheduler_service.scheduler.add_job.assert_called_once()
        call_args = scheduler_service.scheduler.add_job.call_args
        
        # Check trigger type and parameters
        trigger = call_args[1]['trigger']
        assert trigger.minute == '30'
        assert trigger.hour == '8'
        assert trigger.day == '*'
        assert trigger.month == '*'
        assert trigger.day_of_week == '1-5'
    
    def test_once_task_scheduling(self, scheduler_service):
        """Test one-time task scheduling."""
        task_id = str(uuid.uuid4())
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        date_expr = future_time.isoformat()
        timezone_name = "Europe/Chisinau"
        
        # Mock scheduler add_job
        scheduler_service.scheduler.add_job = Mock()
        
        scheduler_service._schedule_once_task(task_id, date_expr, timezone_name)
        
        # Verify job was scheduled
        scheduler_service.scheduler.add_job.assert_called_once()
        call_args = scheduler_service.scheduler.add_job.call_args
        
        # Check job ID and function
        assert call_args[1]['id'] == f"once-{task_id}"
        assert call_args[0][0] == scheduler_service.enqueue_due_work
    
    def test_rrule_task_scheduling(self, scheduler_service):
        """Test RRULE task scheduling."""
        task_id = str(uuid.uuid4())
        rrule_expr = "FREQ=DAILY;BYHOUR=9;BYMINUTE=0"  # Daily at 9:00 AM
        timezone_name = "Europe/Chisinau"
        
        # Mock scheduler add_job
        scheduler_service.scheduler.add_job = Mock()
        
        # Mock next_occurrence to return a future time
        with patch('scheduler.tick.next_occurrence') as mock_next:
            future_time = datetime.now(timezone.utc) + timedelta(hours=1)
            mock_next.return_value = future_time
            
            scheduler_service._schedule_rrule_task(task_id, rrule_expr, timezone_name)
        
        # Verify job was scheduled
        scheduler_service.scheduler.add_job.assert_called_once()
        call_args = scheduler_service.scheduler.add_job.call_args
        
        # Check job ID and parameters
        assert call_args[1]['id'] == f"rrule-{task_id}"
        assert call_args[0][0] == scheduler_service.enqueue_due_work
    
    def test_invalid_cron_expression(self, scheduler_service):
        """Test handling of invalid cron expressions."""
        task_id = str(uuid.uuid4())
        invalid_cron = "30 8 *"  # Missing fields
        timezone_name = "Europe/Chisinau"
        
        with pytest.raises(ValueError, match="must have 5 fields"):
            scheduler_service._schedule_cron_task(task_id, invalid_cron, timezone_name)
    
    def test_past_once_task_skipping(self, scheduler_service, caplog):
        """Test that past one-time tasks are skipped."""
        task_id = str(uuid.uuid4())
        past_time = datetime.now(timezone.utc) - timedelta(hours=1)
        date_expr = past_time.isoformat()
        timezone_name = "Europe/Chisinau"
        
        # Mock scheduler add_job
        scheduler_service.scheduler.add_job = Mock()
        
        scheduler_service._schedule_once_task(task_id, date_expr, timezone_name)
        
        # Verify job was NOT scheduled
        scheduler_service.scheduler.add_job.assert_not_called()
        
        # Verify warning was logged
        assert "scheduled for past date" in caplog.text
    
    def test_rrule_rescheduling(self, scheduler_service):
        """Test RRULE task rescheduling after execution."""
        task_id = str(uuid.uuid4())
        
        # Mock database connection
        mock_conn = Mock()
        scheduler_service.engine.begin.return_value.__enter__.return_value = mock_conn
        
        # Mock task lookup to return RRULE task
        mock_task = Mock()
        mock_task.schedule_kind = 'rrule'
        mock_task.schedule_expr = 'FREQ=DAILY;BYHOUR=9'
        mock_task.timezone = 'Europe/Chisinau'
        mock_conn.execute.return_value.fetchone.return_value = mock_task
        
        # Mock scheduler add_job
        scheduler_service.scheduler.add_job = Mock()
        
        # Mock next_occurrence
        with patch('scheduler.tick.next_occurrence') as mock_next:
            future_time = datetime.now(timezone.utc) + timedelta(days=1)
            mock_next.return_value = future_time
            
            scheduler_service._reschedule_rrule_task_if_needed(task_id)
        
        # Verify rescheduling occurred
        scheduler_service.scheduler.add_job.assert_called_once()
    
    def test_load_and_schedule_tasks_integration(self, scheduler_service):
        """Test loading and scheduling multiple tasks."""
        # Mock tasks from database
        mock_tasks = [
            {
                'id': str(uuid.uuid4()),
                'title': 'Test Cron Task',
                'schedule_kind': 'cron',
                'schedule_expr': '0 9 * * *',
                'timezone': 'Europe/Chisinau'
            },
            {
                'id': str(uuid.uuid4()),
                'title': 'Test RRULE Task',
                'schedule_kind': 'rrule',
                'schedule_expr': 'FREQ=WEEKLY;BYDAY=MO',
                'timezone': 'Europe/Chisinau'
            },
            {
                'id': str(uuid.uuid4()),
                'title': 'Test Event Task',
                'schedule_kind': 'event',
                'schedule_expr': 'user.notification',
                'timezone': 'Europe/Chisinau'
            }
        ]
        
        # Mock database loading
        with patch('scheduler.tick.load_active_tasks') as mock_load:
            mock_load.return_value = mock_tasks
            
            # Mock scheduling methods
            scheduler_service._schedule_cron_task = Mock()
            scheduler_service._schedule_rrule_task = Mock()
            
            scheduler_service.load_and_schedule_tasks()
        
        # Verify tasks were loaded
        mock_load.assert_called_once_with(scheduler_service.database_url)
        
        # Verify scheduling was called for appropriate tasks
        scheduler_service._schedule_cron_task.assert_called_once()
        scheduler_service._schedule_rrule_task.assert_called_once()
        # Event task should not trigger scheduling calls
    
    def test_schedule_task_job_dispatch(self, scheduler_service):
        """Test task job scheduling dispatch to correct handler."""
        
        # Mock scheduling methods
        scheduler_service._schedule_cron_task = Mock()
        scheduler_service._schedule_once_task = Mock()
        scheduler_service._schedule_rrule_task = Mock()
        
        test_cases = [
            ('cron', '0 9 * * *'),
            ('once', '2025-12-25T09:00:00Z'),
            ('rrule', 'FREQ=DAILY'),
            ('event', 'user.action'),
            ('condition', 'weather.rain > 0.5')
        ]
        
        for schedule_kind, schedule_expr in test_cases:
            task = {
                'id': str(uuid.uuid4()),
                'title': f'Test {schedule_kind} Task',
                'schedule_kind': schedule_kind,
                'schedule_expr': schedule_expr,
                'timezone': 'Europe/Chisinau'
            }
            
            scheduler_service.schedule_task_job(task)
        
        # Verify correct methods were called
        assert scheduler_service._schedule_cron_task.call_count == 1
        assert scheduler_service._schedule_once_task.call_count == 1
        assert scheduler_service._schedule_rrule_task.call_count == 1


class TestRRuleIntegration:
    """Test RRULE integration with the scheduler."""
    
    def test_next_occurrence_calculation(self):
        """Test RRULE next occurrence calculation."""
        # Test daily at 9:00 AM
        rrule_expr = "FREQ=DAILY;BYHOUR=9;BYMINUTE=0"
        timezone_name = "Europe/Chisinau"
        
        next_time = next_occurrence(rrule_expr, timezone_name)
        
        assert next_time is not None
        assert next_time.hour == 9
        assert next_time.minute == 0
        assert str(next_time.tzinfo) == "Europe/Chisinau"
    
    def test_business_days_rrule(self):
        """Test business days RRULE expression."""
        rrule_expr = "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=30"
        timezone_name = "Europe/Chisinau"
        
        next_time = next_occurrence(rrule_expr, timezone_name)
        
        assert next_time is not None
        assert next_time.weekday() < 5  # Monday=0 to Friday=4
        assert next_time.hour == 8
        assert next_time.minute == 30
    
    def test_monthly_first_monday(self):
        """Test monthly first Monday RRULE."""
        rrule_expr = "FREQ=MONTHLY;BYDAY=1MO;BYHOUR=10;BYMINUTE=0"
        timezone_name = "Europe/Chisinau"
        
        next_time = next_occurrence(rrule_expr, timezone_name)
        
        assert next_time is not None
        assert next_time.weekday() == 0  # Monday
        assert next_time.hour == 10
        assert next_time.minute == 0
        
        # Verify it's the first Monday of the month
        first_day = next_time.replace(day=1)
        days_to_monday = (7 - first_day.weekday()) % 7
        first_monday = first_day + timedelta(days=days_to_monday)
        assert next_time.day == first_monday.day


if __name__ == "__main__":
    pytest.main([__file__, "-v"])