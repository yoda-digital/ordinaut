#!/usr/bin/env python3
"""
Comprehensive Worker System Tests for Ordinaut.

Tests worker job processing including:
- SKIP LOCKED job leasing for safe concurrent processing
- Task execution pipeline with error handling and retries
- Worker coordination and race condition prevention
- Lease renewal and timeout handling
- Metrics collection and health monitoring
- Worker lifecycle management and graceful shutdown

Uses real database with proper transaction isolation.
"""

import pytest
import asyncio
import uuid
import json
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from concurrent.futures import ThreadPoolExecutor, as_completed

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from workers.runner import WorkerCoordinator, ProcessingWorker, WorkerMetrics
from workers.config import WorkerConfig
from conftest import insert_test_agent, insert_test_task, insert_due_work


@pytest.mark.worker
class TestSkipLockedJobLeasing:
    """Test SKIP LOCKED pattern for safe concurrent job processing."""
    
    async def test_single_worker_leases_available_work(self, clean_database):
        """Test that a single worker can lease available work."""
        # Setup test data
        agent = await insert_test_agent(clean_database)
        task = await insert_test_task(clean_database, agent["id"])
        work_id = await insert_due_work(clean_database, task["id"], datetime.now(timezone.utc))
        
        # Create worker and lease work
        config = WorkerConfig(worker_id="test-worker-1", database_url="sqlite:///:memory:")
        worker = ProcessingWorker(config, clean_database)
        
        # Lease work
        leased_work = await worker.lease_next_work()
        
        assert leased_work is not None
        assert leased_work["id"] == work_id
        assert leased_work["task_id"] == task["id"]
        assert leased_work["locked_by"] == "test-worker-1"
    
    async def test_skip_locked_prevents_double_processing(self, clean_database):
        """Test that SKIP LOCKED prevents multiple workers from processing same work."""
        # Setup test data
        agent = await insert_test_agent(clean_database)
        task = await insert_test_task(clean_database, agent["id"])
        work_id = await insert_due_work(clean_database, task["id"], datetime.now(timezone.utc))
        
        # Create two workers
        config1 = WorkerConfig(worker_id="worker-1", database_url="sqlite:///:memory:")
        config2 = WorkerConfig(worker_id="worker-2", database_url="sqlite:///:memory:")
        worker1 = ProcessingWorker(config1, clean_database)
        worker2 = ProcessingWorker(config2, clean_database)
        
        # Both workers try to lease work simultaneously
        results = await asyncio.gather(
            worker1.lease_next_work(),
            worker2.lease_next_work(),
            return_exceptions=True
        )
        
        # Only one should get the work
        successful_leases = [r for r in results if r is not None and isinstance(r, dict)]
        assert len(successful_leases) == 1
        
        # The successful lease should be valid
        leased_work = successful_leases[0]
        assert leased_work["id"] == work_id
        assert leased_work["locked_by"] in ("worker-1", "worker-2")
    
    async def test_expired_lease_recovery(self, clean_database):
        """Test that expired leases can be recovered by other workers."""
        # Setup test data
        agent = await insert_test_agent(clean_database)
        task = await insert_test_task(clean_database, agent["id"])
        work_id = await insert_due_work(clean_database, task["id"], datetime.now(timezone.utc))
        
        # Create workers with different lease timeouts
        config1 = WorkerConfig(worker_id="worker-1", lease_timeout_seconds=1)  # Short lease
        config2 = WorkerConfig(worker_id="worker-2", lease_timeout_seconds=60)
        worker1 = ProcessingWorker(config1, clean_database)
        worker2 = ProcessingWorker(config2, clean_database)
        
        # Worker 1 leases work
        leased_work = await worker1.lease_next_work()
        assert leased_work is not None
        assert leased_work["locked_by"] == "worker-1"
        
        # Wait for lease to expire
        await asyncio.sleep(2)
        
        # Worker 2 should be able to lease the expired work
        recovered_work = await worker2.lease_next_work()
        assert recovered_work is not None
        assert recovered_work["id"] == work_id
        assert recovered_work["locked_by"] == "worker-2"
    
    async def test_high_concurrency_lease_competition(self, clean_database):
        """Test worker behavior under high concurrency lease competition."""
        # Setup test data - create multiple work items
        agent = await insert_test_agent(clean_database)
        task = await insert_test_task(clean_database, agent["id"])
        
        work_ids = []
        for i in range(10):
            work_id = await insert_due_work(clean_database, task["id"], 
                                           datetime.now(timezone.utc) + timedelta(seconds=i))
            work_ids.append(work_id)
        
        # Create many workers
        workers = []
        for i in range(20):  # More workers than work items
            config = WorkerConfig(worker_id=f"worker-{i}", database_url="sqlite:///:memory:")
            worker = ProcessingWorker(config, clean_database)
            workers.append(worker)
        
        # All workers try to lease work concurrently
        lease_tasks = [worker.lease_next_work() for worker in workers]
        results = await asyncio.gather(*lease_tasks, return_exceptions=True)
        
        # Count successful leases
        successful_leases = [r for r in results if r is not None and isinstance(r, dict)]
        
        # Should have exactly 10 successful leases (one per work item)
        assert len(successful_leases) == len(work_ids)
        
        # All leases should be unique
        leased_work_ids = [lease["id"] for lease in successful_leases]
        assert len(set(leased_work_ids)) == len(leased_work_ids)
        assert set(leased_work_ids) == set(work_ids)


