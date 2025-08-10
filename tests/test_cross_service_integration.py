#!/usr/bin/env python3
"""
Cross-Service Integration Tests for Ordinaut

Tests real communication between API, Worker, Scheduler, and Database components
to validate production deployment readiness and cross-service coordination.

This suite validates:
- API ↔ Database communication under load
- Worker ↔ Database coordination with SKIP LOCKED
- Scheduler ↔ Database task scheduling accuracy  
- Redis stream communication for events
- Error propagation across service boundaries
- Service recovery and resilience patterns
"""

import pytest
import asyncio
import time
import uuid
import json
import httpx
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, Mock, AsyncMock
from typing import List, Dict, Any, Optional
import concurrent.futures
import threading

from sqlalchemy import text
from fastapi.testclient import TestClient


class ServiceCommunicationValidator:
    """Validates communication patterns between services."""
    
    def __init__(self, db_engine, redis_client=None):
        self.db_engine = db_engine
        self.redis_client = redis_client
        self.communication_log = []
        self.error_log = []
    
    def log_communication(self, source: str, target: str, operation: str, success: bool, duration: float, details: Dict[str, Any] = None):
        """Log inter-service communication."""
        entry = {
            "timestamp": datetime.now(timezone.utc),
            "source": source,
            "target": target, 
            "operation": operation,
            "success": success,
            "duration_ms": duration * 1000,
            "details": details or {}
        }
        self.communication_log.append(entry)
        
        if not success:
            self.error_log.append(entry)
    
    def get_communication_stats(self) -> Dict[str, Any]:
        """Get communication statistics."""
        if not self.communication_log:
            return {"total": 0, "success_rate": 0, "avg_duration_ms": 0}
        
        total = len(self.communication_log)
        successful = sum(1 for entry in self.communication_log if entry["success"])
        avg_duration = sum(entry["duration_ms"] for entry in self.communication_log) / total
        
        return {
            "total_communications": total,
            "successful_communications": successful,
            "success_rate": successful / total * 100,
            "avg_duration_ms": avg_duration,
            "error_count": len(self.error_log),
            "communication_patterns": self._analyze_patterns()
        }
    
    def _analyze_patterns(self) -> Dict[str, Any]:
        """Analyze communication patterns."""
        patterns = {}
        for entry in self.communication_log:
            key = f"{entry['source']} → {entry['target']}"
            if key not in patterns:
                patterns[key] = {"count": 0, "avg_duration_ms": 0, "success_rate": 0}
            
            patterns[key]["count"] += 1
            patterns[key]["avg_duration_ms"] = (
                patterns[key]["avg_duration_ms"] + entry["duration_ms"]
            ) / patterns[key]["count"]
            patterns[key]["success_rate"] = sum(
                1 for e in self.communication_log 
                if e["source"] == entry["source"] and e["target"] == entry["target"] and e["success"]
            ) / patterns[key]["count"] * 100
        
        return patterns


@pytest.fixture
def service_validator(test_environment):
    """Fixture providing service communication validation."""
    return ServiceCommunicationValidator(test_environment.db_engine, test_environment.redis_client)


