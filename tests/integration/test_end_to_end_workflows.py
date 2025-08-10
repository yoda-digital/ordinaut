#!/usr/bin/env python3
"""
Comprehensive end-to-end integration tests for Ordinaut.

Tests complete workflows from task creation to execution including:
- Full task lifecycle: creation → scheduling → execution → completion
- RRULE scheduling accuracy and timing validation  
- Pipeline execution with real tool integration
- Multi-component integration (API + Scheduler + Workers)
- Morning briefing and follow-up automation scenarios
- Error handling and recovery in distributed environment
"""

import pytest
import asyncio
import time
import json
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock, Mock
import httpx

from api.main import app
from scheduler.tick import SchedulerService
from workers.runner import WorkerRunner
from workers.config import WorkerConfig
from engine.executor import run_pipeline


class TestCompleteTaskLifecycle:
    """Test complete task lifecycle from creation to execution."""
    
    @pytest.mark.integration
    async def test_once_task_complete_lifecycle(self, test_environment, mock_tool_catalog):
        """Test complete lifecycle of a 'once' scheduled task."""
        
        # 1. Create agent via database
        agent_data = await insert_test_agent(test_environment.db_engine)
        
        # 2. Create task with 'once' schedule (5 seconds from now)
        run_time = datetime.now(timezone.utc) + timedelta(seconds=5)
        task_data = {
            "title": "Integration Test Once Task",
            "description": "End-to-end test of once scheduled task",
            "created_by": agent_data["id"],
            "schedule_kind": "once",
            "schedule_expr": run_time.isoformat(),
            "timezone": "Europe/Chisinau",
            "payload": {
                "pipeline": [
                    {
                        "id": "test_action",
                        "uses": "test-tool.execute",
                        "with": {"message": "Integration test successful"},
                        "save_as": "result"
                    }
                ]
            },
            "status": "active",
            "priority": 5,
            "max_retries": 2
        }
        
        task = await insert_test_task(test_environment.db_engine, agent_data["id"], task_data)
        task_id = task["id"]
        
        # 3. Start scheduler to process the task
        scheduler = SchedulerService(test_environment.db_url, "Europe/Chisinau")
        scheduler.schedule_task_job(task)
        
        # 4. Wait for task to be scheduled and due
        await asyncio.sleep(6)  # Wait for schedule time + buffer
        
        # 5. Verify due_work was created
        with test_environment.db_engine.begin() as conn:
            result = conn.execute(text("""
                SELECT COUNT(*) as work_count FROM due_work 
                WHERE task_id = :task_id AND run_at <= now()
            """), {"task_id": task_id})
            work_count = result.scalar()
            assert work_count > 0, "No due work was created for scheduled task"
        
        # 6. Start worker to process the work
        config = WorkerConfig.from_dict({
            "worker_id": "integration-test-worker",
            "database_url": test_environment.db_url,
            "lease_seconds": 60
        })
        worker = WorkerRunner(config)
        
        # Mock tool execution
        with patch('engine.executor.load_catalog', return_value=mock_tool_catalog):
            with patch('engine.executor.call_tool') as mock_call_tool:
                mock_call_tool.return_value = {"result": "Integration test successful"}
                
                # Process available work
                lease = worker.lease_one()
                assert lease is not None, "Worker should have found work to process"
                
                success = worker.process_work_item(lease)
                assert success is True, "Work item processing should succeed"
        
        # 7. Verify task execution was recorded
        with test_environment.db_engine.begin() as conn:
            result = conn.execute(text("""
                SELECT success, error, output FROM task_run 
                WHERE task_id = :task_id ORDER BY created_at DESC LIMIT 1
            """), {"task_id": task_id})
            run_record = result.fetchone()
            
            assert run_record is not None, "Task run should be recorded"
            assert run_record.success is True, "Task run should be successful"
            assert run_record.error is None, "No error should be recorded for successful run"
            assert run_record.output is not None, "Output should be recorded"
            
            output_data = json.loads(run_record.output)
            assert "result" in output_data["steps"], "Pipeline output should contain result"
        
        # 8. Verify due_work was cleaned up
        with test_environment.db_engine.begin() as conn:
            result = conn.execute(text("""
                SELECT COUNT(*) as remaining_work FROM due_work WHERE task_id = :task_id
            """), {"task_id": task_id})
            remaining_work = result.scalar()
            assert remaining_work == 0, "Due work should be cleaned up after processing"
    
    @pytest.mark.integration
    async def test_cron_task_multiple_executions(self, test_environment, mock_tool_catalog):
        """Test cron task with multiple scheduled executions."""
        
        # Create agent and task
        agent_data = await insert_test_agent(test_environment.db_engine)
        
        # Cron task that runs every 3 seconds for testing
        # Note: This is artificially frequent for testing - real tasks would be less frequent
        task_data = {
            "title": "Integration Test Cron Task",
            "description": "Cron task for integration testing",
            "created_by": agent_data["id"],
            "schedule_kind": "cron",
            "schedule_expr": "*/3 * * * * *",  # Every 3 seconds (non-standard but works for testing)
            "timezone": "Europe/Chisinau",
            "payload": {
                "pipeline": [
                    {
                        "id": "counter",
                        "uses": "test-tool.execute",
                        "with": {"message": "Cron execution ${now}"},
                        "save_as": "result"
                    }
                ]
            },
            "status": "active"
        }
        
        task = await insert_test_task(test_environment.db_engine, agent_data["id"], task_data)
        task_id = task["id"]
        
        # Start scheduler
        scheduler = SchedulerService(test_environment.db_url, "Europe/Chisinau")
        scheduler.schedule_task_job(task)
        
        # Start worker
        config = WorkerConfig.from_dict({
            "worker_id": "cron-test-worker",
            "database_url": test_environment.db_url
        })
        worker = WorkerRunner(config)
        
        execution_count = 0
        max_executions = 3
        
        with patch('engine.executor.load_catalog', return_value=mock_tool_catalog):
            with patch('engine.executor.call_tool') as mock_call_tool:
                mock_call_tool.return_value = {"result": "Cron execution completed"}
                
                # Monitor for multiple executions
                start_time = time.time()
                while execution_count < max_executions and (time.time() - start_time) < 15:  # 15 second timeout
                    lease = worker.lease_one()
                    if lease:
                        success = worker.process_work_item(lease)
                        if success:
                            execution_count += 1
                    else:
                        await asyncio.sleep(1)  # Wait for next scheduled execution
        
        # Verify multiple executions occurred
        assert execution_count >= 2, f"Expected at least 2 executions, got {execution_count}"
        
        # Verify task runs were recorded
        with test_environment.db_engine.begin() as conn:
            result = conn.execute(text("""
                SELECT COUNT(*) as run_count FROM task_run 
                WHERE task_id = :task_id AND success = true
            """), {"task_id": task_id})
            run_count = result.scalar()
            assert run_count >= 2, f"Expected at least 2 successful runs, got {run_count}"
    
    @pytest.mark.integration
    async def test_rrule_task_scheduling_accuracy(self, test_environment, mock_tool_catalog):
        """Test RRULE task scheduling accuracy with timezone handling."""
        
        # Create agent and task
        agent_data = await insert_test_agent(test_environment.db_engine)
        
        # RRULE for every weekday at a specific time
        task_data = {
            "title": "RRULE Accuracy Test",
            "description": "Test RRULE scheduling precision",
            "created_by": agent_data["id"],
            "schedule_kind": "rrule",
            "schedule_expr": "FREQ=MINUTELY;INTERVAL=2;BYSECOND=0",  # Every 2 minutes for testing
            "timezone": "Europe/Chisinau",
            "payload": {
                "pipeline": [
                    {
                        "id": "timestamp",
                        "uses": "test-tool.execute", 
                        "with": {"message": "RRULE execution at ${now}"},
                        "save_as": "timestamp"
                    }
                ]
            },
            "status": "active"
        }
        
        task = await insert_test_task(test_environment.db_engine, agent_data["id"], task_data)
        
        # Start scheduler
        scheduler = SchedulerService(test_environment.db_url, "Europe/Chisinau")
        scheduler.schedule_task_job(task)
        
        # Monitor due_work creation timing
        start_time = time.time()
        due_work_times = []
        
        # Check for due work creation over 6 minutes (should get ~3 executions)
        while (time.time() - start_time) < 360 and len(due_work_times) < 3:  # 6 minutes
            with test_environment.db_engine.begin() as conn:
                result = conn.execute(text("""
                    SELECT run_at FROM due_work 
                    WHERE task_id = :task_id 
                    ORDER BY run_at DESC LIMIT 1
                """), {"task_id": task["id"]})
                
                row = result.fetchone()
                if row and row.run_at not in due_work_times:
                    due_work_times.append(row.run_at)
            
            await asyncio.sleep(30)  # Check every 30 seconds
        
        # Verify timing accuracy (should be close to 2-minute intervals)
        if len(due_work_times) >= 2:
            time_diff = due_work_times[1] - due_work_times[0]
            expected_diff = timedelta(minutes=2)
            
            # Allow 5-second tolerance for scheduling precision
            assert abs((time_diff - expected_diff).total_seconds()) < 5, \
                f"RRULE timing inaccurate: {time_diff} vs expected {expected_diff}"