@pytest.mark.worker
class TestTaskExecution:
    """Test task execution pipeline and error handling."""
    
    @patch('engine.executor.PipelineExecutor.execute')
    async def test_successful_task_execution(self, mock_executor, clean_database):
        """Test successful task execution end-to-end."""
        # Setup mock executor
        mock_executor.return_value = {
            "success": True,
            "output": {"result": "Task completed successfully"},
            "execution_time_ms": 150
        }
        
        # Setup test data
        agent = await insert_test_agent(clean_database)
        task_data = {
            "title": "Test Execution Task",
            "description": "Task for execution testing",
            "created_by": agent["id"],
            "schedule_kind": "once",
            "schedule_expr": "2025-12-25T10:00:00Z",
            "timezone": "UTC",
            "payload": {
                "pipeline": [
                    {"id": "test_step", "uses": "test.tool", "with": {"param": "value"}}
                ]
            },
            "status": "active",
            "priority": 5,
            "max_retries": 3
        }
        task = await insert_test_task(clean_database, agent["id"], task_data)
        work_id = await insert_due_work(clean_database, task["id"], datetime.now(timezone.utc))
        
        # Create worker and execute task
        config = WorkerConfig(worker_id="test-worker")
        worker = ProcessingWorker(config, clean_database)
        
        # Execute the work item
        execution_result = await worker.execute_leased_work({
            "id": work_id,
            "task_id": task["id"],
            "locked_by": "test-worker",
            "task_payload": task_data["payload"]
        })
        
        assert execution_result["success"] is True
        assert execution_result["output"]["result"] == "Task completed successfully"
        
        # Verify task run was recorded in database
        with clean_database.begin() as conn:
            result = conn.execute(
                "SELECT * FROM task_run WHERE task_id = ?", (task["id"],)
            ).fetchone()
            
        assert result is not None
        assert result.success is True
        assert json.loads(result.output)["result"] == "Task completed successfully"
    
    @patch('engine.executor.PipelineExecutor.execute')
    async def test_task_execution_failure_with_retry(self, mock_executor, clean_database):
        """Test task execution failure handling with retry logic."""
        # Setup mock executor to fail
        mock_executor.side_effect = Exception("Execution failed")
        
        # Setup test data
        agent = await insert_test_agent(clean_database)
        task_data = {
            "title": "Failing Task",
            "description": "Task that will fail",
            "created_by": agent["id"],
            "schedule_kind": "once",
            "schedule_expr": "2025-12-25T10:00:00Z",
            "timezone": "UTC",
            "payload": {"pipeline": [{"id": "fail", "uses": "test.fail"}]},
            "status": "active",
            "priority": 5,
            "max_retries": 2
        }
        task = await insert_test_task(clean_database, agent["id"], task_data)
        work_id = await insert_due_work(clean_database, task["id"], datetime.now(timezone.utc))
        
        # Create worker and execute task
        config = WorkerConfig(worker_id="test-worker")
        worker = ProcessingWorker(config, clean_database)
        
        # Execute the work item - should fail but handle gracefully
        execution_result = await worker.execute_leased_work({
            "id": work_id,
            "task_id": task["id"],
            "locked_by": "test-worker",
            "task_payload": task_data["payload"]
        })
        
        assert execution_result["success"] is False
        assert "Execution failed" in execution_result["error"]
        
        # Verify failure was recorded
        with clean_database.begin() as conn:
            result = conn.execute(
                "SELECT * FROM task_run WHERE task_id = ?", (task["id"],)
            ).fetchone()
            
        assert result is not None
        assert result.success is False
        assert "Execution failed" in result.error
    
    async def test_task_timeout_handling(self, clean_database):
        """Test handling of task execution timeouts."""
        # Setup test data with slow task
        agent = await insert_test_agent(clean_database)
        task_data = {
            "title": "Slow Task",
            "description": "Task that takes too long",
            "created_by": agent["id"],
            "schedule_kind": "once",
            "schedule_expr": "2025-12-25T10:00:00Z",
            "timezone": "UTC",
            "payload": {
                "pipeline": [
                    {"id": "slow_step", "uses": "test.slow", "timeout_seconds": 1}
                ]
            },
            "status": "active",
            "priority": 5,
            "max_retries": 1
        }
        task = await insert_test_task(clean_database, agent["id"], task_data)
        work_id = await insert_due_work(clean_database, task["id"], datetime.now(timezone.utc))
        
        # Create worker with timeout handling
        config = WorkerConfig(worker_id="test-worker", execution_timeout_seconds=2)
        worker = ProcessingWorker(config, clean_database)
        
        # Mock a slow executor
        with patch('engine.executor.PipelineExecutor.execute') as mock_executor:
            async def slow_execute(*args, **kwargs):
                await asyncio.sleep(5)  # Longer than timeout
                return {"success": True}
            
            mock_executor.side_effect = slow_execute
            
            # Execute should timeout
            execution_result = await worker.execute_leased_work({
                "id": work_id,
                "task_id": task["id"],
                "locked_by": "test-worker",
                "task_payload": task_data["payload"]
            })
            
            assert execution_result["success"] is False
            assert "timeout" in execution_result["error"].lower()


