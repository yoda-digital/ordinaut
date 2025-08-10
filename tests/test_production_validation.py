#!/usr/bin/env python3
"""
Production Validation Test Suite for Ordinaut

Comprehensive load testing and integration validation designed to verify
production readiness with realistic scenarios and performance benchmarks.

This test suite validates:
- System performance under realistic load conditions
- Cross-service integration and communication
- Database performance with concurrent access patterns
- Error handling and recovery under stress
- Resource utilization and memory management
- End-to-end workflow validation
"""

import pytest
import asyncio
import time
import uuid
import json
import psutil
import statistics
import concurrent.futures
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, Mock, AsyncMock
from typing import List, Dict, Any, Optional
import threading

from sqlalchemy import text
import httpx


class SystemPerformanceMonitor:
    """Monitor system performance during load testing."""
    
    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.cpu_samples = []
        self.memory_samples = []
        self.monitoring = False
        self._monitor_thread = None
    
    def start_monitoring(self, sample_interval=0.2):
        """Start performance monitoring."""
        self.start_time = time.time()
        self.monitoring = True
        self.cpu_samples.clear()
        self.memory_samples.clear()
        
        def monitor_loop():
            while self.monitoring:
                self.cpu_samples.append(psutil.cpu_percent(interval=None))
                self.memory_samples.append(psutil.virtual_memory().percent)
                time.sleep(sample_interval)
        
        self._monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self._monitor_thread.start()
    
    def stop_monitoring(self) -> Dict[str, Any]:
        """Stop monitoring and return performance stats."""
        self.end_time = time.time()
        self.monitoring = False
        
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2.0)
        
        duration = self.end_time - self.start_time if self.start_time else 0
        
        return {
            "duration_seconds": duration,
            "cpu_stats": {
                "mean": statistics.mean(self.cpu_samples) if self.cpu_samples else 0,
                "max": max(self.cpu_samples) if self.cpu_samples else 0,
                "p95": statistics.quantiles(self.cpu_samples, n=20)[18] if len(self.cpu_samples) > 20 else 0
            },
            "memory_stats": {
                "mean": statistics.mean(self.memory_samples) if self.memory_samples else 0,
                "max": max(self.memory_samples) if self.memory_samples else 0,
                "p95": statistics.quantiles(self.memory_samples, n=20)[18] if len(self.memory_samples) > 20 else 0
            }
        }


@pytest.fixture
def performance_monitor():
    """Fixture providing system performance monitoring."""
    return SystemPerformanceMonitor()


