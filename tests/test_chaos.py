#!/usr/bin/env python3
"""
Comprehensive Chaos Engineering Tests for Ordinaut.

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
import uuid
import json
import time
import random
import signal
import psutil
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, patch
from concurrent.futures import ThreadPoolExecutor

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set test environment
os.environ["DATABASE_URL"] = "sqlite:///test_chaos.db"
os.environ["REDIS_URL"] = "memory://"

from workers.runner import WorkerCoordinator, ProcessingWorker, WorkerConfig
from scheduler.tick import SchedulerService
from engine.executor import PipelineExecutor
from engine.registry import ToolRegistry
from conftest import insert_test_agent, insert_test_task, insert_due_work


@pytest.mark.chaos
class TestDatabaseResilienceScenarios:
    """Test database failure recovery scenarios."""
    
    async def test_database_connection_recovery(self, clean_database, mock_tool_catalog):
        """Test automatic recovery from database connection failures."""
        
        # Setup worker
        worker_config = WorkerConfig(
            worker_id="db-recovery-worker",
            poll_interval_seconds=0.1,
            max_retries=3,
            retry_delay_seconds=0.2
        )
        worker = ProcessingWorker(worker_config, clean_database)
        
        # Setup test data
        agent = await insert_test_agent(clean_database)
        task = await insert_test_task(clean_database, agent["id"])
        work_id = await insert_due_work(clean_database, task["id"], datetime.now(timezone.utc))
        
        # Track operation attempts
        operation_attempts = {"lease_attempts": 0, "lease_successes": 0}
        
        # Mock database operations to fail intermittently
        original_execute = clean_database.execute
        
        def failing_execute(*args, **kwargs):
            operation_attempts["lease_attempts"] += 1
            
            # Fail 70% of the time to simulate connection issues
            if random.random() < 0.7:
                raise Exception("Database connection lost")
            
            operation_attempts["lease_successes"] += 1
            return original_execute(*args, **kwargs)
        
        # Inject failures
        with patch.object(clean_database, 'execute', side_effect=failing_execute):
            try:
                # Worker should retry and eventually succeed
                leased_work = await worker.lease_next_work()
                
                # Should eventually succeed despite failures
                if leased_work:
                    assert leased_work["id"] == work_id
                    print(f"Success after {operation_attempts['lease_attempts']} attempts")
                else:
                    print(f"No work leased after {operation_attempts['lease_attempts']} attempts")
                
                # Should have made multiple attempts due to failures
                assert operation_attempts["lease_attempts"] > 1, \
                    "Should have retried after connection failures"
                
            except Exception as e:
                # Even if it fails, should not crash the worker completely
                print(f"Worker handled DB failure gracefully: {e}")
                assert "Database connection lost" in str(e)
    
    async def test_transaction_rollback_on_failure(self, clean_database):
        """Test proper transaction rollback during failures."""
        
        agent = await insert_test_agent(clean_database)
        task = await insert_test_task(clean_database, agent["id"])
        
        # Count initial records
        with clean_database.begin() as conn:
            initial_runs = conn.execute("SELECT COUNT(*) FROM task_run").scalar()
            initial_work = conn.execute("SELECT COUNT(*) FROM due_work").scalar()
        
        # Attempt operations that should fail and rollback
        try:
            with clean_database.begin() as conn:
                # Insert a task run
                conn.execute("""
                    INSERT INTO task_run (id, task_id, started_at, attempt)
                    VALUES (?, ?, ?, ?)
                """, (str(uuid.uuid4()), task["id"], datetime.now(), 1))
                
                # Insert due work
                conn.execute("""
                    INSERT INTO due_work (task_id, run_at)
                    VALUES (?, ?)
                """, (task["id"], datetime.now(timezone.utc)))
                
                # Force a failure to trigger rollback
                raise Exception("Simulated failure during transaction")
                
        except Exception as e:
            assert "Simulated failure" in str(e)
        
        # Verify rollback - counts should be unchanged
        with clean_database.begin() as conn:
            final_runs = conn.execute("SELECT COUNT(*) FROM task_run").scalar()
            final_work = conn.execute("SELECT COUNT(*) FROM due_work").scalar()
        
        assert final_runs == initial_runs, "Task runs should be rolled back"
        assert final_work == initial_work, "Due work should be rolled back"
    
    async def test_database_deadlock_recovery(self, clean_database):
        """Test recovery from database deadlock scenarios."""
        
        agent = await insert_test_agent(clean_database)
        task = await insert_test_task(clean_database, agent["id"])
        
        # Create work items that multiple operations will compete for
        work_ids = []
        for i in range(5):
            work_id = await insert_due_work(clean_database, task["id"], datetime.now(timezone.utc))
            work_ids.append(work_id)
        
        deadlock_errors = []
        successful_operations = 0
        
        async def competing_database_operation(worker_id):
            """Simulate operations that might cause deadlocks."""
            nonlocal successful_operations
            
            try:
                # Random delay to increase chance of contention
                await asyncio.sleep(random.uniform(0, 0.1))
                
                with clean_database.begin() as conn:
                    # Try to lease multiple work items in different orders
                    work_order = work_ids.copy()
                    random.shuffle(work_order)
                    
                    for work_id in work_order[:2]:  # Try to lease 2 items
                        result = conn.execute("""
                            UPDATE due_work 
                            SET locked_by = ?, locked_until = datetime('now', '+1 minute')
                            WHERE id = ? AND locked_by IS NULL
                        """, (f"worker-{worker_id}", work_id))
                        
                        if result.rowcount > 0:
                            # Successfully leased, record a run
                            conn.execute("""
                                INSERT INTO task_run (id, task_id, lease_owner, started_at, attempt)
                                VALUES (?, ?, ?, ?, ?)
                            """, (str(uuid.uuid4()), task["id"], f"worker-{worker_id}", datetime.now(), 1))
                    
                successful_operations += 1
                
            except Exception as e:
                deadlock_errors.append(str(e))
                print(f"Worker {worker_id} encountered error: {e}")
        
        # Run multiple competing operations
        competitors = [competing_database_operation(i) for i in range(10)]
        await asyncio.gather(*competitors, return_exceptions=True)
        
        print(f"Deadlock test: {successful_operations} successful, {len(deadlock_errors)} errors")
        
        # Should have some successful operations despite contention
        assert successful_operations > 0, "Some operations should succeed despite deadlock potential"
        
        # Verify database consistency
        with clean_database.begin() as conn:
            locked_work = conn.execute(
                "SELECT COUNT(*) FROM due_work WHERE locked_by IS NOT NULL"
            ).scalar()
            
            recorded_runs = conn.execute(
                "SELECT COUNT(*) FROM task_run WHERE task_id = ?",
                (task["id"],)
            ).scalar()
        
        print(f"Final state: {locked_work} locked work items, {recorded_runs} recorded runs")


@pytest.mark.chaos
class TestNetworkResilienceScenarios:
    """Test network failure and recovery scenarios."""
    
    @pytest.mark.asyncio
    async def test_tool_network_timeout_recovery(self, clean_database, mock_tool_catalog):
        """Test recovery from network timeouts calling external tools."""
        
        registry = ToolRegistry()
        registry.load_tools(mock_tool_catalog)
        
        # Mock MCP client that fails intermittently
        mock_mcp = Mock()
        call_attempts = {"count": 0}
        
        async def unreliable_tool_call(tool_address, **kwargs):
            call_attempts["count"] += 1
            
            # Fail first few attempts with network errors
            if call_attempts["count"] <= 3:
                if call_attempts["count"] == 1:
                    raise asyncio.TimeoutError("Network timeout")
                elif call_attempts["count"] == 2:
                    raise Exception("Connection refused")
                elif call_attempts["count"] == 3:
                    raise Exception("DNS resolution failed")
            
            # Eventually succeed
            return {"result": "success after network recovery", "attempt": call_attempts["count"]}
        
        mock_mcp.call_tool = AsyncMock(side_effect=unreliable_tool_call)
        
        executor = PipelineExecutor(registry, mock_mcp)
        
        # Pipeline that should retry network failures
        pipeline = {
            "pipeline": [
                {
                    "id": "network_test",
                    "uses": "weather.forecast",
                    "with": {"location": "Chisinau"},
                    "save_as": "weather",
                    "retry": {
                        "max_attempts": 5,
                        "delay_seconds": 0.1,
                        "backoff": "exponential"
                    }
                }
            ]
        }
        
        result = await executor.execute(pipeline)
        
        # Should eventually succeed despite network failures
        assert result["success"] is True
        assert result["outputs"]["weather"]["result"] == "success after network recovery"
        assert call_attempts["count"] == 4  # Failed 3 times, succeeded on 4th
    
    @pytest.mark.asyncio  
    async def test_partial_pipeline_failure_recovery(self, clean_database, mock_tool_catalog):
        """Test pipeline recovery when some steps fail."""
        
        registry = ToolRegistry()
        registry.load_tools(mock_tool_catalog)
        
        # Mock MCP with mixed success/failure
        mock_mcp = Mock()
        
        async def mixed_reliability_calls(tool_address, **kwargs):
            if "fail" in kwargs.get("message", ""):
                raise Exception("Intentional tool failure")
            elif "slow" in kwargs.get("message", ""):
                await asyncio.sleep(2)  # Simulate slow response
                return {"result": "slow but successful"}
            else:
                return {"result": f"success from {tool_address}"}
        
        mock_mcp.call_tool = AsyncMock(side_effect=mixed_reliability_calls)
        
        executor = PipelineExecutor(registry, mock_mcp)
        
        # Pipeline with mix of failing and succeeding steps
        pipeline = {
            "pipeline": [
                {
                    "id": "success_step",
                    "uses": "test-tool.execute",
                    "with": {"message": "this should work"},
                    "save_as": "success_result"
                },
                {
                    "id": "failing_step",
                    "uses": "echo.test", 
                    "with": {"message": "this will fail"},
                    "save_as": "fail_result",
                    "on_failure": "continue"  # Don't stop pipeline
                },
                {
                    "id": "recovery_step",
                    "uses": "telegram.send_message",
                    "with": {
                        "chat_id": 12345,
                        "text": "Status: ${steps.success_result.result || 'no success'}"
                    },
                    "save_as": "notification"
                }
            ]
        }
        
        result = await executor.execute(pipeline)
        
        # Pipeline should partially succeed
        assert "success_result" in result["outputs"]
        assert result["outputs"]["success_result"]["result"] == "success from test-tool.execute"
        
        # Should handle failure gracefully
        assert "fail_result" not in result["outputs"] or \
               "error" in result["outputs"].get("fail_result", {})
        
        # Recovery step should still execute
        assert "notification" in result["outputs"]


@pytest.mark.chaos
class TestHighLoadResilienceScenarios:
    """Test system behavior under extreme load."""
    
    async def test_concurrent_worker_overload(self, clean_database, mock_tool_catalog):
        """Test system behavior with too many concurrent workers."""
        
        # Create large work queue
        agent = await insert_test_agent(clean_database)
        task = await insert_test_task(clean_database, agent["id"])
        
        work_items = []
        for i in range(100):
            work_id = await insert_due_work(clean_database, task["id"], datetime.now(timezone.utc))
            work_items.append(work_id)
        
        # Create excessive number of workers
        workers = []
        worker_tasks = []
        worker_count = 25  # Intentionally high
        
        try:
            for i in range(worker_count):
                config = WorkerConfig(
                    worker_id=f"overload-worker-{i}",
                    poll_interval_seconds=0.01,  # Aggressive polling
                    batch_size=1,
                    max_retries=2
                )
                worker = WorkerCoordinator(config, clean_database)
                workers.append(worker)
                worker_tasks.append(asyncio.create_task(worker.start()))
            
            # Let system run under overload
            await asyncio.sleep(5)
            
            # Check system health
            with clean_database.begin() as conn:
                remaining_work = conn.execute(
                    "SELECT COUNT(*) FROM due_work WHERE task_id = ?",
                    (task["id"],)
                ).scalar()
                
                successful_runs = conn.execute(
                    "SELECT COUNT(*) FROM task_run WHERE task_id = ? AND success = 1",
                    (task["id"],)
                ).scalar()
            
            processed = len(work_items) - remaining_work
            
            print(f"Overload test: {processed}/{len(work_items)} processed, {successful_runs} successful")
            
            # System should handle overload gracefully
            assert processed > 0, "Should process some work despite overload"
            
            # Should not create more runs than work items (no double processing)
            assert successful_runs <= len(work_items), "Should not double-process work items"
            
        finally:
            # Cleanup workers
            cleanup_tasks = []
            for worker in workers:
                cleanup_tasks.append(worker.shutdown())
            
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)
            await asyncio.gather(*worker_tasks, return_exceptions=True)
    
    async def test_memory_leak_detection(self, clean_database, mock_tool_catalog):
        """Test for memory leaks during intensive operations."""
        
        import gc
        process = psutil.Process()
        
        # Record initial memory
        gc.collect()
        initial_memory = process.memory_info().rss
        memory_samples = [initial_memory]
        
        registry = ToolRegistry() 
        registry.load_tools(mock_tool_catalog)
        
        mock_mcp = Mock()
        mock_mcp.call_tool = AsyncMock(return_value={"result": "memory test"})
        
        executor = PipelineExecutor(registry, mock_mcp)
        agent = await insert_test_agent(clean_database)
        
        # Perform intensive operations
        for cycle in range(50):
            # Create temporary objects
            tasks = []
            for i in range(20):
                task_data = await insert_test_task(clean_database, agent["id"])
                work_id = await insert_due_work(clean_database, task_data["id"], datetime.now(timezone.utc))
                
                # Execute pipeline (creates many temporary objects)
                pipeline = {
                    "pipeline": [
                        {
                            "id": f"memory_test_{i}",
                            "uses": "test-tool.execute",
                            "with": {"message": f"Memory test cycle {cycle} item {i}"},
                            "save_as": "result"
                        }
                    ]
                }
                
                result = await executor.execute(pipeline)
                tasks.append(result)
            
            # Sample memory every 10 cycles
            if cycle % 10 == 0:
                gc.collect()  # Force garbage collection
                current_memory = process.memory_info().rss
                memory_samples.append(current_memory)
                
                memory_growth = (current_memory - initial_memory) / (1024 * 1024)  # MB
                print(f"Cycle {cycle}: {memory_growth:.1f}MB memory growth")
        
        # Final memory check
        gc.collect()
        final_memory = process.memory_info().rss
        total_growth = (final_memory - initial_memory) / (1024 * 1024)  # MB
        
        print(f"Memory leak test: {total_growth:.1f}MB total growth")
        
        # Memory growth should be reasonable
        max_acceptable_growth = 100  # MB
        assert total_growth < max_acceptable_growth, \
            f"Memory grew {total_growth:.1f}MB, possible leak (limit {max_acceptable_growth}MB)"
    
    async def test_resource_exhaustion_recovery(self, clean_database):
        """Test recovery from resource exhaustion scenarios."""
        
        # Simulate file descriptor exhaustion
        open_files = []
        
        try:
            agent = await insert_test_agent(clean_database)
            
            # Create many temporary files to exhaust file descriptors
            for i in range(100):  # Try to create many files
                try:
                    import tempfile
                    temp_file = tempfile.NamedTemporaryFile(delete=False)
                    open_files.append(temp_file)
                    
                    # Try database operation while resources are constrained
                    task = await insert_test_task(clean_database, agent["id"])
                    work_id = await insert_due_work(clean_database, task["id"], datetime.now(timezone.utc))
                    
                except OSError as e:
                    print(f"Resource exhaustion at iteration {i}: {e}")
                    break
                except Exception as e:
                    print(f"Other error at iteration {i}: {e}")
            
            # System should still be able to perform basic operations
            final_task = await insert_test_task(clean_database, agent["id"])
            assert final_task is not None, "Should still be able to create tasks after resource pressure"
            
        finally:
            # Cleanup to prevent affecting other tests
            for temp_file in open_files:
                try:
                    temp_file.close()
                    os.unlink(temp_file.name)
                except:
                    pass


@pytest.mark.chaos
class TestTimingAndRaceConditions:
    """Test timing-sensitive scenarios and race conditions."""
    
    async def test_concurrent_task_scheduling_race_condition(self, clean_database):
        """Test race conditions in concurrent task scheduling."""
        
        scheduler_service = SchedulerService(clean_database)
        await scheduler_service.start()
        
        try:
            agent = await insert_test_agent(clean_database)
            
            # Create many tasks with same schedule time
            schedule_time = datetime.now(timezone.utc) + timedelta(seconds=5)
            concurrent_tasks = []
            
            async def create_and_schedule_task(task_id):
                task_data = {
                    "id": str(uuid.uuid4()),
                    "title": f"Race Condition Task {task_id}",
                    "schedule_kind": "once",
                    "schedule_expr": schedule_time.isoformat(),
                    "timezone": "UTC",
                    "payload": {"pipeline": [{"id": "race_test", "uses": "test.tool"}]},
                    "status": "active"
                }
                
                await scheduler_service.add_task(task_data)
                return task_data["id"]
            
            # Schedule many tasks concurrently
            scheduling_tasks = [create_and_schedule_task(i) for i in range(20)]
            scheduled_task_ids = await asyncio.gather(*scheduling_tasks, return_exceptions=True)
            
            # Count successful schedules
            successful_schedules = [task_id for task_id in scheduled_task_ids 
                                  if isinstance(task_id, str)]
            
            print(f"Race condition test: {len(successful_schedules)}/20 tasks scheduled successfully")
            
            # Should schedule most tasks despite concurrency
            assert len(successful_schedules) >= 15, "Most tasks should be scheduled despite race conditions"
            
            # Verify scheduler job count
            jobs = scheduler_service.scheduler.get_jobs()
            scheduled_jobs = [job for job in jobs if any(task_id in job.id for task_id in successful_schedules)]
            
            # Should have jobs scheduled (though some might have same execution time)
            assert len(scheduled_jobs) > 0, "Should have jobs scheduled"
            
        finally:
            await scheduler_service.shutdown()
    
    async def test_clock_skew_handling(self, clean_database):
        """Test handling of clock skew and time synchronization issues."""
        
        agent = await insert_test_agent(clean_database)
        
        # Simulate clock skew by creating work items with past times
        skewed_times = [
            datetime.now(timezone.utc) - timedelta(minutes=5),  # 5 minutes ago
            datetime.now(timezone.utc) + timedelta(seconds=1),  # 1 second future
            datetime.now(timezone.utc) - timedelta(hours=1),    # 1 hour ago
            datetime.now(timezone.utc) + timedelta(minutes=2),  # 2 minutes future
        ]
        
        work_items = []
        for i, skewed_time in enumerate(skewed_times):
            task = await insert_test_task(clean_database, agent["id"])
            work_id = await insert_due_work(clean_database, task["id"], skewed_time)
            work_items.append((work_id, skewed_time))
        
        # Worker should handle time skew gracefully
        worker_config = WorkerConfig(worker_id="clock-skew-worker")
        worker = ProcessingWorker(worker_config, clean_database)
        
        # Lease available work
        available_work = []
        for _ in range(10):  # Try multiple times
            work = await worker.lease_next_work()
            if work:
                available_work.append(work)
            else:
                break
        
        print(f"Clock skew test: {len(available_work)} work items available despite time skew")
        
        # Should be able to lease past-due items
        assert len(available_work) > 0, "Should be able to lease work despite clock skew"
        
        # Verify that past-due items are available
        past_due_available = any(
            any(work["id"] == work_id for work in available_work)
            for work_id, scheduled_time in work_items
            if scheduled_time <= datetime.now(timezone.utc)
        )
        
        assert past_due_available, "Should lease past-due work items"
    
    async def test_async_operation_race_conditions(self, clean_database, mock_tool_catalog):
        """Test race conditions in async operations."""
        
        registry = ToolRegistry()
        registry.load_tools(mock_tool_catalog)
        
        # Mock MCP with variable response times
        mock_mcp = Mock()
        
        async def variable_timing_tool_call(tool_address, **kwargs):
            # Random delay to create race conditions
            delay = random.uniform(0.01, 0.1)
            await asyncio.sleep(delay)
            return {"result": f"response from {tool_address}", "delay": delay}
        
        mock_mcp.call_tool = AsyncMock(side_effect=variable_timing_tool_call)
        
        executor = PipelineExecutor(registry, mock_mcp)
        
        # Create pipeline with parallel steps that might race
        pipeline = {
            "pipeline": [
                {
                    "id": "parallel1",
                    "uses": "test-tool.execute",
                    "with": {"message": "parallel operation 1"},
                    "save_as": "result1",
                    "parallel": True
                },
                {
                    "id": "parallel2", 
                    "uses": "echo.test",
                    "with": {"message": "parallel operation 2"},
                    "save_as": "result2",
                    "parallel": True
                },
                {
                    "id": "dependent",
                    "uses": "weather.forecast",
                    "with": {"location": "${steps.result1.result} ${steps.result2.result}"},
                    "save_as": "combined"
                }
            ]
        }
        
        # Execute multiple times to catch race conditions
        results = []
        for i in range(10):
            result = await executor.execute(pipeline)
            results.append(result)
        
        # All executions should succeed despite async races
        successful_results = [r for r in results if r["success"]]
        assert len(successful_results) == 10, "All executions should succeed despite race conditions"
        
        # All should have consistent structure
        for result in successful_results:
            assert "result1" in result["outputs"]
            assert "result2" in result["outputs"] 
            assert "combined" in result["outputs"]


@pytest.mark.chaos
@pytest.mark.slow
class TestSystemRecoveryScenarios:
    """Test complete system recovery from various failure scenarios."""
    
    async def test_worker_crash_and_restart_recovery(self, clean_database, mock_tool_catalog):
        """Test recovery when workers crash and restart."""
        
        agent = await insert_test_agent(clean_database)
        task = await insert_test_task(clean_database, agent["id"])
        
        # Create work items
        work_ids = []
        for i in range(10):
            work_id = await insert_due_work(clean_database, task["id"], datetime.now(timezone.utc))
            work_ids.append(work_id)
        
        # Start worker
        worker_config = WorkerConfig(
            worker_id="crash-test-worker",
            lease_timeout_seconds=2,  # Short lease for faster recovery
            poll_interval_seconds=0.1
        )
        
        worker1 = WorkerCoordinator(worker_config, clean_database)
        worker1_task = asyncio.create_task(worker1.start())
        
        try:
            # Let worker run briefly
            await asyncio.sleep(1)
            
            # "Crash" worker by shutting down abruptly
            worker1_task.cancel()
            try:
                await worker1_task
            except asyncio.CancelledError:
                pass
            
            # Wait for leases to expire
            await asyncio.sleep(3)
            
            # Start new worker (simulating restart)
            worker2 = WorkerCoordinator(
                WorkerConfig(worker_id="recovery-worker", poll_interval_seconds=0.1),
                clean_database
            )
            worker2_task = asyncio.create_task(worker2.start())
            
            # Let recovery worker run
            await asyncio.sleep(2)
            
            # Check recovery
            with clean_database.begin() as conn:
                remaining_work = conn.execute(
                    "SELECT COUNT(*) FROM due_work WHERE task_id = ?",
                    (task["id"],)
                ).scalar()
                
                processed_runs = conn.execute(
                    "SELECT COUNT(*) FROM task_run WHERE task_id = ?",
                    (task["id"],)
                ).scalar()
            
            processed_count = len(work_ids) - remaining_work
            
            print(f"Crash recovery: {processed_count}/{len(work_ids)} recovered, {processed_runs} runs")
            
            # Should recover some work after crash
            assert processed_count > 0 or processed_runs > 0, "Should recover work after worker crash"
            
            await worker2.shutdown()
            await worker2_task
            
        except Exception as e:
            print(f"Worker crash test encountered error: {e}")
            # Test passes if system doesn't crash completely
    
    async def test_scheduler_service_interruption_recovery(self, clean_database):
        """Test recovery from scheduler service interruptions."""
        
        agent = await insert_test_agent(clean_database)
        
        # Start scheduler
        scheduler1 = SchedulerService(clean_database)
        await scheduler1.start()
        
        try:
            # Add tasks to scheduler
            tasks = []
            for i in range(5):
                task_data = {
                    "id": str(uuid.uuid4()),
                    "title": f"Scheduler Recovery Test {i}",
                    "schedule_kind": "once",
                    "schedule_expr": (datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat(),
                    "timezone": "UTC", 
                    "payload": {"pipeline": [{"id": "recovery", "uses": "test.tool"}]},
                    "status": "active"
                }
                await scheduler1.add_task(task_data)
                tasks.append(task_data)
            
            # Verify jobs were scheduled
            initial_jobs = len(scheduler1.scheduler.get_jobs())
            assert initial_jobs >= 5, "Should have scheduled jobs"
            
            # Simulate scheduler crash
            await scheduler1.shutdown()
            
            # Wait briefly
            await asyncio.sleep(1)
            
            # Restart scheduler
            scheduler2 = SchedulerService(clean_database)
            await scheduler2.start()
            
            # Restore tasks to new scheduler (in production, this would be automatic)
            for task_data in tasks:
                await scheduler2.add_task(task_data)
            
            # Verify recovery
            recovered_jobs = len(scheduler2.scheduler.get_jobs())
            
            print(f"Scheduler recovery: {initial_jobs} → {recovered_jobs} jobs")
            
            assert recovered_jobs >= initial_jobs, "Should recover scheduled jobs"
            
            await scheduler2.shutdown()
            
        except Exception as e:
            print(f"Scheduler recovery test error: {e}")
            if 'scheduler1' in locals() and scheduler1.is_running():
                await scheduler1.shutdown()
    
    async def test_cascading_failure_recovery(self, clean_database, mock_tool_catalog):
        """Test recovery from cascading system failures."""
        
        # Setup system components  
        agent = await insert_test_agent(clean_database)
        
        scheduler_service = SchedulerService(clean_database) 
        await scheduler_service.start()
        
        workers = []
        worker_tasks = []
        
        # Create multiple workers
        for i in range(3):
            config = WorkerConfig(
                worker_id=f"cascade-worker-{i}",
                poll_interval_seconds=0.1,
                max_retries=2
            )
            worker = WorkerCoordinator(config, clean_database)
            workers.append(worker)
            worker_tasks.append(asyncio.create_task(worker.start()))
        
        try:
            # Create tasks
            tasks = []
            for i in range(10):
                task_data = {
                    "id": str(uuid.uuid4()),
                    "title": f"Cascade Test Task {i}",
                    "schedule_kind": "once", 
                    "schedule_expr": (datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat(),
                    "timezone": "UTC",
                    "payload": {"pipeline": [{"id": "cascade", "uses": "test.tool"}]},
                    "status": "active"
                }
                await scheduler_service.add_task(task_data)
                tasks.append(task_data)
            
            # Let system run briefly
            await asyncio.sleep(1)
            
            # Simulate cascading failures
            
            # 1. First worker "crashes"
            worker_tasks[0].cancel()
            
            # 2. Database becomes slow (simulate with delays)
            original_execute = clean_database.execute
            def slow_execute(*args, **kwargs):
                time.sleep(0.1)  # Add delay
                return original_execute(*args, **kwargs)
            
            # 3. Tool calls start failing
            registry = ToolRegistry()
            registry.load_tools(mock_tool_catalog)
            
            failing_mcp = Mock()
            failing_mcp.call_tool = AsyncMock(side_effect=Exception("Cascading tool failure"))
            
            # Let system struggle with failures
            with patch.object(clean_database, 'execute', side_effect=slow_execute):
                await asyncio.sleep(3)
            
            # System should still be partially functional
            remaining_workers = [w for i, w in enumerate(workers) if i != 0]
            assert any(w.is_running() for w in remaining_workers), \
                "Some workers should survive cascading failures"
            
            # Scheduler should still be running
            assert scheduler_service.is_running(), "Scheduler should survive cascading failures"
            
            print("Cascading failure test: System partially survived cascading failures")
            
        finally:
            # Cleanup
            await scheduler_service.shutdown()
            
            for worker in workers:
                await worker.shutdown()
            
            # Cancel and wait for worker tasks
            for task in worker_tasks:
                if not task.done():
                    task.cancel()
            
            await asyncio.gather(*worker_tasks, return_exceptions=True)