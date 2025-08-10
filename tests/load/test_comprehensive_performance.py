#!/usr/bin/env python3
"""
Comprehensive Performance and Load Testing for Ordinaut

Tests system performance under various load conditions:
- High-throughput task processing
- Database connection pooling and scaling
- Memory usage and garbage collection
- Template rendering performance
- Pipeline execution optimization  
- Worker coordination efficiency
- API response times under load

These tests establish performance baselines and verify SLA compliance.
"""

import pytest
import asyncio
import time
import uuid
import json
import psutil
import statistics
import threading
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch, Mock
import gc

from engine.template import render_templates, extract_template_variables
from engine.executor import run_pipeline
from engine.rruler import RRuleProcessor
from api.main import app
from fastapi.testclient import TestClient
from sqlalchemy import text


class PerformanceMonitor:
    """Monitor system performance metrics during testing."""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        """Reset all metrics."""
        self.cpu_samples = []
        self.memory_samples = []
        self.start_time = None
        self.end_time = None
        self.monitoring = False
        self._monitor_thread = None
    
    def start_monitoring(self, sample_interval=0.1):
        """Start monitoring system resources."""
        self.reset()
        self.start_time = time.time()
        self.monitoring = True
        
        def monitor_loop():
            while self.monitoring:
                # Get CPU and memory usage
                cpu_percent = psutil.cpu_percent()
                memory_info = psutil.virtual_memory()
                
                self.cpu_samples.append(cpu_percent)
                self.memory_samples.append(memory_info.percent)
                
                time.sleep(sample_interval)
        
        self._monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self._monitor_thread.start()
    
    def stop_monitoring(self):
        """Stop monitoring and return summary stats."""
        self.monitoring = False
        self.end_time = time.time()
        
        if self._monitor_thread:
            self._monitor_thread.join(timeout=1.0)
        
        return {
            "duration_seconds": self.end_time - self.start_time,
            "cpu_usage": {
                "mean": statistics.mean(self.cpu_samples) if self.cpu_samples else 0,
                "max": max(self.cpu_samples) if self.cpu_samples else 0,
                "samples": len(self.cpu_samples)
            },
            "memory_usage": {
                "mean": statistics.mean(self.memory_samples) if self.memory_samples else 0,
                "max": max(self.memory_samples) if self.memory_samples else 0,
                "samples": len(self.memory_samples)
            }
        }


@pytest.fixture
def performance_monitor():
    """Fixture providing performance monitoring."""
    return PerformanceMonitor()