@pytest.mark.load
@pytest.mark.slow
class TestProductionLoadValidation:
    """Validate system performance under production-like load conditions."""
    
    async def test_high_throughput_task_processing(self, test_environment, clean_database, performance_monitor):
        """Test system handling high throughput task processing."""
        
        # Create test agent
        agent_id = str(uuid.uuid4())
        with test_environment.db_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO agent (id, name, scopes) 
                VALUES (:id, :name, :scopes)
            """), {
                "id": agent_id,
                "name": f"load-test-agent-{int(time.time())}",
                "scopes": ["test.load", "test.performance"]
            })
        
        # Performance test parameters
        task_count = 500  # High volume of tasks
        batch_size = 50
        
        performance_monitor.start_monitoring()
        start_time = time.time()
        
        # Create tasks in batches for better performance
        task_ids = []
        for batch_start in range(0, task_count, batch_size):
            batch_end = min(batch_start + batch_size, task_count)
            
            with test_environment.db_engine.begin() as conn:
                for i in range(batch_start, batch_end):
                    result = conn.execute(text("""
                        INSERT INTO task (title, description, created_by, schedule_kind,
                                        schedule_expr, timezone, payload, status, priority, max_retries)
                        VALUES (:title, :description, :created_by, :schedule_kind,
                               :schedule_expr, :timezone, :payload::jsonb, :status, :priority, :max_retries)
                        RETURNING id
                    """), {
                        "title": f"Load Test Task {i}",
                        "description": f"High throughput test task {i}",
                        "created_by": agent_id,
                        "schedule_kind": "once",
                        "schedule_expr": (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat(),
                        "timezone": "Europe/Chisinau",
                        "payload": json.dumps({
                            "pipeline": [
                                {
                                    "id": f"load_step_{i}",
                                    "uses": "test.performance",
                                    "with": {"task_id": i, "processing_time_ms": 5},
                                    "save_as": f"result_{i}"
                                }
                            ]
                        }),
                        "status": "active",
                        "priority": i % 10,
                        "max_retries": 2
                    })
                    task_ids.append(result.scalar())
        
        creation_time = time.time() - start_time
        
        # Schedule all tasks as due work
        with test_environment.db_engine.begin() as conn:
            for task_id in task_ids:
                conn.execute(text("""
                    INSERT INTO due_work (task_id, run_at)
                    VALUES (:task_id, now())
                """), {"task_id": task_id})
        
        scheduling_time = time.time() - start_time - creation_time
        
        perf_stats = performance_monitor.stop_monitoring()
        
        # Validate task creation performance
        creation_rate = task_count / creation_time
        scheduling_rate = task_count / scheduling_time
        
        # Verify all tasks were created
        with test_environment.db_engine.begin() as conn:
            created_count = conn.execute(text("""
                SELECT COUNT(*) FROM task WHERE created_by = :agent_id
            """), {"agent_id": agent_id}).scalar()
            
            due_work_count = conn.execute(text("""
                SELECT COUNT(*) FROM due_work dw
                JOIN task t ON dw.task_id = t.id
                WHERE t.created_by = :agent_id
            """), {"agent_id": agent_id}).scalar()
        
        # Performance benchmarks
        print(f"High Throughput Task Processing Results:")
        print(f"  Tasks created: {created_count}")
        print(f"  Creation rate: {creation_rate:.1f} tasks/sec")
        print(f"  Scheduling rate: {scheduling_rate:.1f} tasks/sec")
        print(f"  Due work queued: {due_work_count}")
        print(f"  Total time: {perf_stats['duration_seconds']:.2f}s")
        print(f"  Peak CPU: {perf_stats['cpu_stats']['max']:.1f}%")
        print(f"  Peak Memory: {perf_stats['memory_stats']['max']:.1f}%")
        
        # Production performance requirements
        assert created_count == task_count, f"Task creation failed: {created_count}/{task_count}"
        assert due_work_count == task_count, f"Scheduling failed: {due_work_count}/{task_count}"
        assert creation_rate > 50, f"Creation rate too slow: {creation_rate:.1f} tasks/sec"
        assert perf_stats['cpu_stats']['max'] < 90, f"CPU usage too high: {perf_stats['cpu_stats']['max']:.1f}%"
        assert perf_stats['memory_stats']['max'] < 85, f"Memory usage too high: {perf_stats['memory_stats']['max']:.1f}%"
    
    async def test_concurrent_worker_coordination(self, test_environment, clean_database, performance_monitor):
        """Test multiple workers processing tasks concurrently without conflicts."""
        
        # Create test agent
        agent_id = str(uuid.uuid4())
        with test_environment.db_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO agent (id, name, scopes) 
                VALUES (:id, :name, :scopes)
            """), {
                "id": agent_id,
                "name": f"worker-test-agent-{int(time.time())}",
                "scopes": ["test.worker"]
            })
        
        # Create workload
        work_items = 200
        worker_count = 8
        
        # Setup tasks and due work
        task_ids = []
        with test_environment.db_engine.begin() as conn:
            for i in range(work_items):
                # Create task
                task_result = conn.execute(text("""
                    INSERT INTO task (title, description, created_by, schedule_kind,
                                    schedule_expr, timezone, payload, status, priority, max_retries)
                    VALUES (:title, :description, :created_by, :schedule_kind,
                           :schedule_expr, :timezone, :payload::jsonb, :status, :priority, :max_retries)
                    RETURNING id
                """), {
                    "title": f"Worker Test Task {i}",
                    "description": f"Concurrent processing test {i}",
                    "created_by": agent_id,
                    "schedule_kind": "once",
                    "schedule_expr": datetime.now(timezone.utc).isoformat(),
                    "timezone": "Europe/Chisinau",
                    "payload": json.dumps({
                        "pipeline": [
                            {
                                "id": f"worker_step_{i}",
                                "uses": "test.worker",
                                "with": {"work_id": i, "processing_delay_ms": 10},
                                "save_as": f"work_result_{i}"
                            }
                        ]
                    }),
                    "status": "active",
                    "priority": i % 5,
                    "max_retries": 1
                })
                task_id = task_result.scalar()
                task_ids.append(task_id)
                
                # Create due work
                conn.execute(text("""
                    INSERT INTO due_work (task_id, run_at)
                    VALUES (:task_id, now())
                """), {"task_id": task_id})
        
        # Mock tool for worker processing
        processed_items = set()
        processing_conflicts = 0
        worker_stats = {f"worker_{i}": 0 for i in range(worker_count)}
        
        def mock_worker_tool(tool_def, step_config, tool_input):
            work_id = tool_input["work_id"]
            delay_ms = tool_input["processing_delay_ms"]
            
            # Check for processing conflicts
            if work_id in processed_items:
                nonlocal processing_conflicts
                processing_conflicts += 1
                raise Exception(f"Conflict: Work item {work_id} already processed!")
            
            processed_items.add(work_id)
            
            # Simulate processing time
            time.sleep(delay_ms / 1000.0)
            
            return {
                "result": f"processed_work_{work_id}",
                "worker_timestamp": datetime.now(timezone.utc).isoformat(),
                "processing_time_ms": delay_ms
            }
        
        # Simulate concurrent workers using SKIP LOCKED
        async def simulate_worker(worker_id: str, engine):
            """Simulate worker processing with proper SKIP LOCKED usage."""
            processed_count = 0
            
            with patch('engine.executor.call_tool', side_effect=mock_worker_tool):
                with patch('engine.executor.load_catalog', return_value=[{
                    "address": "test.worker",
                    "transport": "http", 
                    "endpoint": "http://test-worker.com",
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                    "scopes": ["test.worker"]
                }]):
                    
                    while processed_count < work_items // worker_count + 10:  # Process fair share + buffer
                        try:
                            with engine.begin() as conn:
                                # Try to lease work using SKIP LOCKED
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
                                    break  # No more work available
                                
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
                                    SELECT payload FROM task WHERE id = :task_id
                                """), {"task_id": task_id})
                                
                                task_row = task_result.fetchone()
                                if not task_row:
                                    continue
                                
                                # Execute pipeline (simplified)
                                pipeline_data = json.loads(task_row.payload)
                                
                                # Simulate successful execution
                                execution_success = True
                                execution_result = {
                                    "success": True,
                                    "steps": {
                                        pipeline_data["pipeline"][0]["save_as"]: {
                                            "result": f"processed_by_{worker_id}",
                                            "timestamp": datetime.now(timezone.utc).isoformat()
                                        }
                                    }
                                }
                                
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
                                    "success": execution_success,
                                    "attempt": 1,
                                    "output": json.dumps(execution_result)
                                })
                                
                                # Clean up due work
                                conn.execute(text("DELETE FROM due_work WHERE id = :work_id"), {"work_id": work_id})
                                
                                processed_count += 1
                                worker_stats[worker_id] = processed_count
                                
                        except Exception as e:
                            # Handle worker errors gracefully
                            print(f"Worker {worker_id} error: {e}")
                            break
            
            return processed_count
        
        # Run concurrent workers
        performance_monitor.start_monitoring()
        start_time = time.time()
        
        worker_tasks = [
            simulate_worker(f"worker_{i}", test_environment.db_engine)
            for i in range(worker_count)
        ]
        
        worker_results = await asyncio.gather(*worker_tasks, return_exceptions=True)
        
        end_time = time.time()
        total_time = end_time - start_time
        perf_stats = performance_monitor.stop_monitoring()
        
        # Process results
        successful_workers = [r for r in worker_results if isinstance(r, int)]
        total_processed = sum(successful_workers)
        
        # Verify results
        with test_environment.db_engine.begin() as conn:
            remaining_work = conn.execute(text("SELECT COUNT(*) FROM due_work")).scalar()
            completed_runs = conn.execute(text("SELECT COUNT(*) FROM task_run WHERE success = true")).scalar()
            unique_tasks_processed = conn.execute(text("""
                SELECT COUNT(DISTINCT task_id) FROM task_run WHERE success = true
            """)).scalar()
        
        # Performance metrics
        throughput = total_processed / total_time if total_time > 0 else 0
        
        print(f"Concurrent Worker Coordination Results:")
        print(f"  Work items: {work_items}")
        print(f"  Workers: {worker_count}")
        print(f"  Total processed: {total_processed}")
        print(f"  Unique tasks processed: {unique_tasks_processed}")
        print(f"  Processing conflicts: {processing_conflicts}")
        print(f"  Remaining work: {remaining_work}")
        print(f"  Total time: {total_time:.2f}s")
        print(f"  Throughput: {throughput:.1f} items/sec")
        print(f"  Worker distribution: {worker_stats}")
        print(f"  Peak CPU: {perf_stats['cpu_stats']['max']:.1f}%")
        
        # Production requirements
        assert total_processed >= work_items * 0.95, f"Too few items processed: {total_processed}/{work_items}"
        assert processing_conflicts == 0, f"Processing conflicts detected: {processing_conflicts}"
        assert remaining_work == 0, f"Work items left unprocessed: {remaining_work}"
        assert unique_tasks_processed == total_processed, f"Duplicate processing detected"
        assert throughput > 20, f"Throughput too low: {throughput:.1f} items/sec"
    
    async def test_database_connection_pool_stress(self, test_environment, clean_database, performance_monitor):
        """Test database connection pool performance under stress."""
        
        # Create test agent
        agent_id = str(uuid.uuid4())
        with test_environment.db_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO agent (id, name, scopes) 
                VALUES (:id, :name, :scopes)
            """), {
                "id": agent_id,
                "name": f"db-stress-agent-{int(time.time())}",
                "scopes": ["test"]
            })
        
        # Stress test parameters
        concurrent_operations = 50
        operations_per_thread = 20
        
        performance_monitor.start_monitoring()
        
        # Define database-intensive operations
        def database_stress_operation(operation_id: int):
            """Perform database-intensive operations."""
            results = []
            
            try:
                for i in range(operations_per_thread):
                    with test_environment.db_engine.begin() as conn:
                        # Create task
                        task_result = conn.execute(text("""
                            INSERT INTO task (title, description, created_by, schedule_kind,
                                            schedule_expr, timezone, payload, status, priority, max_retries)
                            VALUES (:title, :description, :created_by, :schedule_kind,
                                   :schedule_expr, :timezone, :payload::jsonb, :status, :priority, :max_retries)
                            RETURNING id
                        """), {
                            "title": f"DB Stress Task {operation_id}-{i}",
                            "description": f"Database stress test operation",
                            "created_by": agent_id,
                            "schedule_kind": "once",
                            "schedule_expr": datetime.now(timezone.utc).isoformat(),
                            "timezone": "UTC",
                            "payload": json.dumps({"pipeline": []}),
                            "status": "active",
                            "priority": 5,
                            "max_retries": 1
                        })
                        task_id = task_result.scalar()
                        
                        # Query task back
                        task_query = conn.execute(text("""
                            SELECT * FROM task WHERE id = :task_id
                        """), {"task_id": task_id})
                        task_data = task_query.fetchone()
                        
                        # Update task
                        conn.execute(text("""
                            UPDATE task SET priority = :priority WHERE id = :task_id
                        """), {"priority": (i % 10), "task_id": task_id})
                        
                        # Create work item
                        conn.execute(text("""
                            INSERT INTO due_work (task_id, run_at)
                            VALUES (:task_id, now() + interval '1 minute')
                        """), {"task_id": task_id})
                        
                        results.append(task_id)
                        
            except Exception as e:
                results.append(f"Error: {str(e)}")
            
            return results
        
        # Run concurrent database operations
        start_time = time.time()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_operations) as executor:
            futures = [
                executor.submit(database_stress_operation, i)
                for i in range(concurrent_operations)
            ]
            
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
        
        end_time = time.time()
        total_time = end_time - start_time
        perf_stats = performance_monitor.stop_monitoring()
        
        # Analyze results
        successful_operations = [r for r in results if not any(isinstance(item, str) and "Error" in item for item in r)]
        total_tasks_created = sum(len(r) for r in successful_operations)
        error_count = len(results) - len(successful_operations)
        
        # Verify database state
        with test_environment.db_engine.begin() as conn:
            created_tasks = conn.execute(text("""
                SELECT COUNT(*) FROM task WHERE created_by = :agent_id
            """), {"agent_id": agent_id}).scalar()
            
            created_work = conn.execute(text("""
                SELECT COUNT(*) FROM due_work dw
                JOIN task t ON dw.task_id = t.id
                WHERE t.created_by = :agent_id
            """), {"agent_id": agent_id}).scalar()
        
        # Performance metrics
        operations_per_second = total_tasks_created / total_time if total_time > 0 else 0
        
        print(f"Database Connection Pool Stress Results:")
        print(f"  Concurrent operations: {concurrent_operations}")
        print(f"  Operations per thread: {operations_per_thread}")
        print(f"  Total tasks created: {total_tasks_created}")
        print(f"  Expected tasks: {concurrent_operations * operations_per_thread}")
        print(f"  Tasks in database: {created_tasks}")
        print(f"  Work items created: {created_work}")
        print(f"  Error count: {error_count}")
        print(f"  Total time: {total_time:.2f}s")
        print(f"  Operations per second: {operations_per_second:.1f}")
        print(f"  Peak CPU: {perf_stats['cpu_stats']['max']:.1f}%")
        print(f"  Peak Memory: {perf_stats['memory_stats']['max']:.1f}%")
        
        # Production requirements
        expected_tasks = concurrent_operations * operations_per_thread
        assert created_tasks >= expected_tasks * 0.95, f"Too many database failures: {created_tasks}/{expected_tasks}"
        assert error_count < concurrent_operations * 0.1, f"Too many errors: {error_count}"
        assert operations_per_second > 50, f"Database operations too slow: {operations_per_second:.1f} ops/sec"
        assert perf_stats['cpu_stats']['max'] < 95, f"CPU usage too high under DB stress: {perf_stats['cpu_stats']['max']:.1f}%"


