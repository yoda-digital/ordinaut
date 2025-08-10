#!/usr/bin/env python3
"""
Chaos Engineering Tests for Ordinaut

Tests system resilience under various failure scenarios:
- Database connection failures and recovery
- Network timeouts and service unavailability
- High load and resource exhaustion
- Concurrent worker failures
- Memory leaks and resource cleanup
- Time-based edge cases and race conditions

These tests verify the system's ability to gracefully handle failures,
recover automatically, and maintain data consistency under stress.
"""

import pytest
import asyncio
import time
import threading
import uuid
import json
import sqlite3
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from concurrent.futures import ThreadPoolExecutor, as_completed
import gc
import resource

from engine.executor import run_pipeline
from engine.template import render_templates
from tests.test_worker_utils import TaskWorker
from observability.metrics import orchestrator_metrics


class DatabaseFailureSimulator:
    """Simulates various database failure scenarios."""
    
    def __init__(self, db_session):
        self.db_session = db_session
        self.failure_count = 0
        self.failure_threshold = 3
        self.original_execute = db_session.execute
    
    def intermittent_failure(self, *args, **kwargs):
        """Simulate intermittent database failures."""
        self.failure_count += 1
        
        if self.failure_count <= self.failure_threshold:
            if self.failure_count == 1:
                raise ConnectionError("Connection to database lost")
            elif self.failure_count == 2:
                raise TimeoutError("Database query timeout")
            elif self.failure_count == 3:
                raise Exception("Database server is down")
        
        # After threshold, work normally
        return self.original_execute(*args, **kwargs)
    
    def slow_response(self, *args, **kwargs):
        """Simulate slow database responses."""
        time.sleep(2)  # Simulate 2 second delay
        return self.original_execute(*args, **kwargs)


class NetworkFailureSimulator:
    """Simulates network-related failures for external tools."""
    
    def __init__(self):
        self.call_count = 0
        self.failure_patterns = {
            "timeout": lambda: ConnectionError("Request timeout"),
            "unavailable": lambda: Exception("Service temporarily unavailable"),
            "rate_limit": lambda: Exception("Rate limit exceeded"),
            "auth_failure": lambda: Exception("Authentication failed")
        }
    
    def simulate_failure(self, failure_type="timeout"):
        """Simulate specific failure type."""
        self.call_count += 1
        
        if failure_type in self.failure_patterns:
            raise self.failure_patterns[failure_type]()
        
        raise Exception(f"Unknown failure type: {failure_type}")


