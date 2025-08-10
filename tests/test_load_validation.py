#!/usr/bin/env python3
"""
Load Testing and Production Validation for Ordinaut

Simple but comprehensive load tests that validate production readiness
without complex async configurations. Tests real system performance
and identifies bottlenecks.
"""

import pytest
import time
import uuid
import json
import psutil
import statistics
import threading
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List
import concurrent.futures

from sqlalchemy import text


class LoadTestMonitor:
    """Monitor system performance during load tests."""
    
    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.cpu_samples = []
        self.memory_samples = []
        self.monitoring = False
        self._monitor_thread = None
    
    def start_monitoring(self, sample_interval=0.5):
        """Start performance monitoring."""
        self.start_time = time.time()
        self.monitoring = True
        self.cpu_samples.clear()
        self.memory_samples.clear()
        
        def monitor_loop():
            while self.monitoring:
                try:
                    self.cpu_samples.append(psutil.cpu_percent(interval=None))
                    self.memory_samples.append(psutil.virtual_memory().percent)
                except Exception:
                    pass  # Ignore monitoring errors
                time.sleep(sample_interval)
        
        self._monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self._monitor_thread.start()
    
    def stop_monitoring(self) -> Dict[str, Any]:
        """Stop monitoring and return stats."""
        self.end_time = time.time()
        self.monitoring = False
        
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2.0)
        
        duration = self.end_time - self.start_time if self.start_time else 0
        
        return {
            "duration_seconds": duration,
            "cpu_mean": statistics.mean(self.cpu_samples) if self.cpu_samples else 0,
            "cpu_max": max(self.cpu_samples) if self.cpu_samples else 0,
            "memory_mean": statistics.mean(self.memory_samples) if self.memory_samples else 0,
            "memory_max": max(self.memory_samples) if self.memory_samples else 0,
        }


@pytest.fixture
def load_monitor():
    """Fixture providing load testing monitor."""
    return LoadTestMonitor()