class TestMorningBriefingWorkflow:
    """Test realistic morning briefing automation workflow."""
    
    @pytest.mark.integration
    async def test_morning_briefing_pipeline(self, test_environment):
        """Test complete morning briefing pipeline execution."""
        
        # Enhanced tool catalog for morning briefing
        briefing_catalog = [
            {
                "address": "google-calendar.list_events",
                "transport": "http",
                "endpoint": "http://localhost:8091/calendar",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "start": {"type": "string"},
                        "end": {"type": "string"}
                    },
                    "required": ["start", "end"]
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "events": {"type": "array"}
                    },
                    "required": ["events"]
                }
            },
            {
                "address": "weather.forecast",
                "transport": "http",
                "endpoint": "http://localhost:8092/weather",
                "input_schema": {
                    "type": "object",
                    "properties": {"location": {"type": "string"}},
                    "required": ["location"]
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string"},
                        "temp": {"type": "number"},
                        "humidity": {"type": "number"}
                    },
                    "required": ["summary", "temp"]
                }
            },
            {
                "address": "telegram.send_message",
                "transport": "http",
                "endpoint": "http://localhost:8093/telegram",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "chat_id": {"type": "integer"},
                        "text": {"type": "string"}
                    },
                    "required": ["chat_id", "text"]
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"message_id": {"type": "integer"}},
                    "required": ["message_id"]
                }
            }
        ]
        
        # Create agent and morning briefing task
        agent_data = await insert_test_agent(test_environment.db_engine)
        
        task_data = {
            "title": "Daily Morning Briefing",
            "description": "Comprehensive morning briefing with calendar, weather, and notifications",
            "created_by": agent_data["id"],
            "schedule_kind": "once",  # For testing, use 'once' instead of daily schedule
            "schedule_expr": (datetime.now(timezone.utc) + timedelta(seconds=3)).isoformat(),
            "timezone": "Europe/Chisinau",
            "payload": {
                "params": {
                    "date_start": "2025-08-08T00:00:00+03:00",
                    "date_end": "2025-08-08T23:59:59+03:00",
                    "location": "Chisinau",
                    "chat_id": 12345
                },
                "pipeline": [
                    {
                        "id": "calendar",
                        "uses": "google-calendar.list_events",
                        "with": {
                            "start": "${params.date_start}",
                            "end": "${params.date_end}"
                        },
                        "save_as": "events"
                    },
                    {
                        "id": "weather",
                        "uses": "weather.forecast",
                        "with": {"location": "${params.location}"},
                        "save_as": "forecast"
                    },
                    {
                        "id": "notify",
                        "uses": "telegram.send_message",
                        "with": {
                            "chat_id": "${params.chat_id}",
                            "text": "Good morning! Weather: ${steps.forecast.summary} (${steps.forecast.temp}°C). You have ${length(steps.events.events)} events today."
                        },
                        "if": "length(steps.events.events) > `0` || steps.forecast.temp > `-10`",  # Always notify unless extremely cold
                        "save_as": "notification"
                    }
                ]
            },
            "status": "active"
        }
        
        task = await insert_test_task(test_environment.db_engine, agent_data["id"], task_data)
        
        # Wait for task to become due
        await asyncio.sleep(4)
        
        # Create due work manually (simulating scheduler)
        work_id = await insert_due_work(test_environment.db_engine, task["id"])
        
        # Execute pipeline with mocked tool responses
        config = WorkerConfig.from_dict({
            "worker_id": "briefing-worker",
            "database_url": test_environment.db_url
        })
        worker = WorkerRunner(config)
        
        with patch('engine.executor.load_catalog', return_value=briefing_catalog):
            with patch('engine.executor.call_tool') as mock_call_tool:
                # Mock tool responses in order
                mock_call_tool.side_effect = [
                    # Calendar response
                    {
                        "events": [
                            {"title": "Team Standup", "time": "09:00", "location": "Office"},
                            {"title": "Client Meeting", "time": "14:00", "location": "Zoom"},
                            {"title": "Code Review", "time": "16:30", "location": "Conference Room"}
                        ]
                    },
                    # Weather response
                    {
                        "summary": "Partly Cloudy",
                        "temp": 18,
                        "humidity": 65
                    },
                    # Telegram response
                    {"message_id": 789}
                ]
                
                # Process the work
                lease = worker.lease_one()
                assert lease is not None
                
                success = worker.process_work_item(lease)
                assert success is True
        
        # Verify pipeline execution results
        with test_environment.db_engine.begin() as conn:
            result = conn.execute(text("""
                SELECT success, output, error FROM task_run 
                WHERE task_id = :task_id ORDER BY created_at DESC LIMIT 1
            """), {"task_id": task["id"]})
            
            run_record = result.fetchone()
            assert run_record is not None
            assert run_record.success is True
            assert run_record.error is None
            
            output_data = json.loads(run_record.output)
            
            # Verify each step executed correctly
            assert "events" in output_data["steps"]
            assert "forecast" in output_data["steps"]
            assert "notification" in output_data["steps"]
            
            # Verify data flow
            events = output_data["steps"]["events"]["events"]
            assert len(events) == 3
            assert events[0]["title"] == "Team Standup"
            
            forecast = output_data["steps"]["forecast"]
            assert forecast["summary"] == "Partly Cloudy"
            assert forecast["temp"] == 18
            
            notification = output_data["steps"]["notification"]
            assert notification["message_id"] == 789
        
        # Verify final notification message contained correct data
        call_args = mock_call_tool.call_args_list[2]  # Third call (telegram)
        notification_text = call_args[0][2]["text"]  # call_tool(addr, tool, args)
        
        assert "Weather: Partly Cloudy (18°C)" in notification_text
        assert "You have 3 events today" in notification_text