@pytest.mark.load
@pytest.mark.benchmark
class TestTemplateRenderingPerformance:
    """Test template rendering performance under various loads."""
    
    def test_simple_template_rendering_benchmark(self, benchmark):
        """Benchmark simple template rendering performance."""
        
        template = "Hello ${name}, welcome to ${location}!"
        context = {"name": "Alice", "location": "Chisinau"}
        
        def render_template():
            return render_templates(template, context)
        
        result = benchmark(render_template)
        
        assert result == "Hello Alice, welcome to Chisinau!"
        # Should complete in under 1ms
        assert benchmark.stats.mean < 0.001
    
    def test_complex_nested_template_benchmark(self, benchmark):
        """Benchmark complex nested template rendering."""
        
        complex_template = {
            "user": {
                "greeting": "Hello ${user.name}",
                "profile": {
                    "location": "${user.profile.city}, ${user.profile.country}",
                    "preferences": ["${user.preferences[0]}", "${user.preferences[1]}"]
                }
            },
            "tasks": [
                {
                    "title": "${tasks[0].title}",
                    "status": "${tasks[0].status}",
                    "due": "${tasks[0].due_date}"
                },
                {
                    "title": "${tasks[1].title}", 
                    "status": "${tasks[1].status}",
                    "due": "${tasks[1].due_date}"
                }
            ],
            "summary": "User ${user.name} has ${length(tasks)} tasks in ${user.profile.city}"
        }
        
        context = {
            "user": {
                "name": "Bob",
                "profile": {
                    "city": "Chisinau",
                    "country": "Moldova"
                },
                "preferences": ["coding", "coffee"]
            },
            "tasks": [
                {"title": "Review code", "status": "pending", "due_date": "2025-08-09"},
                {"title": "Write docs", "status": "in_progress", "due_date": "2025-08-10"}
            ]
        }
        
        def render_complex():
            return render_templates(complex_template, context)
        
        result = benchmark(render_complex)
        
        assert result["user"]["greeting"] == "Hello Bob"
        assert result["user"]["profile"]["location"] == "Chisinau, Moldova"
        assert result["tasks"][0]["title"] == "Review code"
        # Should complete in under 5ms
        assert benchmark.stats.mean < 0.005
    
    def test_large_template_performance(self, benchmark, performance_monitor):
        """Test performance with large templates and contexts."""
        
        # Create large template structure
        large_template = {
            "pipeline": [
                {
                    "id": f"step_{i}",
                    "uses": f"tool-{i % 10}.action",
                    "with": {
                        f"param_{j}": f"${{steps.step_{i-1}.output.field_{j}}}"
                        for j in range(20)
                    } if i > 0 else {"initial": "value"},
                    "save_as": f"result_{i}"
                }
                for i in range(50)
            ],
            "params": {f"global_param_{k}": f"${{env.param_{k}}}" for k in range(100)}
        }
        
        # Create large context
        large_context = {
            "steps": {
                f"step_{i}": {
                    "output": {f"field_{j}": f"value_{i}_{j}" for j in range(20)}
                }
                for i in range(50)
            },
            "env": {f"param_{k}": f"env_value_{k}" for k in range(100)}
        }
        
        performance_monitor.start_monitoring()
        
        def render_large():
            return render_templates(large_template, large_context)
        
        result = benchmark(render_large)
        
        perf_stats = performance_monitor.stop_monitoring()
        
        # Verify results
        assert len(result["pipeline"]) == 50
        assert len(result["params"]) == 100
        
        # Performance requirements
        assert benchmark.stats.mean < 0.050, f"Large template too slow: {benchmark.stats.mean*1000:.1f}ms"
        assert perf_stats["memory_usage"]["max"] < 90, f"Memory usage too high: {perf_stats['memory_usage']['max']:.1f}%"
        
        print(f"Large template performance: {benchmark.stats.mean*1000:.2f}ms avg, {perf_stats['memory_usage']['max']:.1f}% max memory")
    
    def test_variable_extraction_performance(self, benchmark):
        """Test performance of template variable extraction."""
        
        # Template with many variables
        template_with_variables = {
            "pipeline": [
                {
                    "step": f"step_{i}",
                    "input": f"${{params.input_{i}}}",
                    "previous": f"${{steps.step_{i-1}.output}}" if i > 0 else None,
                    "config": {
                        "nested": f"${{config.section_{i}.value}}",
                        "array": [f"${{array[{j}].field}}" for j in range(5)]
                    }
                }
                for i in range(100)
            ]
        }
        
        def extract_vars():
            return extract_template_variables(template_with_variables)
        
        variables = benchmark(extract_vars)
        
        # Should find all variables
        assert len(variables) > 500  # Many variables in the template
        assert "params.input_0" in variables
        assert "steps.step_99.output" in variables
        assert "config.section_50.value" in variables
        
        # Should be fast
        assert benchmark.stats.mean < 0.010, f"Variable extraction too slow: {benchmark.stats.mean*1000:.1f}ms"
    
    def test_concurrent_template_rendering(self, performance_monitor):
        """Test template rendering under concurrent load."""
        
        template = {
            "message": "Processing ${params.item_id}",
            "details": {
                "user": "${params.user}",
                "timestamp": "${params.timestamp}",
                "data": "${params.data}"
            }
        }
        
        # Generate contexts for concurrent rendering
        contexts = [
            {
                "params": {
                    "item_id": i,
                    "user": f"user_{i}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "data": {"value": i * 10, "status": "active"}
                }
            }
            for i in range(1000)
        ]
        
        performance_monitor.start_monitoring()
        
        def render_item(context):
            return render_templates(template, context)
        
        # Concurrent rendering
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(render_item, ctx) for ctx in contexts]
            results = [future.result() for future in as_completed(futures)]
        
        end_time = time.time()
        total_time = end_time - start_time
        
        perf_stats = performance_monitor.stop_monitoring()
        
        # Verify all completed
        assert len(results) == 1000
        
        # Check a few results
        for i, result in enumerate(results[:5]):
            assert f"Processing {i}" in result["message"]
            assert result["details"]["user"] == f"user_{i}"
        
        # Performance requirements
        throughput = len(results) / total_time
        assert throughput > 100, f"Concurrent rendering too slow: {throughput:.1f} renders/sec"
        assert perf_stats["cpu_usage"]["max"] < 95, f"CPU usage too high: {perf_stats['cpu_usage']['max']:.1f}%"
        
        print(f"Concurrent template rendering: {throughput:.1f} renders/sec, {perf_stats['cpu_usage']['max']:.1f}% max CPU")


