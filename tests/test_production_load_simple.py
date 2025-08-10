#!/usr/bin/env python3
"""
Production Load Testing for Ordinaut

Simple, direct load tests using the actual running PostgreSQL database.
Tests system performance and validates production readiness.
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
import os

from sqlalchemy import create_engine, text


class ProductionLoadMonitor:
    """Monitor system performance during production load tests."""
    
    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.cpu_samples = []
        self.memory_samples = []
        self.monitoring = False
        self._monitor_thread = None
    
    def start_monitoring(self, sample_interval=0.3):
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
def db_engine():
    """Direct database connection for load testing."""
    database_url = os.getenv("DATABASE_URL", "postgresql://orchestrator:secure_password@localhost:5432/orchestrator")
    engine = create_engine(database_url, echo=False, future=True)
    yield engine
    engine.dispose()


@pytest.fixture
def monitor():
    """Performance monitor fixture."""
    return ProductionLoadMonitor()


def cleanup_test_data(db_engine, agent_id: str):
    """Clean up test data after test."""
    try:
        with db_engine.begin() as conn:
            # Clean up in correct order due to foreign keys
            conn.execute(text("DELETE FROM task_run WHERE task_id IN (SELECT id FROM task WHERE created_by = :agent_id)"), {"agent_id": agent_id})
            conn.execute(text("DELETE FROM due_work WHERE task_id IN (SELECT id FROM task WHERE created_by = :agent_id)"), {"agent_id": agent_id})
            conn.execute(text("DELETE FROM task WHERE created_by = :agent_id"), {"agent_id": agent_id})
            conn.execute(text("DELETE FROM agent WHERE id = :agent_id"), {"agent_id": agent_id})
    except Exception as e:
        print(f"Cleanup error: {e}")


def test_production_high_throughput_task_creation(db_engine, monitor):
    """Test high throughput task creation under production conditions."""
    
    # Create test agent
    agent_id = str(uuid.uuid4())
    agent_name = f"prod-load-agent-{int(time.time())}"
    
    try:
        with db_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO agent (id, name, scopes) 
                VALUES (:id, :name, :scopes)
            """), {
                "id": agent_id,
                "name": agent_name,
                "scopes": ["test.create", "test.process"]
            })
        
        # Load test parameters
        target_tasks = 800  # High load
        batch_size = 40
        
        monitor.start_monitoring()
        start_time = time.time()
        
        print(f"Starting high throughput task creation test...")
        print(f"Target: {target_tasks} tasks in batches of {batch_size}")
        
        # Create tasks in optimized batches
        created_count = 0
        error_count = 0
        batch_times = []
        
        for batch_start in range(0, target_tasks, batch_size):
            batch_end = min(batch_start + batch_size, target_tasks)
            batch_start_time = time.time()
            
            try:
                with db_engine.begin() as conn:
                    for i in range(batch_start, batch_end):
                        conn.execute(text("""
                            INSERT INTO task (title, description, created_by, schedule_kind,
                                            schedule_expr, timezone, payload, status, priority, max_retries)
                            VALUES (:title, :description, :created_by, :schedule_kind,
                                   :schedule_expr, :timezone, :payload::jsonb, :status, :priority, :max_retries)
                        """), {
                            "title": f"Production Load Test {i}",
                            "description": f"High throughput production test task {i}",
                            "created_by": agent_id,
                            "schedule_kind": "once",
                            "schedule_expr": (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat(),
                            "timezone": "Europe/Chisinau",
                            "payload": json.dumps({
                                "pipeline": [
                                    {
                                        "id": f"prod_load_step_{i}",
                                        "uses": "test.process",
                                        "with": {"task_id": i, "batch": batch_start // batch_size},
                                        "save_as": f"prod_result_{i}"
                                    }
                                ]
                            }),
                            "status": "active",
                            "priority": i % 10,
                            "max_retries": 3
                        })
                        created_count += 1
                
                batch_time = time.time() - batch_start_time
                batch_times.append(batch_time)
                
                if batch_start % (batch_size * 5) == 0:  # Progress every 5 batches
                    print(f"  Created {created_count}/{target_tasks} tasks...")
                        
            except Exception as e:
                print(f"Batch {batch_start}-{batch_end} error: {e}")
                error_count += batch_end - batch_start
        
        creation_time = time.time() - start_time
        perf_stats = monitor.stop_monitoring()
        
        # Verify database state
        with db_engine.begin() as conn:
            db_count = conn.execute(text("""
                SELECT COUNT(*) FROM task WHERE created_by = :agent_id
            """), {"agent_id": agent_id}).scalar()
        
        # Performance analysis
        creation_rate = created_count / creation_time if creation_time > 0 else 0
        avg_batch_time = statistics.mean(batch_times) if batch_times else 0
        success_rate = created_count / target_tasks * 100
        
        print(f"\n=== PRODUCTION HIGH THROUGHPUT TASK CREATION RESULTS ===")
        print(f"Target tasks: {target_tasks}")
        print(f"Created tasks: {created_count}")
        print(f"Database verified: {db_count}")
        print(f"Success rate: {success_rate:.1f}%")
        print(f"Error count: {error_count}")
        print(f"Creation time: {creation_time:.2f}s")
        print(f"Creation rate: {creation_rate:.1f} tasks/sec")
        print(f"Average batch time: {avg_batch_time*1000:.2f}ms")
        print(f"Peak CPU usage: {perf_stats['cpu_max']:.1f}%")
        print(f"Peak memory usage: {perf_stats['memory_max']:.1f}%")
        print(f"Average CPU usage: {perf_stats['cpu_mean']:.1f}%")
        
        # Production readiness validation
        validation_results = {
            "creation_success": success_rate >= 98,
            "performance_adequate": creation_rate > 80,
            "resource_usage_acceptable": perf_stats['cpu_max'] < 85 and perf_stats['memory_max'] < 80,
            "database_consistency": db_count == created_count,
            "error_rate_acceptable": error_count < target_tasks * 0.02
        }
        
        print(f"\n=== PRODUCTION READINESS VALIDATION ===")
        for check, passed in validation_results.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{check}: {status}")
        
        overall_pass = all(validation_results.values())
        print(f"\nOverall Production Readiness: {'✅ READY' if overall_pass else '❌ NOT READY'}")
        
        # Assertions for automated validation
        assert success_rate >= 98, f"Task creation success rate too low: {success_rate:.1f}%"
        assert db_count == created_count, f"Database consistency issue: {db_count}/{created_count}"
        assert creation_rate > 80, f"Creation throughput insufficient for production: {creation_rate:.1f} tasks/sec"
        assert perf_stats['cpu_max'] < 85, f"CPU usage too high for production: {perf_stats['cpu_max']:.1f}%"
        assert perf_stats['memory_max'] < 80, f"Memory usage too high for production: {perf_stats['memory_max']:.1f}%"
        
        print(f"✅ Production high throughput test PASSED")
        
    finally:
        cleanup_test_data(db_engine, agent_id)


def test_production_concurrent_worker_coordination(db_engine, monitor):
    """Test concurrent worker coordination under production load."""
    
    # Create test agent
    agent_id = str(uuid.uuid4())
    agent_name = f"prod-worker-agent-{int(time.time())}"
    
    try:
        with db_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO agent (id, name, scopes) 
                VALUES (:id, :name, :scopes)
            """), {
                "id": agent_id,
                "name": agent_name,
                "scopes": ["test.worker", "test.concurrent"]
            })
        
        # Production concurrency parameters
        work_items = 150
        worker_count = 12
        
        # Setup tasks and work items
        print(f"Setting up {work_items} work items for {worker_count} concurrent workers...")
        
        task_ids = []
        with db_engine.begin() as conn:
            for i in range(work_items):
                # Create task
                task_result = conn.execute(text("""
                    INSERT INTO task (title, description, created_by, schedule_kind,
                                    schedule_expr, timezone, payload, status, priority, max_retries)
                    VALUES (:title, :description, :created_by, :schedule_kind,
                           :schedule_expr, :timezone, :payload::jsonb, :status, :priority, :max_retries)
                    RETURNING id
                """), {
                    "title": f"Production Worker Test {i}",
                    "description": f"Concurrent worker coordination test {i}",
                    "created_by": agent_id,
                    "schedule_kind": "once",
                    "schedule_expr": datetime.now(timezone.utc).isoformat(),
                    "timezone": "Europe/Chisinau",
                    "payload": json.dumps({
                        "pipeline": [
                            {
                                "id": f"worker_test_step_{i}",
                                "uses": "test.concurrent",
                                "with": {"work_id": i, "concurrent_test": True},
                                "save_as": f"concurrent_result_{i}"
                            }
                        ]
                    }),
                    "status": "active",
                    "priority": i % 8,
                    "max_retries": 2
                })
                task_id = task_result.scalar()
                task_ids.append(task_id)
                
                # Create due work immediately
                conn.execute(text("""
                    INSERT INTO due_work (task_id, run_at)
                    VALUES (:task_id, now())
                """), {"task_id": task_id})
        
        # Track worker coordination
        processed_items = set()
        processing_conflicts = 0
        worker_performance = {}
        lock_contentions = 0
        
        def simulate_production_worker(worker_id: str):
            """Simulate production worker with realistic processing."""
            processed_count = 0
            worker_errors = 0
            
            while processed_count < work_items // worker_count + 8:  # Fair share + buffer
                try:
                    with db_engine.begin() as conn:
                        # Production-style work leasing with SKIP LOCKED
                        work_result = conn.execute(text("""
                            SELECT id, task_id FROM due_work 
                            WHERE run_at <= now() 
                              AND (locked_until IS NULL OR locked_until < now())
                            ORDER BY run_at ASC, id ASC
                            FOR UPDATE SKIP LOCKED
                            LIMIT 1
                        """))
                        
                        work_row = work_result.fetchone()
                        if not work_row:
                            break  # No more work available
                        
                        work_id, task_id = work_row
                        
                        # Check for coordination conflicts (should never happen)
                        if task_id in processed_items:
                            nonlocal processing_conflicts
                            processing_conflicts += 1
                            continue
                        
                        processed_items.add(task_id)
                        
                        # Lease the work item
                        lease_time = datetime.now(timezone.utc) + timedelta(minutes=3)
                        lease_result = conn.execute(text("""
                            UPDATE due_work 
                            SET locked_until = :lease_time, locked_by = :worker_id
                            WHERE id = :work_id
                        """), {
                            "lease_time": lease_time,
                            "worker_id": worker_id,
                            "work_id": work_id
                        })
                        
                        if lease_result.rowcount == 0:
                            # Another worker got it (rare with SKIP LOCKED)
                            nonlocal lock_contentions
                            lock_contentions += 1
                            continue
                        
                        # Simulate realistic processing time
                        processing_time = 0.008 + (processed_count % 5) * 0.003  # 8-20ms variation
                        time.sleep(processing_time)
                        
                        # Record successful execution
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
                                "processed_by": worker_id,
                                "processing_time_ms": processing_time * 1000,
                                "production_test": True
                            })
                        })
                        
                        # Clean up due work
                        conn.execute(text("DELETE FROM due_work WHERE id = :work_id"), {"work_id": work_id})
                        
                        processed_count += 1
                        
                except Exception as e:
                    worker_errors += 1
                    if worker_errors <= 3:  # Log first few errors only
                        print(f"Worker {worker_id} error: {e}")
                    
                    if worker_errors > 10:  # Circuit breaker
                        break
                    
                    time.sleep(0.01)  # Brief pause on errors
            
            worker_performance[worker_id] = {
                "processed": processed_count,
                "errors": worker_errors
            }
            
            return processed_count
        
        # Run concurrent workers
        print("Starting concurrent worker coordination test...")
        monitor.start_monitoring()
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            worker_futures = [
                executor.submit(simulate_production_worker, f"prod-worker-{i}")
                for i in range(worker_count)
            ]
            
            worker_results = [future.result() for future in as_completed(worker_futures)]
        
        total_time = time.time() - start_time
        perf_stats = monitor.stop_monitoring()
        
        # Analyze coordination results
        total_processed = sum(worker_results)
        unique_items_processed = len(processed_items)
        
        # Verify database state
        with db_engine.begin() as conn:
            remaining_work = conn.execute(text("SELECT COUNT(*) FROM due_work WHERE task_id IN (SELECT id FROM task WHERE created_by = :agent_id)"), {"agent_id": agent_id}).scalar()
            completed_runs = conn.execute(text("SELECT COUNT(*) FROM task_run tr JOIN task t ON tr.task_id = t.id WHERE t.created_by = :agent_id AND tr.success = true"), {"agent_id": agent_id}).scalar()
            
            # Check for any duplicate processing in database
            duplicate_check = conn.execute(text("""
                SELECT task_id, COUNT(*) as run_count
                FROM task_run tr
                JOIN task t ON tr.task_id = t.id
                WHERE t.created_by = :agent_id AND tr.success = true
                GROUP BY task_id
                HAVING COUNT(*) > 1
            """), {"agent_id": agent_id}).fetchall()
        
        # Performance metrics
        throughput = total_processed / total_time if total_time > 0 else 0
        coordination_efficiency = unique_items_processed / work_items * 100
        
        # Worker performance analysis
        successful_workers = len([w for w, stats in worker_performance.items() if stats["processed"] > 0])
        total_worker_errors = sum(stats["errors"] for stats in worker_performance.values())
        
        print(f"\n=== PRODUCTION CONCURRENT WORKER COORDINATION RESULTS ===")
        print(f"Work items: {work_items}")
        print(f"Workers deployed: {worker_count}")
        print(f"Successful workers: {successful_workers}")
        print(f"Total processed: {total_processed}")
        print(f"Unique items processed: {unique_items_processed}")
        print(f"Processing conflicts: {processing_conflicts}")
        print(f"Lock contentions: {lock_contentions}")
        print(f"Database duplicates: {len(duplicate_check)}")
        print(f"Remaining work: {remaining_work}")
        print(f"Completed runs: {completed_runs}")
        print(f"Total worker errors: {total_worker_errors}")
        print(f"Coordination efficiency: {coordination_efficiency:.1f}%")
        print(f"Throughput: {throughput:.1f} items/sec")
        print(f"Processing time: {total_time:.2f}s")
        print(f"Peak CPU usage: {perf_stats['cpu_max']:.1f}%")
        print(f"Peak memory usage: {perf_stats['memory_max']:.1f}%")
        
        print(f"\nWorker Performance Distribution:")
        for worker_id, stats in worker_performance.items():
            print(f"  {worker_id}: {stats['processed']} items, {stats['errors']} errors")
        
        # Production coordination validation
        coordination_checks = {
            "no_processing_conflicts": processing_conflicts == 0,
            "no_database_duplicates": len(duplicate_check) == 0,
            "high_coordination_efficiency": coordination_efficiency >= 99,
            "adequate_throughput": throughput > 12,
            "all_work_processed": remaining_work == 0,
            "low_error_rate": total_worker_errors < worker_count * 2,
            "resource_usage_acceptable": perf_stats['cpu_max'] < 90
        }
        
        print(f"\n=== PRODUCTION COORDINATION VALIDATION ===")
        for check, passed in coordination_checks.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{check}: {status}")
        
        overall_coordination_pass = all(coordination_checks.values())
        print(f"\nOverall Coordination Readiness: {'✅ READY' if overall_coordination_pass else '❌ NOT READY'}")
        
        # Automated assertions
        assert processing_conflicts == 0, f"Processing conflicts detected: {processing_conflicts}"
        assert len(duplicate_check) == 0, f"Database duplicates found: {len(duplicate_check)}"
        assert remaining_work == 0, f"Work items left unprocessed: {remaining_work}"
        assert unique_items_processed >= work_items * 0.98, f"Too few items processed: {unique_items_processed}/{work_items}"
        assert coordination_efficiency >= 99, f"Coordination efficiency too low: {coordination_efficiency:.1f}%"
        assert throughput > 12, f"Worker throughput insufficient: {throughput:.1f} items/sec"
        assert total_worker_errors < worker_count * 2, f"Too many worker errors: {total_worker_errors}"
        
        print(f"✅ Production concurrent worker coordination test PASSED")
        
    finally:
        cleanup_test_data(db_engine, agent_id)


def test_production_database_resilience(db_engine, monitor):
    """Test database resilience under production load conditions."""
    
    # Create test agent
    agent_id = str(uuid.uuid4())
    agent_name = f"prod-resilience-agent-{int(time.time())}"
    
    try:
        with db_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO agent (id, name, scopes) 
                VALUES (:id, :name, :scopes)
            """), {
                "id": agent_id,
                "name": agent_name,
                "scopes": ["test.resilience"]
            })
        
        # Resilience test parameters
        stress_operations = 30
        operations_per_thread = 35
        
        print(f"Testing database resilience with {stress_operations} concurrent operations...")
        
        def database_stress_worker(thread_id: int):
            """Perform intensive database operations to test resilience."""
            operations_completed = 0
            operations_failed = 0
            
            try:
                for i in range(operations_per_thread):
                    operation_start = time.time()
                    
                    try:
                        with db_engine.begin() as conn:
                            # Multi-step transaction simulating real workload
                            
                            # 1. Create task
                            task_result = conn.execute(text("""
                                INSERT INTO task (title, description, created_by, schedule_kind,
                                                schedule_expr, timezone, payload, status, priority, max_retries)
                                VALUES (:title, :description, :created_by, :schedule_kind,
                                       :schedule_expr, :timezone, :payload::jsonb, :status, :priority, :max_retries)
                                RETURNING id
                            """), {
                                "title": f"Resilience Test {thread_id}-{i}",
                                "description": f"Database stress resilience test",
                                "created_by": agent_id,
                                "schedule_kind": "once",
                                "schedule_expr": (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat(),
                                "timezone": "UTC",
                                "payload": json.dumps({
                                    "pipeline": [
                                        {
                                            "id": f"stress_step_{thread_id}_{i}",
                                            "uses": "test.resilience",
                                            "with": {"thread_id": thread_id, "operation": i},
                                            "save_as": f"stress_result_{i}"
                                        }
                                    ]
                                }),
                                "status": "active",
                                "priority": i % 10,
                                "max_retries": 2
                            })
                            task_id = task_result.scalar()
                            
                            # 2. Query task back (read after write)
                            task_check = conn.execute(text("SELECT * FROM task WHERE id = :task_id"), {"task_id": task_id})
                            task_data = task_check.fetchone()
                            assert task_data is not None, "Task not found after creation"
                            
                            # 3. Update task
                            conn.execute(text("""
                                UPDATE task SET priority = :new_priority 
                                WHERE id = :task_id
                            """), {"new_priority": (i + 3) % 10, "task_id": task_id})
                            
                            # 4. Create due work
                            conn.execute(text("""
                                INSERT INTO due_work (task_id, run_at)
                                VALUES (:task_id, now() + interval '2 minutes')
                            """), {"task_id": task_id})
                            
                            # 5. Simulate work processing
                            conn.execute(text("""
                                INSERT INTO task_run (id, task_id, lease_owner, started_at,
                                                    finished_at, success, attempt, output)
                                VALUES (:id, :task_id, :lease_owner, :started_at,
                                       :finished_at, :success, :attempt, :output::jsonb)
                            """), {
                                "id": str(uuid.uuid4()),
                                "task_id": task_id,
                                "lease_owner": f"stress-worker-{thread_id}",
                                "started_at": datetime.now(timezone.utc),
                                "finished_at": datetime.now(timezone.utc),
                                "success": True,
                                "attempt": 1,
                                "output": json.dumps({
                                    "success": True,
                                    "stress_test": True,
                                    "thread_id": thread_id,
                                    "operation_time_ms": (time.time() - operation_start) * 1000
                                })
                            })
                            
                            # 6. Clean up due work
                            conn.execute(text("DELETE FROM due_work WHERE task_id = :task_id"), {"task_id": task_id})
                            
                            operations_completed += 1
                            
                    except Exception as e:
                        operations_failed += 1
                        if operations_failed <= 2:  # Log first couple of errors
                            print(f"Thread {thread_id} operation {i} failed: {e}")
                        
                        # Small delay on errors
                        time.sleep(0.01)
                
            except Exception as e:
                print(f"Thread {thread_id} critical error: {e}")
            
            return {
                "thread_id": thread_id,
                "completed": operations_completed,
                "failed": operations_failed,
                "success_rate": operations_completed / operations_per_thread * 100 if operations_per_thread > 0 else 0
            }
        
        # Execute concurrent stress operations
        monitor.start_monitoring()
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=stress_operations) as executor:
            stress_futures = [
                executor.submit(database_stress_worker, i)
                for i in range(stress_operations)
            ]
            
            stress_results = [future.result() for future in as_completed(stress_futures)]
        
        total_time = time.time() - start_time
        perf_stats = monitor.stop_monitoring()
        
        # Analyze resilience results
        total_operations_attempted = stress_operations * operations_per_thread
        total_operations_completed = sum(result["completed"] for result in stress_results)
        total_operations_failed = sum(result["failed"] for result in stress_results)
        overall_success_rate = total_operations_completed / total_operations_attempted * 100
        
        # Verify database state
        with db_engine.begin() as conn:
            db_tasks = conn.execute(text("SELECT COUNT(*) FROM task WHERE created_by = :agent_id"), {"agent_id": agent_id}).scalar()
            db_runs = conn.execute(text("SELECT COUNT(*) FROM task_run tr JOIN task t ON tr.task_id = t.id WHERE t.created_by = :agent_id"), {"agent_id": agent_id}).scalar()
            remaining_work = conn.execute(text("SELECT COUNT(*) FROM due_work dw JOIN task t ON dw.task_id = t.id WHERE t.created_by = :agent_id"), {"agent_id": agent_id}).scalar()
        
        # Performance metrics
        operations_per_second = total_operations_completed / total_time if total_time > 0 else 0
        
        print(f"\n=== PRODUCTION DATABASE RESILIENCE RESULTS ===")
        print(f"Concurrent operations: {stress_operations}")
        print(f"Operations per thread: {operations_per_thread}")
        print(f"Total operations attempted: {total_operations_attempted}")
        print(f"Operations completed: {total_operations_completed}")
        print(f"Operations failed: {total_operations_failed}")
        print(f"Overall success rate: {overall_success_rate:.1f}%")
        print(f"Database tasks created: {db_tasks}")
        print(f"Database runs recorded: {db_runs}")
        print(f"Remaining work items: {remaining_work}")
        print(f"Operations per second: {operations_per_second:.1f}")
        print(f"Total time: {total_time:.2f}s")
        print(f"Peak CPU usage: {perf_stats['cpu_max']:.1f}%")
        print(f"Peak memory usage: {perf_stats['memory_max']:.1f}%")
        print(f"Average CPU usage: {perf_stats['cpu_mean']:.1f}%")
        
        # Thread performance breakdown
        print(f"\nThread Performance Summary:")
        failed_threads = [r for r in stress_results if r["success_rate"] < 90]
        print(f"Threads with >90% success: {len(stress_results) - len(failed_threads)}/{len(stress_results)}")
        
        if failed_threads:
            print("Underperforming threads:")
            for result in failed_threads:
                print(f"  Thread {result['thread_id']}: {result['success_rate']:.1f}% success ({result['completed']}/{operations_per_thread})")
        
        # Database resilience validation
        resilience_checks = {
            "high_overall_success_rate": overall_success_rate >= 95,
            "adequate_throughput": operations_per_second > 40,
            "database_consistency": db_tasks == total_operations_completed,
            "resource_usage_sustainable": perf_stats['cpu_max'] < 95 and perf_stats['memory_max'] < 85,
            "minimal_failed_threads": len(failed_threads) < stress_operations * 0.1,
            "clean_work_state": remaining_work == 0
        }
        
        print(f"\n=== PRODUCTION RESILIENCE VALIDATION ===")
        for check, passed in resilience_checks.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{check}: {status}")
        
        overall_resilience_pass = all(resilience_checks.values())
        print(f"\nOverall Database Resilience: {'✅ RESILIENT' if overall_resilience_pass else '❌ NOT RESILIENT'}")
        
        # Automated assertions
        assert overall_success_rate >= 95, f"Database success rate too low under stress: {overall_success_rate:.1f}%"
        assert db_tasks == total_operations_completed, f"Database consistency issue under stress: {db_tasks}/{total_operations_completed}"
        assert operations_per_second > 40, f"Database throughput insufficient under stress: {operations_per_second:.1f} ops/sec"
        assert perf_stats['cpu_max'] < 95, f"CPU usage too high under database stress: {perf_stats['cpu_max']:.1f}%"
        assert perf_stats['memory_max'] < 85, f"Memory usage too high under database stress: {perf_stats['memory_max']:.1f}%"
        assert len(failed_threads) < stress_operations * 0.1, f"Too many threads failed: {len(failed_threads)}/{stress_operations}"
        
        print(f"✅ Production database resilience test PASSED")
        
    finally:
        cleanup_test_data(db_engine, agent_id)


if __name__ == "__main__":
    # Run production load tests directly
    import sqlalchemy
    print(f"Testing with SQLAlchemy {sqlalchemy.__version__}")
    print("=== PRODUCTION LOAD TESTING SUITE ===")
    pytest.main([
        __file__, 
        "-v", 
        "-s",
        "--tb=short",
        "--disable-warnings"
    ])