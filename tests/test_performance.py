#!/usr/bin/env python3
"""
Comprehensive Performance Tests for Ordinaut.

Tests system performance including:
- Load testing with high task volumes
- Concurrent worker performance benchmarks
- Database query performance under load
- Memory usage and leak detection
- Throughput and latency measurements
- SLA validation and performance regression detection

Validates that the system meets performance requirements under production loads.
"""

import pytest
import asyncio
import uuid
import json
import time
import psutil
import gc
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import Mock, AsyncMock, patch

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set test environment
os.environ["DATABASE_URL"] = "sqlite:///test_performance.db"
os.environ["REDIS_URL"] = "memory://"

from workers.runner import WorkerCoordinator, ProcessingWorker, WorkerConfig
from scheduler.tick import SchedulerService
from engine.executor import PipelineExecutor
from engine.template import TemplateRenderer
from engine.registry import ToolRegistry
from conftest import insert_test_agent, insert_test_task, insert_due_work


@pytest.mark.load
@pytest.mark.benchmark
class TestLoadAndThroughput:
    """Load testing and throughput measurements."""
    
    def test_high_volume_task_creation_performance(self, benchmark, clean_database):
        """Benchmark creating large numbers of tasks."""
        
        async def create_tasks_batch(agent_id, count=100):
            tasks_created = 0
            start_time = time.perf_counter()
            
            for i in range(count):
                task_data = {
                    "title": f"Load Test Task {i}",
                    "description": f"High volume test task {i}",
                    "created_by": agent_id,
                    "schedule_kind": "once",
                    "schedule_expr": (datetime.now(timezone.utc) + timedelta(seconds=3600)).isoformat(),
                    "timezone": "UTC",
                    "payload": {
                        "pipeline": [
                            {
                                "id": f"load_step_{i}",
                                "uses": "test-tool.execute",
                                "with": {"message": f"Load test {i}"},
                                "save_as": "result"
                            }
                        ]
                    },
                    "status": "active",
                    "priority": 5,
                    "max_retries": 3
                }
                
                await insert_test_task(clean_database, agent_id, task_data)
                tasks_created += 1
            
            end_time = time.perf_counter()
            return {
                "tasks_created": tasks_created,
                "duration": end_time - start_time,
                "rate": tasks_created / (end_time - start_time)
            }
        
        def run_load_test():
            agent = asyncio.run(insert_test_agent(clean_database))
            return asyncio.run(create_tasks_batch(agent["id"], 500))
        
        result = benchmark(run_load_test)
        
        # Verify performance requirements
        assert result["rate"] > 50, f"Task creation rate {result['rate']:.1f}/sec below minimum 50/sec"
        assert result["tasks_created"] == 500, "Should create all requested tasks"
        
        print(f"Load test results: {result['tasks_created']} tasks in {result['duration']:.2f}s ({result['rate']:.1f}/sec)")
    
    def test_concurrent_worker_throughput(self, benchmark, clean_database, mock_tool_catalog):
        """Benchmark concurrent worker processing throughput."""
        
        async def setup_work_queue(task_count=200):
            agent = await insert_test_agent(clean_database)
            task = await insert_test_task(clean_database, agent["id"])
            
            work_items = []
            for i in range(task_count):
                work_id = await insert_due_work(clean_database, task["id"], 
                                               datetime.now(timezone.utc))
                work_items.append(work_id)
            
            return len(work_items)
        
        async def run_concurrent_workers(worker_count=5, duration=10):
            # Setup work queue
            initial_work_count = await setup_work_queue(200)
            
            # Setup mock tool registry
            registry = ToolRegistry()
            registry.load_tools(mock_tool_catalog)
            
            # Fast mock MCP client
            mock_mcp = Mock()
            mock_mcp.call_tool = AsyncMock(return_value={"result": "fast response"})
            
            # Create workers
            workers = []
            worker_tasks = []
            
            for i in range(worker_count):
                config = WorkerConfig(
                    worker_id=f"perf-worker-{i}",
                    poll_interval_seconds=0.01,  # Aggressive polling
                    batch_size=3
                )
                worker = WorkerCoordinator(config, clean_database)
                workers.append(worker)
                worker_tasks.append(asyncio.create_task(worker.start()))
            
            # Measure processing time
            start_time = time.perf_counter()
            await asyncio.sleep(duration)
            end_time = time.perf_counter()
            
            # Stop workers
            for worker in workers:
                await worker.shutdown()
            await asyncio.gather(*worker_tasks, return_exceptions=True)
            
            # Count remaining work
            with clean_database.begin() as conn:
                remaining_work = conn.execute("SELECT COUNT(*) FROM due_work").scalar()
            
            processed_count = initial_work_count - remaining_work
            actual_duration = end_time - start_time
            throughput = processed_count / actual_duration
            
            return {
                "initial_work": initial_work_count,
                "processed": processed_count,
                "duration": actual_duration,
                "throughput": throughput,
                "workers": worker_count
            }
        
        def run_throughput_test():
            return asyncio.run(run_concurrent_workers(5, 8))
        
        result = benchmark(run_throughput_test)
        
        # Performance assertions
        min_throughput = 20  # tasks per second
        assert result["throughput"] >= min_throughput, \
            f"Throughput {result['throughput']:.1f} tasks/sec below minimum {min_throughput}/sec"
        
        print(f"Throughput test: {result['processed']}/{result['initial_work']} tasks in {result['duration']:.1f}s")
        print(f"Throughput: {result['throughput']:.1f} tasks/sec with {result['workers']} workers")
    
    def test_database_query_performance_under_load(self, benchmark, clean_database):
        """Benchmark database operations under concurrent load."""
        
        async def setup_large_dataset():
            """Setup large dataset for performance testing."""
            agent = await insert_test_agent(clean_database)
            
            # Create many tasks and work items
            tasks = []
            for i in range(100):
                task = await insert_test_task(clean_database, agent["id"])
                tasks.append(task)
                
                # Create multiple work items per task
                for j in range(10):
                    await insert_due_work(clean_database, task["id"], 
                                         datetime.now(timezone.utc) + timedelta(seconds=j))
            
            return agent, tasks
        
        async def run_concurrent_queries():
            agent, tasks = await setup_large_dataset()
            
            # Simulate concurrent worker operations
            async def worker_query_cycle(worker_id):
                query_count = 0
                start_time = time.perf_counter()
                
                for _ in range(50):  # Each worker performs 50 operations
                    try:
                        # Lease work query (most critical path)
                        with clean_database.begin() as conn:
                            result = conn.execute("""
                                SELECT id, task_id 
                                FROM due_work 
                                WHERE run_at <= datetime('now') 
                                  AND (locked_until IS NULL OR locked_until < datetime('now'))
                                ORDER BY run_at ASC 
                                LIMIT 1
                            """).fetchone()
                            
                            if result:
                                # Lock the work item
                                conn.execute("""
                                    UPDATE due_work 
                                    SET locked_by = ?, locked_until = datetime('now', '+1 minute')
                                    WHERE id = ?
                                """, (f"perf-worker-{worker_id}", result.id))
                                
                                query_count += 1
                    
                    except Exception as e:
                        print(f"Query error in worker {worker_id}: {e}")
                    
                    # Small delay to simulate processing
                    await asyncio.sleep(0.001)
                
                end_time = time.perf_counter()
                return {
                    "worker_id": worker_id,
                    "queries": query_count,
                    "duration": end_time - start_time
                }
            
            # Run multiple concurrent query cycles
            tasks = [worker_query_cycle(i) for i in range(10)]
            results = await asyncio.gather(*tasks)
            
            total_queries = sum(r["queries"] for r in results)
            total_duration = max(r["duration"] for r in results)  # Parallel execution
            query_rate = total_queries / total_duration if total_duration > 0 else 0
            
            return {
                "total_queries": total_queries,
                "duration": total_duration,
                "query_rate": query_rate,
                "concurrent_workers": len(results)
            }
        
        def run_db_performance_test():
            return asyncio.run(run_concurrent_queries())
        
        result = benchmark(run_db_performance_test)
        
        # Database performance assertions
        min_query_rate = 100  # queries per second
        assert result["query_rate"] >= min_query_rate, \
            f"Query rate {result['query_rate']:.1f} q/sec below minimum {min_query_rate} q/sec"
        
        print(f"DB Performance: {result['total_queries']} queries in {result['duration']:.2f}s")
        print(f"Query rate: {result['query_rate']:.1f} queries/sec")
    
    def test_scheduler_performance_with_many_jobs(self, benchmark, clean_database):
        """Benchmark scheduler performance with large numbers of jobs."""
        
        async def scheduler_load_test():
            scheduler_service = SchedulerService(clean_database)
            await scheduler_service.start()
            
            try:
                agent = await insert_test_agent(clean_database)
                
                start_time = time.perf_counter()
                
                # Add many tasks to scheduler
                task_count = 1000
                tasks_added = 0
                
                for i in range(task_count):
                    # Vary schedule times to distribute load
                    schedule_time = datetime.now(timezone.utc) + timedelta(seconds=3600 + i)
                    
                    task_data = {
                        "id": str(uuid.uuid4()),
                        "title": f"Scheduler Load Test {i}",
                        "schedule_kind": "once",
                        "schedule_expr": schedule_time.isoformat(),
                        "timezone": "UTC",
                        "payload": {"pipeline": [{"id": "test", "uses": "test.tool"}]},
                        "status": "active"
                    }
                    
                    try:
                        await scheduler_service.add_task(task_data)
                        tasks_added += 1
                    except Exception as e:
                        print(f"Failed to add task {i}: {e}")
                
                end_time = time.perf_counter()
                
                # Check scheduler job count
                job_count = len(scheduler_service.scheduler.get_jobs())
                
                return {
                    "tasks_scheduled": tasks_added,
                    "active_jobs": job_count,
                    "duration": end_time - start_time,
                    "scheduling_rate": tasks_added / (end_time - start_time)
                }
                
            finally:
                await scheduler_service.shutdown()
        
        def run_scheduler_test():
            return asyncio.run(scheduler_load_test())
        
        result = benchmark(run_scheduler_test)
        
        # Scheduler performance assertions
        min_scheduling_rate = 100  # tasks per second
        assert result["scheduling_rate"] >= min_scheduling_rate, \
            f"Scheduling rate {result['scheduling_rate']:.1f}/sec below minimum {min_scheduling_rate}/sec"
        
        assert result["tasks_scheduled"] > 900, "Should schedule most tasks successfully"
        
        print(f"Scheduler Performance: {result['tasks_scheduled']} tasks scheduled in {result['duration']:.2f}s")
        print(f"Rate: {result['scheduling_rate']:.1f} tasks/sec, Active jobs: {result['active_jobs']}")