@pytest.mark.load
@pytest.mark.benchmark
class TestPipelineExecutionPerformance:
    """Test pipeline execution performance under load."""
    
    @patch('engine.executor.call_tool')
    @patch('engine.executor.load_catalog')
    async def test_simple_pipeline_benchmark(self, mock_load_catalog, mock_call_tool, benchmark):
        """Benchmark simple pipeline execution performance."""
        
        # Setup mocks
        mock_load_catalog.return_value = [{
            "address": "test.fast",
            "transport": "http",
            "endpoint": "http://fast-service.com/api",
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "scopes": ["test"]
        }]
        
        mock_call_tool.return_value = {"result": "success", "execution_time": 1}
        
        pipeline = {
            "pipeline": [
                {
                    "id": "fast_step",
                    "uses": "test.fast",
                    "with": {"input": "test"},
                    "save_as": "fast_result"
                }
            ]
        }
        
        async def run_simple_pipeline():
            return await run_pipeline(pipeline)
        
        result = await benchmark(run_simple_pipeline)
        
        assert result["success"] is True
        assert "fast_result" in result["steps"]
        # Should complete in under 10ms
        assert benchmark.stats.mean < 0.010
    
    @patch('engine.executor.call_tool')
    @patch('engine.executor.load_catalog')
    async def test_multi_step_pipeline_performance(self, mock_load_catalog, mock_call_tool, benchmark):
        """Test multi-step pipeline performance."""
        
        # Setup tool catalog
        mock_load_catalog.return_value = [
            {
                "address": f"service_{i}.action",
                "transport": "http", 
                "endpoint": f"http://service-{i}.com/api",
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "scopes": ["test"]
            }
            for i in range(10)
        ]
        
        # Mock tool responses with varied timing
        def mock_tool_response(tool_def, step_config, tool_input):
            service_num = int(tool_def["address"].split('_')[1])
            processing_time = 0.001 + (service_num * 0.0002)  # 1-3ms variation
            time.sleep(processing_time)
            
            return {
                "result": f"service_{service_num}_result",
                "processing_time": processing_time,
                "input_data": tool_input
            }
        
        mock_call_tool.side_effect = mock_tool_response
        
        # Create multi-step pipeline
        pipeline = {
            "params": {"base_value": 100},
            "pipeline": [
                {
                    "id": f"step_{i}",
                    "uses": f"service_{i}.action",
                    "with": {
                        "value": "${params.base_value}" if i == 0 else f"${{steps.step_{i-1}.result}}",
                        "step_number": i
                    },
                    "save_as": f"result_{i}"
                }
                for i in range(10)
            ]
        }
        
        async def run_multi_step():
            return await run_pipeline(pipeline)
        
        result = await benchmark(run_multi_step)
        
        assert result["success"] is True
        assert len(result["steps"]) == 10
        
        # Verify data flow
        for i in range(10):
            assert f"result_{i}" in result["steps"]
            assert result["steps"][f"result_{i}"]["result"] == f"service_{i}_result"
        
        # Should complete in reasonable time despite 10 steps
        assert benchmark.stats.mean < 0.050, f"Multi-step pipeline too slow: {benchmark.stats.mean*1000:.1f}ms"
    
    @patch('engine.executor.call_tool')
    @patch('engine.executor.load_catalog') 
    async def test_concurrent_pipeline_execution(self, mock_load_catalog, mock_call_tool, performance_monitor):
        """Test concurrent pipeline execution performance."""
        
        # Setup fast mock tools
        mock_load_catalog.return_value = [{
            "address": "concurrent.test",
            "transport": "http",
            "endpoint": "http://concurrent-service.com/api",
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "scopes": ["test"]
        }]
        
        def concurrent_mock_response(*args, **kwargs):
            # Small random delay to simulate network
            time.sleep(0.001 + (time.time() % 0.002))
            return {"result": "concurrent_success", "timestamp": time.time()}
        
        mock_call_tool.side_effect = concurrent_mock_response
        
        # Create pipelines for concurrent execution
        pipelines = [
            {
                "params": {"pipeline_id": i, "input_data": f"data_{i}"},
                "pipeline": [
                    {
                        "id": "concurrent_step",
                        "uses": "concurrent.test", 
                        "with": {
                            "pipeline_id": "${params.pipeline_id}",
                            "data": "${params.input_data}"
                        },
                        "save_as": "concurrent_result"
                    }
                ]
            }
            for i in range(50)
        ]
        
        performance_monitor.start_monitoring()
        start_time = time.time()
        
        # Execute pipelines concurrently
        async def execute_all():
            tasks = [run_pipeline(pipeline) for pipeline in pipelines]
            return await asyncio.gather(*tasks)
        
        results = await execute_all()
        
        end_time = time.time()
        total_time = end_time - start_time
        perf_stats = performance_monitor.stop_monitoring()
        
        # Verify all completed successfully
        assert len(results) == 50
        assert all(result["success"] for result in results)
        
        # Performance metrics
        throughput = len(results) / total_time
        
        print(f"Concurrent pipeline execution:")
        print(f"  - Pipelines: {len(results)}")
        print(f"  - Total time: {total_time:.3f}s")
        print(f"  - Throughput: {throughput:.1f} pipelines/sec")
        print(f"  - Max CPU: {perf_stats['cpu_usage']['max']:.1f}%")
        print(f"  - Max Memory: {perf_stats['memory_usage']['max']:.1f}%")
        
        # Performance requirements
        assert throughput > 10, f"Concurrent execution too slow: {throughput:.1f} pipelines/sec"
        assert perf_stats["cpu_usage"]["max"] < 95, f"CPU usage too high: {perf_stats['cpu_usage']['max']:.1f}%"


