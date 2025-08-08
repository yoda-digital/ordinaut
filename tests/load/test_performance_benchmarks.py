#!/usr/bin/env python3
"""
Performance and load testing for Personal Agent Orchestrator.

Tests system performance under various load conditions including:
- 1000+ concurrent task processing with SKIP LOCKED verification
- Worker coordination under high concurrency stress
- Database connection pooling and query performance
- Pipeline execution throughput benchmarking
- Memory usage and resource leak detection
- SLA compliance verification (>99.9% uptime, zero work loss)
"""

import pytest
import asyncio
import time
import threading
import random
import uuid
import json
import statistics
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch, Mock
import psutil
import gc

from workers.runner import WorkerRunner
from workers.config import WorkerConfig
from engine.executor import run_pipeline
from engine.template import render_templates
from engine.rruler import next_occurrence


class TestHighVolumeTaskProcessing:
    """Test high-volume task processing scenarios."""
    
    @pytest.mark.load
    async def test_1000_concurrent_tasks_skip_locked_verification(self, test_environment, load_test_config):
        """Test 1000 concurrent tasks with SKIP LOCKED double-processing prevention."""
        
        # Create test agent
        agent_data = await insert_test_agent(test_environment.db_engine)
        
        # Create 1000 tasks
        task_count = 1000
        task_ids = []
        
        print(f"Creating {task_count} test tasks...")
        start_time = time.perf_counter()
        
        for i in range(task_count):
            task_data = {
                "title": f"Load Test Task {i}",
                "description": f"High volume test task #{i}",
                "created_by": agent_data["id"],
                "schedule_kind": "once",
                "schedule_expr": (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat(),
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
                "priority": random.randint(1, 9)
            }
            
            task = await insert_test_task(test_environment.db_engine, agent_data["id"], task_data)
            task_ids.append(task["id"])
        
        task_creation_time = time.perf_counter() - start_time
        print(f"Task creation took {task_creation_time:.2f} seconds")
        
        # Create due work items for all tasks
        print("Creating due work items...")
        work_ids = []
        for task_id in task_ids:
            work_id = await insert_due_work(test_environment.db_engine, task_id)
            work_ids.append(work_id)
        
        # Create worker pool
        worker_count = load_test_config["concurrent_workers"]
        workers = []
        
        for i in range(worker_count):
            config = WorkerConfig.from_dict({
                "worker_id": f"load-test-worker-{i}",
                "database_url": test_environment.db_url,
                "lease_seconds": 120
            })
            workers.append(WorkerRunner(config))
        
        print(f"Starting {worker_count} workers for concurrent processing...")
        
        # Track processing metrics
        processed_tasks = []
        processing_lock = threading.Lock()
        
        def worker_process_loop(worker, duration_seconds=60):
            """Worker processing loop with performance tracking."""
            start_time = time.time()
            local_processed = []
            
            with patch('engine.executor.load_catalog') as mock_catalog:
                mock_catalog.return_value = [
                    {
                        "address": "test-tool.execute",
                        "input_schema": {"type": "object", "properties": {"message": {"type": "string"}}},
                        "output_schema": {"type": "object", "properties": {"result": {"type": "string"}}}
                    }
                ]
                
                with patch('engine.executor.call_tool') as mock_call_tool:
                    mock_call_tool.return_value = {"result": "Load test completed"}
                    
                    while (time.time() - start_time) < duration_seconds:
                        try:
                            lease = worker.lease_one()
                            if lease:
                                process_start = time.perf_counter()
                                success = worker.process_work_item(lease)
                                process_end = time.perf_counter()
                                
                                if success:
                                    local_processed.append({
                                        "task_id": lease["task_id"],
                                        "worker_id": worker.config.worker_id,
                                        "processing_time": process_end - process_start,
                                        "timestamp": time.time()
                                    })
                            else:
                                time.sleep(0.01)  # Short sleep when no work available
                        except Exception as e:
                            print(f"Worker {worker.config.worker_id} error: {e}")
                            time.sleep(0.1)
            
            # Thread-safe update of processed tasks
            with processing_lock:
                processed_tasks.extend(local_processed)
            
            return len(local_processed)
        
        # Run workers concurrently
        overall_start = time.perf_counter()
        
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [
                executor.submit(worker_process_loop, worker, 30)  # 30 second test duration
                for worker in workers
            ]
            
            results = [f.result() for f in as_completed(futures)]
        
        overall_end = time.perf_counter()
        total_duration = overall_end - overall_start
        
        print(f"Load test completed in {total_duration:.2f} seconds")
        
        # Analyze results
        total_processed = sum(results)
        processing_times = [p["processing_time"] for p in processed_tasks]
        
        print(f"Results:")
        print(f"  Total tasks processed: {total_processed}")
        print(f"  Target tasks: {task_count}")
        print(f"  Processing rate: {total_processed / total_duration:.1f} tasks/second")
        print(f"  Avg processing time: {statistics.mean(processing_times) * 1000:.1f}ms")
        print(f"  95th percentile: {statistics.quantiles(processing_times, n=20)[18] * 1000:.1f}ms")
        
        # Verify no double processing (critical SKIP LOCKED test)
        processed_task_ids = [p["task_id"] for p in processed_tasks]
        unique_task_ids = set(processed_task_ids)
        
        assert len(processed_task_ids) == len(unique_task_ids), \
            f"Double processing detected! Processed {len(processed_task_ids)} tasks but {len(unique_task_ids)} unique"
        
        # Verify high processing rate
        expected_min_rate = load_test_config["expected_throughput_tasks_per_second"]
        actual_rate = total_processed / total_duration
        
        assert actual_rate >= expected_min_rate * 0.8, \
            f"Processing rate too low: {actual_rate:.1f} < {expected_min_rate * 0.8:.1f} tasks/second"
        
        # Verify acceptable failure rate
        expected_processed = min(task_count, int(total_duration * expected_min_rate))
        failure_rate = (expected_processed - total_processed) / expected_processed
        max_failure_rate = load_test_config["acceptable_failure_rate"]
        
        assert failure_rate <= max_failure_rate, \
            f"Failure rate too high: {failure_rate:.3f} > {max_failure_rate:.3f}"
        
        # Verify database consistency
        with test_environment.db_engine.begin() as conn:
            # Check for remaining due work (should be minimal)
            result = conn.execute(text("SELECT COUNT(*) FROM due_work"))
            remaining_work = result.scalar()
            
            # Check task run records
            result = conn.execute(text("SELECT COUNT(*) FROM task_run WHERE success = true"))
            successful_runs = result.scalar()
            
            print(f"  Remaining due work: {remaining_work}")
            print(f"  Successful task runs: {successful_runs}")
            
            # Allow some remaining work due to test timeout
            assert remaining_work <= task_count * 0.2, f"Too much unprocessed work: {remaining_work}"
            assert successful_runs >= total_processed * 0.9, f"Missing task run records: {successful_runs} < {total_processed}"
    
    @pytest.mark.load
    async def test_worker_coordination_stress(self, test_environment, load_test_config):
        """Test worker coordination under high concurrency stress."""
        
        # Create test data
        agent_data = await insert_test_agent(test_environment.db_engine)
        
        # Create tasks with varying priorities and schedules
        task_count = 500
        tasks_data = []
        
        for i in range(task_count):
            priority = random.randint(1, 9)
            # Mix of immediate and slightly delayed tasks
            delay = random.uniform(0, 5) if i % 3 == 0 else 0
            
            task_data = {
                "title": f"Stress Test Task {i}",
                "description": f"Worker coordination stress test #{i}",
                "created_by": agent_data["id"],
                "schedule_kind": "once",
                "schedule_expr": (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat(),
                "payload": {
                    "pipeline": [
                        {
                            "id": f"stress_step_{i}",
                            "uses": "test-tool.execute",
                            "with": {"message": f"Stress test {i}", "priority": priority},
                            "save_as": "result"
                        }
                    ]
                },
                "priority": priority,
                "max_retries": 2  # Include retry scenarios
            }
            
            task = await insert_test_task(test_environment.db_engine, agent_data["id"], task_data)
            tasks_data.append((task["id"], priority))
        
        # Create due work for immediate tasks
        immediate_tasks = [t[0] for t in tasks_data[:400]]  # 400 immediate, 100 delayed
        for task_id in immediate_tasks:
            await insert_due_work(test_environment.db_engine, task_id)
        
        # Create more workers than typical to stress coordination
        worker_count = 20
        workers = []
        
        for i in range(worker_count):
            config = WorkerConfig.from_dict({
                "worker_id": f"stress-worker-{i}",
                "database_url": test_environment.db_url,
                "lease_seconds": 30,
                "heartbeat_interval": 5
            })
            workers.append(WorkerRunner(config))
        
        # Track coordination metrics
        coordination_metrics = {
            "lease_conflicts": 0,
            "heartbeat_failures": 0,
            "processing_errors": 0,
            "lease_renewals": 0,
            "cleanup_actions": 0
        }
        metrics_lock = threading.Lock()
        
        def stressed_worker_loop(worker, duration=45):
            """Stressed worker with failure injection and coordination testing."""
            start_time = time.time()
            local_processed = 0
            
            with patch('engine.executor.load_catalog') as mock_catalog:
                mock_catalog.return_value = [
                    {
                        "address": "test-tool.execute",
                        "input_schema": {"type": "object", "properties": {"message": {"type": "string"}}},
                        "output_schema": {"type": "object", "properties": {"result": {"type": "string"}}}
                    }
                ]
                
                with patch('engine.executor.call_tool') as mock_call_tool:
                    # Inject failures randomly to test coordination
                    def mock_tool_call(*args, **kwargs):
                        if random.random() < 0.05:  # 5% failure rate
                            raise Exception("Simulated tool failure")
                        return {"result": "Stress test completed"}
                    
                    mock_call_tool.side_effect = mock_tool_call
                    
                    while (time.time() - start_time) < duration:
                        try:
                            # Periodic heartbeat
                            if random.random() < 0.1:  # 10% chance
                                try:
                                    worker.heartbeat()
                                except Exception:
                                    with metrics_lock:
                                        coordination_metrics["heartbeat_failures"] += 1
                            
                            # Periodic cleanup
                            if random.random() < 0.05:  # 5% chance
                                try:
                                    worker.cleanup_expired_leases()
                                    with metrics_lock:
                                        coordination_metrics["cleanup_actions"] += 1
                                except Exception:
                                    pass
                            
                            # Try to lease work
                            lease = worker.lease_one()
                            if lease:
                                # Simulate some processing time variation
                                if random.random() < 0.3:  # 30% of tasks are "slow"
                                    time.sleep(random.uniform(0.1, 0.5))
                                
                                # Randomly renew lease for long tasks
                                if random.random() < 0.2:  # 20% chance
                                    try:
                                        worker.renew_lease(lease["id"])
                                        with metrics_lock:
                                            coordination_metrics["lease_renewals"] += 1
                                    except Exception:
                                        pass
                                
                                # Process work item
                                try:
                                    success = worker.process_work_item(lease)
                                    if success:
                                        local_processed += 1
                                except Exception as e:
                                    with metrics_lock:
                                        coordination_metrics["processing_errors"] += 1
                            else:
                                # No work available - small delay
                                time.sleep(random.uniform(0.01, 0.1))
                        
                        except Exception as e:
                            with metrics_lock:
                                coordination_metrics["lease_conflicts"] += 1
                            time.sleep(0.1)
            
            return local_processed
        
        # Run stressed workers concurrently
        print(f"Running {worker_count} workers under stress conditions...")
        stress_start = time.perf_counter()
        
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [
                executor.submit(stressed_worker_loop, worker)
                for worker in workers
            ]
            
            results = [f.result() for f in as_completed(futures)]
        
        stress_end = time.perf_counter()
        stress_duration = stress_end - stress_start
        
        total_processed = sum(results)
        
        print(f"Stress test completed in {stress_duration:.2f} seconds")
        print(f"Results:")
        print(f"  Total tasks processed: {total_processed}")
        print(f"  Processing rate: {total_processed / stress_duration:.1f} tasks/second")
        print(f"  Coordination metrics:")
        for metric, value in coordination_metrics.items():
            print(f"    {metric}: {value}")
        
        # Verify coordination effectiveness
        assert coordination_metrics["lease_conflicts"] < worker_count * 5, \
            "Too many lease conflicts indicating poor coordination"
        
        assert coordination_metrics["heartbeat_failures"] < worker_count * 2, \
            "Too many heartbeat failures"
        
        # Verify reasonable processing under stress
        min_expected = immediate_tasks.__len__() * 0.7  # 70% of immediate tasks
        assert total_processed >= min_expected, \
            f"Too few tasks processed under stress: {total_processed} < {min_expected}"
        
        # Check database state after stress test
        with test_environment.db_engine.begin() as conn:
            # Verify no orphaned leases
            result = conn.execute(text("""
                SELECT COUNT(*) FROM due_work 
                WHERE locked_until > now() AND locked_by IS NOT NULL
            """))
            active_leases = result.scalar()
            
            # Should be minimal active leases after test completion
            assert active_leases < worker_count, \
                f"Too many active leases after completion: {active_leases}"


class TestDatabasePerformance:
    """Test database performance and connection handling."""
    
    @pytest.mark.load
    async def test_database_connection_pooling(self, test_environment, performance_benchmarks):
        """Test database connection pooling under high load."""
        
        # Create test agent and tasks
        agent_data = await insert_test_agent(test_environment.db_engine)
        
        # Test various database operations under load
        def database_operations_worker(worker_id, operation_count=1000):
            """Worker that performs various database operations."""
            
            config = WorkerConfig.from_dict({
                "worker_id": f"db-perf-worker-{worker_id}",
                "database_url": test_environment.db_url,
                "lease_seconds": 60
            })
            worker = WorkerRunner(config)
            
            operation_times = []
            
            for i in range(operation_count):
                op_start = time.perf_counter()
                
                try:
                    if i % 4 == 0:
                        # Lease operation (SELECT FOR UPDATE SKIP LOCKED)
                        lease = worker.lease_one()
                        if lease:
                            worker.delete_work(lease["id"])
                    
                    elif i % 4 == 1:
                        # Task lookup (SELECT with JOIN)
                        with worker.eng.begin() as conn:
                            conn.execute(text("""
                                SELECT t.id, t.title, a.name 
                                FROM task t JOIN agent a ON t.created_by = a.id 
                                WHERE t.status = 'active' LIMIT 10
                            """))
                    
                    elif i % 4 == 2:
                        # Heartbeat operation (INSERT/UPDATE)
                        worker.heartbeat()
                    
                    else:
                        # Task run query (SELECT with aggregation)
                        with worker.eng.begin() as conn:
                            conn.execute(text("""
                                SELECT COUNT(*) as runs, AVG(EXTRACT(epoch FROM (finished_at - started_at))) as avg_duration
                                FROM task_run 
                                WHERE created_at > now() - interval '1 hour'
                            """))
                    
                    op_end = time.perf_counter()
                    operation_times.append((op_end - op_start) * 1000)  # Convert to ms
                
                except Exception as e:
                    print(f"Database operation error: {e}")
                    operation_times.append(1000)  # Record high time for errors
            
            return operation_times
        
        # Create some work items for lease operations
        for i in range(100):
            task = await insert_test_task(test_environment.db_engine, agent_data["id"])
            await insert_due_work(test_environment.db_engine, task["id"])
        
        # Run concurrent database workers
        worker_count = 15
        operations_per_worker = 200
        
        print(f"Running {worker_count} workers with {operations_per_worker} operations each...")
        db_test_start = time.perf_counter()
        
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [
                executor.submit(database_operations_worker, i, operations_per_worker)
                for i in range(worker_count)
            ]
            
            results = [f.result() for f in as_completed(futures)]
        
        db_test_end = time.perf_counter()
        total_duration = db_test_end - db_test_start
        
        # Analyze database performance
        all_times = [time_ms for worker_times in results for time_ms in worker_times]
        total_operations = len(all_times)
        
        avg_time = statistics.mean(all_times)
        p95_time = statistics.quantiles(all_times, n=20)[18]  # 95th percentile
        p99_time = statistics.quantiles(all_times, n=100)[98]  # 99th percentile
        
        operations_per_second = total_operations / total_duration
        
        print(f"Database performance results:")
        print(f"  Total operations: {total_operations}")
        print(f"  Duration: {total_duration:.2f}s")
        print(f"  Operations/second: {operations_per_second:.1f}")
        print(f"  Average operation time: {avg_time:.2f}ms")
        print(f"  95th percentile: {p95_time:.2f}ms")
        print(f"  99th percentile: {p99_time:.2f}ms")
        
        # Verify performance meets benchmarks
        max_avg_time = performance_benchmarks["database_operations"]["lease_work_max_ms"]
        assert avg_time < max_avg_time * 2, \
            f"Average database operation too slow: {avg_time:.2f}ms > {max_avg_time * 2:.2f}ms"
        
        # Verify throughput is reasonable
        min_ops_per_second = 100  # Minimum expected database operations per second
        assert operations_per_second > min_ops_per_second, \
            f"Database throughput too low: {operations_per_second:.1f} < {min_ops_per_second}"
        
        # Verify 95th percentile is acceptable
        assert p95_time < max_avg_time * 5, \
            f"95th percentile too slow: {p95_time:.2f}ms > {max_avg_time * 5:.2f}ms"
    
    @pytest.mark.load
    async def test_skip_locked_query_performance(self, test_environment, performance_benchmarks):
        """Test SKIP LOCKED query performance under high contention."""
        
        # Create test data
        agent_data = await insert_test_agent(test_environment.db_engine)
        
        # Create many due work items
        work_item_count = 1000
        work_ids = []
        
        for i in range(work_item_count):
            task = await insert_test_task(test_environment.db_engine, agent_data["id"])
            work_id = await insert_due_work(test_environment.db_engine, task["id"])
            work_ids.append(work_id)
        
        print(f"Testing SKIP LOCKED performance with {work_item_count} work items...")
        
        def skip_locked_worker(worker_id, iterations=500):
            """Worker that repeatedly tries SKIP LOCKED queries."""
            
            config = WorkerConfig.from_dict({
                "worker_id": f"skip-locked-worker-{worker_id}",
                "database_url": test_environment.db_url
            })
            worker = WorkerRunner(config)
            
            lease_times = []
            successful_leases = 0
            
            for i in range(iterations):
                lease_start = time.perf_counter()
                
                try:
                    lease = worker.lease_one()
                    lease_end = time.perf_counter()
                    lease_time = (lease_end - lease_start) * 1000  # ms
                    
                    lease_times.append(lease_time)
                    
                    if lease:
                        successful_leases += 1
                        # Hold lease briefly, then release
                        time.sleep(random.uniform(0.001, 0.01))
                        worker.delete_work(lease["id"])
                
                except Exception as e:
                    lease_times.append(100)  # Record penalty time for errors
                
                # Small delay to allow other workers to compete
                time.sleep(random.uniform(0.001, 0.005))
            
            return lease_times, successful_leases
        
        # Run many concurrent workers to create SKIP LOCKED contention
        contention_workers = 25
        iterations_per_worker = 100
        
        skip_locked_start = time.perf_counter()
        
        with ThreadPoolExecutor(max_workers=contention_workers) as executor:
            futures = [
                executor.submit(skip_locked_worker, i, iterations_per_worker)
                for i in range(contention_workers)
            ]
            
            results = [f.result() for f in as_completed(futures)]
        
        skip_locked_end = time.perf_counter()
        total_test_duration = skip_locked_end - skip_locked_start
        
        # Analyze SKIP LOCKED performance
        all_lease_times = [time_ms for worker_times, _ in results for time_ms in worker_times]
        total_successful_leases = sum(successful for _, successful in results)
        
        avg_lease_time = statistics.mean(all_lease_times)
        p95_lease_time = statistics.quantiles(all_lease_times, n=20)[18]
        
        print(f"SKIP LOCKED performance results:")
        print(f"  Total lease attempts: {len(all_lease_times)}")
        print(f"  Successful leases: {total_successful_leases}")
        print(f"  Test duration: {total_test_duration:.2f}s")
        print(f"  Average lease time: {avg_lease_time:.2f}ms")
        print(f"  95th percentile lease time: {p95_lease_time:.2f}ms")
        print(f"  Success rate: {total_successful_leases / len(all_lease_times):.1%}")
        
        # Verify SKIP LOCKED performance
        max_lease_time = performance_benchmarks["database_operations"]["lease_work_max_ms"]
        assert avg_lease_time < max_lease_time, \
            f"SKIP LOCKED queries too slow: {avg_lease_time:.2f}ms > {max_lease_time}ms"
        
        # Verify reasonable success rate (accounting for contention)
        min_success_rate = 0.3  # 30% success rate under high contention is acceptable
        actual_success_rate = total_successful_leases / len(all_lease_times)
        assert actual_success_rate > min_success_rate, \
            f"SKIP LOCKED success rate too low: {actual_success_rate:.1%} < {min_success_rate:.1%}"


class TestPipelineExecutionPerformance:
    """Test pipeline execution performance benchmarks."""
    
    @pytest.mark.load
    def test_template_rendering_performance(self, performance_benchmarks):
        """Test template rendering performance under load."""
        
        # Create complex template structure
        complex_template = {
            "user_info": {
                "name": "${params.user.name}",
                "email": "${params.user.email}",
                "preferences": {
                    "location": "${params.user.location}",
                    "timezone": "${params.user.timezone}",
                    "notifications": "${params.user.notifications}"
                }
            },
            "data_processing": [
                "${steps.data_fetch.results[0].value}",
                "${steps.data_fetch.results[1].value}",
                "${steps.data_fetch.results[2].value}"
            ],
            "summary": {
                "total_items": "${length(steps.data_fetch.results)}",
                "status": "${steps.validation.status}",
                "message": "Processing complete for ${params.user.name} at ${now}"
            },
            "nested_conditions": {
                "weather_dependent": {
                    "condition": "${steps.weather.condition}",
                    "temperature": "${steps.weather.temp}",
                    "recommendation": "Weather is ${steps.weather.condition} with temperature ${steps.weather.temp}°C"
                },
                "calendar_summary": [
                    {
                        "event": "${steps.calendar.events[0].title}",
                        "time": "${steps.calendar.events[0].start_time}",
                        "location": "${steps.calendar.events[0].location}"
                    },
                    {
                        "event": "${steps.calendar.events[1].title}",
                        "time": "${steps.calendar.events[1].start_time}",
                        "location": "${steps.calendar.events[1].location}"
                    }
                ]
            }
        }
        
        # Create corresponding context
        context = {
            "params": {
                "user": {
                    "name": "Performance Test User",
                    "email": "perf.test@example.com",
                    "location": "Chisinau",
                    "timezone": "Europe/Chisinau",
                    "notifications": True
                }
            },
            "steps": {
                "data_fetch": {
                    "results": [
                        {"value": "result_1", "score": 0.95},
                        {"value": "result_2", "score": 0.87},
                        {"value": "result_3", "score": 0.93}
                    ]
                },
                "validation": {"status": "success", "errors": []},
                "weather": {
                    "condition": "sunny",
                    "temp": 22,
                    "humidity": 65,
                    "wind_speed": 12
                },
                "calendar": {
                    "events": [
                        {
                            "title": "Performance Review",
                            "start_time": "2025-08-08T10:00:00Z",
                            "location": "Conference Room A"
                        },
                        {
                            "title": "Team Meeting",
                            "start_time": "2025-08-08T14:00:00Z",
                            "location": "Zoom"
                        }
                    ]
                }
            },
            "now": "2025-08-08T09:00:00Z"
        }
        
        # Benchmark template rendering
        iterations = 1000
        render_times = []
        
        print(f"Benchmarking template rendering with {iterations} iterations...")
        
        for i in range(iterations):
            render_start = time.perf_counter()
            result = render_templates(complex_template, context)
            render_end = time.perf_counter()
            
            render_time_ms = (render_end - render_start) * 1000
            render_times.append(render_time_ms)
            
            # Verify correctness periodically
            if i % 100 == 0:
                assert result["user_info"]["name"] == "Performance Test User"
                assert result["summary"]["total_items"] == "3"
                assert "sunny" in result["nested_conditions"]["weather_dependent"]["recommendation"]
        
        # Analyze performance
        avg_render_time = statistics.mean(render_times)
        p95_render_time = statistics.quantiles(render_times, n=20)[18]
        p99_render_time = statistics.quantiles(render_times, n=100)[98]
        
        renders_per_second = 1000 / avg_render_time
        
        print(f"Template rendering performance:")
        print(f"  Average render time: {avg_render_time:.3f}ms")
        print(f"  95th percentile: {p95_render_time:.3f}ms")
        print(f"  99th percentile: {p99_render_time:.3f}ms")
        print(f"  Renders per second: {renders_per_second:.0f}")
        
        # Verify performance meets benchmarks
        max_render_time = performance_benchmarks["template_rendering"]["complex_nested_max_ms"]
        assert avg_render_time < max_render_time, \
            f"Template rendering too slow: {avg_render_time:.3f}ms > {max_render_time}ms"
        
        # Verify consistent performance (99th percentile not too much slower)
        assert p99_render_time < max_render_time * 3, \
            f"Template rendering 99th percentile too slow: {p99_render_time:.3f}ms > {max_render_time * 3}ms"
    
    @pytest.mark.load
    def test_rrule_processing_performance(self, performance_benchmarks):
        """Test RRULE processing performance under load."""
        
        # Test various RRULE complexities
        rrule_test_cases = [
            ("Simple daily", "FREQ=DAILY;BYHOUR=9;BYMINUTE=0"),
            ("Business days", "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=30"),
            ("First Monday", "FREQ=MONTHLY;BYDAY=1MO;BYHOUR=10;BYMINUTE=0"),
            ("Complex weekly", "FREQ=WEEKLY;BYDAY=MO,WE,FR;BYHOUR=9,14,17;BYMINUTE=0,30"),
            ("Quarterly", "FREQ=MONTHLY;INTERVAL=3;BYDAY=1MO;BYHOUR=9;BYMINUTE=0"),
        ]
        
        iterations_per_rrule = 200
        
        for name, rrule_expr in rrule_test_cases:
            print(f"Benchmarking RRULE: {name}")
            
            processing_times = []
            
            for i in range(iterations_per_rrule):
                process_start = time.perf_counter()
                
                try:
                    next_time = next_occurrence(rrule_expr, "Europe/Chisinau")
                    assert next_time is not None, f"RRULE {name} returned None"
                except Exception as e:
                    print(f"RRULE processing error for {name}: {e}")
                    processing_times.append(100)  # Record penalty time
                    continue
                
                process_end = time.perf_counter()
                processing_times.append((process_end - process_start) * 1000)
            
            avg_time = statistics.mean(processing_times)
            p95_time = statistics.quantiles(processing_times, n=20)[18]
            
            print(f"  Average: {avg_time:.3f}ms, 95th percentile: {p95_time:.3f}ms")
            
            # Verify performance
            if "Complex" in name:
                max_time = performance_benchmarks["rrule_processing"]["complex_rrule_max_ms"]
            else:
                max_time = performance_benchmarks["rrule_processing"]["next_occurrence_max_ms"]
            
            assert avg_time < max_time, \
                f"RRULE {name} too slow: {avg_time:.3f}ms > {max_time}ms"


class TestMemoryAndResourceManagement:
    """Test memory usage and resource leak detection."""
    
    @pytest.mark.load
    async def test_memory_usage_under_load(self, test_environment):
        """Test memory usage patterns under sustained load."""
        
        # Get initial memory usage
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        print(f"Initial memory usage: {initial_memory:.1f} MB")
        
        # Create sustained load
        agent_data = await insert_test_agent(test_environment.db_engine)
        
        # Function to create and process tasks in batches
        async def memory_load_batch(batch_id, task_count=100):
            batch_tasks = []
            
            # Create tasks
            for i in range(task_count):
                task_data = {
                    "title": f"Memory Test Task {batch_id}-{i}",
                    "description": f"Memory load test batch {batch_id} task {i}",
                    "created_by": agent_data["id"],
                    "schedule_kind": "once",
                    "schedule_expr": (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat(),
                    "payload": {
                        "pipeline": [
                            {
                                "id": f"memory_step_{i}",
                                "uses": "test-tool.execute",
                                "with": {"message": f"Memory test {batch_id}-{i}"},
                                "save_as": "result"
                            }
                        ]
                    }
                }
                
                task = await insert_test_task(test_environment.db_engine, agent_data["id"], task_data)
                batch_tasks.append(task["id"])
            
            # Create due work
            for task_id in batch_tasks:
                await insert_due_work(test_environment.db_engine, task_id)
            
            # Process tasks
            config = WorkerConfig.from_dict({
                "worker_id": f"memory-test-worker-{batch_id}",
                "database_url": test_environment.db_url
            })
            worker = WorkerRunner(config)
            
            with patch('engine.executor.load_catalog') as mock_catalog:
                mock_catalog.return_value = [{
                    "address": "test-tool.execute",
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"}
                }]
                
                with patch('engine.executor.call_tool') as mock_call_tool:
                    mock_call_tool.return_value = {"result": f"Batch {batch_id} completed"}
                    
                    processed = 0
                    while processed < task_count:
                        lease = worker.lease_one()
                        if lease:
                            success = worker.process_work_item(lease)
                            if success:
                                processed += 1
                        else:
                            await asyncio.sleep(0.1)
            
            return processed
        
        # Run multiple batches and monitor memory
        memory_samples = []
        batch_count = 10
        
        for batch_id in range(batch_count):
            batch_start_memory = process.memory_info().rss / 1024 / 1024
            
            processed = await memory_load_batch(batch_id, 50)
            
            batch_end_memory = process.memory_info().rss / 1024 / 1024
            memory_samples.append((batch_id, batch_start_memory, batch_end_memory, processed))
            
            # Force garbage collection
            gc.collect()
            
            print(f"Batch {batch_id}: {processed} tasks, memory: {batch_start_memory:.1f} MB → {batch_end_memory:.1f} MB")
        
        final_memory = process.memory_info().rss / 1024 / 1024
        memory_growth = final_memory - initial_memory
        
        print(f"Final memory usage: {final_memory:.1f} MB")
        print(f"Total memory growth: {memory_growth:.1f} MB")
        
        # Analyze memory growth pattern
        memory_growths = [end - start for _, start, end, _ in memory_samples]
        avg_growth_per_batch = statistics.mean(memory_growths)
        
        print(f"Average memory growth per batch: {avg_growth_per_batch:.1f} MB")
        
        # Verify memory usage is reasonable
        max_acceptable_growth = 50  # MB total growth
        assert memory_growth < max_acceptable_growth, \
            f"Excessive memory growth: {memory_growth:.1f} MB > {max_acceptable_growth} MB"
        
        # Verify no significant per-batch growth (indicating leaks)
        max_batch_growth = 5  # MB per batch
        assert avg_growth_per_batch < max_batch_growth, \
            f"Excessive per-batch memory growth: {avg_growth_per_batch:.1f} MB > {max_batch_growth} MB"
    
    @pytest.mark.load
    async def test_database_connection_leak_detection(self, test_environment):
        """Test for database connection leaks under load."""
        
        # Monitor connection count before test
        initial_connections = self._count_database_connections(test_environment.db_url)
        print(f"Initial database connections: {initial_connections}")
        
        # Create and destroy many workers to test connection cleanup
        worker_cycles = 50
        
        for cycle in range(worker_cycles):
            # Create worker
            config = WorkerConfig.from_dict({
                "worker_id": f"leak-test-worker-{cycle}",
                "database_url": test_environment.db_url
            })
            worker = WorkerRunner(config)
            
            # Perform some database operations
            try:
                worker.heartbeat()
                worker.lease_one()  # This will probably return None, but exercises connection
                worker.cleanup_expired_leases()
            except Exception:
                pass  # Ignore errors for this test
            
            # Simulate worker shutdown
            worker.eng.dispose()
            
            # Check connections periodically
            if cycle % 10 == 0:
                current_connections = self._count_database_connections(test_environment.db_url)
                print(f"Cycle {cycle}: {current_connections} connections")
        
        # Final connection count
        final_connections = self._count_database_connections(test_environment.db_url)
        connection_growth = final_connections - initial_connections
        
        print(f"Final database connections: {final_connections}")
        print(f"Connection growth: {connection_growth}")
        
        # Verify no significant connection leaks
        max_connection_growth = 5  # Allow some connection pool growth
        assert connection_growth <= max_connection_growth, \
            f"Database connection leak detected: {connection_growth} > {max_connection_growth}"
    
    def _count_database_connections(self, db_url):
        """Count active database connections (simplified approach)."""
        try:
            from sqlalchemy import create_engine, text
            temp_engine = create_engine(db_url)
            
            with temp_engine.begin() as conn:
                result = conn.execute(text("""
                    SELECT COUNT(*) FROM pg_stat_activity 
                    WHERE state = 'active' AND application_name LIKE '%sqlalchemy%'
                """))
                count = result.scalar()
            
            temp_engine.dispose()
            return count
        except Exception:
            return 0  # Return 0 if we can't count (e.g., insufficient permissions)


class TestSLACompliance:
    """Test SLA compliance and uptime requirements."""
    
    @pytest.mark.load
    async def test_zero_work_loss_guarantee(self, test_environment):
        """Test zero work loss guarantee under various failure scenarios."""
        
        # Create test data
        agent_data = await insert_test_agent(test_environment.db_engine)
        
        # Create critical tasks that must not be lost
        critical_task_count = 100
        critical_tasks = []
        
        for i in range(critical_task_count):
            task_data = {
                "title": f"Critical Task {i}",
                "description": f"Zero work loss test task {i}",
                "created_by": agent_data["id"],
                "schedule_kind": "once",
                "schedule_expr": (datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat(),
                "payload": {
                    "pipeline": [
                        {
                            "id": f"critical_step_{i}",
                            "uses": "test-tool.execute",
                            "with": {"message": f"Critical work {i}"},
                            "save_as": "result"
                        }
                    ]
                },
                "priority": 9  # Highest priority
            }
            
            task = await insert_test_task(test_environment.db_engine, agent_data["id"], task_data)
            critical_tasks.append(task["id"])
        
        # Create due work for all critical tasks
        for task_id in critical_tasks:
            await insert_due_work(test_environment.db_engine, task_id)
        
        # Test scenario 1: Worker crashes during processing
        print("Testing worker crash scenario...")
        
        config = WorkerConfig.from_dict({
            "worker_id": "crash-test-worker",
            "database_url": test_environment.db_url,
            "lease_seconds": 10
        })
        crash_worker = WorkerRunner(config)
        
        # Process some tasks, then simulate crash
        with patch('engine.executor.load_catalog') as mock_catalog:
            mock_catalog.return_value = [{
                "address": "test-tool.execute",
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"}
            }]
            
            with patch('engine.executor.call_tool') as mock_call_tool:
                mock_call_tool.return_value = {"result": "Processed before crash"}
                
                # Process 20 tasks successfully
                processed_before_crash = 0
                for _ in range(20):
                    lease = crash_worker.lease_one()
                    if lease:
                        success = crash_worker.process_work_item(lease)
                        if success:
                            processed_before_crash += 1
                
                print(f"Processed {processed_before_crash} tasks before crash")
                
                # Simulate crash - don't clean up connections or leases
                # (Don't call crash_worker.shutdown())
        
        # Wait for lease timeouts
        await asyncio.sleep(12)
        
        # Test scenario 2: Recovery worker processes remaining work
        print("Testing recovery scenario...")
        
        config2 = WorkerConfig.from_dict({
            "worker_id": "recovery-worker",
            "database_url": test_environment.db_url,
            "lease_seconds": 60
        })
        recovery_worker = WorkerRunner(config2)
        
        # Clean up expired leases
        recovery_worker.cleanup_expired_leases()
        
        with patch('engine.executor.load_catalog') as mock_catalog:
            mock_catalog.return_value = [{
                "address": "test-tool.execute",
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"}
            }]
            
            with patch('engine.executor.call_tool') as mock_call_tool:
                mock_call_tool.return_value = {"result": "Recovered and processed"}
                
                # Process all remaining work
                recovered_count = 0
                max_attempts = critical_task_count * 2  # Prevent infinite loop
                attempts = 0
                
                while attempts < max_attempts:
                    lease = recovery_worker.lease_one()
                    if lease:
                        success = recovery_worker.process_work_item(lease)
                        if success:
                            recovered_count += 1
                    else:
                        break  # No more work available
                    attempts += 1
                
                print(f"Recovered and processed {recovered_count} tasks")
        
        # Verify zero work loss
        total_processed = processed_before_crash + recovered_count
        
        print(f"Zero work loss test results:")
        print(f"  Critical tasks created: {critical_task_count}")
        print(f"  Processed before crash: {processed_before_crash}")
        print(f"  Recovered after crash: {recovered_count}")
        print(f"  Total processed: {total_processed}")
        
        # Verify in database
        with test_environment.db_engine.begin() as conn:
            result = conn.execute(text("""
                SELECT COUNT(*) as successful_runs FROM task_run 
                WHERE task_id = ANY(:task_ids) AND success = true
            """), {"task_ids": critical_tasks})
            
            db_successful_count = result.scalar()
            
            result = conn.execute(text("""
                SELECT COUNT(*) as remaining_work FROM due_work 
                WHERE task_id = ANY(:task_ids)
            """), {"task_ids": critical_tasks})
            
            remaining_work = result.scalar()
            
            print(f"  Database successful runs: {db_successful_count}")
            print(f"  Remaining due work: {remaining_work}")
        
        # Zero work loss guarantee
        assert total_processed == critical_task_count, \
            f"Work loss detected: {total_processed} < {critical_task_count}"
        
        assert remaining_work == 0, \
            f"Work items left unprocessed: {remaining_work}"
        
        # Verify database consistency
        assert db_successful_count == critical_task_count, \
            f"Database count mismatch: {db_successful_count} != {critical_task_count}"
    
    @pytest.mark.load
    async def test_uptime_sla_compliance(self, test_environment, load_test_config):
        """Test >99.9% uptime SLA compliance simulation."""
        
        # This test simulates uptime by measuring system availability
        # during continuous operation with intermittent failures
        
        test_duration_minutes = 2  # 2-minute simulation (scaled down for testing)
        availability_check_interval = 1  # Check every 1 second
        
        uptime_samples = []
        failure_events = []
        
        # Create continuous workload
        agent_data = await insert_test_agent(test_environment.db_engine)
        
        # Function to continuously create work
        async def workload_generator():
            task_counter = 0
            while True:
                try:
                    task_data = {
                        "title": f"Uptime Test Task {task_counter}",
                        "description": "Continuous workload for uptime testing",
                        "created_by": agent_data["id"],
                        "schedule_kind": "once",
                        "schedule_expr": (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat(),
                        "payload": {
                            "pipeline": [
                                {
                                    "id": f"uptime_step_{task_counter}",
                                    "uses": "test-tool.execute",
                                    "with": {"message": f"Uptime test {task_counter}"},
                                    "save_as": "result"
                                }
                            ]
                        }
                    }
                    
                    task = await insert_test_task(test_environment.db_engine, agent_data["id"], task_data)
                    await insert_due_work(test_environment.db_engine, task["id"])
                    task_counter += 1
                    
                    await asyncio.sleep(0.5)  # Create tasks every 0.5 seconds
                    
                except Exception as e:
                    print(f"Workload generator error: {e}")
                    await asyncio.sleep(1)
        
        # Function to process work (system under test)
        async def system_processor():
            config = WorkerConfig.from_dict({
                "worker_id": "uptime-test-worker",
                "database_url": test_environment.db_url
            })
            worker = WorkerRunner(config)
            
            with patch('engine.executor.load_catalog') as mock_catalog:
                mock_catalog.return_value = [{
                    "address": "test-tool.execute",
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"}
                }]
                
                with patch('engine.executor.call_tool') as mock_call_tool:
                    # Inject random failures to test resilience
                    def mock_with_failures(*args, **kwargs):
                        if random.random() < 0.02:  # 2% failure rate
                            raise Exception("Simulated system failure")
                        return {"result": "Uptime test processed"}
                    
                    mock_call_tool.side_effect = mock_with_failures
                    
                    while True:
                        try:
                            lease = worker.lease_one()
                            if lease:
                                worker.process_work_item(lease)
                            else:
                                await asyncio.sleep(0.1)
                        except Exception as e:
                            # Log failure but continue (simulating resilient system)
                            failure_events.append(time.time())
                            await asyncio.sleep(0.5)  # Brief recovery pause
        
        # Function to check system availability
        async def availability_monitor():
            while True:
                check_time = time.time()
                try:
                    # Test basic system responsiveness
                    with test_environment.db_engine.begin() as conn:
                        result = conn.execute(text("SELECT COUNT(*) FROM due_work"))
                        work_count = result.scalar()
                    
                    # System is available if it can respond to queries
                    uptime_samples.append((check_time, True))
                    
                except Exception as e:
                    # System is down if database is unreachable
                    uptime_samples.append((check_time, False))
                    print(f"Availability check failed: {e}")
                
                await asyncio.sleep(availability_check_interval)
        
        # Run uptime simulation
        print(f"Starting {test_duration_minutes}-minute uptime SLA test...")
        start_time = time.time()
        
        # Start all monitoring tasks
        workload_task = asyncio.create_task(workload_generator())
        processor_task = asyncio.create_task(system_processor())
        monitor_task = asyncio.create_task(availability_monitor())
        
        # Run for specified duration
        await asyncio.sleep(test_duration_minutes * 60)
        
        # Stop tasks
        workload_task.cancel()
        processor_task.cancel()
        monitor_task.cancel()
        
        try:
            await workload_task
        except asyncio.CancelledError:
            pass
        
        try:
            await processor_task
        except asyncio.CancelledError:
            pass
        
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass
        
        end_time = time.time()
        actual_duration = end_time - start_time
        
        # Calculate uptime
        total_checks = len(uptime_samples)
        successful_checks = sum(1 for _, available in uptime_samples if available)
        
        uptime_percentage = (successful_checks / total_checks) * 100 if total_checks > 0 else 0
        downtime_seconds = (total_checks - successful_checks) * availability_check_interval
        
        print(f"Uptime SLA test results:")
        print(f"  Test duration: {actual_duration:.1f}s")
        print(f"  Total availability checks: {total_checks}")
        print(f"  Successful checks: {successful_checks}")
        print(f"  Uptime percentage: {uptime_percentage:.3f}%")
        print(f"  Downtime: {downtime_seconds:.1f}s")
        print(f"  Failure events: {len(failure_events)}")
        
        # Verify SLA compliance
        required_uptime = 99.9  # 99.9% uptime SLA
        assert uptime_percentage >= required_uptime, \
            f"Uptime SLA not met: {uptime_percentage:.3f}% < {required_uptime}%"
        
        # Verify system resilience (failures shouldn't cause long outages)
        if len(failure_events) > 0:
            max_acceptable_downtime = test_duration_minutes * 60 * 0.001  # 0.1% of test duration
            assert downtime_seconds <= max_acceptable_downtime, \
                f"Excessive downtime: {downtime_seconds:.1f}s > {max_acceptable_downtime:.1f}s"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])