@pytest.mark.load
@pytest.mark.slow
class TestDatabaseLoadPerformance:
    """Test database performance under various load conditions."""
    
    def test_high_volume_task_creation(self, test_environment, clean_database, load_monitor):
        """Test high volume task creation performance."""
        
        # Create test agent
        agent_id = str(uuid.uuid4())
        with test_environment.db_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO agent (id, name, scopes) 
                VALUES (:id, :name, :scopes)
            """), {
                "id": agent_id,
                "name": f"load-test-agent-{int(time.time())}",
                "scopes": ["test.create"]
            })
        
        # Test parameters
        task_count = 1000
        batch_size = 50
        
        load_monitor.start_monitoring()
        start_time = time.time()
        
        # Create tasks in batches for better performance
        created_count = 0
        error_count = 0
        
        for batch_start in range(0, task_count, batch_size):
            batch_end = min(batch_start + batch_size, task_count)
            
            try:
                with test_environment.db_engine.begin() as conn:
                    for i in range(batch_start, batch_end):
                        conn.execute(text("""
                            INSERT INTO task (title, description, created_by, schedule_kind,
                                            schedule_expr, timezone, payload, status, priority, max_retries)
                            VALUES (:title, :description, :created_by, :schedule_kind,
                                   :schedule_expr, :timezone, :payload::jsonb, :status, :priority, :max_retries)
                        """), {
                            "title": f"Load Test Task {i}",
                            "description": f"High volume test task {i}",
                            "created_by": agent_id,
                            "schedule_kind": "once",
                            "schedule_expr": (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat(),
                            "timezone": "Europe/Chisinau",
                            "payload": json.dumps({
                                "pipeline": [
                                    {
                                        "id": f"load_step_{i}",
                                        "uses": "test.load",
                                        "with": {"task_id": i},
                                        "save_as": f"result_{i}"
                                    }
                                ]
                            }),
                            "status": "active",
                            "priority": i % 10,
                            "max_retries": 2
                        })
                        created_count += 1
                        
            except Exception as e:
                print(f"Batch {batch_start}-{batch_end} failed: {e}")
                error_count += batch_end - batch_start
        
        creation_time = time.time() - start_time
        perf_stats = load_monitor.stop_monitoring()
        
        # Verify database state
        with test_environment.db_engine.begin() as conn:
            db_count = conn.execute(text("""
                SELECT COUNT(*) FROM task WHERE created_by = :agent_id
            """), {"agent_id": agent_id}).scalar()
        
        # Performance metrics
        creation_rate = created_count / creation_time if creation_time > 0 else 0
        
        print(f"High Volume Task Creation Results:")
        print(f"  Target tasks: {task_count}")
        print(f"  Created tasks: {created_count}")
        print(f"  Database count: {db_count}")
        print(f"  Error count: {error_count}")
        print(f"  Creation time: {creation_time:.2f}s")
        print(f"  Creation rate: {creation_rate:.1f} tasks/sec")
        print(f"  Peak CPU: {perf_stats['cpu_max']:.1f}%")
        print(f"  Peak Memory: {perf_stats['memory_max']:.1f}%")
        
        # Production requirements
        assert created_count >= task_count * 0.95, f"Too many creation failures: {created_count}/{task_count}"
        assert db_count == created_count, f"Database consistency issue: {db_count}/{created_count}"
        assert creation_rate > 100, f"Creation rate too slow: {creation_rate:.1f} tasks/sec"
        assert perf_stats['cpu_max'] < 90, f"CPU usage too high: {perf_stats['cpu_max']:.1f}%"
    
    def test_concurrent_worker_simulation(self, test_environment, clean_database, load_monitor):
        """Test concurrent worker processing with SKIP LOCKED."""
        
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
        worker_count = 10
        
        # Setup tasks and work
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
                                "with": {"work_id": i},
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
        
        # Track processing
        processed_items = set()
        processing_conflicts = 0
        
        def simulate_worker(worker_id: str):
            """Simulate worker processing with SKIP LOCKED."""
            processed_count = 0
            
            while processed_count < work_items // worker_count + 10:  # Fair share + buffer
                try:
                    with test_environment.db_engine.begin() as conn:
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
                        
                        # Check for conflicts (should never happen with SKIP LOCKED)
                        if task_id in processed_items:
                            nonlocal processing_conflicts
                            processing_conflicts += 1
                            continue
                        
                        processed_items.add(task_id)
                        
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
                        
                        # Simulate processing
                        time.sleep(0.01)  # 10ms processing time
                        
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
                            "success": True,
                            "attempt": 1,
                            "output": json.dumps({
                                "success": True,
                                "processed_by": worker_id
                            })
                        })
                        
                        # Clean up due work
                        conn.execute(text("DELETE FROM due_work WHERE id = :work_id"), {"work_id": work_id})
                        
                        processed_count += 1
                        
                except Exception as e:
                    # Handle worker errors gracefully
                    if "could not obtain lock" not in str(e).lower():
                        print(f"Worker {worker_id} error: {e}")
                    time.sleep(0.01)  # Brief pause on errors
            
            return processed_count
        
        # Run concurrent workers
        load_monitor.start_monitoring()
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            worker_futures = [
                executor.submit(simulate_worker, f"worker-{i}")
                for i in range(worker_count)
            ]
            
            worker_results = [future.result() for future in as_completed(worker_futures)]
        
        total_time = time.time() - start_time
        perf_stats = load_monitor.stop_monitoring()
        
        # Analyze results
        total_processed = sum(worker_results)
        unique_items_processed = len(processed_items)
        
        # Verify database state
        with test_environment.db_engine.begin() as conn:
            remaining_work = conn.execute(text("SELECT COUNT(*) FROM due_work")).scalar()
            completed_runs = conn.execute(text("SELECT COUNT(*) FROM task_run WHERE success = true")).scalar()
        
        # Performance metrics
        throughput = total_processed / total_time if total_time > 0 else 0
        
        print(f"Concurrent Worker Simulation Results:")
        print(f"  Work items: {work_items}")
        print(f"  Workers: {worker_count}")
        print(f"  Total processed: {total_processed}")
        print(f"  Unique items processed: {unique_items_processed}")
        print(f"  Processing conflicts: {processing_conflicts}")
        print(f"  Remaining work: {remaining_work}")
        print(f"  Completed runs: {completed_runs}")
        print(f"  Total time: {total_time:.2f}s")
        print(f"  Throughput: {throughput:.1f} items/sec")
        print(f"  Peak CPU: {perf_stats['cpu_max']:.1f}%")
        print(f"  Worker distribution: {worker_results}")
        
        # Production requirements
        assert total_processed >= work_items * 0.95, f"Too few items processed: {total_processed}/{work_items}"
        assert processing_conflicts == 0, f"Processing conflicts detected: {processing_conflicts}"
        assert remaining_work == 0, f"Work items left unprocessed: {remaining_work}"
        assert unique_items_processed == total_processed, f"Duplicate processing detected"
        assert throughput > 15, f"Throughput too low: {throughput:.1f} items/sec"
    
    def test_database_connection_stress(self, test_environment, clean_database, load_monitor):
        """Test database connection pool under stress."""
        
        # Create test agent
        agent_id = str(uuid.uuid4())
        with test_environment.db_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO agent (id, name, scopes) 
                VALUES (:id, :name, :scopes)
            """), {
                "id": agent_id,
                "name": f"stress-test-agent-{int(time.time())}",
                "scopes": ["test.stress"]
            })
        
        # Stress test parameters
        concurrent_operations = 20
        operations_per_thread = 25
        
        def database_stress_operation(thread_id: int):
            """Perform database-intensive operations."""
            results = []
            
            try:
                for i in range(operations_per_thread):
                    with test_environment.db_engine.begin() as conn:
                        # Multi-operation transaction
                        task_result = conn.execute(text("""
                            INSERT INTO task (title, description, created_by, schedule_kind,
                                            schedule_expr, timezone, payload, status, priority, max_retries)
                            VALUES (:title, :description, :created_by, :schedule_kind,
                                   :schedule_expr, :timezone, :payload::jsonb, :status, :priority, :max_retries)
                            RETURNING id
                        """), {
                            "title": f"Stress Test Task {thread_id}-{i}",
                            "description": f"Database stress test",
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
                        
                        # Read back
                        conn.execute(text("SELECT * FROM task WHERE id = :task_id"), {"task_id": task_id})
                        
                        # Update
                        conn.execute(text("""
                            UPDATE task SET priority = :priority WHERE id = :task_id
                        """), {"priority": i % 10, "task_id": task_id})
                        
                        # Create work
                        conn.execute(text("""
                            INSERT INTO due_work (task_id, run_at)
                            VALUES (:task_id, now() + interval '1 minute')
                        """), {"task_id": task_id})
                        
                        results.append(task_id)
                        
            except Exception as e:
                results.append(f"Error: {str(e)}")
            
            return results
        
        # Run concurrent database operations
        load_monitor.start_monitoring()
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=concurrent_operations) as executor:
            stress_futures = [
                executor.submit(database_stress_operation, i)
                for i in range(concurrent_operations)
            ]
            
            stress_results = [future.result() for future in as_completed(stress_futures)]
        
        total_time = time.time() - start_time
        perf_stats = load_monitor.stop_monitoring()
        
        # Analyze results
        successful_operations = [r for r in stress_results if not any(isinstance(item, str) and "Error" in item for item in r)]
        total_tasks_created = sum(len(r) for r in successful_operations)
        error_count = len(stress_results) - len(successful_operations)
        
        # Verify database state
        with test_environment.db_engine.begin() as conn:
            db_tasks = conn.execute(text("""
                SELECT COUNT(*) FROM task WHERE created_by = :agent_id
            """), {"agent_id": agent_id}).scalar()
            
            db_work = conn.execute(text("""
                SELECT COUNT(*) FROM due_work dw
                JOIN task t ON dw.task_id = t.id
                WHERE t.created_by = :agent_id
            """), {"agent_id": agent_id}).scalar()
        
        # Performance metrics
        expected_tasks = concurrent_operations * operations_per_thread
        operations_per_second = total_tasks_created / total_time if total_time > 0 else 0
        success_rate = total_tasks_created / expected_tasks * 100
        
        print(f"Database Connection Stress Results:")
        print(f"  Concurrent operations: {concurrent_operations}")
        print(f"  Operations per thread: {operations_per_thread}")
        print(f"  Expected tasks: {expected_tasks}")
        print(f"  Total tasks created: {total_tasks_created}")
        print(f"  Tasks in database: {db_tasks}")
        print(f"  Work items created: {db_work}")
        print(f"  Error count: {error_count}")
        print(f"  Success rate: {success_rate:.1f}%")
        print(f"  Total time: {total_time:.2f}s")
        print(f"  Operations per second: {operations_per_second:.1f}")
        print(f"  Peak CPU: {perf_stats['cpu_max']:.1f}%")
        print(f"  Peak Memory: {perf_stats['memory_max']:.1f}%")
        
        # Production requirements
        assert success_rate >= 95, f"Too many database failures: {success_rate:.1f}%"
        assert db_tasks == total_tasks_created, f"Database consistency issue: {db_tasks}/{total_tasks_created}"
        assert operations_per_second > 50, f"Database operations too slow: {operations_per_second:.1f} ops/sec"
        assert perf_stats['cpu_max'] < 95, f"CPU usage too high: {perf_stats['cpu_max']:.1f}%"


@pytest.mark.integration
@pytest.mark.slow
class TestEndToEndWorkflowValidation:
    """Test complete end-to-end workflows."""
    
    def test_task_lifecycle_validation(self, test_environment, clean_database, load_monitor):
        """Test complete task lifecycle from creation to completion."""
        
        # Create test agent
        agent_id = str(uuid.uuid4())
        with test_environment.db_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO agent (id, name, scopes) 
                VALUES (:id, :name, :scopes)
            """), {
                "id": agent_id,
                "name": f"lifecycle-agent-{int(time.time())}",
                "scopes": ["test.lifecycle"]
            })
        
        # Create test tasks
        task_count = 50
        task_ids = []
        
        load_monitor.start_monitoring()
        
        # Step 1: Create tasks
        with test_environment.db_engine.begin() as conn:
            for i in range(task_count):
                task_result = conn.execute(text("""
                    INSERT INTO task (title, description, created_by, schedule_kind,
                                    schedule_expr, timezone, payload, status, priority, max_retries)
                    VALUES (:title, :description, :created_by, :schedule_kind,
                           :schedule_expr, :timezone, :payload::jsonb, :status, :priority, :max_retries)
                    RETURNING id
                """), {
                    "title": f"Lifecycle Test Task {i}",
                    "description": f"End-to-end lifecycle test",
                    "created_by": agent_id,
                    "schedule_kind": "once",
                    "schedule_expr": (datetime.now(timezone.utc) + timedelta(seconds=5)).isoformat(),
                    "timezone": "Europe/Chisinau",
                    "payload": json.dumps({
                        "pipeline": [
                            {
                                "id": f"lifecycle_step_{i}",
                                "uses": "test.lifecycle",
                                "with": {"task_number": i},
                                "save_as": f"lifecycle_result_{i}"
                            }
                        ]
                    }),
                    "status": "active",
                    "priority": i % 10,
                    "max_retries": 2
                })
                task_ids.append(task_result.scalar())
        
        # Step 2: Schedule tasks (simulate scheduler)
        with test_environment.db_engine.begin() as conn:
            for task_id in task_ids:
                conn.execute(text("""
                    INSERT INTO due_work (task_id, run_at)
                    VALUES (:task_id, now() + interval '1 second')
                """), {"task_id": task_id})
        
        # Step 3: Wait for tasks to become due
        time.sleep(2)
        
        # Step 4: Simulate worker processing all tasks
        def process_all_tasks():
            """Process all available tasks."""
            processed = 0
            
            while processed < task_count:
                try:
                    with test_environment.db_engine.begin() as conn:
                        # Get available work
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
                            break
                        
                        work_id, task_id = work_row
                        
                        # Lease and process
                        lease_time = datetime.now(timezone.utc) + timedelta(minutes=5)
                        conn.execute(text("""
                            UPDATE due_work 
                            SET locked_until = :lease_time, locked_by = 'lifecycle-worker'
                            WHERE id = :work_id
                        """), {"lease_time": lease_time, "work_id": work_id})
                        
                        # Get task details
                        task_result = conn.execute(text("""
                            SELECT payload FROM task WHERE id = :task_id
                        """), {"task_id": task_id})
                        
                        task_row = task_result.fetchone()
                        pipeline_data = json.loads(task_row.payload)
                        
                        # Simulate processing
                        time.sleep(0.005)  # 5ms processing
                        
                        # Record execution
                        conn.execute(text("""
                            INSERT INTO task_run (id, task_id, lease_owner, started_at,
                                                finished_at, success, attempt, output)
                            VALUES (:id, :task_id, :lease_owner, :started_at,
                                   :finished_at, :success, :attempt, :output::jsonb)
                        """), {
                            "id": str(uuid.uuid4()),
                            "task_id": task_id,
                            "lease_owner": "lifecycle-worker",
                            "started_at": datetime.now(timezone.utc),
                            "finished_at": datetime.now(timezone.utc),
                            "success": True,
                            "attempt": 1,
                            "output": json.dumps({
                                "success": True,
                                "lifecycle_test": True,
                                "task_number": pipeline_data["pipeline"][0]["with"]["task_number"]
                            })
                        })
                        
                        # Clean up
                        conn.execute(text("DELETE FROM due_work WHERE id = :work_id"), {"work_id": work_id})
                        
                        processed += 1
                        
                except Exception as e:
                    print(f"Processing error: {e}")
                    break
            
            return processed
        
        # Process tasks
        processed_count = process_all_tasks()
        
        perf_stats = load_monitor.stop_monitoring()
        
        # Step 5: Verify complete lifecycle
        with test_environment.db_engine.begin() as conn:
            # Check all tasks were created
            created_tasks = conn.execute(text("""
                SELECT COUNT(*) FROM task WHERE created_by = :agent_id
            """), {"agent_id": agent_id}).scalar()
            
            # Check all runs were recorded
            task_runs = conn.execute(text("""
                SELECT COUNT(*) FROM task_run tr
                JOIN task t ON tr.task_id = t.id
                WHERE t.created_by = :agent_id AND tr.success = true
            """), {"agent_id": agent_id}).scalar()
            
            # Check no remaining work
            remaining_work = conn.execute(text("""
                SELECT COUNT(*) FROM due_work dw
                JOIN task t ON dw.task_id = t.id
                WHERE t.created_by = :agent_id
            """), {"agent_id": agent_id}).scalar()
            
            # Get sample task run output
            sample_run = conn.execute(text("""
                SELECT output FROM task_run tr
                JOIN task t ON tr.task_id = t.id
                WHERE t.created_by = :agent_id AND tr.success = true
                LIMIT 1
            """), {"agent_id": agent_id}).fetchone()
        
        # Analyze lifecycle completion
        lifecycle_completion_rate = task_runs / task_count * 100
        processing_efficiency = processed_count / task_count * 100
        
        print(f"Task Lifecycle Validation Results:")
        print(f"  Target tasks: {task_count}")
        print(f"  Created tasks: {created_tasks}")
        print(f"  Processed tasks: {processed_count}")
        print(f"  Successful runs: {task_runs}")
        print(f"  Remaining work: {remaining_work}")
        print(f"  Lifecycle completion: {lifecycle_completion_rate:.1f}%")
        print(f"  Processing efficiency: {processing_efficiency:.1f}%")
        print(f"  Total time: {perf_stats['duration_seconds']:.2f}s")
        print(f"  Peak CPU: {perf_stats['cpu_max']:.1f}%")
        
        if sample_run:
            output_data = json.loads(sample_run.output)
            print(f"  Sample output: {output_data}")
        
        # Production lifecycle requirements
        assert created_tasks == task_count, f"Task creation incomplete: {created_tasks}/{task_count}"
        assert task_runs == task_count, f"Task execution incomplete: {task_runs}/{task_count}"
        assert remaining_work == 0, f"Unprocessed work remaining: {remaining_work}"
        assert lifecycle_completion_rate >= 99, f"Lifecycle completion too low: {lifecycle_completion_rate:.1f}%"
        assert processing_efficiency >= 99, f"Processing efficiency too low: {processing_efficiency:.1f}%"
        
        print("✅ Complete task lifecycle validation successful")


if __name__ == "__main__":
    pytest.main([
        __file__, 
        "-v", 
        "--tb=short", 
        "-s",
        "--maxfail=3",
        "--disable-warnings"
    ])