@pytest.mark.load
@pytest.mark.benchmark
class TestDatabasePerformanceUnderLoad:
    """Test database operations performance under load."""
    
    async def test_high_volume_task_insertion(self, test_environment, clean_database, performance_monitor):
        """Test performance of inserting many tasks."""
        
        # Create test agent
        agent_id = str(uuid.uuid4())
        with test_environment.db_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO agent (id, name, scopes) 
                VALUES (:id, :name, :scopes)
            """), {
                "id": agent_id,
                "name": f"load-test-agent-{int(time.time())}",
                "scopes": ["test"]
            })
        
        performance_monitor.start_monitoring()
        start_time = time.time()
        
        # Insert large batch of tasks
        task_count = 1000
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
                    "title": f"Load Test Task {i}",
                    "description": f"High volume insertion test task {i}",
                    "created_by": agent_id,
                    "schedule_kind": "once",
                    "schedule_expr": (datetime.now(timezone.utc) + timedelta(minutes=i)).isoformat(),
                    "timezone": "Europe/Chisinau",
                    "payload": json.dumps({
                        "pipeline": [
                            {
                                "id": f"load_step_{i}",
                                "uses": "test.load",
                                "with": {"task_number": i},
                                "save_as": f"load_result_{i}"
                            }
                        ]
                    }),
                    "status": "active",
                    "priority": i % 10,
                    "max_retries": 3
                })
                task_ids.append(result.scalar())
        
        end_time = time.time()
        insertion_time = end_time - start_time
        perf_stats = performance_monitor.stop_monitoring()
        
        # Verify all tasks were inserted
        with test_environment.db_engine.begin() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM task WHERE created_by = :agent_id"), 
                                {"agent_id": agent_id}).scalar()
            assert count == task_count
        
        # Performance metrics
        insertion_rate = task_count / insertion_time
        
        print(f"High volume task insertion:")
        print(f"  - Tasks inserted: {task_count}")
        print(f"  - Insertion time: {insertion_time:.3f}s") 
        print(f"  - Insertion rate: {insertion_rate:.1f} tasks/sec")
        print(f"  - Max CPU: {perf_stats['cpu_usage']['max']:.1f}%")
        
        # Performance requirements
        assert insertion_rate > 100, f"Insertion too slow: {insertion_rate:.1f} tasks/sec"
        assert insertion_time < 15, f"Insertion took too long: {insertion_time:.1f}s"
    
    async def test_concurrent_work_leasing_performance(self, test_environment, clean_database, performance_monitor):
        """Test performance of concurrent work leasing with SKIP LOCKED."""
        
        # Create test data
        agent_id = str(uuid.uuid4())
        with test_environment.db_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO agent (id, name, scopes) VALUES (:id, :name, :scopes)
            """), {
                "id": agent_id,
                "name": f"leasing-test-agent-{int(time.time())}",
                "scopes": ["test"]
            })
        
        # Create many tasks with due work
        work_item_count = 500
        task_ids = []
        
        with test_environment.db_engine.begin() as conn:
            for i in range(work_item_count):
                # Insert task
                task_result = conn.execute(text("""
                    INSERT INTO task (title, description, created_by, schedule_kind,
                                    schedule_expr, timezone, payload, status, priority, max_retries)
                    VALUES (:title, :description, :created_by, :schedule_kind,
                           :schedule_expr, :timezone, :payload::jsonb, :status, :priority, :max_retries)
                    RETURNING id
                """), {
                    "title": f"Leasing Test Task {i}",
                    "description": f"Concurrent leasing test task {i}",
                    "created_by": agent_id,
                    "schedule_kind": "once",
                    "schedule_expr": datetime.now(timezone.utc).isoformat(),
                    "timezone": "Europe/Chisinau",
                    "payload": json.dumps({"pipeline": []}),
                    "status": "active",
                    "priority": i % 10,
                    "max_retries": 1
                })
                task_id = task_result.scalar()
                task_ids.append(task_id)
                
                # Insert due work
                conn.execute(text("""
                    INSERT INTO due_work (task_id, run_at)
                    VALUES (:task_id, now())
                """), {"task_id": task_id})
        
        performance_monitor.start_monitoring()
        
        # Simulate many concurrent workers leasing work
        lease_results = []
        lease_conflicts = 0
        
        def worker_leasing_simulation(worker_id):
            """Simulate worker leasing work items."""
            leased_items = []
            
            for _ in range(50):  # Each worker tries to lease up to 50 items
                try:
                    with test_environment.db_engine.begin() as conn:
                        # Try to lease work with SKIP LOCKED
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
                        update_result = conn.execute(text("""
                            UPDATE due_work 
                            SET locked_until = :lease_time, locked_by = :worker_id
                            WHERE id = :work_id
                        """), {
                            "lease_time": lease_time,
                            "worker_id": worker_id,
                            "work_id": work_id
                        })
                        
                        if update_result.rowcount > 0:
                            leased_items.append((work_id, task_id))
                            
                            # Simulate brief processing
                            time.sleep(0.001)
                            
                            # Complete work
                            conn.execute(text("""
                                INSERT INTO task_run (id, task_id, lease_owner, started_at,
                                                    finished_at, success, attempt, output)
                                VALUES (:id, :task_id, :lease_owner, now(), now(), true, 1, '{}')
                            """), {
                                "id": str(uuid.uuid4()),
                                "task_id": task_id,
                                "lease_owner": worker_id
                            })
                            
                            # Clean up due work
                            conn.execute(text("DELETE FROM due_work WHERE id = :work_id"), 
                                       {"work_id": work_id})
                
                except Exception as e:
                    if "could not obtain lock" in str(e).lower():
                        lease_conflicts += 1
                    # Continue trying
            
            return len(leased_items)
        
        # Run concurrent workers
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [
                executor.submit(worker_leasing_simulation, f"load-worker-{i}")
                for i in range(20)
            ]
            
            lease_results = [future.result() for future in as_completed(futures)]
        
        end_time = time.time()
        total_time = end_time - start_time
        perf_stats = performance_monitor.stop_monitoring()
        
        # Verify results
        total_leased = sum(lease_results)
        
        # Check remaining work
        with test_environment.db_engine.begin() as conn:
            remaining_work = conn.execute(text("SELECT COUNT(*) FROM due_work")).scalar()
            completed_runs = conn.execute(text("SELECT COUNT(*) FROM task_run WHERE success = true")).scalar()
        
        print(f"Concurrent work leasing performance:")
        print(f"  - Work items: {work_item_count}")
        print(f"  - Workers: 20")
        print(f"  - Total leased: {total_leased}")
        print(f"  - Remaining work: {remaining_work}")
        print(f"  - Completed runs: {completed_runs}")
        print(f"  - Total time: {total_time:.3f}s")
        print(f"  - Throughput: {total_leased / total_time:.1f} leases/sec")
        print(f"  - Lease conflicts: {lease_conflicts}")
        
        # Performance requirements
        assert total_leased >= work_item_count * 0.95, f"Too few items processed: {total_leased}/{work_item_count}"
        assert remaining_work == 0, f"Work items left unprocessed: {remaining_work}"
        assert total_leased / total_time > 50, f"Leasing throughput too low: {total_leased / total_time:.1f}/sec"


