#!/usr/bin/env python3
"""
Comprehensive unit tests for worker concurrency and SKIP LOCKED patterns.

Tests worker coordination, lease management, and concurrent processing including:
- SKIP LOCKED work leasing prevents double processing
- Lease timeout and recovery mechanisms  
- Exponential backoff with jitter for retry logic
- Worker heartbeat and health monitoring
- Race condition prevention under high concurrency
- Graceful shutdown and resource cleanup
"""

import pytest
import asyncio
import time
import uuid
import threading
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock
from concurrent.futures import ThreadPoolExecutor, as_completed

from workers.runner import WorkerRunner
from workers.config import WorkerConfig, WorkerMetrics, WorkerState
from workers.coordinator import WorkerCoordinator


class TestSkipLockedLeasing:
    """Test SKIP LOCKED work leasing patterns."""
    
    @pytest.mark.integration
    async def test_skip_locked_prevents_double_processing(self, clean_database):
        """Test that SKIP LOCKED prevents double processing of work items."""
        
        # Create test data
        agent_data = await insert_test_agent(clean_database)
        task_data = await insert_test_task(clean_database, agent_data["id"])
        work_id = await insert_due_work(clean_database, task_data["id"])
        
        # Create two workers
        config1 = WorkerConfig.from_dict({
            "worker_id": "worker-1",
            "database_url": clean_database.url,
            "lease_seconds": 60
        })
        config2 = WorkerConfig.from_dict({
            "worker_id": "worker-2", 
            "database_url": clean_database.url,
            "lease_seconds": 60
        })
        
        worker1 = WorkerRunner(config1)
        worker2 = WorkerRunner(config2)
        
        # Worker 1 leases work
        lease1 = worker1.lease_one()
        assert lease1 is not None
        assert lease1["id"] == work_id
        assert lease1["task_id"] == task_data["id"]
        
        # Worker 2 should not get the same work (SKIP LOCKED)
        lease2 = worker2.lease_one()
        assert lease2 is None  # Should be None because work is locked
        
        # Complete work with worker 1
        worker1.delete_work(lease1["id"])
        
        # Verify work is no longer available
        remaining_work = worker1.lease_one()
        assert remaining_work is None
    
    @pytest.mark.integration
    async def test_concurrent_lease_attempts(self, clean_database):
        """Test concurrent lease attempts by multiple workers."""
        
        # Create multiple work items
        agent_data = await insert_test_agent(clean_database)
        work_items = []
        
        for i in range(10):
            task_data = await insert_test_task(clean_database, agent_data["id"])
            work_id = await insert_due_work(clean_database, task_data["id"])
            work_items.append(work_id)
        
        # Create multiple workers
        workers = []
        for i in range(5):
            config = WorkerConfig.from_dict({
                "worker_id": f"worker-{i}",
                "database_url": clean_database.url,
                "lease_seconds": 60
            })
            workers.append(WorkerRunner(config))
        
        # Concurrent lease attempts
        leased_items = []
        
        def lease_work(worker):
            lease = worker.lease_one()
            if lease:
                leased_items.append((worker.config.worker_id, lease["id"]))
            return lease
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(lease_work, worker) for worker in workers]
            results = [f.result() for f in as_completed(futures)]
        
        # Count successful leases
        successful_leases = [r for r in results if r is not None]
        assert len(successful_leases) <= len(work_items)
        
        # Verify no duplicate work item IDs
        leased_work_ids = [item[1] for item in leased_items]
        assert len(leased_work_ids) == len(set(leased_work_ids))  # No duplicates
        
        # Clean up
        for worker in workers:
            if hasattr(worker, 'current_lease') and worker.current_lease:
                worker.delete_work(worker.current_lease["id"])
    
    @pytest.mark.integration
    async def test_lease_timeout_recovery(self, clean_database):
        """Test that expired leases are recoverable by other workers."""
        
        # Create test data
        agent_data = await insert_test_agent(clean_database)
        task_data = await insert_test_task(clean_database, agent_data["id"])
        work_id = await insert_due_work(clean_database, task_data["id"])
        
        # Worker 1 leases work with short timeout
        config1 = WorkerConfig.from_dict({
            "worker_id": "worker-1",
            "database_url": clean_database.url,
            "lease_seconds": 1  # Very short lease
        })
        worker1 = WorkerRunner(config1)
        
        lease1 = worker1.lease_one()
        assert lease1 is not None
        assert lease1["id"] == work_id
        
        # Wait for lease to expire
        time.sleep(2)
        
        # Worker 2 should be able to lease the expired work
        config2 = WorkerConfig.from_dict({
            "worker_id": "worker-2",
            "database_url": clean_database.url,
            "lease_seconds": 60
        })
        worker2 = WorkerRunner(config2)
        
        recovered_lease = worker2.lease_one()
        assert recovered_lease is not None
        assert recovered_lease["id"] == work_id
        assert recovered_lease["task_id"] == task_data["id"]
        
        # Clean up
        worker2.delete_work(recovered_lease["id"])
    
    @pytest.mark.integration
    async def test_lease_renewal(self, clean_database):
        """Test lease renewal for long-running tasks."""
        
        # Create test data
        agent_data = await insert_test_agent(clean_database)
        task_data = await insert_test_task(clean_database, agent_data["id"])
        work_id = await insert_due_work(clean_database, task_data["id"])
        
        config = WorkerConfig.from_dict({
            "worker_id": "test-worker",
            "database_url": clean_database.url,
            "lease_seconds": 5  # Short lease for testing
        })
        worker = WorkerRunner(config)
        
        # Lease work item
        lease = worker.lease_one()
        assert lease is not None
        original_locked_until = lease["locked_until"]
        
        # Wait a bit then renew lease
        time.sleep(2)
        worker.renew_lease(lease["id"], 10)
        
        # Verify lease was renewed
        assert worker.current_lease["locked_until"] > original_locked_until
        
        # Another worker should not be able to lease it
        config2 = WorkerConfig.from_dict({
            "worker_id": "worker-2",
            "database_url": clean_database.url,
            "lease_seconds": 60
        })
        worker2 = WorkerRunner(config2)
        
        competing_lease = worker2.lease_one()
        assert competing_lease is None
        
        # Clean up
        worker.delete_work(lease["id"])