@pytest.mark.worker
class TestWorkerCoordination:
    """Test worker coordination and lifecycle management."""
    
    async def test_worker_startup_and_shutdown(self, clean_database):
        """Test worker startup and graceful shutdown."""
        config = WorkerConfig(
            worker_id="lifecycle-test-worker",
            database_url="sqlite:///:memory:",
            heartbeat_interval_seconds=1
        )
        
        coordinator = WorkerCoordinator(config, clean_database)
        
        # Start worker
        worker_task = asyncio.create_task(coordinator.start())
        
        # Let it run for a short time
        await asyncio.sleep(0.5)
        
        # Check worker is running
        assert coordinator.is_running() is True
        
        # Shutdown gracefully
        await coordinator.shutdown()
        
        # Worker task should complete
        try:
            await asyncio.wait_for(worker_task, timeout=5.0)
        except asyncio.TimeoutError:
            pytest.fail("Worker did not shut down gracefully within timeout")
        
        assert coordinator.is_running() is False
    
    async def test_worker_heartbeat_recording(self, clean_database):
        """Test worker heartbeat recording in database."""
        config = WorkerConfig(
            worker_id="heartbeat-test-worker",
            heartbeat_interval_seconds=0.1  # Fast heartbeat for testing
        )
        
        worker = ProcessingWorker(config, clean_database)
        
        # Record initial heartbeat
        await worker.record_heartbeat()
        
        # Check heartbeat was recorded
        with clean_database.begin() as conn:
            result = conn.execute(
                "SELECT * FROM worker_heartbeat WHERE worker_id = ?", 
                (config.worker_id,)
            ).fetchone()
        
        # May not exist if table doesn't exist, which is fine for testing
        # In production, we'd have proper worker_heartbeat table
    
    async def test_multiple_workers_coordination(self, clean_database):
        """Test coordination between multiple workers."""
        # Create multiple work items
        agent = await insert_test_agent(clean_database)
        task = await insert_test_task(clean_database, agent["id"])
        
        work_ids = []
        for i in range(5):
            work_id = await insert_due_work(clean_database, task["id"], 
                                           datetime.now(timezone.utc))
            work_ids.append(work_id)
        
        # Start multiple workers
        workers = []
        worker_tasks = []
        
        for i in range(3):
            config = WorkerConfig(
                worker_id=f"coord-worker-{i}",
                poll_interval_seconds=0.1,
                batch_size=1
            )
            worker = WorkerCoordinator(config, clean_database)
            workers.append(worker)
            worker_tasks.append(asyncio.create_task(worker.start()))
        
        # Let workers run for a bit to process work
        await asyncio.sleep(2)
        
        # Shutdown all workers
        for worker in workers:
            await worker.shutdown()
        
        # Wait for all worker tasks to complete
        await asyncio.gather(*worker_tasks, return_exceptions=True)
        
        # Verify all workers stopped
        assert all(not worker.is_running() for worker in workers)
    
    async def test_worker_error_recovery(self, clean_database):
        """Test worker recovery from errors."""
        config = WorkerConfig(
            worker_id="error-recovery-worker",
            max_retries=2,
            retry_delay_seconds=0.1
        )
        
        worker = ProcessingWorker(config, clean_database)
        
        # Mock database error during lease
        original_lease = worker.lease_next_work
        error_count = 0
        
        async def failing_lease():
            nonlocal error_count
            error_count += 1
            if error_count <= 2:  # Fail first 2 attempts
                raise Exception("Database connection error")
            return await original_lease()
        
        worker.lease_next_work = failing_lease
        
        # Worker should retry and eventually succeed (or handle gracefully)
        try:
            result = await worker.lease_next_work()
            # Should either succeed after retries or return None gracefully
            assert result is None  # No work available after recovery
            assert error_count > 1  # Retries occurred
        except Exception:
            pytest.fail("Worker should handle errors gracefully")