@pytest.mark.load
@pytest.mark.benchmark
class TestRRuleProcessingPerformance:
    """Test RRULE processing performance under various scenarios."""
    
    def test_simple_rrule_performance(self, benchmark):
        """Benchmark simple RRULE processing performance."""
        
        processor = RRuleProcessor("Europe/Chisinau")
        base_time = datetime(2025, 8, 8, 10, 0, 0)
        rrule = "FREQ=DAILY;BYHOUR=9;BYMINUTE=0"
        
        def process_simple_rrule():
            return processor.get_next_occurrence(rrule, base_time)
        
        result = benchmark(process_simple_rrule)
        
        assert result is not None
        assert result.hour == 9
        assert result.minute == 0
        # Should complete in under 1ms
        assert benchmark.stats.mean < 0.001
    
    def test_complex_rrule_performance(self, benchmark):
        """Benchmark complex RRULE processing performance."""
        
        processor = RRuleProcessor("Europe/Chisinau")
        base_time = datetime(2025, 8, 8, 10, 0, 0)
        
        # Complex RRULE: Every Monday, Wednesday, Friday at 9:00 and 14:30
        complex_rrule = "FREQ=WEEKLY;BYDAY=MO,WE,FR;BYHOUR=9,14;BYMINUTE=0,30"
        
        def process_complex_rrule():
            return processor.get_next_occurrence(complex_rrule, base_time)
        
        result = benchmark(process_complex_rrule)
        
        assert result is not None
        # Should complete in under 5ms even for complex rules
        assert benchmark.stats.mean < 0.005
    
    def test_rrule_performance_with_dst_transitions(self, benchmark):
        """Test RRULE performance around DST transitions."""
        
        processor = RRuleProcessor("Europe/Chisinau")
        
        # Test around spring forward (March 30, 2025)
        base_time = datetime(2025, 3, 29, 20, 0, 0)  # Day before spring forward
        dst_rrule = "FREQ=DAILY;BYHOUR=2;BYMINUTE=30"  # Time that doesn't exist on spring forward
        
        def process_dst_rrule():
            return processor.get_next_occurrence(dst_rrule, base_time)
        
        result = benchmark(process_dst_rrule)
        
        assert result is not None
        # Should handle DST gracefully and still be fast
        assert benchmark.stats.mean < 0.010
    
    def test_bulk_rrule_processing_performance(self, performance_monitor):
        """Test performance of processing many RRULE calculations."""
        
        processor = RRuleProcessor("Europe/Chisinau")
        
        # Generate various RRULE expressions
        rrules = [
            "FREQ=DAILY;BYHOUR=9;BYMINUTE=0",
            "FREQ=WEEKLY;BYDAY=MO;BYHOUR=10;BYMINUTE=30", 
            "FREQ=MONTHLY;BYMONTHDAY=1;BYHOUR=8;BYMINUTE=0",
            "FREQ=WEEKLY;BYDAY=MO,WE,FR;BYHOUR=14;BYMINUTE=0",
            "FREQ=MINUTELY;INTERVAL=30",
            "FREQ=HOURLY;BYHOUR=9,10,11,14,15,16;BYMINUTE=0",
            "FREQ=DAILY;BYHOUR=6,12,18;BYMINUTE=0,30"
        ]
        
        base_times = [
            datetime(2025, 8, 8, 10, 0, 0),
            datetime(2025, 12, 25, 15, 30, 0),
            datetime(2025, 3, 30, 1, 0, 0),  # DST transition day
            datetime(2025, 10, 26, 1, 0, 0), # DST transition day
            datetime(2025, 2, 29, 12, 0, 0)  # Non-leap year edge case
        ]
        
        performance_monitor.start_monitoring()
        start_time = time.time()
        
        # Process many combinations
        results = []
        for base_time in base_times:
            for rrule in rrules:
                try:
                    next_occurrence = processor.get_next_occurrence(rrule, base_time)
                    if next_occurrence:
                        results.append((rrule, base_time, next_occurrence))
                except Exception as e:
                    print(f"RRULE processing error: {e}")
        
        end_time = time.time()
        total_time = end_time - start_time
        perf_stats = performance_monitor.stop_monitoring()
        
        # Calculate performance metrics
        total_calculations = len(base_times) * len(rrules)
        successful_calculations = len(results)
        calculation_rate = successful_calculations / total_time
        
        print(f"Bulk RRULE processing performance:")
        print(f"  - Total calculations: {total_calculations}")
        print(f"  - Successful: {successful_calculations}")
        print(f"  - Total time: {total_time:.3f}s")
        print(f"  - Calculation rate: {calculation_rate:.1f} calculations/sec")
        print(f"  - Avg time per calculation: {(total_time/successful_calculations)*1000:.2f}ms")
        
        # Performance requirements
        assert successful_calculations >= total_calculations * 0.9, "Too many RRULE processing failures"
        assert calculation_rate > 100, f"RRULE processing too slow: {calculation_rate:.1f} calculations/sec"
        assert (total_time/successful_calculations) < 0.010, "Individual calculations too slow"


