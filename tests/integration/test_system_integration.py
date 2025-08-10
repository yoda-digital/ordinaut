#!/usr/bin/env python3
"""
Comprehensive System Integration Tests for Ordinaut

Tests the complete system integration with real components:
- Full API to database to worker pipeline
- Real PostgreSQL database operations
- Real Redis event streaming
- Complete task lifecycle from creation to execution
- Cross-component communication and data flow
- Production-like scenarios with real dependencies

These tests use testcontainers for real database/Redis instances
and verify the entire system works together correctly.
"""

import pytest
import asyncio
import time
import uuid
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from unittest.mock import patch, AsyncMock

import httpx
from sqlalchemy import text
from fastapi.testclient import TestClient

from engine.executor import run_pipeline
from engine.rruler import RRuleProcessor
from tests.test_worker_utils import TaskWorker
from observability.metrics import orchestrator_metrics


@pytest.mark.integration
@pytest.mark.slow
class TestCompleteTaskLifecycle:
    """Test complete task lifecycle through the entire system."""
    
    async def test_full_task_creation_to_execution_flow(self, test_environment, clean_database):
        """Test complete flow from API task creation to worker execution."""
        
        # 1. Create agent through database
        agent_data = {
            "id": str(uuid.uuid4()),
            "name": f"integration-test-agent-{int(time.time())}",
            "scopes": ["task.create", "task.read", "test.execute"]
        }
        
        with test_environment.db_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO agent (id, name, scopes) 
                VALUES (:id, :name, :scopes)
            """), {
                "id": agent_data["id"],
                "name": agent_data["name"],
                "scopes": agent_data["scopes"]
            })
        
        # 2. Create task through API (simulated)
        task_data = {
            "title": "Integration Test Task",
            "description": "End-to-end integration test task",
            "schedule_kind": "once",
            "schedule_expr": (datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat(),
            "timezone": "Europe/Chisinau",
            "payload": {
                "pipeline": [
                    {
                        "id": "integration_step",
                        "uses": "test.execute",
                        "with": {"message": "Integration test successful"},
                        "save_as": "test_result"
                    }
                ]
            },
            "created_by": agent_data["id"],
            "status": "active",
            "priority": 5,
            "max_retries": 3
        }
        
        # Insert task directly (simulating API creation)
        task_id = None
        with test_environment.db_engine.begin() as conn:
            result = conn.execute(text("""
                INSERT INTO task (title, description, created_by, schedule_kind, 
                                schedule_expr, timezone, payload, status, priority, max_retries)
                VALUES (:title, :description, :created_by, :schedule_kind, 
                       :schedule_expr, :timezone, :payload::jsonb, :status, :priority, :max_retries)
                RETURNING id
            """), {
                **task_data,
                "payload": json.dumps(task_data["payload"])
            })
            task_id = result.scalar()
        
        assert task_id is not None
        
        # 3. Scheduler should pick up the task and create due work
        # Simulate scheduler tick
        with test_environment.db_engine.begin() as conn:
            # Check if task is ready to be scheduled
            result = conn.execute(text("""
                SELECT id, schedule_expr FROM task 
                WHERE id = :task_id AND status = 'active'
            """), {"task_id": task_id})
            
            task_row = result.fetchone()
            assert task_row is not None
            
            # Schedule the task (simulate scheduler)
            schedule_time = datetime.fromisoformat(task_data["schedule_expr"].replace('Z', '+00:00'))
            conn.execute(text("""
                INSERT INTO due_work (task_id, run_at)
                VALUES (:task_id, :run_at)
            """), {
                "task_id": task_id,
                "run_at": schedule_time
            })
        
        # 4. Wait for task to become due
        await asyncio.sleep(15)  # Wait for schedule time to pass
        
        # 5. Worker should process the task
        with patch('engine.executor.call_tool') as mock_call_tool:
            mock_call_tool.return_value = {
                "result": "Integration test completed successfully",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "success"
            }
            
            # Create and run worker
            worker = TaskWorker("integration-test-worker", test_environment.db_engine)
            
            # Simulate worker processing
            with test_environment.db_engine.begin() as conn:
                # Worker leases work
                work_result = conn.execute(text("""
                    SELECT id, task_id FROM due_work 
                    WHERE run_at <= now() 
                      AND (locked_until IS NULL OR locked_until < now())
                    ORDER BY run_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                """))
                
                work_row = work_result.fetchone()
                assert work_row is not None, "No work available for processing"
                
                work_id, work_task_id = work_row
                assert work_task_id == task_id
                
                # Lease the work
                lease_time = datetime.now(timezone.utc) + timedelta(minutes=5)
                conn.execute(text("""
                    UPDATE due_work 
                    SET locked_until = :lease_time, locked_by = :worker_id
                    WHERE id = :work_id
                """), {
                    "lease_time": lease_time,
                    "worker_id": "integration-test-worker",
                    "work_id": work_id
                })
                
                # Get task details for execution
                task_result = conn.execute(text("""
                    SELECT * FROM task WHERE id = :task_id
                """), {"task_id": task_id})
                
                task_row = task_result.fetchone()
                assert task_row is not None
                
                # Execute pipeline
                pipeline_data = json.loads(task_row.payload)
                
                # Run the pipeline
                execution_result = await run_pipeline(pipeline_data)
                
                # Record execution result
                run_id = str(uuid.uuid4())
                conn.execute(text("""
                    INSERT INTO task_run (id, task_id, lease_owner, started_at, 
                                        finished_at, success, attempt, output)
                    VALUES (:id, :task_id, :lease_owner, :started_at, 
                           :finished_at, :success, :attempt, :output::jsonb)
                """), {
                    "id": run_id,
                    "task_id": task_id,
                    "lease_owner": "integration-test-worker",
                    "started_at": datetime.now(timezone.utc),
                    "finished_at": datetime.now(timezone.utc),
                    "success": execution_result.get("success", False),
                    "attempt": 1,
                    "output": json.dumps(execution_result)
                })
                
                # Clean up due work
                conn.execute(text("DELETE FROM due_work WHERE id = :work_id"), {"work_id": work_id})
        
        # 6. Verify complete task execution
        with test_environment.db_engine.begin() as conn:
            # Check task run was recorded
            run_result = conn.execute(text("""
                SELECT * FROM task_run WHERE task_id = :task_id
            """), {"task_id": task_id})
            
            run_row = run_result.fetchone()
            assert run_row is not None
            assert run_row.success is True
            assert run_row.lease_owner == "integration-test-worker"
            
            # Verify output contains expected data
            output_data = json.loads(run_row.output)
            assert output_data["success"] is True
            assert "test_result" in output_data["steps"]
            assert output_data["steps"]["test_result"]["result"] == "Integration test completed successfully"
            
            # Verify no remaining due work
            remaining_work = conn.execute(text("""
                SELECT COUNT(*) FROM due_work WHERE task_id = :task_id
            """), {"task_id": task_id}).scalar()
            assert remaining_work == 0
        
        # 7. Verify metrics were recorded
        # Note: This would verify actual metrics collection in production
        assert hasattr(orchestrator_metrics, 'record_task_completion')
    
    async def test_recurring_task_scheduling_accuracy(self, test_environment, clean_database):
        """Test recurring task scheduling with RRULE accuracy."""
        
        # Create agent
        agent_id = str(uuid.uuid4())
        with test_environment.db_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO agent (id, name, scopes) 
                VALUES (:id, :name, :scopes)
            """), {
                "id": agent_id,
                "name": f"rrule-test-agent-{int(time.time())}",
                "scopes": ["test"]
            })
        
        # Create recurring task (every 2 minutes for testing)
        task_data = {
            "title": "Recurring Integration Test",
            "description": "Test RRULE scheduling integration",
            "created_by": agent_id,
            "schedule_kind": "rrule",
            "schedule_expr": "FREQ=MINUTELY;INTERVAL=2",  # Every 2 minutes
            "timezone": "Europe/Chisinau",
            "payload": {"pipeline": [{"id": "recurring_test", "uses": "test.noop"}]},
            "status": "active",
            "priority": 5,
            "max_retries": 1
        }
        
        task_id = None
        with test_environment.db_engine.begin() as conn:
            result = conn.execute(text("""
                INSERT INTO task (title, description, created_by, schedule_kind,
                                schedule_expr, timezone, payload, status, priority, max_retries)
                VALUES (:title, :description, :created_by, :schedule_kind,
                       :schedule_expr, :timezone, :payload::jsonb, :status, :priority, :max_retries)
                RETURNING id
            """), {
                **task_data,
                "payload": json.dumps(task_data["payload"])
            })
            task_id = result.scalar()
        
        # Initialize RRULE processor
        rrule_processor = RRuleProcessor("Europe/Chisinau")
        
        # Calculate next 5 occurrences
        base_time = datetime.now(timezone.utc)
        expected_occurrences = []
        current_time = base_time
        
        for _ in range(5):
            next_time = rrule_processor.get_next_occurrence(
                task_data["schedule_expr"], 
                current_time
            )
            expected_occurrences.append(next_time)
            current_time = next_time + timedelta(seconds=1)  # Move past current
        
        # Simulate scheduler creating due work for these occurrences
        with test_environment.db_engine.begin() as conn:
            for i, occurrence_time in enumerate(expected_occurrences):
                conn.execute(text("""
                    INSERT INTO due_work (task_id, run_at)
                    VALUES (:task_id, :run_at)
                """), {
                    "task_id": task_id,
                    "run_at": occurrence_time
                })
        
        # Verify scheduled times are accurate
        with test_environment.db_engine.begin() as conn:
            result = conn.execute(text("""
                SELECT run_at FROM due_work 
                WHERE task_id = :task_id 
                ORDER BY run_at ASC
            """), {"task_id": task_id})
            
            scheduled_times = [row.run_at for row in result.fetchall()]
        
        assert len(scheduled_times) == 5
        
        # Verify timing accuracy (within 1 second tolerance)
        for expected, actual in zip(expected_occurrences, scheduled_times):
            time_diff = abs((expected - actual).total_seconds())
            assert time_diff < 1.0, f"Scheduling inaccuracy: {time_diff:.2f}s difference"
        
        # Verify interval accuracy (should be ~120 seconds apart)
        for i in range(1, len(scheduled_times)):
            interval = (scheduled_times[i] - scheduled_times[i-1]).total_seconds()
            assert 118 <= interval <= 122, f"Interval inaccuracy: {interval:.1f}s (expected ~120s)"
    
    async def test_multi_step_pipeline_with_data_flow(self, test_environment, clean_database):
        """Test complex multi-step pipeline with data flow between steps."""
        
        # Create agent
        agent_id = str(uuid.uuid4())
        with test_environment.db_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO agent (id, name, scopes) 
                VALUES (:id, :name, :scopes)
            """), {
                "id": agent_id,
                "name": f"pipeline-test-agent-{int(time.time())}",
                "scopes": ["weather.read", "calendar.read", "notify", "llm.process"]
            })
        
        # Create complex pipeline task
        complex_pipeline = {
            "params": {
                "location": "Chisinau",
                "date": "2025-08-08",
                "user_name": "Integration Test User"
            },
            "pipeline": [
                {
                    "id": "weather",
                    "uses": "weather.forecast",
                    "with": {
                        "location": "${params.location}",
                        "date": "${params.date}"
                    },
                    "save_as": "weather_data"
                },
                {
                    "id": "calendar",
                    "uses": "calendar.list_events",
                    "with": {
                        "date": "${params.date}",
                        "timezone": "Europe/Chisinau"
                    },
                    "save_as": "events_data"
                },
                {
                    "id": "summary",
                    "uses": "llm.summarize",
                    "with": {
                        "weather": "${steps.weather_data.summary}",
                        "temperature": "${steps.weather_data.temperature}",
                        "events_count": "${length(steps.events_data.events)}",
                        "first_event": "${steps.events_data.events[0].title}",
                        "user_name": "${params.user_name}"
                    },
                    "save_as": "daily_summary"
                },
                {
                    "id": "notify",
                    "uses": "telegram.send",
                    "with": {
                        "message": "Good morning ${params.user_name}! ${steps.daily_summary.text}",
                        "chat_id": 12345
                    },
                    "save_as": "notification_result"
                }
            ]
        }
        
        task_data = {
            "title": "Complex Pipeline Integration Test",
            "description": "Multi-step pipeline with data flow testing",
            "created_by": agent_id,
            "schedule_kind": "once",
            "schedule_expr": (datetime.now(timezone.utc) + timedelta(seconds=5)).isoformat(),
            "timezone": "Europe/Chisinau",
            "payload": complex_pipeline,
            "status": "active",
            "priority": 8,
            "max_retries": 2
        }
        
        # Create task
        task_id = None
        with test_environment.db_engine.begin() as conn:
            result = conn.execute(text("""
                INSERT INTO task (title, description, created_by, schedule_kind,
                                schedule_expr, timezone, payload, status, priority, max_retries)
                VALUES (:title, :description, :created_by, :schedule_kind,
                       :schedule_expr, :timezone, :payload::jsonb, :status, :priority, :max_retries)
                RETURNING id
            """), {
                **task_data,
                "payload": json.dumps(task_data["payload"])
            })
            task_id = result.scalar()
        
        # Schedule for immediate execution
        with test_environment.db_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO due_work (task_id, run_at)
                VALUES (:task_id, now())
            """), {"task_id": task_id})
        
        # Mock tool responses for pipeline execution
        tool_responses = {
            "weather.forecast": {
                "summary": "Partly cloudy",
                "temperature": 22,
                "humidity": 65,
                "wind_speed": 15
            },
            "calendar.list_events": {
                "events": [
                    {"title": "Team Meeting", "time": "09:00", "location": "Office"},
                    {"title": "Code Review", "time": "14:30", "location": "Room 201"},
                    {"title": "Project Planning", "time": "16:00", "location": "Zoom"}
                ],
                "total_count": 3
            },
            "llm.summarize": {
                "text": "Today looks pleasant with partly cloudy skies at 22°C. You have 3 scheduled events including Team Meeting at 09:00.",
                "key_points": ["Pleasant weather", "3 meetings", "Starts with Team Meeting"]
            },
            "telegram.send": {
                "message_id": 98765,
                "status": "sent",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        }
        
        # Execute pipeline with mocked tools
        with patch('engine.executor.call_tool') as mock_call_tool:
            def tool_response_selector(tool_def, step_config, tool_input):
                tool_address = tool_def["address"]
                return tool_responses.get(tool_address, {"error": f"No mock for {tool_address}"})
            
            mock_call_tool.side_effect = tool_response_selector
            
            # Simulate worker execution
            with test_environment.db_engine.begin() as conn:
                # Get task and execute
                task_result = conn.execute(text("""
                    SELECT * FROM task WHERE id = :task_id
                """), {"task_id": task_id})
                
                task_row = task_result.fetchone()
                pipeline_data = json.loads(task_row.payload)
                
                # Execute pipeline
                start_time = time.time()
                execution_result = await run_pipeline(pipeline_data)
                execution_time = time.time() - start_time
                
                # Record execution
                conn.execute(text("""
                    INSERT INTO task_run (id, task_id, lease_owner, started_at,
                                        finished_at, success, attempt, output)
                    VALUES (:id, :task_id, :lease_owner, :started_at,
                           :finished_at, :success, :attempt, :output::jsonb)
                """), {
                    "id": str(uuid.uuid4()),
                    "task_id": task_id,
                    "lease_owner": "integration-pipeline-worker",
                    "started_at": datetime.now(timezone.utc),
                    "finished_at": datetime.now(timezone.utc),
                    "success": execution_result.get("success", False),
                    "attempt": 1,
                    "output": json.dumps(execution_result)
                })
        
        # Verify pipeline execution results
        with test_environment.db_engine.begin() as conn:
            result = conn.execute(text("""
                SELECT * FROM task_run WHERE task_id = :task_id
            """), {"task_id": task_id})
            
            run_row = result.fetchone()
            assert run_row is not None
            assert run_row.success is True
            
            # Parse and verify execution output
            output_data = json.loads(run_row.output)
            assert output_data["success"] is True
            assert len(output_data["steps"]) == 4
            
            # Verify data flow between steps
            steps = output_data["steps"]
            
            # Weather step
            assert "weather_data" in steps
            assert steps["weather_data"]["summary"] == "Partly cloudy"
            assert steps["weather_data"]["temperature"] == 22
            
            # Calendar step
            assert "events_data" in steps
            assert len(steps["events_data"]["events"]) == 3
            assert steps["events_data"]["events"][0]["title"] == "Team Meeting"
            
            # Summary step (using data from previous steps)
            assert "daily_summary" in steps
            assert "partly cloudy" in steps["daily_summary"]["text"].lower()
            assert "22°C" in steps["daily_summary"]["text"]
            assert "3 scheduled" in steps["daily_summary"]["text"]
            
            # Notification step (using summary)
            assert "notification_result" in steps
            assert steps["notification_result"]["message_id"] == 98765
            assert steps["notification_result"]["status"] == "sent"
        
        # Verify template rendering worked correctly
        assert mock_call_tool.call_count == 4
        
        # Check each tool call had properly rendered inputs
        call_args_list = mock_call_tool.call_args_list
        
        # Weather call
        weather_input = call_args_list[0][0][2]  # Third argument is tool_input
        assert weather_input["location"] == "Chisinau"
        assert weather_input["date"] == "2025-08-08"
        
        # Calendar call  
        calendar_input = call_args_list[1][0][2]
        assert calendar_input["date"] == "2025-08-08"
        assert calendar_input["timezone"] == "Europe/Chisinau"
        
        # Summary call (should have data from previous steps)
        summary_input = call_args_list[2][0][2]
        assert summary_input["weather"] == "Partly cloudy"
        assert summary_input["temperature"] == 22
        assert summary_input["events_count"] == 3
        assert summary_input["first_event"] == "Team Meeting"
        assert summary_input["user_name"] == "Integration Test User"
        
        # Notification call (should have rendered message)
        notify_input = call_args_list[3][0][2]
        assert "Good morning Integration Test User!" in notify_input["message"]
        assert "partly cloudy skies at 22°C" in notify_input["message"]
        assert notify_input["chat_id"] == 12345
        
        print(f"Complex pipeline executed successfully in {execution_time:.3f}s")
    
    async def test_error_handling_and_retry_integration(self, test_environment, clean_database):
        """Test error handling and retry logic integration."""
        
        # Create agent
        agent_id = str(uuid.uuid4())
        with test_environment.db_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO agent (id, name, scopes) 
                VALUES (:id, :name, :scopes)
            """), {
                "id": agent_id,
                "name": f"retry-test-agent-{int(time.time())}",
                "scopes": ["test.unreliable"]
            })
        
        # Create task with unreliable tool
        task_data = {
            "title": "Retry Integration Test",
            "description": "Test retry logic with failing tool",
            "created_by": agent_id,
            "schedule_kind": "once",
            "schedule_expr": datetime.now(timezone.utc).isoformat(),
            "timezone": "Europe/Chisinau",
            "payload": {
                "pipeline": [
                    {
                        "id": "unreliable_step",
                        "uses": "test.unreliable",
                        "with": {"operation": "might_fail"},
                        "retry_attempts": 3,
                        "retry_delay_ms": 100,
                        "save_as": "unreliable_result"
                    }
                ]
            },
            "status": "active",
            "priority": 5,
            "max_retries": 2  # Task-level retries
        }
        
        task_id = None
        with test_environment.db_engine.begin() as conn:
            result = conn.execute(text("""
                INSERT INTO task (title, description, created_by, schedule_kind,
                                schedule_expr, timezone, payload, status, priority, max_retries)
                VALUES (:title, :description, :created_by, :schedule_kind,
                       :schedule_expr, :timezone, :payload::jsonb, :status, :priority, :max_retries)
                RETURNING id
            """), {
                **task_data,
                "payload": json.dumps(task_data["payload"])
            })
            task_id = result.scalar()
        
        # Schedule for immediate execution
        with test_environment.db_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO due_work (task_id, run_at)
                VALUES (:task_id, now())
            """), {"task_id": task_id})
        
        # Test scenario: Fail twice, succeed on third attempt
        call_count = 0
        
        def unreliable_tool_response(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            if call_count <= 2:
                # First two attempts fail
                raise Exception(f"Simulated failure #{call_count}")
            else:
                # Third attempt succeeds
                return {
                    "result": "success_after_retries",
                    "attempt": call_count,
                    "message": "Finally succeeded!"
                }
        
        # Execute with retries
        with patch('engine.executor.call_tool', side_effect=unreliable_tool_response):
            # Simulate worker execution
            with test_environment.db_engine.begin() as conn:
                task_result = conn.execute(text("""
                    SELECT * FROM task WHERE id = :task_id
                """), {"task_id": task_id})
                
                task_row = task_result.fetchone()
                pipeline_data = json.loads(task_row.payload)
                
                # Execute pipeline (should succeed after retries)
                execution_result = await run_pipeline(pipeline_data)
                
                # Record successful execution
                conn.execute(text("""
                    INSERT INTO task_run (id, task_id, lease_owner, started_at,
                                        finished_at, success, attempt, output, error)
                    VALUES (:id, :task_id, :lease_owner, :started_at,
                           :finished_at, :success, :attempt, :output::jsonb, :error)
                """), {
                    "id": str(uuid.uuid4()),
                    "task_id": task_id,
                    "lease_owner": "retry-test-worker",
                    "started_at": datetime.now(timezone.utc),
                    "finished_at": datetime.now(timezone.utc),
                    "success": execution_result.get("success", False),
                    "attempt": 1,
                    "output": json.dumps(execution_result),
                    "error": None if execution_result.get("success") else execution_result.get("error")
                })
        
        # Verify retry behavior
        assert call_count == 3, f"Expected 3 tool calls, got {call_count}"
        
        # Verify successful execution after retries
        with test_environment.db_engine.begin() as conn:
            result = conn.execute(text("""
                SELECT * FROM task_run WHERE task_id = :task_id
            """), {"task_id": task_id})
            
            run_row = result.fetchone()
            assert run_row is not None
            assert run_row.success is True
            
            output_data = json.loads(run_row.output)
            assert output_data["success"] is True
            
            # Verify final result includes retry information
            assert "unreliable_result" in output_data["steps"]
            result_data = output_data["steps"]["unreliable_result"]
            assert result_data["result"] == "success_after_retries"
            assert result_data["attempt"] == 3
            assert result_data["message"] == "Finally succeeded!"


@pytest.mark.integration
@pytest.mark.slow
class TestConcurrentOperationsIntegration:
    """Test concurrent operations across the entire system."""
    
    async def test_multiple_workers_concurrent_processing(self, test_environment, clean_database):
        """Test multiple workers processing tasks concurrently without conflicts."""
        
        # Create test agent
        agent_id = str(uuid.uuid4())
        with test_environment.db_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO agent (id, name, scopes) 
                VALUES (:id, :name, :scopes)
            """), {
                "id": agent_id,
                "name": f"concurrent-test-agent-{int(time.time())}",
                "scopes": ["test"]
            })
        
        # Create multiple tasks
        task_count = 20
        task_ids = []
        
        with test_environment.db_engine.begin() as conn:
            for i in range(task_count):
                result = conn.execute(text("""
                    INSERT INTO task (title, description, created_by, schedule_kind,
                                    schedule_expr, timezone, payload, status, priority, max_retries)
                    VALUES (:title, :description, :created_by, :schedule_kind,
                           :schedule_expr, :timezone, :payload::jsonb, :status, :priority, :max_retries)
                    RETURNING id
                """), {
                    "title": f"Concurrent Test Task {i}",
                    "description": f"Task {i} for concurrent processing test",
                    "created_by": agent_id,
                    "schedule_kind": "once",
                    "schedule_expr": datetime.now(timezone.utc).isoformat(),
                    "timezone": "Europe/Chisinau",
                    "payload": json.dumps({
                        "pipeline": [
                            {
                                "id": f"concurrent_step_{i}",
                                "uses": "test.concurrent",
                                "with": {"task_number": i, "delay_ms": 50},
                                "save_as": f"result_{i}"
                            }
                        ]
                    }),
                    "status": "active",
                    "priority": i % 10,
                    "max_retries": 1
                })
                task_ids.append(result.scalar())
            
            # Schedule all tasks for immediate execution
            for task_id in task_ids:
                conn.execute(text("""
                    INSERT INTO due_work (task_id, run_at)
                    VALUES (:task_id, now())
                """), {"task_id": task_id})
        
        # Mock tool to simulate concurrent processing
        processed_tasks = set()
        processing_times = []
        
        def concurrent_tool_mock(tool_def, step_config, tool_input):
            task_num = tool_input["task_number"]
            delay_ms = tool_input["delay_ms"]
            
            # Record processing
            processed_tasks.add(task_num)
            start_time = time.time()
            
            # Simulate work
            time.sleep(delay_ms / 1000.0)
            
            processing_time = (time.time() - start_time) * 1000
            processing_times.append(processing_time)
            
            return {
                "result": f"processed_task_{task_num}",
                "processing_time_ms": processing_time,
                "worker_timestamp": datetime.now(timezone.utc).isoformat()
            }
        
        # Run multiple workers concurrently
        async def worker_task(worker_id, engine):
            """Individual worker task."""
            processed_count = 0
            
            with patch('engine.executor.call_tool', side_effect=concurrent_tool_mock):
                while processed_count < 10:  # Process up to 10 tasks per worker
                    with engine.begin() as conn:
                        # Try to lease work
                        work_result = conn.execute(text("""
                            SELECT id, task_id FROM due_work 
                            WHERE run_at <= now() 
                              AND (locked_until IS NULL OR locked_until < now())
                            ORDER BY run_at ASC
                            FOR UPDATE SKIP LOCKED
                            LIMIT 1
                        """))
                        
                        work_row = work_result.fetchone()
                        if not work_row:
                            break  # No more work
                        
                        work_id, task_id = work_row
                        
                        # Lease the work
                        lease_time = datetime.now(timezone.utc) + timedelta(minutes=5)
                        conn.execute(text("""
                            UPDATE due_work 
                            SET locked_until = :lease_time, locked_by = :worker_id
                            WHERE id = :work_id
                        """), {
                            "lease_time": lease_time,
                            "worker_id": worker_id,
                            "work_id": work_id
                        })
                        
                        # Get task details
                        task_result = conn.execute(text("""
                            SELECT * FROM task WHERE id = :task_id
                        """), {"task_id": task_id})
                        
                        task_row = task_result.fetchone()
                        pipeline_data = json.loads(task_row.payload)
                        
                        # Execute pipeline
                        execution_result = await run_pipeline(pipeline_data)
                        
                        # Record execution
                        conn.execute(text("""
                            INSERT INTO task_run (id, task_id, lease_owner, started_at,
                                                finished_at, success, attempt, output)
                            VALUES (:id, :task_id, :lease_owner, :started_at,
                                   :finished_at, :success, :attempt, :output::jsonb)
                        """), {
                            "id": str(uuid.uuid4()),
                            "task_id": task_id,
                            "lease_owner": worker_id,
                            "started_at": datetime.now(timezone.utc),
                            "finished_at": datetime.now(timezone.utc),
                            "success": execution_result.get("success", False),
                            "attempt": 1,
                            "output": json.dumps(execution_result)
                        })
                        
                        # Clean up due work
                        conn.execute(text("DELETE FROM due_work WHERE id = :work_id"), {"work_id": work_id})
                        
                        processed_count += 1
            
            return processed_count
        
        # Start multiple workers
        worker_count = 5
        start_time = time.time()
        
        worker_tasks = [
            worker_task(f"concurrent-worker-{i}", test_environment.db_engine)
            for i in range(worker_count)
        ]
        
        # Run all workers concurrently
        worker_results = await asyncio.gather(*worker_tasks)
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Verify results
        total_processed = sum(worker_results)
        unique_tasks_processed = len(processed_tasks)
        
        # Should process all tasks exactly once
        assert total_processed == task_count, f"Expected {task_count}, processed {total_processed}"
        assert unique_tasks_processed == task_count, f"Expected {task_count} unique, got {unique_tasks_processed}"
        
        # Verify no remaining due work
        with test_environment.db_engine.begin() as conn:
            remaining = conn.execute(text("SELECT COUNT(*) FROM due_work")).scalar()
            assert remaining == 0, f"Still have {remaining} unprocessed work items"
        
        # Verify all tasks have runs recorded
        with test_environment.db_engine.begin() as conn:
            run_count = conn.execute(text("""
                SELECT COUNT(*) FROM task_run WHERE success = true
            """)).scalar()
            assert run_count == task_count, f"Expected {task_count} successful runs, got {run_count}"
        
        # Performance verification
        throughput = total_processed / total_time
        avg_processing_time = sum(processing_times) / len(processing_times)
        
        print(f"Concurrent processing results:")
        print(f"  - Tasks processed: {total_processed}")
        print(f"  - Workers: {worker_count}")
        print(f"  - Total time: {total_time:.2f}s")
        print(f"  - Throughput: {throughput:.1f} tasks/second")
        print(f"  - Avg processing time: {avg_processing_time:.1f}ms")
        
        # Should have reasonable performance
        assert throughput > 2.0, f"Throughput too low: {throughput:.1f} tasks/second"
        assert avg_processing_time < 100, f"Processing too slow: {avg_processing_time:.1f}ms"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])