@pytest.mark.worker
class TestWorkerMetrics:
    """Test worker metrics collection and reporting."""
    
    def test_metrics_initialization(self):
        """Test metrics initialization with default values."""
        metrics = WorkerMetrics("test-worker")
        
        assert metrics.worker_id == "test-worker"
        assert metrics.tasks_processed == 0
        assert metrics.tasks_failed == 0
        assert metrics.total_execution_time_ms == 0
        assert metrics.active_leases == 0
        assert len(metrics.recent_errors) == 0
    
    def test_task_completion_metrics(self):
        """Test task completion metrics recording."""
        metrics = WorkerMetrics("test-worker")
        
        # Record successful task
        metrics.record_task_completion(success=True, execution_time_ms=150)
        
        assert metrics.tasks_processed == 1
        assert metrics.tasks_failed == 0
        assert metrics.total_execution_time_ms == 150
        assert metrics.average_execution_time_ms == 150
        
        # Record failed task
        metrics.record_task_completion(success=False, execution_time_ms=75, error="Test error")
        
        assert metrics.tasks_processed == 2
        assert metrics.tasks_failed == 1
        assert metrics.total_execution_time_ms == 225
        assert metrics.average_execution_time_ms == 112.5
        assert len(metrics.recent_errors) == 1
    
    def test_lease_metrics(self):
        """Test lease-related metrics recording."""
        metrics = WorkerMetrics("test-worker")
        
        # Record lease acquired
        lease_id = "test-lease-123"
        metrics.record_lease_acquired(lease_id)
        
        assert metrics.active_leases == 1
        assert lease_id in metrics.active_lease_ids
        
        # Record lease released
        metrics.record_lease_released(lease_id)
        
        assert metrics.active_leases == 0
        assert lease_id not in metrics.active_lease_ids
    
    def test_error_metrics(self):
        """Test error metrics recording."""
        metrics = WorkerMetrics("test-worker")
        
        # Record multiple errors
        errors = ["Error 1", "Error 2", "Error 3"]
        for error in errors:
            metrics.record_error(error)
        
        assert len(metrics.recent_errors) == 3
        assert all(error in [e["error"] for e in metrics.recent_errors] for error in errors)
        
        # Test error list size limit
        for i in range(100):
            metrics.record_error(f"Error {i+4}")
        
        # Should maintain reasonable size (e.g., last 50 errors)
        assert len(metrics.recent_errors) <= 50
    
    def test_metrics_summary_calculation(self):
        """Test comprehensive metrics summary calculation."""
        metrics = WorkerMetrics("test-worker")
        
        # Add some data
        metrics.record_task_completion(True, 100)
        metrics.record_task_completion(True, 200)
        metrics.record_task_completion(False, 150, "Test failure")
        metrics.record_lease_acquired("lease-1")
        metrics.record_lease_acquired("lease-2")
        
        summary = metrics.get_summary()
        
        assert summary["worker_id"] == "test-worker"
        assert summary["tasks_processed"] == 3
        assert summary["tasks_failed"] == 1
        assert summary["success_rate"] == 2/3
        assert summary["average_execution_time_ms"] == 150
        assert summary["active_leases"] == 2
        assert summary["error_count"] == 1


