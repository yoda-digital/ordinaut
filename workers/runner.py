# workers/runner.py
import os, sys, time, json, logging, uuid, random, signal, threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text
from engine.executor import run_pipeline
from workers.config import WorkerConfig, WorkerMetrics, setup_logging, validate_database_connection, WorkerState

# Import observability components
from observability.metrics import orchestrator_metrics, track_task_execution
from observability.logging import worker_logger, set_request_context, generate_run_id

# Global state for graceful shutdown
shutdown_requested = threading.Event()

class WorkerRunner:
    """Main worker process for executing scheduled tasks with SKIP LOCKED pattern."""
    
    def __init__(self, config: WorkerConfig):
        self.config = config
        self.logger = worker_logger  # Use structured logger
        self.legacy_logger = setup_logging(config)  # Keep legacy for compatibility
        self.metrics = WorkerMetrics()
        self.state = WorkerState.STARTING
        self.current_lease = None
        self.last_heartbeat = 0
        self.last_cleanup = 0
        
        # Database connection
        engine_kwargs = {
            "pool_pre_ping": True,
            "future": True,
        }
        
        # Add pool settings only for non-SQLite databases
        if not config.database_url.startswith("sqlite"):
            engine_kwargs.update({
                "pool_recycle": 3600,  # Recycle connections every hour
                "pool_size": 5,
                "max_overflow": 10
            })
        
        self.eng = create_engine(config.database_url, **engine_kwargs)
        
        self.logger.info(f"Worker {config.worker_id} initializing")
    
    def exponential_backoff_with_jitter(self, attempt: int) -> float:
        """Calculate exponential backoff delay with optional jitter."""
        base_delay = self.config.backoff_base_delay
        max_delay = self.config.backoff_max_delay
        
        # Calculate exponential backoff
        delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
        
        # Add jitter if enabled
        if self.config.backoff_jitter:
            jitter = delay * (0.5 + random.random() * 0.5)  # 50-100% of delay
            return jitter
        else:
            return delay
    
    def should_retry_task(self, task: dict, attempt: int) -> bool:
        """Determine if a task should be retried based on attempt count and configuration."""
        max_retries = task.get("max_retries", 3)
        return attempt <= max_retries
    
    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            self.logger.info(f"Received signal {signum}, initiating graceful shutdown")
            shutdown_requested.set()
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
    
    def lease_one(self):
        """Lease a single work item using SKIP LOCKED for safe concurrent access."""
        try:
            with self.eng.begin() as cx:
                row = cx.execute(text("""
                    SELECT id, task_id, run_at
                    FROM due_work
                    WHERE run_at <= now()
                      AND (locked_until IS NULL OR locked_until < now())
                    ORDER BY run_at
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                """)).fetchone()
                
                if not row:
                    return None
                
                locked_until = datetime.now(timezone.utc) + timedelta(seconds=self.config.lease_seconds)
                cx.execute(text("""
                    UPDATE due_work
                    SET locked_until=:lu, locked_by=:lb
                    WHERE id=:id
                """), {"lu": locked_until, "lb": self.config.worker_id, "id": row.id})
                
                lease = dict(id=row.id, task_id=row.task_id, run_at=row.run_at, locked_until=locked_until)
                self.current_lease = lease
                self.metrics.record_lease_acquired()
                
                # Log lease acquisition with structured logging
                self.logger.lease_acquired(
                    worker_id=self.config.worker_id,
                    task_id=row.task_id,
                    lease_duration_seconds=self.config.lease_seconds
                )
                
                # Record metrics
                orchestrator_metrics.record_lease_duration(
                    worker_id=self.config.worker_id,
                    duration=self.config.lease_seconds
                )
                
                return lease
                
        except Exception as e:
            self.logger.error(f"Failed to lease work: {e}", exception=str(e))
            self.metrics.record_error()
            orchestrator_metrics.record_redis_operation("lease_work", "error")
            return None
    
    def fetch_task(self, task_id):
        """Fetch task definition from database."""
        try:
            with self.eng.begin() as cx:
                row = cx.execute(text("SELECT * FROM task WHERE id=:tid"), {"tid": task_id}).mappings().first()
                return dict(row) if row else None
        except Exception as e:
            self.logger.error(f"Failed to fetch task {task_id}: {e}")
            self.metrics.record_error()
            return None
    
    def record_run(self, task_id, started_at, success, output=None, error=None, attempt=1):
        """Record task execution attempt in task_run table."""
        try:
            with self.eng.begin() as cx:
                cx.execute(text("""
                    INSERT INTO task_run (task_id, lease_owner, started_at, finished_at, success, output, error, attempt)
                    VALUES (:tid, :owner, :sa, now(), :sc, :out::jsonb, :err, :attempt)
                """), {
                    "tid": task_id,
                    "owner": self.config.worker_id,
                    "sa": started_at,
                    "sc": success,
                    "out": json.dumps(output) if output is not None else None,
                    "err": error,
                    "attempt": attempt
                })
        except Exception as e:
            self.logger.error(f"Failed to record task run for {task_id}: {e}")
            self.metrics.record_error()
    
    def delete_work(self, work_id):
        """Remove work item from due_work table after processing."""
        try:
            with self.eng.begin() as cx:
                cx.execute(text("DELETE FROM due_work WHERE id=:id"), {"id": work_id})
        except Exception as e:
            self.logger.error(f"Failed to delete work item {work_id}: {e}")
            self.metrics.record_error()
    
    def renew_lease(self, work_id, lease_seconds=None):
        """Renew lease on work item to prevent timeout during long-running tasks."""
        if lease_seconds is None:
            lease_seconds = self.config.lease_seconds
            
        locked_until = datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)
        
        try:
            with self.eng.begin() as cx:
                result = cx.execute(text("""
                    UPDATE due_work
                    SET locked_until=:lu
                    WHERE id=:id AND locked_by=:lb
                """), {"lu": locked_until, "id": work_id, "lb": self.config.worker_id})
                
                if result.rowcount > 0:
                    self.logger.debug(f"Renewed lease for work item {work_id}")
                    self.metrics.record_lease_renewed()
                    if self.current_lease and self.current_lease["id"] == work_id:
                        self.current_lease["locked_until"] = locked_until
                else:
                    self.logger.warning(f"Failed to renew lease for work item {work_id} - lease may be expired")
                    self.metrics.record_lease_expired()
                    
        except Exception as e:
            self.logger.warning(f"Failed to renew lease for work item {work_id}: {e}")
            self.metrics.record_error()
    
    def should_retry(self, task: dict, attempt: int, error: Exception) -> bool:
        """Determine if task should be retried based on error type and attempt count."""
        max_retries = int(task.get("max_retries", 3))
        if attempt >= max_retries + 1:  # +1 because attempts start at 1
            return False
        
        # Don't retry validation errors or configuration errors
        error_msg = str(error).lower()
        non_retryable_keywords = ["schema", "validation", "configuration", "permission", "authentication", "authorization"]
        
        if any(keyword in error_msg for keyword in non_retryable_keywords):
            self.logger.info(f"Task {task['id']} failed with non-retryable error: {error}")
            return False
        
        return True
    
    def process_work_item(self, lease: dict) -> bool:
        """Process a single work item with retry logic and proper error handling."""
        task = self.fetch_task(lease["task_id"])
        if not task or task["status"] != "active":
            self.logger.info(f"Skipping inactive/missing task {lease['task_id']}")
            self.delete_work(lease["id"])
            return True  # Successfully handled (by skipping)

        attempt = 0
        started = datetime.now(timezone.utc)
        last_error = None
        max_retries = int(task.get("max_retries", 3))

        self.logger.info(f"Processing task {task['id']} - {task.get('title', 'Untitled')}")
        self.state = WorkerState.PROCESSING

        while attempt < max_retries + 1:
            attempt += 1
            self.logger.debug(f"Task {task['id']} attempt {attempt}/{max_retries + 1}")
            
            try:
                # Check if shutdown was requested
                if shutdown_requested.is_set():
                    self.logger.info(f"Shutdown requested, aborting task {task['id']}")
                    return False
                
                # Renew lease before potentially long-running execution
                if attempt > 1:  # Don't renew on first attempt (just acquired lease)
                    self.renew_lease(lease["id"])
                
                # Execute pipeline with timeout protection
                task_start_time = time.time()
                ctx = run_pipeline(task)
                processing_time = time.time() - task_start_time
                
                # Record successful execution
                self.record_run(task["id"], started, True, output=ctx, attempt=attempt)
                self.metrics.record_task_completed(True, processing_time, attempt - 1)
                self.logger.info(f"Task {task['id']} completed successfully on attempt {attempt} ({processing_time:.2f}s)")
                
                # Clean up work item
                self.delete_work(lease["id"])
                self.current_lease = None
                return True
                
            except Exception as e:
                last_error = str(e)
                processing_time = time.time() - task_start_time if 'task_start_time' in locals() else 0
                self.logger.error(f"Task {task['id']} attempt {attempt} failed: {last_error}")
                
                # Record failed attempt
                self.record_run(task["id"], started, False, error=last_error, attempt=attempt)
                
                # Check if we should retry
                if not self.should_retry(task, attempt, e):
                    self.logger.error(f"Task {task['id']} will not be retried due to error type")
                    break
                
                # Don't sleep after the last attempt or if shutdown requested
                if attempt < max_retries + 1 and not shutdown_requested.is_set():
                    delay = self.exponential_backoff_with_jitter(attempt)
                    self.logger.info(f"Retrying task {task['id']} in {delay:.2f} seconds")
                    
                    # Sleep with shutdown check
                    sleep_start = time.time()
                    while time.time() - sleep_start < delay:
                        if shutdown_requested.is_set():
                            self.logger.info("Shutdown requested during retry delay")
                            break
                        time.sleep(0.1)

        # All retries exhausted
        processing_time = time.time() - started.timestamp() if 'started' in locals() else 0
        self.metrics.record_task_completed(False, processing_time, attempt - 1)
        self.delete_work(lease["id"])
        self.current_lease = None
        self.logger.error(f"Task {task['id']} failed permanently after {attempt} attempts: {last_error}")
        return False
    
    def heartbeat(self):
        """Send worker heartbeat to indicate liveness."""
        try:
            # Get current queue depth for heartbeat logging
            queue_depth = 0
            active_leases = 1 if self.current_lease else 0
            
            with self.eng.begin() as cx:
                # Get queue depth
                result = cx.execute(text("""
                    SELECT COUNT(*) as depth FROM due_work 
                    WHERE run_at <= now() AND (locked_until IS NULL OR locked_until < now())
                """)).fetchone()
                queue_depth = result.depth if result else 0
                
                # Record heartbeat
                cx.execute(text("""
                    INSERT INTO worker_heartbeat (worker_id, last_heartbeat, processed_count, pid, hostname)
                    VALUES (:worker_id, now(), :count, :pid, :hostname)
                    ON CONFLICT (worker_id) 
                    DO UPDATE SET 
                        last_heartbeat = now(),
                        processed_count = EXCLUDED.processed_count,
                        pid = EXCLUDED.pid,
                        hostname = EXCLUDED.hostname
                """), {
                    "worker_id": self.config.worker_id,
                    "count": self.metrics.tasks_processed,
                    "pid": os.getpid(),
                    "hostname": os.uname().nodename
                })
                
                self.metrics.record_heartbeat_sent()
                self.last_heartbeat = time.time()
                
                # Record metrics
                orchestrator_metrics.record_worker_heartbeat(self.config.worker_id)
                orchestrator_metrics.update_queue_depth(queue_depth)
                orchestrator_metrics.update_active_workers(
                    worker_id=self.config.worker_id,
                    state=self.state.value,
                    count=1
                )
                
                # Log heartbeat with structured logging
                self.logger.worker_heartbeat(
                    worker_id=self.config.worker_id,
                    queue_depth=queue_depth,
                    active_leases=active_leases
                )
                
        except Exception as e:
            self.logger.warning(f"Failed to send heartbeat: {e}", exception=str(e))
            self.metrics.record_error()
            orchestrator_metrics.record_redis_operation("heartbeat", "error")
    
    def cleanup_expired_leases(self):
        """Clean up expired leases from crashed/stuck workers."""
        try:
            with self.eng.begin() as cx:
                result = cx.execute(text("""
                    UPDATE due_work 
                    SET locked_until = NULL, locked_by = NULL
                    WHERE locked_until < now() - interval '60 seconds'
                      AND locked_by != :worker_id
                """), {"worker_id": self.config.worker_id})
                
                if result.rowcount > 0:
                    self.logger.info(f"Cleaned up {result.rowcount} expired leases")
                    
                self.last_cleanup = time.time()
                
        except Exception as e:
            self.logger.warning(f"Failed to cleanup expired leases: {e}")
            self.metrics.record_error()
    
    def run(self):
        """Main worker loop - lease work items and process them."""
        self.logger.info(f"Worker {self.config.worker_id} starting up (PID: {os.getpid()})")
        self.setup_signal_handlers()
        
        # Validate database connection
        if not validate_database_connection(self.config.database_url):
            self.logger.error("Database connection validation failed")
            self.state = WorkerState.ERROR
            return
        
        self.state = WorkerState.READY
        
        # Initialize timing
        self.last_heartbeat = time.time()
        self.last_cleanup = time.time()
        
        # Send initial heartbeat
        self.heartbeat()
        
        try:
            while not shutdown_requested.is_set():
                try:
                    # Send heartbeat periodically
                    now = time.time()
                    if now - self.last_heartbeat > self.config.heartbeat_interval:
                        self.heartbeat()
                    
                    # Clean up expired leases periodically
                    if now - self.last_cleanup > self.config.cleanup_interval:
                        self.cleanup_expired_leases()
                    
                    # Try to lease work
                    lease = self.lease_one()
                    if not lease:
                        time.sleep(0.5)  # No work available, short sleep
                        continue
                    
                    # Process work item
                    self.process_work_item(lease)
                    
                except Exception as e:
                    self.logger.error(f"Unexpected error in worker loop: {e}")
                    self.metrics.record_error()
                    time.sleep(5)  # Longer sleep on unexpected errors
                    
        except KeyboardInterrupt:
            self.logger.info("Keyboard interrupt received")
        finally:
            self.shutdown()
    
    def shutdown(self):
        """Graceful shutdown of worker process."""
        self.logger.info(f"Worker {self.config.worker_id} shutting down gracefully")
        self.state = WorkerState.STOPPING
        
        # Release current lease if any
        if self.current_lease:
            try:
                with self.eng.begin() as cx:
                    cx.execute(text("""
                        UPDATE due_work 
                        SET locked_until = NULL, locked_by = NULL
                        WHERE id = :id AND locked_by = :worker_id
                    """), {"id": self.current_lease["id"], "worker_id": self.config.worker_id})
                    
                self.logger.info(f"Released lease for work item {self.current_lease['id']}")
            except Exception as e:
                self.logger.error(f"Failed to release lease during shutdown: {e}")
        
        # Final metrics report
        metrics_summary = self.metrics.get_summary()
        self.logger.info(f"Worker final metrics: {json.dumps(metrics_summary, indent=2)}")
        
        self.state = WorkerState.STOPPED
        self.logger.info(f"Worker {self.config.worker_id} shutdown complete")

def main():
    """Main entry point for worker process."""
    worker_id = f"worker-{uuid.uuid4()}"
    
    try:
        config = WorkerConfig.from_environment(worker_id)
        worker = WorkerRunner(config)
        worker.run()
    except KeyboardInterrupt:
        pass  # Handled in worker.run()
    except Exception as e:
        logging.error(f"Fatal worker error: {e}")
        raise

if __name__ == "__main__":
    main()