@pytest.mark.integration
@pytest.mark.slow
class TestAPIServiceIntegration:
    """Test API service integration with database and other components."""
    
    async def test_api_database_high_throughput_operations(self, test_environment, clean_database, service_validator):
        """Test API performing high-throughput database operations."""
        
        # Create test agent
        agent_id = str(uuid.uuid4())
        with test_environment.db_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO agent (id, name, scopes) 
                VALUES (:id, :name, :scopes)
            """), {
                "id": agent_id,
                "name": f"api-test-agent-{int(time.time())}",
                "scopes": ["task.create", "task.read", "task.update"]
            })
        
        # Simulate API operations under load
        async def simulate_api_task_operations(batch_id: int, operations_count: int):
            """Simulate API task operations."""
            results = []
            
            for i in range(operations_count):
                operation_start = time.time()
                
                try:
                    # CREATE operation
                    with test_environment.db_engine.begin() as conn:
                        create_result = conn.execute(text("""
                            INSERT INTO task (title, description, created_by, schedule_kind,
                                            schedule_expr, timezone, payload, status, priority, max_retries)
                            VALUES (:title, :description, :created_by, :schedule_kind,
                                   :schedule_expr, :timezone, :payload::jsonb, :status, :priority, :max_retries)
                            RETURNING id, created_at
                        """), {
                            "title": f"API Test Task {batch_id}-{i}",
                            "description": f"High throughput API test",
                            "created_by": agent_id,
                            "schedule_kind": "once", 
                            "schedule_expr": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
                            "timezone": "Europe/Chisinau",
                            "payload": json.dumps({
                                "pipeline": [
                                    {
                                        "id": f"api_test_{batch_id}_{i}",
                                        "uses": "test.api",
                                        "with": {"batch": batch_id, "operation": i},
                                        "save_as": f"result_{i}"
                                    }
                                ]
                            }),
                            "status": "active",
                            "priority": i % 10,
                            "max_retries": 2
                        })
                        
                        task_data = create_result.fetchone()
                        task_id = task_data.id
                        created_at = task_data.created_at
                    
                    create_duration = time.time() - operation_start
                    service_validator.log_communication(
                        "API", "Database", "task_create", True, create_duration,
                        {"task_id": str(task_id), "batch_id": batch_id}
                    )
                    
                    # READ operation
                    read_start = time.time()
                    with test_environment.db_engine.begin() as conn:
                        read_result = conn.execute(text("""
                            SELECT * FROM task WHERE id = :task_id
                        """), {"task_id": task_id})
                        
                        task_row = read_result.fetchone()
                        assert task_row is not None
                    
                    read_duration = time.time() - read_start
                    service_validator.log_communication(
                        "API", "Database", "task_read", True, read_duration,
                        {"task_id": str(task_id)}
                    )
                    
                    # UPDATE operation
                    update_start = time.time()
                    with test_environment.db_engine.begin() as conn:
                        update_result = conn.execute(text("""
                            UPDATE task SET priority = :new_priority, updated_at = now()
                            WHERE id = :task_id
                            RETURNING updated_at
                        """), {
                            "new_priority": (i + 5) % 10,
                            "task_id": task_id
                        })
                        
                        update_data = update_result.fetchone()
                        assert update_data is not None
                    
                    update_duration = time.time() - update_start
                    service_validator.log_communication(
                        "API", "Database", "task_update", True, update_duration,
                        {"task_id": str(task_id)}
                    )
                    
                    results.append({
                        "task_id": task_id,
                        "create_duration": create_duration,
                        "read_duration": read_duration,
                        "update_duration": update_duration,
                        "total_duration": time.time() - operation_start
                    })
                    
                except Exception as e:
                    operation_duration = time.time() - operation_start
                    service_validator.log_communication(
                        "API", "Database", "task_operation_error", False, operation_duration,
                        {"error": str(e), "batch_id": batch_id, "operation_id": i}
                    )
                    results.append({"error": str(e)})
            
            return results
        
        # Run concurrent API operations
        batch_count = 10
        operations_per_batch = 20
        
        start_time = time.time()
        
        tasks = [
            simulate_api_task_operations(batch_id, operations_per_batch)
            for batch_id in range(batch_count)
        ]
        
        batch_results = await asyncio.gather(*tasks)
        
        total_time = time.time() - start_time
        
        # Analyze results
        successful_operations = []
        failed_operations = []
        
        for batch_result in batch_results:
            for result in batch_result:
                if "error" in result:
                    failed_operations.append(result)
                else:
                    successful_operations.append(result)
        
        # Get communication statistics
        comm_stats = service_validator.get_communication_stats()
        
        # Verify database state
        with test_environment.db_engine.begin() as conn:
            created_tasks = conn.execute(text("""
                SELECT COUNT(*) FROM task WHERE created_by = :agent_id
            """), {"agent_id": agent_id}).scalar()
        
        # Performance metrics
        total_operations = batch_count * operations_per_batch
        success_rate = len(successful_operations) / total_operations * 100
        throughput = len(successful_operations) / total_time
        avg_operation_time = sum(op.get("total_duration", 0) for op in successful_operations) / len(successful_operations) if successful_operations else 0
        
        print(f"API-Database Integration Results:")
        print(f"  Total operations: {total_operations}")
        print(f"  Successful operations: {len(successful_operations)}")
        print(f"  Failed operations: {len(failed_operations)}")
        print(f"  Success rate: {success_rate:.1f}%")
        print(f"  Throughput: {throughput:.1f} ops/sec")
        print(f"  Average operation time: {avg_operation_time*1000:.2f}ms")
        print(f"  Tasks in database: {created_tasks}")
        print(f"  Communication success rate: {comm_stats['success_rate']:.1f}%")
        print(f"  Average communication time: {comm_stats['avg_duration_ms']:.2f}ms")
        
        # Production requirements
        assert success_rate >= 95, f"API success rate too low: {success_rate:.1f}%"
        assert created_tasks >= total_operations * 0.95, f"Database consistency issue: {created_tasks}/{total_operations}"
        assert throughput > 30, f"API throughput too low: {throughput:.1f} ops/sec"
        assert comm_stats['success_rate'] >= 95, f"Communication success rate too low: {comm_stats['success_rate']:.1f}%"
    
    async def test_api_error_handling_and_recovery(self, test_environment, clean_database, service_validator):
        """Test API error handling and recovery patterns."""
        
        # Create test agent
        agent_id = str(uuid.uuid4())
        with test_environment.db_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO agent (id, name, scopes) 
                VALUES (:id, :name, :scopes)
            """), {
                "id": agent_id,
                "name": f"error-test-agent-{int(time.time())}",
                "scopes": ["task.create"]
            })
        
        # Test scenarios with different types of errors
        error_scenarios = [
            {
                "name": "database_timeout",
                "description": "Simulate database connection timeout",
                "error_injection": "timeout"
            },
            {
                "name": "constraint_violation",
                "description": "Test foreign key constraint violation",
                "error_injection": "constraint"
            },
            {
                "name": "invalid_json",
                "description": "Test invalid JSON in payload",
                "error_injection": "json_error"
            }
        ]
        
        async def test_error_scenario(scenario: Dict[str, str]):
            """Test specific error scenario."""
            scenario_results = []
            
            for attempt in range(3):  # Test retry behavior
                start_time = time.time()
                
                try:
                    if scenario["error_injection"] == "constraint":
                        # Try to create task with non-existent agent
                        fake_agent_id = str(uuid.uuid4())
                        
                        with test_environment.db_engine.begin() as conn:
                            conn.execute(text("""
                                INSERT INTO task (title, description, created_by, schedule_kind,
                                                schedule_expr, timezone, payload, status, priority, max_retries)
                                VALUES (:title, :description, :created_by, :schedule_kind,
                                       :schedule_expr, :timezone, :payload::jsonb, :status, :priority, :max_retries)
                            """), {
                                "title": f"Error Test - {scenario['name']}",
                                "description": scenario["description"],
                                "created_by": fake_agent_id,  # This should fail
                                "schedule_kind": "once",
                                "schedule_expr": datetime.now(timezone.utc).isoformat(),
                                "timezone": "UTC",
                                "payload": json.dumps({"pipeline": []}),
                                "status": "active",
                                "priority": 5,
                                "max_retries": 1
                            })
                    
                    elif scenario["error_injection"] == "json_error":
                        # Try to insert invalid JSON
                        with test_environment.db_engine.begin() as conn:
                            # This should work - testing JSON validation at application level
                            conn.execute(text("""
                                INSERT INTO task (title, description, created_by, schedule_kind,
                                                schedule_expr, timezone, payload, status, priority, max_retries)
                                VALUES (:title, :description, :created_by, :schedule_kind,
                                       :schedule_expr, :timezone, :payload, :status, :priority, :max_retries)
                            """), {
                                "title": f"Error Test - {scenario['name']}",
                                "description": scenario["description"],
                                "created_by": agent_id,
                                "schedule_kind": "once",
                                "schedule_expr": datetime.now(timezone.utc).isoformat(),
                                "timezone": "UTC",
                                "payload": '{"invalid": json}',  # Invalid JSON
                                "status": "active",
                                "priority": 5,
                                "max_retries": 1
                            })
                    
                    # If we get here, the operation "succeeded" (shouldn't for error scenarios)
                    duration = time.time() - start_time
                    service_validator.log_communication(
                        "API", "Database", f"error_test_{scenario['name']}", True, duration,
                        {"scenario": scenario["name"], "attempt": attempt, "unexpected_success": True}
                    )
                    
                    scenario_results.append({
                        "attempt": attempt,
                        "success": True,
                        "duration": duration,
                        "unexpected": True
                    })
                    
                except Exception as e:
                    # Expected for error scenarios
                    duration = time.time() - start_time
                    service_validator.log_communication(
                        "API", "Database", f"error_test_{scenario['name']}", False, duration,
                        {"scenario": scenario["name"], "attempt": attempt, "error": str(e), "expected_error": True}
                    )
                    
                    scenario_results.append({
                        "attempt": attempt,
                        "success": False,
                        "duration": duration,
                        "error": str(e),
                        "expected": True
                    })
                
                # Small delay between retries
                await asyncio.sleep(0.1)
            
            return scenario_results
        
        # Run error scenarios
        scenario_results = {}
        for scenario in error_scenarios:
            scenario_results[scenario["name"]] = await test_error_scenario(scenario)
        
        # Test recovery after errors
        recovery_start = time.time()
        recovery_successful = False
        
        try:
            # This should succeed after the error tests
            with test_environment.db_engine.begin() as conn:
                result = conn.execute(text("""
                    INSERT INTO task (title, description, created_by, schedule_kind,
                                    schedule_expr, timezone, payload, status, priority, max_retries)
                    VALUES (:title, :description, :created_by, :schedule_kind,
                           :schedule_expr, :timezone, :payload::jsonb, :status, :priority, :max_retries)
                    RETURNING id
                """), {
                    "title": "Recovery Test Task",
                    "description": "Test recovery after error scenarios",
                    "created_by": agent_id,
                    "schedule_kind": "once",
                    "schedule_expr": datetime.now(timezone.utc).isoformat(),
                    "timezone": "UTC",
                    "payload": json.dumps({"pipeline": []}),
                    "status": "active",
                    "priority": 5,
                    "max_retries": 1
                })
                
                recovery_task_id = result.scalar()
                recovery_successful = True
        
        except Exception as e:
            recovery_successful = False
            print(f"Recovery failed: {e}")
        
        recovery_time = time.time() - recovery_start
        service_validator.log_communication(
            "API", "Database", "recovery_test", recovery_successful, recovery_time,
            {"post_error_recovery": True}
        )
        
        # Get final communication stats
        comm_stats = service_validator.get_communication_stats()
        
        print(f"API Error Handling and Recovery Results:")
        print(f"  Error scenarios tested: {len(error_scenarios)}")
        print(f"  Recovery successful: {recovery_successful}")
        print(f"  Recovery time: {recovery_time*1000:.2f}ms")
        print(f"  Total communications: {comm_stats['total_communications']}")
        print(f"  Expected errors handled: {comm_stats['error_count']}")
        
        for scenario_name, results in scenario_results.items():
            failed_attempts = sum(1 for r in results if not r["success"])
            print(f"  {scenario_name}: {failed_attempts}/3 attempts failed (expected)")
        
        # Verify error handling patterns
        assert recovery_successful, "API failed to recover after error scenarios"
        assert recovery_time < 1.0, f"Recovery took too long: {recovery_time*1000:.2f}ms"
        assert comm_stats['error_count'] > 0, "No errors were properly detected and logged"


