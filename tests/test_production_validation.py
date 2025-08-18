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
        
        # REMOVED: Concurrent worker coordination testing disabled - tools moved to extensions
        # This test is disabled until tools are implemented as extensions
        pytest.skip("Concurrent worker coordination testing disabled - tools moved to extensions")
        
    
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
        
        # REMOVED: End-to-end workflow testing disabled - tools moved to extensions
        # This test is disabled until tools are implemented as extensions
        pytest.skip("Morning briefing workflow testing disabled - tools moved to extensions")


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