class TestRetryMechanisms:
    """Test retry logic and backoff strategies."""
    
    def test_exponential_backoff_calculation(self):
        """Test exponential backoff delay calculation."""
        config = WorkerConfig.from_dict({
            "worker_id": "test-worker",
            "database_url": "sqlite:///:memory:",
            "backoff_base_delay": 1.0,
            "backoff_max_delay": 60.0,
            "backoff_jitter": True
        })
        worker = WorkerRunner(config)
        
        # Test exponential growth
        delay1 = worker.exponential_backoff_with_jitter(1)
        delay2 = worker.exponential_backoff_with_jitter(2)
        delay3 = worker.exponential_backoff_with_jitter(3)
        
        # Should grow exponentially but with jitter
        assert 0.5 <= delay1 <= 1.0  # Base delay with jitter
        assert 1.0 <= delay2 <= 2.0  # 2^1 with jitter
        assert 2.0 <= delay3 <= 4.0  # 2^2 with jitter
        
        # Test maximum cap
        delay_high = worker.exponential_backoff_with_jitter(10)
        assert delay_high <= 60.0  # Should be capped at max_delay
    
    def test_exponential_backoff_without_jitter(self):
        """Test exponential backoff without jitter."""
        config = WorkerConfig.from_dict({
            "worker_id": "test-worker", 
            "database_url": "sqlite:///:memory:",
            "backoff_base_delay": 2.0,
            "backoff_max_delay": 30.0,
            "backoff_jitter": False
        })
        worker = WorkerRunner(config)
        
        delay1 = worker.exponential_backoff_with_jitter(1)
        delay2 = worker.exponential_backoff_with_jitter(2)
        delay3 = worker.exponential_backoff_with_jitter(3)
        
        # Should be exact values without jitter
        assert delay1 == 2.0  # 2^0 * 2.0
        assert delay2 == 4.0  # 2^1 * 2.0
        assert delay3 == 8.0  # 2^2 * 2.0
    
    def test_retry_decision_logic(self):
        """Test retry decision based on error types."""
        config = WorkerConfig.from_dict({
            "worker_id": "test-worker",
            "database_url": "sqlite:///:memory:"
        })
        worker = WorkerRunner(config)
        
        task = {"id": "test-task", "max_retries": 3}
        
        # Network errors should be retried
        network_error = Exception("Connection timeout")
        assert worker.should_retry(task, 1, network_error) is True
        assert worker.should_retry(task, 2, network_error) is True
        assert worker.should_retry(task, 3, network_error) is True
        assert worker.should_retry(task, 4, network_error) is False  # Exceeded max retries
        
        # Validation errors should not be retried
        validation_error = Exception("Schema validation failed")
        assert worker.should_retry(task, 1, validation_error) is False
        
        # Configuration errors should not be retried
        config_error = Exception("Configuration error: missing parameter")
        assert worker.should_retry(task, 1, config_error) is False
        
        # Authentication errors should not be retried
        auth_error = Exception("Authentication failed")
        assert worker.should_retry(task, 1, auth_error) is False