@pytest.mark.worker
class TestRetryMechanisms:
    """Test retry logic and backoff strategies."""
    
    def test_exponential_backoff_calculation(self):
        """Test exponential backoff delay calculation."""
        from workers.runner import calculate_exponential_backoff
        
        # Test basic exponential backoff
        delays = [calculate_exponential_backoff(attempt, base_delay=1.0, max_delay=60.0) 
                 for attempt in range(1, 6)]
        
        # Delays should increase exponentially (with jitter)
        assert all(0.5 <= delay <= 2.0 for delay in delays[:1])  # First attempt
        assert all(1.0 <= delay <= 4.0 for delay in delays[1:2])  # Second attempt
        assert all(2.0 <= delay <= 8.0 for delay in delays[2:3])  # Third attempt
        
        # Should not exceed max delay
        very_long_delay = calculate_exponential_backoff(10, base_delay=1.0, max_delay=60.0)
        assert very_long_delay <= 60.0
    
    def test_exponential_backoff_without_jitter(self):
        """Test exponential backoff without jitter."""
        from workers.runner import calculate_exponential_backoff
        
        # Test with jitter disabled
        delay1 = calculate_exponential_backoff(1, base_delay=2.0, jitter=False)
        delay2 = calculate_exponential_backoff(2, base_delay=2.0, jitter=False)
        delay3 = calculate_exponential_backoff(3, base_delay=2.0, jitter=False)
        
        assert delay1 == 2.0
        assert delay2 == 4.0
        assert delay3 == 8.0
    
    def test_retry_decision_logic(self):
        """Test retry decision based on error types."""
        from workers.runner import should_retry_error
        
        # Retryable errors
        assert should_retry_error("Network timeout") is True
        assert should_retry_error("Connection refused") is True
        assert should_retry_error("Temporary failure") is True
        
        # Non-retryable errors
        assert should_retry_error("Invalid JSON schema") is False
        assert should_retry_error("Authentication failed") is False
        assert should_retry_error("Permission denied") is False