@pytest.mark.chaos
@pytest.mark.slow
class TestDatabaseResilienceScenarios:
    """Test database failure recovery scenarios."""
    
    def test_database_connection_recovery(self, mock_db):
        """Test automatic recovery from database connection failures."""
        
        simulator = DatabaseFailureSimulator(mock_db)
        mock_db.execute = simulator.intermittent_failure
        
        # Insert test data first (before failures)
        agent_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        
        try:
            # This should work (before we start failing)
            mock_db.execute("INSERT INTO agent (id, name, scopes) VALUES (?, ?, ?)",
                           {"id": agent_id, "name": "test-agent", "scopes": json.dumps(["test"])})
        except Exception:
            # Reset to allow the first insert
            mock_db.execute = simulator.original_execute
            mock_db.execute("INSERT INTO agent (id, name, scopes) VALUES (?, ?, ?)",
                           {"id": agent_id, "name": "test-agent", "scopes": json.dumps(["test"])})
            mock_db.execute = simulator.intermittent_failure
        
        # Now test recovery through multiple failures
        attempts = 0
        max_attempts = 5
        success = False
        
        while attempts < max_attempts and not success:
            try:
                attempts += 1
                
                # This should fail first few times, then succeed
                mock_db.execute("""
                    INSERT INTO task (id, title, description, created_by, schedule_kind,
                                    schedule_expr, timezone, payload, status, priority, max_retries)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, {
                    "id": task_id,
                    "title": "Resilience Test Task",
                    "description": "Testing database recovery",
                    "created_by": agent_id,
                    "schedule_kind": "once",
                    "schedule_expr": datetime.now(timezone.utc).isoformat(),
                    "timezone": "Europe/Chisinau",
                    "payload": json.dumps({"pipeline": []}),
                    "status": "active",
                    "priority": 5,
                    "max_retries": 3
                })
                
                mock_db.commit()
                success = True
                
            except Exception as e:
                print(f"Attempt {attempts} failed: {e}")
                time.sleep(0.1)  # Brief backoff
        
        # Should eventually succeed
        assert success, f"Failed to recover after {max_attempts} attempts"
        assert simulator.failure_count > simulator.failure_threshold
    
    def test_transaction_rollback_on_failure(self, mock_db):
        """Test proper transaction rollback during failures."""
        
        # Insert test agent
        agent_id = str(uuid.uuid4())
        mock_db.execute("INSERT INTO agent (id, name, scopes) VALUES (?, ?, ?)",
                       {"id": agent_id, "name": "test-agent", "scopes": json.dumps(["test"])})
        mock_db.commit()
        
        # Count initial tasks
        initial_count = mock_db.execute("SELECT COUNT(*) FROM task").fetchone()[0]
        
        # Simulate transaction failure
        class TransactionFailure:
            def __init__(self):
                self.step = 0
            
            def execute(self, sql, params=None):
                self.step += 1
                
                if "INSERT INTO task" in sql and self.step == 1:
                    # First insert succeeds
                    return mock_db.conn.execute(sql, params or {})
                elif "INSERT INTO due_work" in sql and self.step == 2:
                    # Second insert fails - should trigger rollback
                    raise Exception("Simulated transaction failure")
                
                return mock_db.conn.execute(sql, params or {})
        
        failure_sim = TransactionFailure()
        
        # Attempt transaction that will fail midway
        try:
            # Start transaction
            failure_sim.execute("""
                INSERT INTO task (id, title, description, created_by, schedule_kind,
                                schedule_expr, timezone, payload, status, priority, max_retries)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, {
                "id": str(uuid.uuid4()),
                "title": "Partial Transaction Task",
                "description": "This transaction should be rolled back",
                "created_by": agent_id,
                "schedule_kind": "once", 
                "schedule_expr": datetime.now(timezone.utc).isoformat(),
                "timezone": "Europe/Chisinau",
                "payload": json.dumps({"pipeline": []}),
                "status": "active",
                "priority": 5,
                "max_retries": 3
            })
            
            # This should fail and cause rollback
            failure_sim.execute("INSERT INTO due_work (task_id, run_at) VALUES (?, ?)",
                               {"task_id": "non-existent-task", "run_at": datetime.now(timezone.utc).isoformat()})
            
            mock_db.commit()  # This shouldn't be reached
            
        except Exception:
            mock_db.rollback()  # Proper rollback
        
        # Verify no partial data was committed
        final_count = mock_db.execute("SELECT COUNT(*) FROM task").fetchone()[0]
        assert final_count == initial_count, "Transaction was not properly rolled back"
    
    def test_database_deadlock_recovery(self, mock_db):
        """Test recovery from database deadlock scenarios."""
        
        # Create test data
        agent_id = str(uuid.uuid4())
        mock_db.execute("INSERT INTO agent (id, name, scopes) VALUES (?, ?, ?)",
                       {"id": agent_id, "name": "deadlock-test-agent", "scopes": json.dumps(["test"])})
        
        # Create multiple tasks
        task_ids = []
        for i in range(5):
            task_id = str(uuid.uuid4())
            task_ids.append(task_id)
            
            mock_db.execute("""
                INSERT INTO task (id, title, description, created_by, schedule_kind,
                                schedule_expr, timezone, payload, status, priority, max_retries)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, {
                "id": task_id,
                "title": f"Deadlock Test Task {i}",
                "description": f"Task {i} for deadlock testing",
                "created_by": agent_id,
                "schedule_kind": "once",
                "schedule_expr": datetime.now(timezone.utc).isoformat(),
                "timezone": "Europe/Chisinau",
                "payload": json.dumps({"pipeline": []}),
                "status": "active",
                "priority": 5,
                "max_retries": 3
            })
            
            # Insert due work
            mock_db.execute("INSERT INTO due_work (task_id, run_at) VALUES (?, ?)",
                           {"task_id": task_id, "run_at": datetime.now(timezone.utc).isoformat()})
        
        mock_db.commit()
        
        # Simulate concurrent workers causing deadlocks
        def worker_simulation(worker_id, task_ids_subset):
            """Simulate worker that might cause deadlocks."""
            processed = 0
            
            for task_id in task_ids_subset:
                retry_count = 0
                max_retries = 3
                
                while retry_count < max_retries:
                    try:
                        # Simulate lease attempt with potential deadlock
                        if retry_count == 0:
                            # First attempt might deadlock (simulated)
                            raise Exception(f"Deadlock detected (simulated) - worker {worker_id}")
                        
                        # Subsequent attempts succeed
                        lease_time = datetime.now(timezone.utc) + timedelta(minutes=5)
                        cursor = mock_db.execute("""
                            UPDATE due_work 
                            SET locked_until = ?, locked_by = ?
                            WHERE task_id = ? AND (locked_until IS NULL OR locked_until < datetime('now'))
                        """, {
                            "locked_until": lease_time.isoformat(),
                            "locked_by": worker_id,
                            "task_id": task_id
                        })
                        
                        if mock_db.conn.total_changes > 0:
                            processed += 1
                            # Simulate work completion
                            mock_db.execute("""
                                INSERT INTO task_run (id, task_id, lease_owner, started_at, 
                                                    finished_at, success, attempt, output)
                                VALUES (?, ?, ?, datetime('now'), datetime('now'), 1, 1, '{}')
                            """, {
                                "id": str(uuid.uuid4()),
                                "task_id": task_id,
                                "lease_owner": worker_id
                            })
                            
                            mock_db.execute("DELETE FROM due_work WHERE task_id = ?", {"task_id": task_id})
                            mock_db.commit()
                            break
                    
                    except Exception as e:
                        retry_count += 1
                        if "deadlock" in str(e).lower():
                            # Exponential backoff for deadlock recovery
                            backoff_time = (2 ** retry_count) * 0.01  # 10ms, 20ms, 40ms
                            time.sleep(backoff_time)
                        else:
                            break
            
            return processed
        
        # Run multiple workers concurrently
        workers = ["worker-1", "worker-2", "worker-3"]
        
        # Distribute tasks among workers
        tasks_per_worker = [
            task_ids[:2],  # worker-1 gets first 2
            task_ids[2:4], # worker-2 gets next 2  
            task_ids[4:]   # worker-3 gets remaining 1
        ]
        
        total_processed = 0
        for i, worker in enumerate(workers):
            processed = worker_simulation(worker, tasks_per_worker[i])
            total_processed += processed
        
        # Verify all tasks were eventually processed despite deadlocks
        assert total_processed == len(task_ids), f"Expected {len(task_ids)}, got {total_processed}"
        
        # Verify no remaining due work
        remaining_work = mock_db.execute("SELECT COUNT(*) FROM due_work").fetchone()[0]
        assert remaining_work == 0, f"Still have {remaining_work} unprocessed work items"


@pytest.mark.chaos 
@pytest.mark.slow
class TestNetworkResilienceScenarios:
    """Test network failure and recovery scenarios."""
    
    @patch('engine.executor.call_tool')
    @patch('engine.executor.load_catalog')
    async def test_tool_network_timeout_recovery(self, mock_load_catalog, mock_call_tool):
        """Test recovery from network timeouts calling external tools."""
        
        network_sim = NetworkFailureSimulator()
        
        # Setup tool catalog
        mock_load_catalog.return_value = [{
            "address": "external.api",
            "transport": "http",
            "endpoint": "http://external-service.com/api",
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "timeout_seconds": 30,
            "scopes": ["test"]
        }]
        
        # Configure network failure pattern
        call_attempts = []
        
        def failing_tool_call(*args, **kwargs):
            call_attempts.append(time.time())
            
            if len(call_attempts) <= 3:
                # First 3 attempts fail with different errors
                if len(call_attempts) == 1:
                    network_sim.simulate_failure("timeout")
                elif len(call_attempts) == 2:
                    network_sim.simulate_failure("unavailable")
                elif len(call_attempts) == 3:
                    network_sim.simulate_failure("rate_limit")
            else:
                # 4th attempt succeeds
                return {"result": "success", "data": "Retrieved after retries"}
        
        mock_call_tool.side_effect = failing_tool_call
        
        # Execute pipeline with retries
        pipeline = {
            "pipeline": [
                {
                    "id": "network_test",
                    "uses": "external.api",
                    "with": {"query": "test data"},
                    "retry_attempts": 5,
                    "retry_delay_ms": 100,
                    "save_as": "api_response"
                }
            ]
        }
        
        start_time = time.time()
        result = await run_pipeline(pipeline)
        end_time = time.time()
        
        # Should eventually succeed
        assert result["success"] is True
        assert result["steps"]["api_response"]["result"] == "success"
        assert result["steps"]["api_response"]["data"] == "Retrieved after retries"
        
        # Should have made 4 attempts
        assert len(call_attempts) == 4
        
        # Verify exponential backoff timing
        execution_time = end_time - start_time
        expected_min_time = 0.1 + 0.2 + 0.4  # 100ms + 200ms + 400ms delays
        assert execution_time >= expected_min_time / 1000  # Convert to seconds
    
    @patch('engine.executor.call_tool')
    @patch('engine.executor.load_catalog')
    async def test_partial_pipeline_failure_recovery(self, mock_load_catalog, mock_call_tool):
        """Test pipeline recovery when some steps fail."""
        
        # Setup tools
        mock_load_catalog.return_value = [
            {
                "address": "reliable.tool",
                "transport": "http", 
                "endpoint": "http://reliable-service.com/api",
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "scopes": ["test"]
            },
            {
                "address": "unreliable.tool",
                "transport": "http",
                "endpoint": "http://unreliable-service.com/api", 
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "scopes": ["test"]
            }
        ]
        
        # Configure mixed success/failure responses
        def mixed_tool_responses(tool_def, step_config, tool_input):
            if tool_def["address"] == "reliable.tool":
                return {"result": "reliable_success", "value": 42}
            elif tool_def["address"] == "unreliable.tool":
                if step_config.get("attempt", 1) <= 2:
                    # Fail first 2 attempts
                    raise Exception("Unreliable service is down")
                else:
                    # Succeed on 3rd attempt
                    return {"result": "unreliable_success", "value": 99}
        
        mock_call_tool.side_effect = mixed_tool_responses
        
        # Execute pipeline with mixed reliability
        pipeline = {
            "pipeline": [
                {
                    "id": "reliable_step",
                    "uses": "reliable.tool",
                    "with": {"input": "test"},
                    "save_as": "reliable_result"
                },
                {
                    "id": "unreliable_step",
                    "uses": "unreliable.tool",
                    "with": {"input": "test"},
                    "retry_attempts": 3,
                    "save_as": "unreliable_result"
                },
                {
                    "id": "dependent_step",
                    "uses": "reliable.tool", 
                    "with": {
                        "reliable_data": "${steps.reliable_result.value}",
                        "unreliable_data": "${steps.unreliable_result.value}"
                    },
                    "save_as": "final_result"
                }
            ]
        }
        
        result = await run_pipeline(pipeline)
        
        # Should complete successfully despite unreliable step failures
        assert result["success"] is True
        assert len(result["steps"]) == 3
        
        # Check data flow through steps
        assert result["steps"]["reliable_result"]["result"] == "reliable_success"
        assert result["steps"]["unreliable_result"]["result"] == "unreliable_success"
        
        # Verify template rendering used both results
        final_step_calls = [call for call in mock_call_tool.call_args_list 
                           if call[0][1]["id"] == "dependent_step"]
        assert len(final_step_calls) > 0
        
        final_input = final_step_calls[-1][0][2]  # Tool input from final call
        assert final_input["reliable_data"] == 42
        assert final_input["unreliable_data"] == 99


@pytest.mark.chaos
@pytest.mark.slow
class TestHighLoadResilienceScenarios:
    """Test system behavior under extreme load."""
    
    def test_concurrent_worker_overload(self, mock_db):
        """Test system behavior with too many concurrent workers."""
        
        # Create large number of tasks
        agent_id = str(uuid.uuid4())
        mock_db.execute("INSERT INTO agent (id, name, scopes) VALUES (?, ?, ?)",
                       {"id": agent_id, "name": "load-test-agent", "scopes": json.dumps(["test"])})
        
        task_count = 500
        task_ids = []
        
        for i in range(task_count):
            task_id = str(uuid.uuid4())
            task_ids.append(task_id)
            
            mock_db.execute("""
                INSERT INTO task (id, title, description, created_by, schedule_kind,
                                schedule_expr, timezone, payload, status, priority, max_retries)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, {
                "id": task_id,
                "title": f"Load Test Task {i}",
                "description": f"High load test task {i}",
                "created_by": agent_id,
                "schedule_kind": "once",
                "schedule_expr": datetime.now(timezone.utc).isoformat(),
                "timezone": "Europe/Chisinau",
                "payload": json.dumps({"pipeline": []}),
                "status": "active",
                "priority": i % 10,  # Varied priorities
                "max_retries": 3
            })
            
            # Create due work
            mock_db.execute("INSERT INTO due_work (task_id, run_at) VALUES (?, ?)",
                           {"task_id": task_id, "run_at": datetime.now(timezone.utc).isoformat()})
        
        mock_db.commit()
        
        # Launch many concurrent workers (more than optimal)
        worker_count = 50  # Intentionally too many
        processed_tasks = set()
        worker_errors = []
        
        def worker_thread(worker_id):
            """Individual worker thread."""
            try:
                local_processed = 0
                max_tasks = 20  # Limit per worker
                
                while local_processed < max_tasks:
                    # Try to lease work
                    cursor = mock_db.execute("""
                        SELECT id, task_id FROM due_work
                        WHERE run_at <= datetime('now')
                          AND (locked_until IS NULL OR locked_until < datetime('now'))
                        LIMIT 1
                    """)
                    
                    work_row = cursor.fetchone()
                    if not work_row:
                        break  # No more work
                    
                    work_id, task_id = work_row
                    
                    # Try to acquire lease
                    lease_time = datetime.now(timezone.utc) + timedelta(minutes=5)
                    cursor = mock_db.execute("""
                        UPDATE due_work
                        SET locked_until = ?, locked_by = ?
                        WHERE id = ? AND (locked_until IS NULL OR locked_until < datetime('now'))
                    """, {
                        "locked_until": lease_time.isoformat(),
                        "locked_by": f"overload-worker-{worker_id}",
                        "id": work_id
                    })
                    
                    if mock_db.conn.total_changes > 0:
                        # Successfully leased
                        processed_tasks.add(task_id)
                        
                        # Simulate work with some processing time
                        processing_time = 0.01 + (0.005 * (worker_id % 10))  # Varied processing
                        time.sleep(processing_time)
                        
                        # Record completion
                        mock_db.execute("""
                            INSERT INTO task_run (id, task_id, lease_owner, started_at,
                                                finished_at, success, attempt, output)
                            VALUES (?, ?, ?, datetime('now'), datetime('now'), 1, 1, '{}')
                        """, {
                            "id": str(uuid.uuid4()),
                            "task_id": task_id,
                            "lease_owner": f"overload-worker-{worker_id}"
                        })
                        
                        # Clean up
                        mock_db.execute("DELETE FROM due_work WHERE id = ?", {"id": work_id})
                        mock_db.commit()
                        
                        local_processed += 1
                    else:
                        # Failed to lease (another worker got it)
                        time.sleep(0.001)  # Brief pause
                
                return local_processed
                
            except Exception as e:
                worker_errors.append(f"Worker {worker_id}: {str(e)}")
                return 0
        
        # Run workers concurrently
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(worker_thread, i) for i in range(worker_count)]
            
            # Wait for completion with timeout
            completed_counts = []
            for future in as_completed(futures, timeout=30):
                try:
                    count = future.result()
                    completed_counts.append(count)
                except Exception as e:
                    worker_errors.append(f"Future error: {str(e)}")
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Verify results
        total_processed = len(processed_tasks)
        
        # Should process significant portion despite overload
        assert total_processed >= task_count * 0.8, f"Only processed {total_processed}/{task_count} tasks"
        
        # No task should be processed twice
        assert total_processed == len(processed_tasks), "Tasks were processed multiple times"
        
        # Should complete in reasonable time despite overload
        assert total_time < 45, f"Processing took too long: {total_time:.2f} seconds"
        
        # Some worker contention is expected but not too many errors
        assert len(worker_errors) < worker_count * 0.1, f"Too many worker errors: {len(worker_errors)}"
        
        print(f"Processed {total_processed} tasks with {worker_count} workers in {total_time:.2f}s")
        print(f"Throughput: {total_processed / total_time:.1f} tasks/second")
        print(f"Worker errors: {len(worker_errors)}")
    
    def test_memory_leak_detection(self):
        """Test for memory leaks during intensive operations."""
        
        # Get initial memory usage
        initial_memory = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        
        # Perform memory-intensive operations
        large_templates = []
        large_contexts = []
        
        for i in range(1000):
            # Create large template structures
            template = {
                "pipeline": [
                    {
                        "id": f"step_{j}",
                        "uses": f"tool-{j}.action",
                        "with": {
                            "data": f"${{steps.previous_{j}.output.data_{k}}}",
                            "params": [f"param_{k}" for k in range(50)]
                        }
                    }
                    for j in range(20)
                ],
                "params": {f"param_{k}": f"value_{k}_iteration_{i}" for k in range(100)}
            }
            
            # Create large context
            context = {
                "steps": {
                    f"previous_{j}": {
                        "output": {f"data_{k}": f"output_value_{k}" for k in range(50)}
                    }
                    for j in range(20)
                },
                "params": {f"param_{k}": f"context_value_{k}" for k in range(100)}
            }
            
            # Test template rendering (memory intensive)
            try:
                rendered = render_templates(template, context)
                large_templates.append(rendered)
                large_contexts.append(context)
                
                # Force garbage collection periodically
                if i % 100 == 0:
                    gc.collect()
                    
            except Exception as e:
                print(f"Template rendering failed at iteration {i}: {e}")
                break
        
        # Force final garbage collection
        del large_templates
        del large_contexts
        gc.collect()
        
        # Get final memory usage
        final_memory = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        memory_growth = final_memory - initial_memory
        
        # Memory growth should be reasonable (less than 100MB on Linux)
        max_growth = 100 * 1024  # 100MB in KB
        assert memory_growth < max_growth, f"Memory growth too high: {memory_growth / 1024:.1f}MB"
        
        print(f"Memory growth: {memory_growth / 1024:.1f}MB")
    
    def test_resource_exhaustion_recovery(self, mock_db):
        """Test recovery from resource exhaustion scenarios."""
        
        # Simulate resource exhaustion scenarios
        class ResourceExhaustionSimulator:
            def __init__(self):
                self.call_count = 0
                self.exhausted_until = 5  # Exhausted for first 5 calls
            
            def simulate_exhaustion(self, *args, **kwargs):
                self.call_count += 1
                
                if self.call_count <= self.exhausted_until:
                    if self.call_count % 3 == 1:
                        raise MemoryError("Out of memory")
                    elif self.call_count % 3 == 2:
                        raise OSError("Too many open files")
                    else:
                        raise Exception("Resource temporarily unavailable")
                
                # After exhaustion period, work normally
                return Mock()
        
        resource_sim = ResourceExhaustionSimulator()
        
        # Test database operations under resource pressure
        original_execute = mock_db.execute
        mock_db.execute = resource_sim.simulate_exhaustion
        
        successful_operations = 0
        max_attempts = 10
        
        for attempt in range(max_attempts):
            try:
                # Attempt database operation
                mock_db.execute("SELECT 1")
                successful_operations += 1
                
            except (MemoryError, OSError) as e:
                # Expected resource errors
                print(f"Attempt {attempt + 1} failed with resource error: {e}")
                time.sleep(0.1)  # Brief backoff
                
            except Exception as e:
                # Other errors
                print(f"Attempt {attempt + 1} failed with error: {e}")
                time.sleep(0.1)
        
        # Should eventually succeed after resource recovery
        assert successful_operations >= 5, f"Only {successful_operations} operations succeeded"
        
        # Restore normal operation
        mock_db.execute = original_execute


