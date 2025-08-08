# workers/config.py
"""
Configuration and utilities for the worker system.
Provides centralized configuration management and utility functions.
"""

import os
import logging
from dataclasses import dataclass
from typing import Optional

@dataclass
class WorkerConfig:
    """Configuration for worker processes."""
    
    # Database connection
    database_url: str
    
    # Worker identification
    worker_id: str
    lease_seconds: int = 60
    
    # Processing behavior
    max_concurrent_leases: int = 1
    backoff_base_delay: float = 1.0
    backoff_max_delay: float = 60.0
    backoff_jitter: bool = True
    
    # Health monitoring
    heartbeat_interval: int = 30  # seconds
    lease_renewal_interval: int = 30  # seconds
    cleanup_interval: int = 300  # seconds (5 minutes)
    
    # Operational limits
    max_processing_time: int = 3600  # seconds (1 hour)
    graceful_shutdown_timeout: int = 30  # seconds
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    @classmethod
    def from_environment(cls, worker_id: str) -> "WorkerConfig":
        """Create configuration from environment variables."""
        return cls(
            database_url=os.environ["DATABASE_URL"],
            worker_id=worker_id,
            lease_seconds=int(os.environ.get("WORKER_LEASE_SECONDS", "60")),
            max_concurrent_leases=int(os.environ.get("WORKER_MAX_LEASES", "1")),
            backoff_base_delay=float(os.environ.get("WORKER_BACKOFF_BASE", "1.0")),
            backoff_max_delay=float(os.environ.get("WORKER_BACKOFF_MAX", "60.0")),
            heartbeat_interval=int(os.environ.get("WORKER_HEARTBEAT_INTERVAL", "30")),
            lease_renewal_interval=int(os.environ.get("WORKER_LEASE_RENEWAL_INTERVAL", "30")),
            cleanup_interval=int(os.environ.get("WORKER_CLEANUP_INTERVAL", "300")),
            max_processing_time=int(os.environ.get("WORKER_MAX_PROCESSING_TIME", "3600")),
            graceful_shutdown_timeout=int(os.environ.get("WORKER_SHUTDOWN_TIMEOUT", "30")),
            log_level=os.environ.get("WORKER_LOG_LEVEL", "INFO"),
        )
    
    @classmethod
    def from_dict(cls, config_dict: dict) -> "WorkerConfig":
        """Create configuration from dictionary."""
        # Extract and convert values with defaults
        return cls(
            database_url=config_dict["database_url"],
            worker_id=config_dict["worker_id"],
            lease_seconds=config_dict.get("lease_seconds", 60),
            max_concurrent_leases=config_dict.get("max_concurrent_leases", 1),
            backoff_base_delay=config_dict.get("backoff_base_delay", 1.0),
            backoff_max_delay=config_dict.get("backoff_max_delay", 60.0),
            backoff_jitter=config_dict.get("backoff_jitter", True),
            heartbeat_interval=config_dict.get("heartbeat_interval", 30),
            lease_renewal_interval=config_dict.get("lease_renewal_interval", 30),
            cleanup_interval=config_dict.get("cleanup_interval", 300),
            max_processing_time=config_dict.get("max_processing_time", 3600),
            graceful_shutdown_timeout=config_dict.get("graceful_shutdown_timeout", 30),
            log_level=config_dict.get("log_level", "INFO"),
            log_format=config_dict.get("log_format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )

class WorkerMetrics:
    """Simple metrics collection for worker monitoring."""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        """Reset all metrics."""
        self.tasks_processed = 0
        self.tasks_succeeded = 0
        self.tasks_failed = 0
        self.tasks_retried = 0
        self.total_processing_time = 0.0
        self.leases_acquired = 0
        self.leases_renewed = 0
        self.leases_expired = 0
        self.heartbeats_sent = 0
        self.errors_encountered = 0
    
    def record_task_completed(self, success: bool, processing_time: float, retries: int = 0):
        """Record completion of a task."""
        self.tasks_processed += 1
        if success:
            self.tasks_succeeded += 1
        else:
            self.tasks_failed += 1
        self.tasks_retried += retries
        self.total_processing_time += processing_time
    
    def record_lease_acquired(self):
        """Record acquisition of a work lease."""
        self.leases_acquired += 1
    
    def record_lease_renewed(self):
        """Record renewal of a work lease."""
        self.leases_renewed += 1
    
    def record_lease_expired(self):
        """Record expiration of a work lease."""
        self.leases_expired += 1
    
    def record_heartbeat_sent(self):
        """Record sending of worker heartbeat."""
        self.heartbeats_sent += 1
    
    def record_error(self):
        """Record an error encountered during processing."""
        self.errors_encountered += 1
    
    def get_summary(self) -> dict:
        """Get summary of all metrics."""
        success_rate = (self.tasks_succeeded / max(self.tasks_processed, 1)) * 100
        avg_processing_time = self.total_processing_time / max(self.tasks_processed, 1)
        
        return {
            "tasks": {
                "processed": self.tasks_processed,
                "succeeded": self.tasks_succeeded,
                "failed": self.tasks_failed,
                "retried": self.tasks_retried,
                "success_rate_percent": round(success_rate, 2),
                "avg_processing_time_seconds": round(avg_processing_time, 3)
            },
            "leases": {
                "acquired": self.leases_acquired,
                "renewed": self.leases_renewed,
                "expired": self.leases_expired
            },
            "operations": {
                "heartbeats_sent": self.heartbeats_sent,
                "errors_encountered": self.errors_encountered
            }
        }

def setup_logging(config: WorkerConfig) -> logging.Logger:
    """Setup logging for worker process."""
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper()),
        format=config.log_format,
        handlers=[
            logging.StreamHandler(),
        ]
    )
    
    # Add worker ID to all log messages
    logger = logging.getLogger(f"worker.{config.worker_id[:8]}")
    
    return logger