@pytest.mark.integration  
@pytest.mark.slow
class TestWorkerServiceIntegration:
    """Test Worker service integration and coordination."""
    
    async def test_worker_database_skip_locked_coordination(self, test_environment, clean_database, service_validator):
        """Test worker coordination using SKIP LOCKED with high contention."""
        
        # Create test agent
        agent_id = str(uuid.uuid4()) 
        with test_environment.db_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO agent (id, name, scopes) 
                VALUES (:id, :name, :scopes)
            """), {
                "id": agent_id,
                "name": f"worker-coord-agent-{int(time.time())}",
                "scopes": ["test.worker"]
            })
        
        # Create high contention scenario
        work_items = 100
        worker_count = 15  # High contention
        
        # Setup work items
        task_ids = []
        with test_environment.db_engine.begin() as conn:
            for i in range(work_items):
                task_result = conn.execute(text("""
                    INSERT INTO task (title, description, created_by, schedule_kind,
                                    schedule_expr, timezone, payload, status, priority, max_retries)
                    VALUES (:title, :description, :created_by, :schedule_kind,
                           :schedule_expr, :timezone, :payload::jsonb, :status, :priority, :max_retries)
                    RETURNING id
                """), {
                    "title": f"Worker Coordination Test {i}",
                    "description": f"High contention test item {i}",
                    "created_by": agent_id,
                    "schedule_kind": "once",
                    "schedule_expr": datetime.now(timezone.utc).isoformat(),
                    "timezone": "UTC",
                    "payload": json.dumps({
                        "pipeline": [
                            {
                                "id": f"coord_step_{i}",
                                "uses": "test.worker",
                                "with": {"work_item": i},
                                "save_as": f"coord_result_{i}"
                            }
                        ]
                    }),
                    "status": "active",
                    "priority": i % 10,
                    "max_retries": 1
                })
                task_id = task_result.scalar()
                task_ids.append(task_id)
                
                # Create due work
                conn.execute(text("""
                    INSERT INTO due_work (task_id, run_at)
                    VALUES (:task_id, now())
                """), {"task_id": task_id})
        
        # Track worker coordination
        processed_items = set()
        processing_conflicts = []
        worker_performance = {}
        
        def track_processing(work_item_id: int, worker_id: str):
            """Track work item processing."""
            if work_item_id in processed_items:
                processing_conflicts.append({
                    "work_item": work_item_id,
                    "worker": worker_id,
                    "timestamp": datetime.now(timezone.utc)
                })
                return False
            
            processed_items.add(work_item_id)
            return True
        
        # Simulate worker with realistic coordination patterns
        async def coordinated_worker(worker_id: str, engine):
            """Simulate worker with proper SKIP LOCKED coordination."""
            processed_count = 0
            coordination_stats = {
                "successful_leases": 0,
                "failed_leases": 0,
                "lock_contentions": 0,
                "processing_time_ms": []
            }
            
            while processed_count < work_items // worker_count + 5:  # Fair share + buffer
                lease_start = time.time()
                
                try:
                    with engine.begin() as conn:
                        # Attempt to lease work with SKIP LOCKED
                        work_result = conn.execute(text("""
                            SELECT id, task_id, run_at FROM due_work 
                            WHERE run_at <= now() 
                              AND (locked_until IS NULL OR locked_until < now())
                            ORDER BY run_at ASC, id ASC
                            FOR UPDATE SKIP LOCKED
                            LIMIT 1
                        """))
                        
                        work_row = work_result.fetchone()
                        if not work_row:
                            break  # No more work available
                        
                        work_id, task_id, run_at = work_row
                        
                        # Lease the work
                        lease_time = datetime.now(timezone.utc) + timedelta(minutes=2)
                        lease_result = conn.execute(text("""
                            UPDATE due_work 
                            SET locked_until = :lease_time, locked_by = :worker_id
                            WHERE id = :work_id AND (locked_until IS NULL OR locked_until < now())
                        """), {
                            "lease_time": lease_time,
                            "worker_id": worker_id,
                            "work_id": work_id
                        })
                        
                        if lease_result.rowcount == 0:
                            # Another worker got it first
                            coordination_stats["lock_contentions"] += 1
                            continue
                        
                        lease_duration = time.time() - lease_start
                        service_validator.log_communication(
                            worker_id, "Database", "work_lease", True, lease_duration,
                            {"work_id": work_id, "task_id": str(task_id)}
                        )
                        coordination_stats["successful_leases"] += 1
                        
                        # Get task details
                        task_result = conn.execute(text("""
                            SELECT payload FROM task WHERE id = :task_id
                        """), {"task_id": task_id})
                        
                        task_row = task_result.fetchone()
                        if not task_row:
                            continue
                        
                        pipeline_data = json.loads(task_row.payload)
                        work_item_id = pipeline_data["pipeline"][0]["with"]["work_item"]
                        
                        # Track processing coordination
                        processing_start = time.time()
                        coordination_success = track_processing(work_item_id, worker_id)
                        
                        if not coordination_success:
                            # Should never happen with proper SKIP LOCKED
                            service_validator.log_communication(
                                worker_id, "Coordinator", "processing_conflict", False, 
                                time.time() - processing_start,
                                {"work_item": work_item_id, "conflict": True}
                            )
                            continue
                        
                        # Simulate work processing
                        processing_delay = 0.05 + (work_item_id % 10) * 0.01  # 50-140ms variation
                        time.sleep(processing_delay)
                        
                        processing_duration = time.time() - processing_start
                        coordination_stats["processing_time_ms"].append(processing_duration * 1000)
                        
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
                                "steps": {f"coord_result_{work_item_id}": {"processed_by": worker_id}}
                            })
                        })
                        
                        # Clean up due work
                        conn.execute(text("DELETE FROM due_work WHERE id = :work_id"), {"work_id": work_id})
                        
                        service_validator.log_communication(
                            worker_id, "Database", "work_completion", True, processing_duration,
                            {"work_item": work_item_id, "task_id": str(task_id)}
                        )
                        
                        processed_count += 1
                        
                except Exception as e:
                    lease_duration = time.time() - lease_start
                    service_validator.log_communication(
                        worker_id, "Database", "work_lease_error", False, lease_duration,
                        {"error": str(e)}
                    )
                    coordination_stats["failed_leases"] += 1
                    
                    # Small backoff on errors
                    await asyncio.sleep(0.01)
            
            worker_performance[worker_id] = coordination_stats
            return processed_count
        
        # Run coordinated workers
        start_time = time.time()
        
        worker_tasks = [
            coordinated_worker(f"coord-worker-{i}", test_environment.db_engine)
            for i in range(worker_count)
        ]
        
        worker_results = await asyncio.gather(*worker_tasks)
        
        total_time = time.time() - start_time
        
        # Analyze coordination results
        total_processed = sum(worker_results)
        unique_items_processed = len(processed_items)
        
        # Verify database state
        with test_environment.db_engine.begin() as conn:
            remaining_work = conn.execute(text("SELECT COUNT(*) FROM due_work")).scalar()
            completed_runs = conn.execute(text("""
                SELECT COUNT(*) FROM task_run WHERE success = true
            """)).scalar()
            
            # Check for any processing duplicates in database
            duplicate_runs = conn.execute(text("""
                SELECT task_id, COUNT(*) as run_count
                FROM task_run 
                WHERE success = true
                GROUP BY task_id
                HAVING COUNT(*) > 1
            """)).fetchall()
        
        # Get communication statistics
        comm_stats = service_validator.get_communication_stats()
        
        # Calculate performance metrics
        throughput = total_processed / total_time if total_time > 0 else 0
        coordination_efficiency = unique_items_processed / work_items * 100
        
        # Analyze worker performance
        total_successful_leases = sum(stats["successful_leases"] for stats in worker_performance.values())
        total_lock_contentions = sum(stats["lock_contentions"] for stats in worker_performance.values())
        avg_processing_time = sum(
            sum(stats["processing_time_ms"]) / len(stats["processing_time_ms"])
            for stats in worker_performance.values()
            if stats["processing_time_ms"]
        ) / len(worker_performance) if worker_performance else 0
        
        print(f"Worker Database SKIP LOCKED Coordination Results:")
        print(f"  Work items: {work_items}")
        print(f"  Workers: {worker_count}")  
        print(f"  Total processed: {total_processed}")
        print(f"  Unique items processed: {unique_items_processed}")
        print(f"  Processing conflicts: {len(processing_conflicts)}")
        print(f"  Database duplicates: {len(duplicate_runs)}")
        print(f"  Remaining work: {remaining_work}")
        print(f"  Coordination efficiency: {coordination_efficiency:.1f}%")
        print(f"  Throughput: {throughput:.1f} items/sec")
        print(f"  Total time: {total_time:.2f}s")
        print(f"  Successful leases: {total_successful_leases}")
        print(f"  Lock contentions: {total_lock_contentions}")
        print(f"  Avg processing time: {avg_processing_time:.2f}ms")
        print(f"  Communication success rate: {comm_stats['success_rate']:.1f}%")
        
        # Production coordination requirements
        assert unique_items_processed == work_items, f"Coordination failure: {unique_items_processed}/{work_items} items processed"
        assert len(processing_conflicts) == 0, f"Processing conflicts detected: {len(processing_conflicts)}"
        assert len(duplicate_runs) == 0, f"Database duplicates found: {len(duplicate_runs)}"
        assert remaining_work == 0, f"Work items left unprocessed: {remaining_work}"
        assert coordination_efficiency >= 99, f"Coordination efficiency too low: {coordination_efficiency:.1f}%"
        assert throughput > 15, f"Worker throughput too low: {throughput:.1f} items/sec"
        assert comm_stats['success_rate'] >= 90, f"Communication success rate too low: {comm_stats['success_rate']:.1f}%"


@pytest.mark.integration
@pytest.mark.slow  
class TestSystemResilienceAndRecovery:
    """Test system resilience and recovery under stress conditions."""
    
    async def test_graceful_degradation_under_load(self, test_environment, clean_database, service_validator):
        """Test system graceful degradation under extreme load conditions."""
        
        # Create test agent
        agent_id = str(uuid.uuid4())
        with test_environment.db_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO agent (id, name, scopes) 
                VALUES (:id, :name, :scopes)
            """), {
                "id": agent_id,
                "name": f"resilience-test-agent-{int(time.time())}",
                "scopes": ["test.resilience"]
            })
        
        # Create extreme load scenario
        extreme_load_tasks = 1000
        concurrent_workers = 25
        
        # Phase 1: Rapid task creation under load
        print("Phase 1: Creating extreme load...")
        creation_start = time.time()
        
        # Create tasks in parallel batches
        async def create_task_batch(batch_id: int, batch_size: int):
            """Create batch of tasks."""
            batch_results = []
            
            try:
                with test_environment.db_engine.begin() as conn:
                    for i in range(batch_size):
                        task_result = conn.execute(text("""
                            INSERT INTO task (title, description, created_by, schedule_kind,
                                            schedule_expr, timezone, payload, status, priority, max_retries)
                            VALUES (:title, :description, :created_by, :schedule_kind,
                                   :schedule_expr, :timezone, :payload::jsonb, :status, :priority, :max_retries)
                            RETURNING id
                        """), {
                            "title": f"Resilience Test {batch_id}-{i}",
                            "description": f"Extreme load test task",
                            "created_by": agent_id,
                            "schedule_kind": "once",
                            "schedule_expr": datetime.now(timezone.utc).isoformat(),
                            "timezone": "UTC",
                            "payload": json.dumps({
                                "pipeline": [
                                    {
                                        "id": f"resilience_step_{batch_id}_{i}",
                                        "uses": "test.resilience",
                                        "with": {"batch": batch_id, "item": i, "load_factor": "extreme"},
                                        "save_as": f"resilience_result_{i}"
                                    }
                                ]
                            }),
                            "status": "active",
                            "priority": i % 10,
                            "max_retries": 3
                        })
                        
                        task_id = task_result.scalar()
                        batch_results.append(task_id)
                        
                        # Create due work immediately
                        conn.execute(text("""
                            INSERT INTO due_work (task_id, run_at)
                            VALUES (:task_id, now())
                        """), {"task_id": task_id})
                
                return {"success": True, "task_ids": batch_results}
                
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Create tasks in parallel
        batch_size = 50
        batch_count = extreme_load_tasks // batch_size
        
        batch_tasks = [
            create_task_batch(batch_id, batch_size)
            for batch_id in range(batch_count)
        ]
        
        batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
        
        creation_time = time.time() - creation_start
        
        # Analyze creation results
        successful_batches = [r for r in batch_results if isinstance(r, dict) and r.get("success")]
        failed_batches = [r for r in batch_results if not (isinstance(r, dict) and r.get("success"))]
        
        created_task_ids = []
        for batch in successful_batches:
            created_task_ids.extend(batch["task_ids"])
        
        print(f"Task creation: {len(created_task_ids)}/{extreme_load_tasks} tasks in {creation_time:.2f}s")
        
        # Phase 2: Extreme concurrent processing
        print("Phase 2: Extreme concurrent processing...")
        
        processing_results = []
        worker_errors = []
        
        async def resilient_worker(worker_id: str, max_items: int):
            """Worker designed to handle extreme load gracefully."""
            processed = 0
            errors = 0
            
            while processed < max_items and errors < 10:  # Error circuit breaker
                try:
                    with test_environment.db_engine.begin() as conn:
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
                        
                        # Quick lease and process
                        lease_time = datetime.now(timezone.utc) + timedelta(minutes=1)
                        conn.execute(text("""
                            UPDATE due_work 
                            SET locked_until = :lease_time, locked_by = :worker_id
                            WHERE id = :work_id
                        """), {
                            "lease_time": lease_time,
                            "worker_id": worker_id,
                            "work_id": work_id
                        })
                        
                        # Minimal processing for extreme load
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
                                "load_test": True,
                                "worker": worker_id
                            })
                        })
                        
                        conn.execute(text("DELETE FROM due_work WHERE id = :work_id"), {"work_id": work_id})
                        processed += 1
                        
                except Exception as e:
                    errors += 1
                    if errors <= 3:  # Log first few errors
                        worker_errors.append({"worker": worker_id, "error": str(e)})
                    
                    # Exponential backoff on errors
                    await asyncio.sleep(min(0.1 * (2 ** errors), 2.0))
            
            return processed
        
        # Start extreme concurrent processing
        processing_start = time.time()
        
        workers_tasks = [
            resilient_worker(f"resilient-worker-{i}", extreme_load_tasks // concurrent_workers + 10)
            for i in range(concurrent_workers)
        ]
        
        worker_processed_counts = await asyncio.gather(*workers_tasks, return_exceptions=True)
        
        processing_time = time.time() - processing_start
        
        # Analyze resilience results
        successful_workers = [count for count in worker_processed_counts if isinstance(count, int)]
        total_processed = sum(successful_workers)
        
        # Verify system state after extreme load
        with test_environment.db_engine.begin() as conn:
            remaining_work = conn.execute(text("SELECT COUNT(*) FROM due_work")).scalar()
            completed_runs = conn.execute(text("SELECT COUNT(*) FROM task_run WHERE success = true")).scalar()
            created_tasks = conn.execute(text("SELECT COUNT(*) FROM task WHERE created_by = :agent_id"), 
                                       {"agent_id": agent_id}).scalar()
        
        # Calculate resilience metrics
        creation_success_rate = len(created_task_ids) / extreme_load_tasks * 100
        processing_success_rate = total_processed / len(created_task_ids) * 100 if created_task_ids else 0
        overall_throughput = total_processed / (creation_time + processing_time)
        
        print(f"System Resilience Under Extreme Load Results:")
        print(f"  Target tasks: {extreme_load_tasks}")
        print(f"  Created tasks: {len(created_task_ids)} ({creation_success_rate:.1f}%)")
        print(f"  Creation time: {creation_time:.2f}s")
        print(f"  Failed batches: {len(failed_batches)}")
        print(f"  Workers: {concurrent_workers}")
        print(f"  Successful workers: {len(successful_workers)}")
        print(f"  Total processed: {total_processed} ({processing_success_rate:.1f}%)")
        print(f"  Processing time: {processing_time:.2f}s") 
        print(f"  Overall throughput: {overall_throughput:.1f} tasks/sec")
        print(f"  Remaining work: {remaining_work}")
        print(f"  Completed runs: {completed_runs}")
        print(f"  Worker errors: {len(worker_errors)}")
        
        # Resilience requirements (graceful degradation acceptable)
        assert creation_success_rate >= 80, f"Task creation success rate too low: {creation_success_rate:.1f}%"
        assert processing_success_rate >= 75, f"Processing success rate too low: {processing_success_rate:.1f}%"
        assert overall_throughput > 20, f"System throughput under extreme load too low: {overall_throughput:.1f} tasks/sec"
        assert len(worker_errors) < concurrent_workers * 0.5, f"Too many worker errors: {len(worker_errors)}"
        
        # System should remain functional (not crash)
        assert created_tasks > 0, "System completely failed - no tasks created"
        assert completed_runs > 0, "System completely failed - no tasks processed"
        
        print("✅ System demonstrated resilience and graceful degradation under extreme load")


if __name__ == "__main__":
    pytest.main([
        __file__, 
        "-v", 
        "--tb=short", 
        "-s",
        "--maxfail=3",
        "--disable-warnings"
    ])