@pytest.mark.load
@pytest.mark.benchmark
class TestMemoryUsageAndLeakDetection:
    """Test memory usage patterns and detect potential leaks."""
    
    def test_template_rendering_memory_usage(self, performance_monitor):
        """Test memory usage during intensive template rendering."""
        
        # Get initial memory
        import tracemalloc
        tracemalloc.start()
        
        performance_monitor.start_monitoring()
        
        # Create many template rendering operations
        template = {
            "complex_data": {
                f"section_{i}": {
                    "values": [f"${{data.section_{i}.value_{j}}}" for j in range(10)],
                    "metadata": {
                        "created": "${metadata.timestamp}",
                        "version": f"${{metadata.version_{i}}}"
                    }
                }
                for i in range(20)
            }
        }
        
        # Process many contexts
        results = []
        for iteration in range(500):
            context = {
                "data": {
                    f"section_{i}": {
                        f"value_{j}": f"data_{iteration}_{i}_{j}"
                        for j in range(10)
                    }
                    for i in range(20)
                },
                "metadata": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    **{f"version_{i}": f"v{iteration}.{i}" for i in range(20)}
                }
            }
            
            result = render_templates(template, context)
            results.append(result)
            
            # Force garbage collection periodically
            if iteration % 100 == 0:
                gc.collect()
        
        # Get final memory snapshot
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        perf_stats = performance_monitor.stop_monitoring()
        
        # Verify results
        assert len(results) == 500
        
        # Memory usage analysis
        memory_mb = current / 1024 / 1024
        peak_memory_mb = peak / 1024 / 1024
        
        print(f"Template rendering memory usage:")
        print(f"  - Operations: 500")
        print(f"  - Current memory: {memory_mb:.2f} MB")
        print(f"  - Peak memory: {peak_memory_mb:.2f} MB")
        print(f"  - Memory per operation: {current / len(results):.0f} bytes")
        
        # Memory requirements (should not use excessive memory)
        assert memory_mb < 100, f"Memory usage too high: {memory_mb:.2f} MB"
        assert peak_memory_mb < 200, f"Peak memory usage too high: {peak_memory_mb:.2f} MB"
    
    def test_pipeline_execution_memory_cleanup(self, performance_monitor):
        """Test memory cleanup after pipeline executions."""
        
        import tracemalloc
        tracemalloc.start()
        
        performance_monitor.start_monitoring()
        
        # Mock tool that returns large data
        def large_data_tool(*args, **kwargs):
            return {
                "result": "success",
                "large_data": [{"item": i, "data": "x" * 1000} for i in range(100)],  # ~100KB per response
                "metadata": {"processed_at": datetime.now(timezone.utc).isoformat()}
            }
        
        with patch('engine.executor.call_tool', side_effect=large_data_tool):
            with patch('engine.executor.load_catalog', return_value=[{
                "address": "large.data", "transport": "http", "endpoint": "http://test.com",
                "input_schema": {"type": "object"}, "output_schema": {"type": "object"}, "scopes": ["test"]
            }]):
                
                # Execute many pipelines
                results = []
                
                async def execute_pipelines():
                    for i in range(50):
                        pipeline = {
                            "params": {"iteration": i},
                            "pipeline": [
                                {
                                    "id": f"large_step_{i}",
                                    "uses": "large.data",
                                    "with": {"iteration": "${params.iteration}"},
                                    "save_as": f"large_result_{i}"
                                }
                            ]
                        }
                        
                        result = await run_pipeline(pipeline)
                        results.append(result)
                        
                        # Periodic cleanup
                        if i % 10 == 0:
                            gc.collect()
                    
                    return results
                
                # Run the test
                import asyncio
                pipeline_results = asyncio.run(execute_pipelines())
        
        # Memory analysis
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        perf_stats = performance_monitor.stop_monitoring()
        
        # Verify execution results
        assert len(pipeline_results) == 50
        assert all(result["success"] for result in pipeline_results)
        
        # Memory metrics
        memory_mb = current / 1024 / 1024
        peak_memory_mb = peak / 1024 / 1024
        memory_per_pipeline = current / len(pipeline_results)
        
        print(f"Pipeline execution memory usage:")
        print(f"  - Pipelines executed: {len(pipeline_results)}")
        print(f"  - Current memory: {memory_mb:.2f} MB")
        print(f"  - Peak memory: {peak_memory_mb:.2f} MB")
        print(f"  - Memory per pipeline: {memory_per_pipeline:.0f} bytes")
        
        # Memory requirements
        assert memory_mb < 150, f"Memory usage too high: {memory_mb:.2f} MB"
        assert memory_per_pipeline < 1024 * 1024, f"Memory per pipeline too high: {memory_per_pipeline:.0f} bytes"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "--benchmark-only"])