def validate_database_connection(database_url: str) -> bool:
    """Validate that database connection is working."""
    try:
        from sqlalchemy import create_engine, text
        eng = create_engine(database_url, pool_pre_ping=True, future=True)
        with eng.begin() as cx:
            cx.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logging.error(f"Database connection failed: {e}")
        return False

def get_database_info(database_url: str) -> dict:
    """Get database connection and schema information."""
    from sqlalchemy import create_engine, text
    
    eng = create_engine(database_url, pool_pre_ping=True, future=True)
    
    with eng.begin() as cx:
        # Check required tables exist
        tables_result = cx.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
              AND table_name IN ('task', 'task_run', 'due_work', 'worker_heartbeat')
            ORDER BY table_name
        """)).fetchall()
        
        # Check queue statistics
        queue_result = cx.execute(text("""
            SELECT 
                COUNT(*) as total_due_work,
                COUNT(*) FILTER (WHERE run_at <= now()) as ready_now,
                COUNT(*) FILTER (WHERE locked_until IS NOT NULL) as leased_count
            FROM due_work
        """)).mappings().first()
        
        # Check active tasks
        task_result = cx.execute(text("""
            SELECT status, COUNT(*) as count
            FROM task
            GROUP BY status
            ORDER BY status
        """)).mappings().fetchall()
        
        return {
            "tables_found": [row[0] for row in tables_result],
            "queue_stats": dict(queue_result) if queue_result else {},
            "task_counts": [dict(row) for row in task_result]
        }

class WorkerError(Exception):
    """Base exception for worker-related errors."""
    pass

class LeaseExpiredError(WorkerError):
    """Raised when a worker's lease on a work item has expired."""
    pass

class TaskValidationError(WorkerError):
    """Raised when a task fails validation."""
    pass

class ToolExecutionError(WorkerError):
    """Raised when tool execution fails."""
    pass

# Worker state enumeration
class WorkerState:
    STARTING = "starting"
    READY = "ready"
    PROCESSING = "processing"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"