class TestErrorHandlingAndRecovery:
    """Test error handling and recovery scenarios in distributed environment."""
    
    @pytest.mark.integration
    async def test_task_retry_on_failure(self, test_environment, mock_tool_catalog):
        """Test task retry mechanism on failures."""
        
        # Create agent and task with retry configuration
        agent_data = await insert_test_agent(test_environment.db_engine)
        
        task_data = {
            "title": "Retry Test Task",
            "description": "Task designed to test retry mechanisms",
            "created_by": agent_data["id"],
            "schedule_kind": "once",
            "schedule_expr": (datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat(),
            "payload": {
                "pipeline": [
                    {
                        "id": "flaky_action",
                        "uses": "test-tool.execute",
                        "with": {"message": "This might fail"},
                        "save_as": "result"
                    }
                ]
            },
            "status": "active",
            "max_retries": 3
        }
        
        task = await insert_test_task(test_environment.db_engine, agent_data["id"], task_data)
        
        # Wait for task to be due
        await asyncio.sleep(3)
        work_id = await insert_due_work(test_environment.db_engine, task["id"])
        
        # Setup worker
        config = WorkerConfig.from_dict({
            "worker_id": "retry-test-worker",
            "database_url": test_environment.db_url
        })
        worker = WorkerRunner(config)
        
        with patch('engine.executor.load_catalog', return_value=mock_tool_catalog):
            with patch('engine.executor.call_tool') as mock_call_tool:
                # First two calls fail, third succeeds
                mock_call_tool.side_effect = [
                    Exception("Network timeout"),  # First attempt fails
                    Exception("Service unavailable"),  # Second attempt fails
                    {"result": "Success on third try"}  # Third attempt succeeds
                ]
                
                lease = worker.lease_one()
                success = worker.process_work_item(lease)
                assert success is True
        
        # Verify retry attempts were recorded
        with test_environment.db_engine.begin() as conn:
            result = conn.execute(text("""
                SELECT attempt, success, error FROM task_run 
                WHERE task_id = :task_id ORDER BY attempt ASC
            """), {"task_id": task["id"]})
            
            runs = result.fetchall()
            assert len(runs) == 3  # Should have 3 attempts
            
            # First two should be failures
            assert runs[0].attempt == 1
            assert runs[0].success is False
            assert "Network timeout" in runs[0].error
            
            assert runs[1].attempt == 2
            assert runs[1].success is False
            assert "Service unavailable" in runs[1].error
            
            # Third should be success
            assert runs[2].attempt == 3
            assert runs[2].success is True
            assert runs[2].error is None
    
    @pytest.mark.integration
    async def test_permanent_failure_after_max_retries(self, test_environment, mock_tool_catalog):
        """Test permanent failure after exhausting max retries."""
        
        # Create agent and task
        agent_data = await insert_test_agent(test_environment.db_engine)
        
        task_data = {
            "title": "Permanent Failure Test",
            "description": "Task that will permanently fail",
            "created_by": agent_data["id"],
            "schedule_kind": "once",
            "schedule_expr": (datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat(),
            "payload": {
                "pipeline": [
                    {
                        "id": "failing_action",
                        "uses": "test-tool.execute",
                        "with": {"message": "This will always fail"},
                        "save_as": "result"
                    }
                ]
            },
            "status": "active",
            "max_retries": 2
        }
        
        task = await insert_test_task(test_environment.db_engine, agent_data["id"], task_data)
        
        # Wait and create due work
        await asyncio.sleep(3)
        work_id = await insert_due_work(test_environment.db_engine, task["id"])
        
        # Setup worker
        config = WorkerConfig.from_dict({
            "worker_id": "failure-test-worker",
            "database_url": test_environment.db_url
        })
        worker = WorkerRunner(config)
        
        with patch('engine.executor.load_catalog', return_value=mock_tool_catalog):
            with patch('engine.executor.call_tool') as mock_call_tool:
                # Always fail
                mock_call_tool.side_effect = Exception("Permanent service error")
                
                lease = worker.lease_one()
                success = worker.process_work_item(lease)
                assert success is False  # Should ultimately fail
        
        # Verify all retry attempts were made
        with test_environment.db_engine.begin() as conn:
            result = conn.execute(text("""
                SELECT COUNT(*) as attempt_count FROM task_run 
                WHERE task_id = :task_id
            """), {"task_id": task["id"]})
            
            attempt_count = result.scalar()
            assert attempt_count == 3  # max_retries + 1 (initial attempt)
            
            # Verify all attempts failed
            result = conn.execute(text("""
                SELECT COUNT(*) as failed_count FROM task_run 
                WHERE task_id = :task_id AND success = false
            """), {"task_id": task["id"]})
            
            failed_count = result.scalar()
            assert failed_count == 3  # All attempts failed
        
        # Verify due work was cleaned up even after permanent failure
        with test_environment.db_engine.begin() as conn:
            result = conn.execute(text("""
                SELECT COUNT(*) as remaining_work FROM due_work WHERE task_id = :task_id
            """), {"task_id": task["id"]})
            
            remaining_work = result.scalar()
            assert remaining_work == 0  # Should be cleaned up
    
    @pytest.mark.integration
    async def test_worker_crash_recovery(self, test_environment):
        """Test recovery from worker crash scenarios."""
        
        # Create test data
        agent_data = await insert_test_agent(test_environment.db_engine)
        task_data = await insert_test_task(test_environment.db_engine, agent_data["id"])
        work_id = await insert_due_work(test_environment.db_engine, task_data["id"])
        
        # Worker 1 leases work but "crashes" (doesn't complete or release)
        config1 = WorkerConfig.from_dict({
            "worker_id": "crashed-worker",
            "database_url": test_environment.db_url,
            "lease_seconds": 5  # Short lease for testing
        })
        worker1 = WorkerRunner(config1)
        
        lease = worker1.lease_one()
        assert lease is not None
        # Simulate crash - don't complete work or clean up lease
        
        # Wait for lease to expire
        await asyncio.sleep(6)
        
        # Worker 2 should be able to recover the work
        config2 = WorkerConfig.from_dict({
            "worker_id": "recovery-worker",
            "database_url": test_environment.db_url,
            "lease_seconds": 60
        })
        worker2 = WorkerRunner(config2)
        
        # Cleanup expired leases first
        worker2.cleanup_expired_leases()
        
        # Should be able to lease the recovered work
        recovered_lease = worker2.lease_one()
        assert recovered_lease is not None
        assert recovered_lease["id"] == work_id
        
        # Clean up
        worker2.delete_work(work_id)


class TestMultiComponentIntegration:
    """Test integration between API, Scheduler, and Workers."""
    
    @pytest.mark.integration 
    async def test_api_to_execution_flow(self, test_environment, mock_tool_catalog):
        """Test complete flow from API task creation to worker execution."""
        
        # First ensure we have a test agent in the database
        agent_data = await insert_test_agent(test_environment.db_engine)
        
        # Create task via API (simulated)
        task_request = {
            "title": "API Integration Test",
            "description": "Task created via API for integration testing",
            "schedule_kind": "once", 
            "schedule_expr": (datetime.now(timezone.utc) + timedelta(seconds=5)).isoformat(),
            "timezone": "Europe/Chisinau",
            "payload": {
                "pipeline": [
                    {
                        "id": "api_test",
                        "uses": "test-tool.execute",
                        "with": {"message": "API to execution integration test"},
                        "save_as": "api_result"
                    }
                ]
            },
            "created_by": str(agent_data["id"]),
            "priority": 7
        }
        
        # Insert task directly (simulating API creation)
        with test_environment.db_engine.begin() as conn:
            result = conn.execute(text("""
                INSERT INTO task (title, description, created_by, schedule_kind, schedule_expr, timezone, payload, status, priority)
                VALUES (:title, :description, :created_by, :schedule_kind, :schedule_expr, :timezone, :payload::jsonb, 'active', :priority)
                RETURNING id
            """), {
                **task_request,
                "payload": json.dumps(task_request["payload"])
            })
            task_id = result.scalar()
        
        # Start scheduler
        scheduler = SchedulerService(test_environment.db_url, "Europe/Chisinau")
        
        # Load and schedule the task
        with test_environment.db_engine.begin() as conn:
            result = conn.execute(text("SELECT * FROM task WHERE id = :id"), {"id": task_id})
            task_row = result.fetchone()
            task_dict = dict(task_row._mapping)
            
        scheduler.schedule_task_job(task_dict)
        
        # Wait for scheduling
        await asyncio.sleep(6)
        
        # Start worker
        config = WorkerConfig.from_dict({
            "worker_id": "api-integration-worker",
            "database_url": test_environment.db_url
        })
        worker = WorkerRunner(config)
        
        with patch('engine.executor.load_catalog', return_value=mock_tool_catalog):
            with patch('engine.executor.call_tool') as mock_call_tool:
                mock_call_tool.return_value = {"result": "API integration successful"}
                
                # Process work
                lease = worker.lease_one()
                assert lease is not None
                
                success = worker.process_work_item(lease)
                assert success is True
        
        # Verify end-to-end execution
        with test_environment.db_engine.begin() as conn:
            result = conn.execute(text("""
                SELECT tr.success, tr.output, t.title, t.priority 
                FROM task_run tr JOIN task t ON tr.task_id = t.id
                WHERE t.id = :task_id
            """), {"task_id": task_id})
            
            row = result.fetchone()
            assert row is not None
            assert row.success is True
            assert row.title == "API Integration Test"
            assert row.priority == 7
            
            output = json.loads(row.output)
            assert output["steps"]["api_result"]["result"] == "API integration successful"
    
    @pytest.mark.integration
    async def test_concurrent_scheduler_worker_coordination(self, test_environment, mock_tool_catalog):
        """Test coordination between scheduler and multiple workers."""
        
        # Create multiple tasks with staggered schedules
        agent_data = await insert_test_agent(test_environment.db_engine)
        task_ids = []
        
        base_time = datetime.now(timezone.utc)
        for i in range(5):
            task_data = {
                "title": f"Coordination Test Task {i}",
                "description": f"Task {i} for scheduler-worker coordination test",
                "created_by": agent_data["id"],
                "schedule_kind": "once",
                "schedule_expr": (base_time + timedelta(seconds=2 + i)).isoformat(),
                "payload": {
                    "pipeline": [
                        {
                            "id": f"task_{i}",
                            "uses": "test-tool.execute",
                            "with": {"message": f"Coordination test {i}"},
                            "save_as": "result"
                        }
                    ]
                }
            }
            
            task = await insert_test_task(test_environment.db_engine, agent_data["id"], task_data)
            task_ids.append(task["id"])
        
        # Start scheduler
        scheduler = SchedulerService(test_environment.db_url, "Europe/Chisinau")
        
        # Load and schedule all tasks
        with test_environment.db_engine.begin() as conn:
            result = conn.execute(text("SELECT * FROM task WHERE created_by = :agent_id"), 
                                {"agent_id": agent_data["id"]})
            tasks = result.fetchall()
            
        for task_row in tasks:
            task_dict = dict(task_row._mapping)
            scheduler.schedule_task_job(task_dict)
        
        # Start multiple workers
        workers = []
        for i in range(3):
            config = WorkerConfig.from_dict({
                "worker_id": f"coordination-worker-{i}",
                "database_url": test_environment.db_url
            })
            workers.append(WorkerRunner(config))
        
        # Wait for all tasks to be scheduled
        await asyncio.sleep(10)
        
        with patch('engine.executor.load_catalog', return_value=mock_tool_catalog):
            with patch('engine.executor.call_tool') as mock_call_tool:
                mock_call_tool.return_value = {"result": "Coordination test completed"}
                
                # Process work with all workers concurrently
                completed_tasks = set()
                
                async def worker_process(worker):
                    while len(completed_tasks) < len(task_ids):
                        lease = worker.lease_one()
                        if lease:
                            success = worker.process_work_item(lease)
                            if success:
                                completed_tasks.add(lease["task_id"])
                        else:
                            await asyncio.sleep(0.5)
                
                # Run workers concurrently
                await asyncio.gather(*[worker_process(w) for w in workers])
        
        # Verify all tasks were completed exactly once
        assert len(completed_tasks) == len(task_ids)
        
        with test_environment.db_engine.begin() as conn:
            result = conn.execute(text("""
                SELECT COUNT(*) as total_runs FROM task_run 
                WHERE task_id = ANY(:task_ids) AND success = true
            """), {"task_ids": task_ids})
            
            total_runs = result.scalar()
            assert total_runs == len(task_ids)  # Each task executed exactly once


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])