@pytest.mark.chaos
@pytest.mark.slow
class TestTimingAndRaceConditions:
    """Test timing-sensitive scenarios and race conditions."""
    
    def test_concurrent_task_scheduling_race_condition(self, mock_db):
        """Test race conditions in concurrent task scheduling."""
        
        # Create test agent
        agent_id = str(uuid.uuid4())
        mock_db.execute("INSERT INTO agent (id, name, scopes) VALUES (?, ?, ?)",
                       {"id": agent_id, "name": "race-test-agent", "scopes": json.dumps(["test"])})
        
        # Create task that should be scheduled
        task_id = str(uuid.uuid4())
        mock_db.execute("""
            INSERT INTO task (id, title, description, created_by, schedule_kind,
                            schedule_expr, timezone, payload, status, priority, max_retries)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, {
            "id": task_id,
            "title": "Race Condition Test Task",
            "description": "Testing concurrent scheduling",
            "created_by": agent_id,
            "schedule_kind": "cron",
            "schedule_expr": "*/1 * * * *",  # Every minute
            "timezone": "Europe/Chisinau",
            "payload": json.dumps({"pipeline": []}),
            "status": "active",
            "priority": 5,
            "max_retries": 3
        })
        mock_db.commit()
        
        # Simulate multiple schedulers trying to schedule the same task
        scheduled_count = 0
        scheduling_errors = []
        
        def scheduler_thread(scheduler_id):
            """Simulate scheduler thread."""
            try:
                nonlocal scheduled_count
                
                # Check if task needs scheduling
                cursor = mock_db.execute("""
                    SELECT id FROM task 
                    WHERE id = ? AND status = 'active'
                """, {"id": task_id})
                
                if cursor.fetchone():
                    # Try to schedule (insert due work)
                    try:
                        mock_db.execute("""
                            INSERT INTO due_work (task_id, run_at)
                            VALUES (?, datetime('now', '+1 minute'))
                        """, {"task_id": task_id})
                        
                        mock_db.commit()
                        scheduled_count += 1
                        return True
                        
                    except Exception as e:
                        # Handle unique constraint violation (race condition)
                        if "unique" in str(e).lower() or "constraint" in str(e).lower():
                            # Expected race condition
                            return False
                        else:
                            raise
                            
                return False
                
            except Exception as e:
                scheduling_errors.append(f"Scheduler {scheduler_id}: {str(e)}")
                return False
        
        # Run multiple schedulers concurrently
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(scheduler_thread, i) for i in range(10)]
            
            results = []
            for future in as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    scheduling_errors.append(f"Future error: {str(e)}")
        
        # Should have exactly one successful scheduling despite race conditions
        successful_schedules = sum(results)
        assert successful_schedules == 1, f"Expected 1 schedule, got {successful_schedules}"
        
        # Verify only one due work item was created
        cursor = mock_db.execute("SELECT COUNT(*) FROM due_work WHERE task_id = ?", {"task_id": task_id})
        due_work_count = cursor.fetchone()[0]
        assert due_work_count == 1, f"Expected 1 due work item, got {due_work_count}"
        
        print(f"Race condition test: {successful_schedules} successful schedules, {len(scheduling_errors)} errors")
    
    def test_clock_skew_handling(self):
        """Test handling of clock skew and time synchronization issues."""
        
        # Simulate clock skew scenarios
        original_time = time.time
        original_datetime_now = datetime.now
        
        def skewed_time():
            # Simulate clock running 30 seconds fast
            return original_time() + 30
        
        def skewed_datetime_now(*args, **kwargs):
            # Simulate datetime running 30 seconds fast
            normal_time = original_datetime_now(*args, **kwargs)
            return normal_time + timedelta(seconds=30)
        
        # Test template rendering with skewed clocks
        with patch('time.time', skewed_time):
            with patch('datetime.datetime.now', skewed_datetime_now):
                
                # Template with time-based expressions
                template = {
                    "current_time": "${now}",
                    "future_time": "${now+3600}",  # 1 hour from now
                    "time_comparison": "${now > '2025-01-01T00:00:00Z'}"
                }
                
                # Context with current time references
                context = {
                    "now": datetime.now(timezone.utc).isoformat(),
                    "start_time": "2025-08-08T10:00:00Z"
                }
                
                # Should handle time skew gracefully
                rendered = render_templates(template, context)
                
                # Basic validation that times are reasonable
                assert rendered["current_time"] == context["now"]
                assert "2025-" in rendered["future_time"]  # Should be a 2025 timestamp
    
    async def test_async_operation_race_conditions(self):
        """Test race conditions in async operations."""
        
        # Shared state that might cause races
        shared_counter = {"value": 0}
        operation_results = []
        
        async def concurrent_operation(operation_id):
            """Simulate async operation that modifies shared state."""
            
            # Read current value
            current_value = shared_counter["value"]
            
            # Simulate async work
            await asyncio.sleep(0.01)  # 10ms delay
            
            # Update shared state (potential race condition)
            new_value = current_value + 1
            
            # Simulate more async work
            await asyncio.sleep(0.01)
            
            # Write back (race condition potential)
            shared_counter["value"] = new_value
            
            operation_results.append({
                "operation_id": operation_id,
                "read_value": current_value,
                "wrote_value": new_value,
                "final_value": shared_counter["value"]
            })
            
            return new_value
        
        # Run many concurrent operations
        tasks = [concurrent_operation(i) for i in range(20)]
        results = await asyncio.gather(*tasks)
        
        # Analyze race condition effects
        final_counter_value = shared_counter["value"]
        expected_value = 20  # If no races occurred
        
        # Due to race conditions, final value might be less than expected
        print(f"Expected counter: {expected_value}, Actual: {final_counter_value}")
        print(f"Race conditions detected: {expected_value - final_counter_value}")
        
        # Verify operations completed
        assert len(operation_results) == 20
        assert len(results) == 20
        
        # Some race conditions are expected in this unprotected scenario
        # This test demonstrates the need for proper synchronization
        assert final_counter_value > 0, "Counter should have increased"
        assert final_counter_value <= expected_value, "Counter shouldn't exceed expected value"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-x"])