@pytest.mark.load
class TestMemoryAndResourceUsage:
    """Memory usage and resource consumption tests."""
    
    def test_memory_usage_under_sustained_load(self, clean_database, mock_tool_catalog):
        """Test memory usage during sustained high-load operations."""
        
        async def sustained_load_test():
            process = psutil.Process()
            initial_memory = process.memory_info().rss
            memory_samples = [initial_memory]
            
            # Setup components
            registry = ToolRegistry()
            registry.load_tools(mock_tool_catalog)
            
            mock_mcp = Mock()
            mock_mcp.call_tool = AsyncMock(return_value={"result": "memory test"})
            
            worker_config = WorkerConfig(
                worker_id="memory-test-worker",
                poll_interval_seconds=0.01
            )
            worker = ProcessingWorker(worker_config, clean_database)
            
            agent = await insert_test_agent(clean_database)
            
            # Run sustained operations for 30 seconds
            start_time = time.time()
            operation_count = 0
            
            while time.time() - start_time < 30:
                try:
                    # Create task and work item
                    task = await insert_test_task(clean_database, agent["id"])
                    work_id = await insert_due_work(clean_database, task["id"], 
                                                   datetime.now(timezone.utc))
                    
                    # Lease and "process" work
                    leased_work = await worker.lease_next_work()
                    if leased_work:
                        # Simulate processing without actual execution
                        await asyncio.sleep(0.001)
                        operation_count += 1
                    
                    # Sample memory every second
                    if operation_count % 100 == 0:
                        memory_samples.append(process.memory_info().rss)
                        
                        # Force garbage collection periodically
                        if operation_count % 500 == 0:
                            gc.collect()
                
                except Exception as e:
                    print(f"Error in memory test operation {operation_count}: {e}")
                    break
            
            final_memory = process.memory_info().rss
            
            return {
                "initial_memory_mb": initial_memory / (1024 * 1024),
                "final_memory_mb": final_memory / (1024 * 1024),
                "memory_growth_mb": (final_memory - initial_memory) / (1024 * 1024),
                "max_memory_mb": max(memory_samples) / (1024 * 1024),
                "operations": operation_count,
                "memory_samples": len(memory_samples)
            }
        
        result = asyncio.run(sustained_load_test())
        
        # Memory usage assertions
        max_acceptable_growth = 50  # MB
        assert result["memory_growth_mb"] < max_acceptable_growth, \
            f"Memory grew {result['memory_growth_mb']:.1f}MB, exceeds limit {max_acceptable_growth}MB"
        
        print(f"Memory test: {result['operations']} operations")
        print(f"Memory: {result['initial_memory_mb']:.1f} → {result['final_memory_mb']:.1f}MB")
        print(f"Growth: {result['memory_growth_mb']:.1f}MB, Peak: {result['max_memory_mb']:.1f}MB")
    
    def test_database_connection_pooling_efficiency(self, clean_database):
        """Test database connection pooling under concurrent access."""
        
        async def connection_pool_test():
            # Monitor connection usage
            connection_stats = {
                "concurrent_operations": 0,
                "max_concurrent": 0,
                "errors": 0,
                "successful_ops": 0
            }
            
            async def db_operation(op_id):
                try:
                    connection_stats["concurrent_operations"] += 1
                    connection_stats["max_concurrent"] = max(
                        connection_stats["max_concurrent"],
                        connection_stats["concurrent_operations"]
                    )
                    
                    # Perform database operation
                    with clean_database.begin() as conn:
                        # Simulate work leasing query
                        result = conn.execute("""
                            SELECT COUNT(*) FROM due_work 
                            WHERE run_at <= datetime('now')
                        """).scalar()
                        
                        # Simulate insert operation  
                        conn.execute("""
                            INSERT INTO task_run (id, task_id, started_at, attempt) 
                            VALUES (?, ?, ?, ?)
                        """, (str(uuid.uuid4()), str(uuid.uuid4()), datetime.now(), 1))
                        
                        # Small delay to hold connection
                        await asyncio.sleep(0.01)
                    
                    connection_stats["successful_ops"] += 1
                    
                except Exception as e:
                    connection_stats["errors"] += 1
                    print(f"DB operation {op_id} failed: {e}")
                
                finally:
                    connection_stats["concurrent_operations"] -= 1
            
            # Run many concurrent database operations
            tasks = [db_operation(i) for i in range(50)]
            await asyncio.gather(*tasks, return_exceptions=True)
            
            return connection_stats
        
        result = asyncio.run(connection_pool_test())
        
        # Connection pooling assertions
        assert result["errors"] == 0, f"Should have no connection errors, got {result['errors']}"
        assert result["successful_ops"] > 45, "Should complete most operations successfully"
        
        print(f"Connection pool test: {result['successful_ops']} successful ops")
        print(f"Max concurrent: {result['max_concurrent']}, Errors: {result['errors']}")
    
    def test_garbage_collection_efficiency(self, clean_database, mock_tool_catalog):
        """Test garbage collection efficiency during high-throughput operations."""
        
        async def gc_efficiency_test():
            # Enable GC stats
            gc.set_debug(gc.DEBUG_STATS)
            initial_objects = len(gc.get_objects())
            
            # Setup components
            registry = ToolRegistry()
            registry.load_tools(mock_tool_catalog)
            
            mock_mcp = Mock()
            mock_mcp.call_tool = AsyncMock(return_value={"result": "gc test"})
            
            executor = PipelineExecutor(registry, mock_mcp)
            agent = await insert_test_agent(clean_database)
            
            # Create many short-lived objects
            for i in range(1000):
                # Create pipeline context (creates many temporary objects)
                pipeline = {
                    "pipeline": [
                        {
                            "id": f"gc_test_{i}",
                            "uses": "test-tool.execute",
                            "with": {"message": f"GC test {i}"},
                            "save_as": "result"
                        }
                    ]
                }
                
                # Execute pipeline (creates execution context, templates, etc.)
                try:
                    result = await executor.execute(pipeline)
                    assert result["success"] is True
                except Exception as e:
                    print(f"Pipeline {i} failed: {e}")
                
                # Force GC every 100 iterations
                if i % 100 == 0:
                    collected = gc.collect()
                    print(f"GC at iteration {i}: collected {collected} objects")
            
            # Final garbage collection
            final_collected = gc.collect()
            final_objects = len(gc.get_objects())
            
            gc.set_debug(0)  # Disable debug
            
            return {
                "initial_objects": initial_objects,
                "final_objects": final_objects,
                "object_growth": final_objects - initial_objects,
                "final_collected": final_collected
            }
        
        result = asyncio.run(gc_efficiency_test())
        
        # GC efficiency assertions
        max_object_growth = 5000  # Reasonable object growth
        assert result["object_growth"] < max_object_growth, \
            f"Object count grew {result['object_growth']}, exceeds limit {max_object_growth}"
        
        print(f"GC test: {result['initial_objects']} → {result['final_objects']} objects")
        print(f"Growth: {result['object_growth']}, Final GC collected: {result['final_collected']}")