class TestWorkerMetrics:
    """Test worker metrics collection and reporting."""
    
    def test_metrics_initialization(self):
        """Test metrics initialization with default values."""
        metrics = WorkerMetrics()
        
        assert metrics.tasks_processed == 0
        assert metrics.tasks_succeeded == 0
        assert metrics.tasks_failed == 0
        assert metrics.leases_acquired == 0
        assert metrics.leases_renewed == 0
        assert metrics.leases_expired == 0
        assert metrics.errors_encountered == 0
        assert metrics.heartbeats_sent == 0
        
        summary = metrics.get_summary()
        assert summary["success_rate"] == 0.0
        assert summary["avg_processing_time_ms"] == 0.0
    
    def test_task_completion_metrics(self):
        """Test task completion metrics recording."""
        metrics = WorkerMetrics()
        
        # Record successful tasks
        metrics.record_task_completed(True, 1.5, 0)  # Success, 1.5s, no retries
        metrics.record_task_completed(True, 2.3, 1)  # Success, 2.3s, 1 retry
        
        # Record failed task
        metrics.record_task_completed(False, 0.8, 2)  # Failed, 0.8s, 2 retries
        
        assert metrics.tasks_processed == 3
        assert metrics.tasks_succeeded == 2
        assert metrics.tasks_failed == 1
        
        summary = metrics.get_summary()
        assert summary["success_rate"] == pytest.approx(0.667, abs=0.01)
        assert summary["avg_processing_time_ms"] == pytest.approx(1533.33, abs=1)
    
    def test_lease_metrics(self):
        """Test lease-related metrics recording."""
        metrics = WorkerMetrics()
        
        metrics.record_lease_acquired()
        metrics.record_lease_acquired()
        metrics.record_lease_renewed()
        metrics.record_lease_expired()
        
        assert metrics.leases_acquired == 2
        assert metrics.leases_renewed == 1
        assert metrics.leases_expired == 1
    
    def test_error_metrics(self):
        """Test error metrics recording."""
        metrics = WorkerMetrics()
        
        for _ in range(5):
            metrics.record_error()
        
        assert metrics.errors_encountered == 5
        
        summary = metrics.get_summary()
        assert summary["errors_encountered"] == 5
    
    def test_heartbeat_metrics(self):
        """Test heartbeat metrics recording."""
        metrics = WorkerMetrics()
        
        for _ in range(10):
            metrics.record_heartbeat_sent()
        
        assert metrics.heartbeats_sent == 10
    
    def test_metrics_summary_calculation(self):
        """Test comprehensive metrics summary calculation."""
        metrics = WorkerMetrics()
        
        # Simulate realistic worker activity
        processing_times = [1.2, 0.8, 2.1, 1.5, 3.2, 0.9, 1.8]
        retry_counts = [0, 1, 0, 2, 1, 0, 1]
        successes = [True, True, False, True, True, True, False]
        
        for time, retries, success in zip(processing_times, retry_counts, successes):
            metrics.record_task_completed(success, time, retries)
        
        for _ in range(10):
            metrics.record_lease_acquired()
        
        for _ in range(2):
            metrics.record_lease_renewed()
        
        metrics.record_lease_expired()
        
        for _ in range(3):
            metrics.record_error()
        
        summary = metrics.get_summary()
        
        assert summary["tasks_processed"] == 7
        assert summary["success_rate"] == pytest.approx(0.714, abs=0.01)  # 5/7
        assert summary["avg_processing_time_ms"] > 1000  # Should be > 1 second
        assert summary["total_retry_attempts"] == 5  # Sum of retry counts
        assert summary["leases_acquired"] == 10
        assert summary["errors_encountered"] == 3