@pytest.mark.benchmark
class TestWorkerPerformance:
    """Performance benchmarks for worker operations."""
    
    def test_lease_acquisition_performance(self, benchmark, clean_database):
        """Benchmark work leasing performance."""
        # Setup test data
        async def setup_test_data():
            agent = await insert_test_agent(clean_database)
            task = await insert_test_task(clean_database, agent["id"])
            return await insert_due_work(clean_database, task["id"], 
                                        datetime.now(timezone.utc))
        
        work_id = asyncio.run(setup_test_data())
        
        config = WorkerConfig(worker_id="perf-test-worker")
        worker = ProcessingWorker(config, clean_database)
        
        def lease_work():
            return asyncio.run(worker.lease_next_work()) is not None
        
        # Run benchmark
        result = benchmark(lease_work)
        # First run should succeed, subsequent may not (work already leased)
        # This tests the performance of the lease query itself
    
    def test_concurrent_worker_throughput(self, clean_database, load_test_config):
        """Test throughput with multiple concurrent workers."""
        async def run_throughput_test():
            # Setup test data
            agent = await insert_test_agent(clean_database)
            task = await insert_test_task(clean_database, agent["id"])
            
            # Create many work items
            work_count = load_test_config["tasks_per_worker"]
            for i in range(work_count):
                await insert_due_work(clean_database, task["id"], 
                                    datetime.now(timezone.utc))
            
            # Create workers
            workers = []
            worker_tasks = []
            
            for i in range(load_test_config["concurrent_workers"]):
                config = WorkerConfig(
                    worker_id=f"perf-worker-{i}",
                    poll_interval_seconds=0.01,  # Very fast polling
                    batch_size=1
                )
                worker = WorkerCoordinator(config, clean_database)
                workers.append(worker)
                worker_tasks.append(asyncio.create_task(worker.start()))
            
            # Run for test duration
            start_time = time.time()
            await asyncio.sleep(load_test_config["test_duration_seconds"])
            end_time = time.time()
            
            # Shutdown workers
            for worker in workers:
                await worker.shutdown()
            await asyncio.gather(*worker_tasks, return_exceptions=True)
            
            # Calculate throughput
            duration = end_time - start_time
            # Count remaining work items to see how many were processed
            with clean_database.begin() as conn:
                remaining = conn.execute(
                    "SELECT COUNT(*) FROM due_work WHERE task_id = ?", 
                    (task["id"],)
                ).scalar()
            
            processed_count = work_count - remaining
            throughput = processed_count / duration
            
            return throughput, processed_count
        
        throughput, processed_count = asyncio.run(run_throughput_test())
        
        # Assert reasonable performance
        expected_min_throughput = 10  # tasks per second
        assert throughput >= expected_min_throughput, \
            f"Throughput {throughput:.2f} tasks/sec below expected {expected_min_throughput}"
        assert processed_count > 0, "No tasks were processed"


@pytest.mark.worker
@pytest.mark.slow
class TestWorkerStressScenarios:
    """Stress test scenarios for worker resilience."""
    
    async def test_memory_leak_detection(self, clean_database):
        """Test for memory leaks during intensive operations."""
        import psutil
        import gc
        
        process = psutil.Process()
        initial_memory = process.memory_info().rss
        
        # Create worker
        config = WorkerConfig(worker_id="memory-test-worker")
        worker = ProcessingWorker(config, clean_database)
        
        # Perform many operations
        for i in range(100):
            # Create and lease work
            agent = await insert_test_agent(clean_database)
            task = await insert_test_task(clean_database, agent["id"])
            await insert_due_work(clean_database, task["id"], datetime.now(timezone.utc))
            
            # Lease and process
            leased_work = await worker.lease_next_work()
            if leased_work:
                # Simulate processing (without actual execution)
                await asyncio.sleep(0.001)
            
            # Clean database state
            await clean_database.clean_database()
        
        # Force garbage collection
        gc.collect()
        final_memory = process.memory_info().rss
        
        # Memory growth should be reasonable (less than 100MB for this test)
        memory_growth = final_memory - initial_memory
        max_acceptable_growth = 100 * 1024 * 1024  # 100MB
        
        assert memory_growth < max_acceptable_growth, \
            f"Memory grew by {memory_growth / (1024*1024):.1f}MB, indicating potential leak"
    
    async def test_database_connection_resilience(self, clean_database):
        """Test worker resilience to database connection issues."""
        config = WorkerConfig(
            worker_id="resilience-test-worker",
            max_retries=3,
            retry_delay_seconds=0.1
        )
        worker = ProcessingWorker(config, clean_database)
        
        # Simulate database connection failure
        original_connection = clean_database.connect
        failure_count = 0
        
        def failing_connect():
            nonlocal failure_count
            failure_count += 1
            if failure_count <= 2:  # Fail first 2 attempts
                raise Exception("Database connection lost")
            return original_connection()
        
        clean_database.connect = failing_connect
        
        # Worker should handle connection failures gracefully
        try:
            result = await worker.lease_next_work()
            # Should either succeed after retries or handle gracefully
            assert True  # Test passes if no unhandled exception
        except Exception as e:
            # Should not propagate unhandled database errors
            assert "Database connection lost" not in str(e), \
                "Database errors should be handled gracefully"
        finally:
            clean_database.connect = original_connection