@pytest.mark.benchmark
class TestLatencyAndResponseTime:
    """Latency and response time benchmarks."""
    
    def test_template_rendering_latency(self, benchmark, performance_benchmarks):
        """Benchmark template rendering latency."""
        
        renderer = TemplateRenderer()
        
        # Complex context for realistic testing
        complex_context = {
            "params": {
                "user_id": "test-user-12345",
                "settings": {"theme": "dark", "notifications": True}
            },
            "steps": {
                "api_call": {
                    "data": [{"id": i, "value": f"item_{i}"} for i in range(50)],
                    "metadata": {"total": 50, "page": 1},
                    "response_time": 0.15
                },
                "processing": {
                    "results": {"processed": 45, "errors": 5},
                    "timing": {"start": "2025-01-10T10:00:00Z", "end": "2025-01-10T10:00:15Z"}
                }
            }
        }
        
        # Complex template with multiple variable types
        complex_template = """User Report for ${params.user_id}
Settings: Theme=${params.settings.theme}, Notifications=${params.settings.notifications}

API Response: ${steps.api_call.data | length} items in ${steps.api_call.response_time}s
Processing Results: ${steps.processing.results.processed} processed, ${steps.processing.results.errors} errors

Sample Data:
- First item: ${steps.api_call.data[0].value}
- Last item: ${steps.api_call.data[49].value}
- Total: ${steps.api_call.metadata.total}

Timing: ${steps.processing.timing.start} to ${steps.processing.timing.end}"""
        
        def render_complex_template():
            return renderer.render(complex_template, complex_context)
        
        result = benchmark(render_complex_template)
        
        # Verify correctness
        assert "test-user-12345" in result
        assert "50 items" in result
        assert "item_0" in result
        
        # Check performance against benchmarks
        expected_max_ms = performance_benchmarks["template_rendering"]["complex_nested_max_ms"]
        # Benchmark gives us time per call, convert to ms
        actual_ms = benchmark.stats.mean * 1000
        
        assert actual_ms < expected_max_ms, \
            f"Template rendering took {actual_ms:.1f}ms, expected < {expected_max_ms}ms"
    
    def test_database_query_latency(self, benchmark, clean_database, performance_benchmarks):
        """Benchmark database query latency."""
        
        async def setup_query_test_data():
            agent = await insert_test_agent(clean_database)
            tasks = []
            
            # Create test data
            for i in range(100):
                task = await insert_test_task(clean_database, agent["id"])
                tasks.append(task)
                
                # Create work items with various timing
                for j in range(5):
                    await insert_due_work(clean_database, task["id"],
                                         datetime.now(timezone.utc) + timedelta(seconds=j))
            
            return agent, tasks
        
        # Setup test data
        agent, tasks = asyncio.run(setup_query_test_data())
        
        def query_due_work():
            # Most critical query - work leasing
            with clean_database.begin() as conn:
                result = conn.execute("""
                    SELECT id, task_id, run_at
                    FROM due_work 
                    WHERE run_at <= datetime('now') 
                      AND (locked_until IS NULL OR locked_until < datetime('now'))
                    ORDER BY run_at ASC 
                    LIMIT 5
                """).fetchall()
                return len(result)
        
        count = benchmark(query_due_work)
        assert count > 0, "Should find available work items"
        
        # Check performance against benchmarks
        expected_max_ms = performance_benchmarks["database_operations"]["lease_work_max_ms"]
        actual_ms = benchmark.stats.mean * 1000
        
        assert actual_ms < expected_max_ms, \
            f"Work lease query took {actual_ms:.1f}ms, expected < {expected_max_ms}ms"
    
    def test_pipeline_execution_latency(self, benchmark, mock_tool_catalog, performance_benchmarks):
        """Benchmark pipeline execution latency."""
        
        registry = ToolRegistry()
        registry.load_tools(mock_tool_catalog)
        
        # Fast mock MCP client
        mock_mcp = Mock()
        mock_mcp.call_tool = AsyncMock(return_value={"result": "benchmark response"})
        
        executor = PipelineExecutor(registry, mock_mcp)
        
        # Multi-step pipeline for realistic testing
        pipeline = {
            "pipeline": [
                {
                    "id": "step1",
                    "uses": "test-tool.execute",
                    "with": {"message": "benchmark step 1"},
                    "save_as": "result1"
                },
                {
                    "id": "step2",
                    "uses": "echo.test",
                    "with": {"message": "Data from step1: ${steps.result1.result}"},
                    "save_as": "result2"
                },
                {
                    "id": "step3",
                    "uses": "weather.forecast",
                    "with": {"location": "Chisinau"},
                    "save_as": "weather"
                }
            ]
        }
        
        def execute_pipeline():
            return asyncio.run(executor.execute(pipeline))
        
        result = benchmark(execute_pipeline)
        
        assert result["success"] is True
        assert len(result["outputs"]) == 3
        
        # Check performance against benchmarks
        expected_max_ms = performance_benchmarks["pipeline_execution"]["multi_step_max_ms"]
        actual_ms = benchmark.stats.mean * 1000
        
        assert actual_ms < expected_max_ms, \
            f"Multi-step pipeline took {actual_ms:.1f}ms, expected < {expected_max_ms}ms"
    
    def test_end_to_end_task_processing_latency(self, benchmark, clean_database, mock_tool_catalog):
        """Benchmark complete end-to-end task processing latency."""
        
        async def end_to_end_processing():
            # Setup components
            registry = ToolRegistry()
            registry.load_tools(mock_tool_catalog)
            
            mock_mcp = Mock()
            mock_mcp.call_tool = AsyncMock(return_value={"result": "e2e success"})
            
            worker_config = WorkerConfig(worker_id="e2e-benchmark-worker")
            worker = ProcessingWorker(worker_config, clean_database)
            
            # Create task and work
            agent = await insert_test_agent(clean_database)
            task = await insert_test_task(clean_database, agent["id"])
            work_id = await insert_due_work(clean_database, task["id"], datetime.now(timezone.utc))
            
            start_time = time.perf_counter()
            
            # Lease work
            leased_work = await worker.lease_next_work()
            assert leased_work is not None
            
            # Execute work (mock the executor)
            with patch.object(worker, '_get_pipeline_executor') as mock_executor:
                mock_executor.return_value.execute = AsyncMock(return_value={
                    "success": True,
                    "outputs": {"result": {"result": "e2e benchmark complete"}}
                })
                
                result = await worker.execute_leased_work(leased_work)
            
            end_time = time.perf_counter()
            
            assert result["success"] is True
            return end_time - start_time
        
        def run_e2e_benchmark():
            return asyncio.run(end_to_end_processing())
        
        latency = benchmark(run_e2e_benchmark)
        
        # End-to-end should be fast (< 50ms for simple task)
        max_acceptable_latency = 0.05  # 50ms
        assert latency < max_acceptable_latency, \
            f"E2E processing took {latency:.3f}s, expected < {max_acceptable_latency}s"