class TestWorkerHeartbeat:
    """Test worker heartbeat and health monitoring."""
    
    @pytest.mark.integration
    async def test_heartbeat_recording(self, clean_database):
        """Test worker heartbeat recording in database."""
        config = WorkerConfig.from_dict({
            "worker_id": "heartbeat-test-worker",
            "database_url": clean_database.url,
            "heartbeat_interval": 1
        })
        worker = WorkerRunner(config)
        
        # Send heartbeat
        worker.heartbeat()
        
        # Verify heartbeat was recorded
        with clean_database.begin() as conn:
            result = conn.execute(text("""
                SELECT worker_id, processed_count, pid, hostname 
                FROM worker_heartbeat 
                WHERE worker_id = :worker_id
            """), {"worker_id": config.worker_id})
            
            row = result.fetchone()
            assert row is not None
            assert row.worker_id == config.worker_id
            assert row.processed_count == 0  # Initially 0
            assert row.pid == os.getpid()
            assert row.hostname == os.uname().nodename
    
    @pytest.mark.integration
    async def test_heartbeat_updates(self, clean_database):
        """Test heartbeat updates with task processing counts."""
        config = WorkerConfig.from_dict({
            "worker_id": "heartbeat-update-worker",
            "database_url": clean_database.url
        })
        worker = WorkerRunner(config)
        
        # Initial heartbeat
        worker.heartbeat()
        
        # Simulate task processing
        worker.metrics.record_task_completed(True, 1.0, 0)
        worker.metrics.record_task_completed(True, 1.5, 1)
        
        # Updated heartbeat
        worker.heartbeat()
        
        # Verify update
        with clean_database.begin() as conn:
            result = conn.execute(text("""
                SELECT processed_count FROM worker_heartbeat 
                WHERE worker_id = :worker_id
            """), {"worker_id": config.worker_id})
            
            row = result.fetchone()
            assert row is not None
            assert row.processed_count == 2  # Two tasks processed
    
    def test_heartbeat_interval_timing(self):
        """Test heartbeat interval timing logic."""
        config = WorkerConfig.from_dict({
            "worker_id": "timing-test-worker",
            "database_url": "sqlite:///:memory:",
            "heartbeat_interval": 5
        })
        
        # Mock the heartbeat method to avoid database calls
        with patch.object(WorkerRunner, 'heartbeat') as mock_heartbeat:
            worker = WorkerRunner(config)
            worker.last_heartbeat = time.time() - 6  # 6 seconds ago
            
            # Simulate main loop logic
            now = time.time()
            should_heartbeat = now - worker.last_heartbeat > config.heartbeat_interval
            
            assert should_heartbeat is True
            
            # After heartbeat, should not need another immediately
            worker.last_heartbeat = now
            should_heartbeat = now - worker.last_heartbeat > config.heartbeat_interval
            assert should_heartbeat is False


