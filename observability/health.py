"""
Comprehensive health check system for Personal Agent Orchestrator.

Provides database, Redis, worker, and scheduler health monitoring
with detailed status reporting and integration points.
"""

import asyncio
import time
from datetime import datetime, timezone, timedelta
from enum import Enum
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Any
import psycopg
import redis.asyncio as redis
from sqlalchemy import create_engine, text
import os

from .logging import StructuredLogger, set_request_context


class HealthStatus(Enum):
    """Health status enumeration."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthCheck:
    """Individual health check result."""
    name: str
    status: HealthStatus
    message: str
    duration_ms: float
    details: Optional[Dict[str, Any]] = None
    timestamp: Optional[datetime] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)


@dataclass
class SystemHealthReport:
    """Complete system health report."""
    status: HealthStatus
    timestamp: datetime
    checks: List[HealthCheck]
    summary: Dict[str, Any]
    uptime_seconds: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'status': self.status.value,
            'timestamp': self.timestamp.isoformat() + 'Z',
            'checks': [
                {
                    'name': check.name,
                    'status': check.status.value,
                    'message': check.message,
                    'duration_ms': check.duration_ms,
                    'details': check.details or {},
                    'timestamp': check.timestamp.isoformat() + 'Z' if check.timestamp else None
                }
                for check in self.checks
            ],
            'summary': self.summary,
            'uptime_seconds': self.uptime_seconds
        }


class SystemHealthMonitor:
    """Comprehensive system health monitoring."""
    
    def __init__(self, database_url: str = None, redis_url: str = None):
        self.database_url = database_url or os.getenv("DATABASE_URL")
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.logger = StructuredLogger("orchestrator.health")
        self.start_time = time.time()
        
        # Database connection for health checks
        if self.database_url:
            self.db_engine = create_engine(
                self.database_url,
                pool_pre_ping=True,
                future=True,
                pool_size=2,  # Small pool for health checks
                max_overflow=0
            )
        else:
            self.db_engine = None
            
    async def check_database_health(self) -> HealthCheck:
        """Check PostgreSQL database health and performance."""
        start_time = time.time()
        
        if not self.db_engine:
            return HealthCheck(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message="Database connection not configured",
                duration_ms=0,
                details={"error": "DATABASE_URL not set"}
            )
        
        try:
            with self.db_engine.begin() as conn:
                # Basic connectivity check
                result = conn.execute(text("SELECT 1 as health_check"))
                row = result.fetchone()
                
                if not row or row.health_check != 1:
                    raise Exception("Health check query returned unexpected result")
                
                # Check critical tables exist
                table_checks = conn.execute(text("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                      AND table_name IN ('task', 'due_work', 'task_run', 'agent')
                """)).fetchall()
                
                expected_tables = {'task', 'due_work', 'task_run', 'agent'}
                found_tables = {row.table_name for row in table_checks}
                missing_tables = expected_tables - found_tables
                
                if missing_tables:
                    return HealthCheck(
                        name="database",
                        status=HealthStatus.UNHEALTHY,
                        message=f"Missing required tables: {missing_tables}",
                        duration_ms=(time.time() - start_time) * 1000,
                        details={"missing_tables": list(missing_tables)}
                    )
                
                # Check queue depth and performance
                queue_stats = conn.execute(text("""
                    SELECT 
                        COUNT(*) as total_due_work,
                        COUNT(*) FILTER (WHERE run_at <= now()) as overdue_work,
                        COUNT(*) FILTER (WHERE locked_until > now()) as locked_work,
                        EXTRACT(EPOCH FROM (now() - MIN(run_at))) as oldest_overdue_seconds
                    FROM due_work
                """)).fetchone()
                
                # Check database performance
                perf_stats = conn.execute(text("""
                    SELECT 
                        numbackends,
                        xact_commit + xact_rollback as total_transactions,
                        tup_returned,
                        tup_fetched,
                        tup_inserted,
                        tup_updated,
                        tup_deleted
                    FROM pg_stat_database 
                    WHERE datname = current_database()
                """)).fetchone()
                
                duration_ms = (time.time() - start_time) * 1000
                
                # Determine health status based on queue and performance
                status = HealthStatus.HEALTHY
                message = "Database connection successful"
                
                if queue_stats.overdue_work > 100:
                    status = HealthStatus.DEGRADED
                    message = f"High overdue work count: {queue_stats.overdue_work}"
                elif queue_stats.oldest_overdue_seconds and queue_stats.oldest_overdue_seconds > 300:
                    status = HealthStatus.DEGRADED
                    message = f"Oldest overdue work: {queue_stats.oldest_overdue_seconds:.1f}s"
                elif duration_ms > 1000:  # Database response > 1 second
                    status = HealthStatus.DEGRADED
                    message = f"Slow database response: {duration_ms:.1f}ms"
                
                return HealthCheck(
                    name="database",
                    status=status,
                    message=message,
                    duration_ms=duration_ms,
                    details={
                        "total_due_work": queue_stats.total_due_work,
                        "overdue_work": queue_stats.overdue_work,
                        "locked_work": queue_stats.locked_work,
                        "oldest_overdue_seconds": queue_stats.oldest_overdue_seconds,
                        "active_connections": perf_stats.numbackends,
                        "total_transactions": perf_stats.total_transactions
                    }
                )
                
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthCheck(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message=f"Database health check failed: {e}",
                duration_ms=duration_ms,
                details={"exception": str(e)}
            )
    
    async def check_redis_health(self) -> HealthCheck:
        """Check Redis health and stream functionality."""
        start_time = time.time()
        
        try:
            redis_client = redis.from_url(self.redis_url)
            
            # Basic connectivity check
            ping_result = await redis_client.ping()
            if not ping_result:
                raise Exception("Redis ping failed")
            
            # Test stream operations (used for events)
            test_stream = "health_check_stream"
            test_data = {"timestamp": datetime.now(timezone.utc).isoformat()}
            
            # Add test entry to stream
            stream_id = await redis_client.xadd(test_stream, test_data)
            
            # Read back the entry
            stream_data = await redis_client.xread({test_stream: "0-0"}, count=1)
            
            # Cleanup test stream
            await redis_client.delete(test_stream)
            
            # Check Redis info for performance metrics
            info = await redis_client.info()
            memory_usage_mb = info.get('used_memory', 0) / (1024 * 1024)
            connected_clients = info.get('connected_clients', 0)
            
            await redis_client.close()
            
            duration_ms = (time.time() - start_time) * 1000
            
            # Determine health status
            status = HealthStatus.HEALTHY
            message = "Redis connection successful"
            
            if memory_usage_mb > 1024:  # > 1GB memory usage
                status = HealthStatus.DEGRADED
                message = f"High Redis memory usage: {memory_usage_mb:.1f}MB"
            elif connected_clients > 100:
                status = HealthStatus.DEGRADED
                message = f"High client connection count: {connected_clients}"
            elif duration_ms > 500:  # Redis response > 500ms
                status = HealthStatus.DEGRADED
                message = f"Slow Redis response: {duration_ms:.1f}ms"
            
            return HealthCheck(
                name="redis",
                status=status,
                message=message,
                duration_ms=duration_ms,
                details={
                    "memory_usage_mb": round(memory_usage_mb, 2),
                    "connected_clients": connected_clients,
                    "stream_test_passed": bool(stream_id and stream_data),
                    "redis_version": info.get('redis_version', 'unknown')
                }
            )
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthCheck(
                name="redis",
                status=HealthStatus.UNHEALTHY,
                message=f"Redis health check failed: {e}",
                duration_ms=duration_ms,
                details={"exception": str(e)}
            )
    
    async def check_worker_health(self) -> HealthCheck:
        """Check worker system health and heartbeats."""
        start_time = time.time()
        
        if not self.db_engine:
            return HealthCheck(
                name="workers",
                status=HealthStatus.UNHEALTHY,
                message="Cannot check workers - database not configured",
                duration_ms=0
            )
        
        try:
            with self.db_engine.begin() as conn:
                # Check for recent worker heartbeats
                worker_stats = conn.execute(text("""
                    SELECT 
                        COUNT(DISTINCT worker_id) as total_workers,
                        COUNT(DISTINCT worker_id) FILTER (
                            WHERE last_seen > now() - interval '30 seconds'
                        ) as active_workers,
                        COUNT(DISTINCT worker_id) FILTER (
                            WHERE last_seen > now() - interval '2 minutes'
                        ) as recent_workers,
                        MAX(last_seen) as latest_heartbeat,
                        EXTRACT(EPOCH FROM (now() - MIN(last_seen))) as oldest_heartbeat_age
                    FROM worker_heartbeat
                    WHERE last_seen > now() - interval '10 minutes'
                """)).fetchone()
                
                # Check active work leases
                lease_stats = conn.execute(text("""
                    SELECT 
                        COUNT(*) as active_leases,
                        COUNT(DISTINCT locked_by) as workers_with_leases,
                        AVG(EXTRACT(EPOCH FROM (locked_until - now()))) as avg_lease_remaining_seconds
                    FROM due_work
                    WHERE locked_until > now()
                      AND locked_by IS NOT NULL
                """)).fetchone()
                
                duration_ms = (time.time() - start_time) * 1000
                
                # Determine worker health status
                status = HealthStatus.HEALTHY
                message = f"{worker_stats.active_workers} active workers"
                
                if worker_stats.active_workers == 0:
                    status = HealthStatus.UNHEALTHY
                    message = "No active workers detected"
                elif worker_stats.active_workers < worker_stats.recent_workers // 2:
                    status = HealthStatus.DEGRADED  
                    message = f"Only {worker_stats.active_workers} of {worker_stats.recent_workers} workers active"
                elif worker_stats.oldest_heartbeat_age and worker_stats.oldest_heartbeat_age > 120:
                    status = HealthStatus.DEGRADED
                    message = f"Stale worker detected (oldest: {worker_stats.oldest_heartbeat_age:.1f}s)"
                
                return HealthCheck(
                    name="workers",
                    status=status,
                    message=message,
                    duration_ms=duration_ms,
                    details={
                        "total_workers": worker_stats.total_workers,
                        "active_workers": worker_stats.active_workers,
                        "recent_workers": worker_stats.recent_workers,
                        "latest_heartbeat": worker_stats.latest_heartbeat.isoformat() + 'Z' if worker_stats.latest_heartbeat else None,
                        "oldest_heartbeat_age_seconds": worker_stats.oldest_heartbeat_age,
                        "active_leases": lease_stats.active_leases,
                        "workers_with_leases": lease_stats.workers_with_leases,
                        "avg_lease_remaining_seconds": lease_stats.avg_lease_remaining_seconds
                    }
                )
                
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthCheck(
                name="workers",
                status=HealthStatus.UNHEALTHY,
                message=f"Worker health check failed: {e}",
                duration_ms=duration_ms,
                details={"exception": str(e)}
            )
    
    async def check_scheduler_health(self) -> HealthCheck:
        """Check scheduler responsiveness and performance."""
        start_time = time.time()
        
        if not self.db_engine:
            return HealthCheck(
                name="scheduler",
                status=HealthStatus.UNHEALTHY,
                message="Cannot check scheduler - database not configured",
                duration_ms=0
            )
        
        try:
            with self.db_engine.begin() as conn:
                # Check scheduler lag (oldest overdue work)
                lag_stats = conn.execute(text("""
                    SELECT 
                        COUNT(*) FILTER (WHERE run_at <= now()) as overdue_count,
                        EXTRACT(EPOCH FROM (now() - MIN(run_at))) as max_lag_seconds,
                        AVG(EXTRACT(EPOCH FROM (now() - run_at))) FILTER (
                            WHERE run_at <= now()
                        ) as avg_lag_seconds
                    FROM due_work
                    WHERE run_at <= now() + interval '5 minutes'
                """)).fetchone()
                
                # Check recent scheduler activity
                scheduler_stats = conn.execute(text("""
                    SELECT 
                        COUNT(*) as recent_due_work,
                        COUNT(DISTINCT task_id) as unique_tasks_scheduled
                    FROM due_work
                    WHERE created_at > now() - interval '5 minutes'
                """)).fetchone()
                
                duration_ms = (time.time() - start_time) * 1000
                
                # Determine scheduler health
                status = HealthStatus.HEALTHY
                message = "Scheduler operating normally"
                
                if lag_stats.max_lag_seconds and lag_stats.max_lag_seconds > 60:
                    status = HealthStatus.UNHEALTHY
                    message = f"High scheduler lag: {lag_stats.max_lag_seconds:.1f}s"
                elif lag_stats.max_lag_seconds and lag_stats.max_lag_seconds > 30:
                    status = HealthStatus.DEGRADED
                    message = f"Moderate scheduler lag: {lag_stats.max_lag_seconds:.1f}s"
                elif lag_stats.overdue_count > 50:
                    status = HealthStatus.DEGRADED
                    message = f"High overdue work count: {lag_stats.overdue_count}"
                
                return HealthCheck(
                    name="scheduler",
                    status=status,
                    message=message,
                    duration_ms=duration_ms,
                    details={
                        "overdue_count": lag_stats.overdue_count,
                        "max_lag_seconds": lag_stats.max_lag_seconds,
                        "avg_lag_seconds": lag_stats.avg_lag_seconds,
                        "recent_due_work": scheduler_stats.recent_due_work,
                        "unique_tasks_scheduled": scheduler_stats.unique_tasks_scheduled
                    }
                )
                
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthCheck(
                name="scheduler",
                status=HealthStatus.UNHEALTHY,
                message=f"Scheduler health check failed: {e}",
                duration_ms=duration_ms,
                details={"exception": str(e)}
            )
    
    async def get_system_health(self, request_id: str = None) -> SystemHealthReport:
        """Get comprehensive system health status."""
        if request_id:
            set_request_context(request_id=request_id)
        
        self.logger.info("Starting comprehensive system health check")
        
        # Run all health checks concurrently
        checks = await asyncio.gather(
            self.check_database_health(),
            self.check_redis_health(),
            self.check_worker_health(),
            self.check_scheduler_health(),
            return_exceptions=True
        )
        
        # Handle any exceptions in health checks
        valid_checks = []
        for i, check in enumerate(checks):
            if isinstance(check, Exception):
                check_name = ["database", "redis", "workers", "scheduler"][i]
                valid_checks.append(HealthCheck(
                    name=check_name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Health check failed with exception: {check}",
                    duration_ms=0,
                    details={"exception": str(check)}
                ))
            else:
                valid_checks.append(check)
        
        # Determine overall system status
        statuses = [check.status for check in valid_checks]
        
        if all(status == HealthStatus.HEALTHY for status in statuses):
            overall_status = HealthStatus.HEALTHY
        elif any(status == HealthStatus.UNHEALTHY for status in statuses):
            overall_status = HealthStatus.UNHEALTHY
        else:
            overall_status = HealthStatus.DEGRADED
        
        # Create summary
        summary = {
            "total_checks": len(valid_checks),
            "healthy_checks": len([c for c in valid_checks if c.status == HealthStatus.HEALTHY]),
            "degraded_checks": len([c for c in valid_checks if c.status == HealthStatus.DEGRADED]),
            "unhealthy_checks": len([c for c in valid_checks if c.status == HealthStatus.UNHEALTHY]),
            "total_duration_ms": sum(check.duration_ms for check in valid_checks),
            "slowest_check": max(valid_checks, key=lambda c: c.duration_ms).name if valid_checks else None
        }
        
        report = SystemHealthReport(
            status=overall_status,
            timestamp=datetime.now(timezone.utc),
            checks=valid_checks,
            summary=summary,
            uptime_seconds=time.time() - self.start_time
        )
        
        # Log health status
        self.logger.info(
            f"System health check completed: {overall_status.value}",
            overall_status=overall_status.value,
            total_checks=len(valid_checks),
            healthy_checks=summary["healthy_checks"],
            total_duration_ms=summary["total_duration_ms"],
            event_type="health_check_completed"
        )
        
        return report
    
    async def get_quick_health(self) -> Dict[str, Any]:
        """Get quick health status for readiness/liveness probes."""
        start_time = time.time()
        
        try:
            # Quick database check only
            db_check = await self.check_database_health()
            duration_ms = (time.time() - start_time) * 1000
            
            return {
                "status": db_check.status.value,
                "timestamp": datetime.now(timezone.utc).isoformat() + 'Z',
                "database": db_check.status == HealthStatus.HEALTHY,
                "duration_ms": duration_ms,
                "uptime_seconds": time.time() - self.start_time
            }
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return {
                "status": HealthStatus.UNHEALTHY.value,
                "timestamp": datetime.now(timezone.utc).isoformat() + 'Z',
                "database": False,
                "duration_ms": duration_ms,
                "error": str(e),
                "uptime_seconds": time.time() - self.start_time
            }