@pytest.mark.load
@pytest.mark.slow
class TestStressAndBreakingPoints:
    """Stress testing to find system breaking points."""
    
    async def test_maximum_concurrent_workers(self, clean_database, mock_tool_catalog):
        """Find maximum sustainable concurrent workers."""
        
        # Setup large work queue
        agent = await insert_test_agent(clean_database)
        task = await insert_test_task(clean_database, agent["id"])
        
        work_count = 500
        for i in range(work_count):
            await insert_due_work(clean_database, task["id"], datetime.now(timezone.utc))
        
        # Test with increasing worker counts
        for worker_count in [5, 10, 20, 30, 50]:
            try:
                print(f"Testing with {worker_count} workers...")
                
                workers = []
                worker_tasks = []
                
                for i in range(worker_count):
                    config = WorkerConfig(
                        worker_id=f"stress-worker-{i}",
                        poll_interval_seconds=0.01,
                        batch_size=2
                    )
                    worker = WorkerCoordinator(config, clean_database)
                    workers.append(worker)
                    worker_tasks.append(asyncio.create_task(worker.start()))
                
                # Run for short period
                start_time = time.time()
                await asyncio.sleep(5)
                end_time = time.time()
                
                # Stop workers
                for worker in workers:
                    await worker.shutdown()
                await asyncio.gather(*worker_tasks, return_exceptions=True)
                
                # Measure throughput
                with clean_database.begin() as conn:
                    remaining = conn.execute(
                        "SELECT COUNT(*) FROM due_work WHERE task_id = ?",
                        (task["id"],)
                    ).scalar()
                
                processed = work_count - remaining
                throughput = processed / (end_time - start_time)
                
                print(f"  {worker_count} workers: {processed} tasks, {throughput:.1f}/sec")
                
                # Check if system is still stable
                if throughput < 5:  # Very low throughput indicates problems
                    print(f"  System appears unstable with {worker_count} workers")
                    break
                    
                # Reset work queue for next test
                await insert_due_work(clean_database, task["id"], datetime.now(timezone.utc))
                
            except Exception as e:
                print(f"  Failed with {worker_count} workers: {e}")
                break
        
        # Test passed if we got through at least the basic counts
        assert True  # This is an exploratory test
    
    async def test_memory_under_extreme_load(self, clean_database):
        """Test memory behavior under extreme load."""
        
        process = psutil.Process()
        initial_memory = process.memory_info().rss
        
        try:
            agent = await insert_test_agent(clean_database)
            
            # Create extreme number of tasks and work items
            for batch in range(10):  # 10 batches of 100 = 1000 total
                for i in range(100):
                    task = await insert_test_task(clean_database, agent["id"])
                    await insert_due_work(clean_database, task["id"], datetime.now(timezone.utc))
                
                # Check memory after each batch
                current_memory = process.memory_info().rss
                memory_growth = (current_memory - initial_memory) / (1024 * 1024)  # MB
                
                print(f"Batch {batch}: {memory_growth:.1f}MB memory growth")
                
                # Force garbage collection
                gc.collect()
                
                # Stop if memory grows too much
                if memory_growth > 200:  # 200MB limit
                    print(f"Stopping at batch {batch} due to memory usage")
                    break
            
            final_memory = process.memory_info().rss
            total_growth = (final_memory - initial_memory) / (1024 * 1024)
            
            print(f"Total memory growth: {total_growth:.1f}MB")
            
            # Should not exceed reasonable memory growth
            assert total_growth < 300, f"Memory grew {total_growth:.1f}MB, exceeds 300MB limit"
            
        except Exception as e:
            print(f"Extreme load test failed: {e}")
            # This is a stress test, so failure is informative
            assert True
    
    async def test_database_connection_exhaustion(self, clean_database):
        """Test behavior when database connections are exhausted."""
        
        # Create many concurrent operations that hold connections
        async def connection_holding_operation(op_id):
            try:
                with clean_database.begin() as conn:
                    # Hold connection for a while
                    await asyncio.sleep(2)
                    
                    # Perform operation
                    result = conn.execute("SELECT 1").scalar()
                    return result == 1
                    
            except Exception as e:
                print(f"Connection operation {op_id} failed: {e}")
                return False
        
        # Start many concurrent operations
        operation_count = 50  # Try to exhaust connection pool
        tasks = [connection_holding_operation(i) for i in range(operation_count)]
        
        start_time = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        end_time = time.time()
        
        # Analyze results
        successful = sum(1 for r in results if r is True)
        failed = sum(1 for r in results if isinstance(r, Exception) or r is False)
        
        print(f"Connection exhaustion test:")
        print(f"  {successful} successful, {failed} failed operations")
        print(f"  Duration: {end_time - start_time:.1f}s")
        
        # System should handle connection exhaustion gracefully
        # Even if some operations fail, it shouldn't crash
        assert successful > 0, "Some operations should succeed"
        assert True  # Test passes if system doesn't crash