class TestWorkerLifecycle:
    """Test worker lifecycle management and state transitions."""
    
    def test_worker_state_transitions(self):
        """Test worker state transitions during lifecycle."""
        config = WorkerConfig.from_dict({
            "worker_id": "lifecycle-test-worker",
            "database_url": "sqlite:///:memory:"
        })
        worker = WorkerRunner(config)
        
        # Initial state
        assert worker.state == WorkerState.STARTING
        
        # Simulate state changes
        worker.state = WorkerState.READY
        assert worker.state == WorkerState.READY
        
        worker.state = WorkerState.PROCESSING
        assert worker.state == WorkerState.PROCESSING
        
        worker.state = WorkerState.STOPPING
        assert worker.state == WorkerState.STOPPING
        
        worker.state = WorkerState.STOPPED
        assert worker.state == WorkerState.STOPPED
    
    def test_graceful_shutdown_signal_handling(self):
        """Test graceful shutdown signal handling."""
        config = WorkerConfig.from_dict({
            "worker_id": "shutdown-test-worker",
            "database_url": "sqlite:///:memory:"
        })
        worker = WorkerRunner(config)
        
        # Mock signal handler setup
        with patch('signal.signal') as mock_signal:
            worker.setup_signal_handlers()
            
            # Verify signal handlers were registered
            assert mock_signal.call_count >= 2  # SIGTERM and SIGINT
    
    @pytest.mark.integration
    async def test_lease_cleanup_on_shutdown(self, clean_database):
        """Test that worker releases leases during graceful shutdown."""
        
        # Create test data
        agent_data = await insert_test_agent(clean_database)
        task_data = await insert_test_task(clean_database, agent_data["id"])
        work_id = await insert_due_work(clean_database, task_data["id"])
        
        config = WorkerConfig.from_dict({
            "worker_id": "shutdown-cleanup-worker",
            "database_url": clean_database.url
        })
        worker = WorkerRunner(config)
        
        # Lease work item
        lease = worker.lease_one()
        assert lease is not None
        assert worker.current_lease is not None
        
        # Simulate graceful shutdown
        worker.shutdown()
        
        # Verify lease was released
        with clean_database.begin() as conn:
            result = conn.execute(text("""
                SELECT locked_until, locked_by FROM due_work WHERE id = :work_id
            """), {"work_id": work_id})
            
            row = result.fetchone()
            assert row is not None
            assert row.locked_until is None
            assert row.locked_by is None
    
    def test_worker_config_validation(self):
        """Test worker configuration validation."""
        
        # Valid configuration
        valid_config = {
            "worker_id": "test-worker",
            "database_url": "postgresql://user:pass@host:5432/db",
            "lease_seconds": 60,
            "heartbeat_interval": 30
        }
        
        config = WorkerConfig.from_dict(valid_config)
        assert config.worker_id == "test-worker"
        assert config.lease_seconds == 60
        assert config.heartbeat_interval == 30
        
        # Test required field validation
        with pytest.raises(ValueError):
            WorkerConfig.from_dict({})  # Missing required fields
        
        # Test invalid values
        with pytest.raises(ValueError):
            WorkerConfig.from_dict({
                **valid_config,
                "lease_seconds": -1  # Negative value
            })


class TestExpiredLeaseCleanup:
    """Test cleanup of expired leases from crashed/stuck workers."""
    
    @pytest.mark.integration
    async def test_cleanup_expired_leases(self, clean_database):
        """Test cleanup of expired leases from other workers."""
        
        # Create test data
        agent_data = await insert_test_agent(clean_database)
        task_data = await insert_test_task(clean_database, agent_data["id"])
        work_id = await insert_due_work(clean_database, task_data["id"])
        
        # Simulate expired lease from crashed worker
        expired_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        with clean_database.begin() as conn:
            conn.execute(text("""
                UPDATE due_work 
                SET locked_until = :expired_time, locked_by = 'crashed-worker'
                WHERE id = :work_id
            """), {"expired_time": expired_time, "work_id": work_id})
        
        # Create cleanup worker
        config = WorkerConfig.from_dict({
            "worker_id": "cleanup-worker",
            "database_url": clean_database.url
        })
        worker = WorkerRunner(config)
        
        # Run cleanup
        worker.cleanup_expired_leases()
        
        # Verify lease was cleaned up
        with clean_database.begin() as conn:
            result = conn.execute(text("""
                SELECT locked_until, locked_by FROM due_work WHERE id = :work_id
            """), {"work_id": work_id})
            
            row = result.fetchone()
            assert row is not None
            assert row.locked_until is None
            assert row.locked_by is None
    
    @pytest.mark.integration
    async def test_cleanup_preserves_active_leases(self, clean_database):
        """Test that cleanup preserves active leases from current worker."""
        
        # Create test data
        agent_data = await insert_test_agent(clean_database)
        task_data = await insert_test_task(clean_database, agent_data["id"])
        work_id = await insert_due_work(clean_database, task_data["id"])
        
        config = WorkerConfig.from_dict({
            "worker_id": "active-worker",
            "database_url": clean_database.url,
            "lease_seconds": 300  # 5 minutes
        })
        worker = WorkerRunner(config)
        
        # Lease work with current worker
        lease = worker.lease_one()
        assert lease is not None
        
        # Run cleanup (should preserve own lease)
        worker.cleanup_expired_leases()
        
        # Verify lease is still active
        with clean_database.begin() as conn:
            result = conn.execute(text("""
                SELECT locked_until, locked_by FROM due_work WHERE id = :work_id
            """), {"work_id": work_id})
            
            row = result.fetchone()
            assert row is not None
            assert row.locked_until is not None
            assert row.locked_by == config.worker_id
        
        # Clean up
        worker.delete_work(work_id)
    
    def test_cleanup_interval_timing(self):
        """Test cleanup interval timing logic."""
        config = WorkerConfig.from_dict({
            "worker_id": "cleanup-timing-worker",
            "database_url": "sqlite:///:memory:",
            "cleanup_interval": 300  # 5 minutes
        })
        
        with patch.object(WorkerRunner, 'cleanup_expired_leases') as mock_cleanup:
            worker = WorkerRunner(config)
            worker.last_cleanup = time.time() - 400  # 400 seconds ago
            
            # Simulate main loop logic
            now = time.time()
            should_cleanup = now - worker.last_cleanup > config.cleanup_interval
            
            assert should_cleanup is True
            
            # After cleanup, should not need another immediately
            worker.last_cleanup = now
            should_cleanup = now - worker.last_cleanup > config.cleanup_interval
            assert should_cleanup is False