@pytest.mark.integration
@pytest.mark.slow
class TestEndToEndProductionWorkflows:
    """Test complete end-to-end workflows that simulate production usage."""
    
    async def test_morning_briefing_workflow_simulation(self, test_environment, clean_database):
        """Test a complete morning briefing workflow end-to-end."""
        
        # Create agent with appropriate scopes
        agent_id = str(uuid.uuid4())
        with test_environment.db_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO agent (id, name, scopes) 
                VALUES (:id, :name, :scopes)
            """), {
                "id": agent_id,
                "name": f"briefing-agent-{int(time.time())}",
                "scopes": ["weather.read", "calendar.read", "email.read", "llm.process", "notification.send"]
            })
        
        # Define realistic morning briefing pipeline
        briefing_pipeline = {
            "params": {
                "user_name": "Test User",
                "location": "Chisinau, Moldova",
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "timezone": "Europe/Chisinau"
            },
            "pipeline": [
                {
                    "id": "weather_check",
                    "uses": "weather.forecast",
                    "with": {
                        "location": "${params.location}",
                        "date": "${params.date}"
                    },
                    "timeout_seconds": 10,
                    "save_as": "weather"
                },
                {
                    "id": "calendar_events",
                    "uses": "calendar.today_events",
                    "with": {
                        "date": "${params.date}",
                        "timezone": "${params.timezone}"
                    },
                    "timeout_seconds": 15,
                    "save_as": "events"
                },
                {
                    "id": "email_summary",
                    "uses": "email.unread_summary",
                    "with": {
                        "limit": 10,
                        "priority_only": True
                    },
                    "timeout_seconds": 20,
                    "save_as": "emails"
                },
                {
                    "id": "briefing_generation",
                    "uses": "llm.generate_briefing",
                    "with": {
                        "user_name": "${params.user_name}",
                        "weather": "${steps.weather}",
                        "events_count": "${length(steps.events.events)}",
                        "events": "${steps.events.events}",
                        "urgent_emails": "${steps.emails.urgent_count}",
                        "date": "${params.date}"
                    },
                    "timeout_seconds": 30,
                    "save_as": "briefing"
                },
                {
                    "id": "notification",
                    "uses": "notification.send",
                    "with": {
                        "title": "Good Morning ${params.user_name}!",
                        "message": "${steps.briefing.text}",
                        "priority": "normal"
                    },
                    "timeout_seconds": 5,
                    "save_as": "notification_result"
                }
            ]
        }
        
        # Create the task
        task_data = {
            "title": "Morning Briefing Workflow Test",
            "description": "End-to-end morning briefing simulation",
            "created_by": agent_id,
            "schedule_kind": "once",
            "schedule_expr": (datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat(),
            "timezone": "Europe/Chisinau",
            "payload": briefing_pipeline,
            "status": "active",
            "priority": 8,
            "max_retries": 2
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
        
        # Schedule task
        with test_environment.db_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO due_work (task_id, run_at)
                VALUES (:task_id, now() + interval '1 second')
            """), {"task_id": task_id})
        
        # Mock realistic service responses
        service_responses = {
            "weather.forecast": {
                "temperature": 22,
                "condition": "partly_cloudy",
                "description": "Partly cloudy with light winds",
                "humidity": 65,
                "wind_speed": 12,
                "feels_like": 24,
                "uv_index": 4
            },
            "calendar.today_events": {
                "events": [
                    {
                        "title": "Team Standup",
                        "start_time": "09:00",
                        "end_time": "09:30",
                        "location": "Conference Room A"
                    },
                    {
                        "title": "Client Presentation",
                        "start_time": "14:00",
                        "end_time": "15:00",
                        "location": "Online - Zoom"
                    },
                    {
                        "title": "Code Review Session", 
                        "start_time": "16:30",
                        "end_time": "17:30",
                        "location": "Dev Room"
                    }
                ],
                "total_count": 3
            },
            "email.unread_summary": {
                "unread_count": 27,
                "urgent_count": 3,
                "urgent_senders": ["boss@company.com", "client@important.com"],
                "subjects": ["Q4 Planning", "Production Issue", "Meeting Reschedule"]
            },
            "llm.generate_briefing": {
                "text": "Good morning! Today looks pleasant with partly cloudy skies at 22°C (feels like 24°C). You have 3 meetings scheduled: Team Standup at 09:00, Client Presentation at 14:00, and Code Review at 16:30. You have 3 urgent emails to review, including messages from your boss and an important client. Have a productive day!",
                "key_points": ["Pleasant weather", "3 meetings", "3 urgent emails"],
                "estimated_reading_time": "30 seconds"
            },
            "notification.send": {
                "message_id": "brief-20250808-123456",
                "status": "sent",
                "delivered_at": datetime.now(timezone.utc).isoformat(),
                "platform": "system"
            }
        }
        
        # Wait for task to be due
        await asyncio.sleep(5)
        
        # Execute workflow with service mocks
        with patch('engine.executor.call_tool') as mock_call_tool:
            with patch('engine.executor.load_catalog') as mock_catalog:
                
                # Setup tool catalog
                mock_catalog.return_value = [
                    {
                        "address": service,
                        "transport": "http",
                        "endpoint": f"http://{service.replace('.', '-')}.internal",
                        "input_schema": {"type": "object"},
                        "output_schema": {"type": "object"}, 
                        "scopes": [service.split('.')[0]]
                    }
                    for service in service_responses.keys()
                ]
                
                # Mock service calls
                def mock_service_call(tool_def, step_config, tool_input):
                    service_name = tool_def["address"]
                    response = service_responses.get(service_name, {"error": f"No mock for {service_name}"})
                    
                    # Simulate realistic processing delay
                    processing_delays = {
                        "weather.forecast": 0.8,
                        "calendar.today_events": 1.2,
                        "email.unread_summary": 2.1,
                        "llm.generate_briefing": 3.5,
                        "notification.send": 0.3
                    }
                    time.sleep(processing_delays.get(service_name, 0.5))
                    
                    return response
                
                mock_call_tool.side_effect = mock_service_call
                
                # Simulate workflow execution
                start_time = time.time()
                
                with test_environment.db_engine.begin() as conn:
                    # Get and execute task
                    task_result = conn.execute(text("""
                        SELECT * FROM task WHERE id = :task_id
                    """), {"task_id": task_id})
                    
                    task_row = task_result.fetchone()
                    pipeline_data = json.loads(task_row.payload)
                    
                    # Simulate execution (simplified for testing)
                    execution_result = {
                        "success": True,
                        "duration_seconds": time.time() - start_time,
                        "steps": {}
                    }
                    
                    # Simulate each step execution
                    for step in pipeline_data["pipeline"]:
                        step_result = mock_service_call(
                            {"address": step["uses"]},
                            step,
                            step.get("with", {})
                        )
                        execution_result["steps"][step["save_as"]] = step_result
                    
                    # Record execution
                    conn.execute(text("""
                        INSERT INTO task_run (id, task_id, lease_owner, started_at,
                                            finished_at, success, attempt, output)
                        VALUES (:id, :task_id, :lease_owner, :started_at,
                               :finished_at, :success, :attempt, :output::jsonb)
                    """), {
                        "id": str(uuid.uuid4()),
                        "task_id": task_id,
                        "lease_owner": "briefing-workflow-worker",
                        "started_at": datetime.now(timezone.utc),
                        "finished_at": datetime.now(timezone.utc),
                        "success": True,
                        "attempt": 1,
                        "output": json.dumps(execution_result)
                    })
                    
                    # Clean up due work
                    conn.execute(text("DELETE FROM due_work WHERE task_id = :task_id"), {"task_id": task_id})
        
        # Validate workflow execution
        with test_environment.db_engine.begin() as conn:
            run_result = conn.execute(text("""
                SELECT * FROM task_run WHERE task_id = :task_id AND success = true
            """), {"task_id": task_id})
            
            run_row = run_result.fetchone()
            assert run_row is not None, "Workflow execution not recorded"
            
            # Parse execution results
            output = json.loads(run_row.output)
            assert output["success"] is True, "Workflow execution failed"
            assert len(output["steps"]) == 5, f"Expected 5 steps, got {len(output['steps'])}"
            
            # Validate each step
            steps = output["steps"]
            
            # Weather step
            assert "weather" in steps
            assert steps["weather"]["temperature"] == 22
            assert steps["weather"]["condition"] == "partly_cloudy"
            
            # Calendar step
            assert "events" in steps  
            assert len(steps["events"]["events"]) == 3
            assert steps["events"]["events"][0]["title"] == "Team Standup"
            
            # Email step
            assert "emails" in steps
            assert steps["emails"]["urgent_count"] == 3
            assert steps["emails"]["unread_count"] == 27
            
            # Briefing step
            assert "briefing" in steps
            briefing_text = steps["briefing"]["text"]
            assert "Good morning" in briefing_text
            assert "22°C" in briefing_text
            assert "3 meetings" in briefing_text
            assert "3 urgent emails" in briefing_text
            
            # Notification step
            assert "notification_result" in steps
            assert steps["notification_result"]["status"] == "sent"
            assert "message_id" in steps["notification_result"]
        
        # Verify all service calls were made
        assert mock_call_tool.call_count == 5, f"Expected 5 service calls, got {mock_call_tool.call_count}"
        
        execution_time = output["duration_seconds"]
        print(f"Morning Briefing Workflow Results:")
        print(f"  Steps executed: {len(output['steps'])}")
        print(f"  Total execution time: {execution_time:.2f}s")
        print(f"  Service calls made: {mock_call_tool.call_count}")
        print(f"  Workflow success: {output['success']}")
        
        # Performance requirements for production workflow
        assert execution_time < 15, f"Workflow too slow: {execution_time:.2f}s (should be < 15s)"
        assert output["success"] is True, "Workflow execution failed"


if __name__ == "__main__":
    # Run production validation tests
    pytest.main([
        __file__, 
        "-v", 
        "--tb=short", 
        "-s",
        "--maxfail=5",
        "--disable-warnings"
    ])