class TestHighConcurrencyScenarios:
    """Test worker behavior under high concurrency scenarios."""
    
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_high_concurrency_lease_competition(self, clean_database, load_test_config):
        """Test worker behavior under high concurrency lease competition."""
        
        # Create many work items
        agent_data = await insert_test_agent(clean_database)
        work_items = []
        
        for i in range(load_test_config["max_queue_depth"] // 10):  # 100 work items
            task_data = await insert_test_task(clean_database, agent_data["id"])
            work_id = await insert_due_work(clean_database, task_data["id"])
            work_items.append(work_id)
        
        # Create many competing workers
        workers = []
        for i in range(load_test_config["concurrent_workers"]):
            config = WorkerConfig.from_dict({
                "worker_id": f"high-concurrency-worker-{i}",
                "database_url": clean_database.url,
                "lease_seconds": 30
            })
            workers.append(WorkerRunner(config))
        
        # Concurrent lease attempts
        lease_results = []
        
        def compete_for_leases(worker):
            leases = []
            for _ in range(20):  # Each worker tries 20 times
                lease = worker.lease_one()
                if lease:
                    leases.append(lease)
                time.sleep(0.01)  # Small delay to simulate processing
            return leases
        
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=load_test_config["concurrent_workers"]) as executor:
            futures = [executor.submit(compete_for_leases, worker) for worker in workers]
            results = [f.result() for f in as_completed(futures)]
        
        end_time = time.time()
        
        # Flatten results
        all_leases = [lease for worker_leases in results for lease in worker_leases]
        
        # Verify no double-processing
        lease_ids = [lease["id"] for lease in all_leases]
        assert len(lease_ids) == len(set(lease_ids))  # No duplicates
        
        # Performance check
        execution_time = end_time - start_time
        assert execution_time < 30  # Should complete within reasonable time
        
        # Clean up leases
        for lease in all_leases:
            # Find worker that has this lease
            for worker in workers:
                if worker.current_lease and worker.current_lease["id"] == lease["id"]:
                    worker.delete_work(lease["id"])
                    break
    
    @pytest.mark.integration
    def test_worker_pool_coordination(self, clean_database):
        """Test coordination between multiple workers in a pool."""
        
        # This would test WorkerCoordinator if implemented
        # For now, test basic multi-worker coordination
        
        configs = []
        for i in range(3):
            config = WorkerConfig.from_dict({
                "worker_id": f"pool-worker-{i}",
                "database_url": clean_database.url,
                "heartbeat_interval": 5
            })
            configs.append(config)
        
        workers = [WorkerRunner(config) for config in configs]
        
        # Send heartbeats from all workers
        for worker in workers:
            worker.heartbeat()
        
        # Verify all workers are registered
        with clean_database.begin() as conn:
            result = conn.execute(text("""
                SELECT COUNT(*) as worker_count FROM worker_heartbeat
                WHERE worker_id LIKE 'pool-worker-%'
            """))
            
            row = result.fetchone()
            assert row.worker_count == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])