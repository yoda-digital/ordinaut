"""
System health monitoring for Ordinaut.

Provides comprehensive health checks for all system components including
database, Redis, workers, scheduler, and external dependencies.
"""

import time
import asyncio
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Dict, List, Optional, Any, Union
import logging

from sqlalchemy import text

from observability.logging import StructuredLogger, set_request_context
from observability.metrics import orchestrator_metrics

# Import database and Redis dependencies
try:
    from api.dependencies import get_database, get_redis_connection
except ImportError:
    # Fallback for when running outside API context
    get_database = None
    get_redis_connection = None


class HealthStatus(Enum):
    """Health status levels."""
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
    timestamp: str
    details: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        result['status'] = self.status.value
        return result


@dataclass
class SystemHealthReport:
    """Complete system health report."""
    status: HealthStatus
    timestamp: str
    checks: List[HealthCheck]
    summary: Dict[str, Any]
    request_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'status': self.status.value,
            'timestamp': self.timestamp,
            'request_id': self.request_id,
            'summary': self.summary,
            'checks': [check.to_dict() for check in self.checks]
        }


class SystemHealthMonitor:
    """Comprehensive system health monitoring."""
    
    def __init__(self):
        self.logger = StructuredLogger("orchestrator.health")
        self.start_time = time.time()
        self._last_check_cache = {}
        self._cache_ttl = 30  # Cache results for 30 seconds
    
    async def check_database_health(self) -> HealthCheck:
        """Check PostgreSQL database health."""
        start_time = time.time()
        timestamp = datetime.utcnow().isoformat() + 'Z'
        
        try:
            if get_database is None:
                return HealthCheck(
                    name="database",
                    status=HealthStatus.DEGRADED,
                    message="Database health check not available (running outside API context)",
                    duration_ms=0,
                    timestamp=timestamp
                )
            
            # Test basic connectivity
            async with get_database() as conn:
                # Simple connectivity test
                result = await conn.execute(text("SELECT 1 as health_check"))
                row = result.fetchone()
                
                if row and row[0] == 1:
                    # Test orchestrator-specific functionality
                    result = await conn.execute(text("SELECT COUNT(*) as task_count FROM task"))
                    task_row = result.fetchone()
                    
                    duration = (time.time() - start_time) * 1000
                    
                    return HealthCheck(
                        name="database",
                        status=HealthStatus.HEALTHY,
                        message="Database connection successful",
                        duration_ms=duration,
                        timestamp=timestamp,
                        details={
                            "connection_test": "passed",
                            "schema_test": "passed",
                            "task_table_accessible": True
                        }
                    )
                else:
                    raise Exception("Health check query returned unexpected result")
                    
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            
            return HealthCheck(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message="Database health check failed",
                duration_ms=duration,
                timestamp=timestamp,
                error=str(e),
                details={"connection_test": "failed"}
            )
    
    async def check_redis_health(self) -> HealthCheck:
        """Check Redis health."""
        start_time = time.time()
        timestamp = datetime.utcnow().isoformat() + 'Z'
        
        try:
            if get_redis_connection is None:
                return HealthCheck(
                    name="redis",
                    status=HealthStatus.DEGRADED,
                    message="Redis health check not available (running outside API context)",
                    duration_ms=0,
                    timestamp=timestamp
                )
            
            redis = await get_redis_connection()
            
            # Test basic connectivity
            ping_result = await redis.ping()
            
            if ping_result:
                # Test stream operations (orchestrator-specific)
                test_stream = "health-check-stream"
                await redis.xadd(test_stream, {"test": "health"})
                
                # Clean up test data
                await redis.delete(test_stream)
                
                duration = (time.time() - start_time) * 1000
                
                return HealthCheck(
                    name="redis",
                    status=HealthStatus.HEALTHY,
                    message="Redis connection and stream operations successful",
                    duration_ms=duration,
                    timestamp=timestamp,
                    details={
                        "ping_test": "passed",
                        "stream_test": "passed"
                    }
                )
            else:
                raise Exception("Redis ping failed")
                
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self.logger.error(f"Redis health check failed: {e}")
            
            return HealthCheck(
                name="redis",
                status=HealthStatus.UNHEALTHY,
                message="Redis health check failed",
                duration_ms=duration,
                timestamp=timestamp,
                error=str(e),
                details={"ping_test": "failed"}
            )
    
    async def check_worker_health(self) -> HealthCheck:
        """Check worker system health."""
        start_time = time.time()
        timestamp = datetime.utcnow().isoformat() + 'Z'
        
        try:
            if get_database is None:
                return HealthCheck(
                    name="workers",
                    status=HealthStatus.DEGRADED,
                    message="Worker health check not available (no database access)",
                    duration_ms=0,
                    timestamp=timestamp
                )
            
            async with get_database() as conn:
                # Check for recent worker heartbeats
                result = await conn.execute(text("""
                    SELECT 
                        COUNT(*) as active_workers,
                        MAX(extract(epoch from (now() - last_seen))) as max_heartbeat_age
                    FROM worker_heartbeat 
                    WHERE last_seen > now() - interval '2 minutes'
                """))
                row = result.fetchone()
                
                active_workers = row[0] if row else 0
                max_heartbeat_age = row[1] if row and row[1] is not None else 999
                
                # Check queue depth
                result = await conn.execute(text("""
                    SELECT COUNT(*) as queue_depth 
                    FROM due_work 
                    WHERE run_at <= now() 
                      AND (locked_until IS NULL OR locked_until < now())
                """))
                queue_row = result.fetchone()
                queue_depth = queue_row[0] if queue_row else 0
                
                duration = (time.time() - start_time) * 1000
                
                # Determine status based on worker activity
                if active_workers == 0:
                    status = HealthStatus.UNHEALTHY
                    message = "No active workers detected"
                elif active_workers < 2:
                    status = HealthStatus.DEGRADED
                    message = f"Low worker count: {active_workers} active"
                else:
                    status = HealthStatus.HEALTHY
                    message = f"{active_workers} active workers"
                
                return HealthCheck(
                    name="workers",
                    status=status,
                    message=message,
                    duration_ms=duration,
                    timestamp=timestamp,
                    details={
                        "active_workers": active_workers,
                        "max_heartbeat_age_seconds": max_heartbeat_age,
                        "queue_depth": queue_depth,
                        "heartbeat_test": "passed"
                    }
                )
                    
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            
            return HealthCheck(
                name="workers",
                status=HealthStatus.UNHEALTHY,
                message="Worker health check failed",
                duration_ms=duration,
                timestamp=timestamp,
                error=str(e),
                details={"heartbeat_test": "failed"}
            )
    
    async def check_scheduler_health(self) -> HealthCheck:
        """Check scheduler health."""
        start_time = time.time()
        timestamp = datetime.utcnow().isoformat() + 'Z'
        
        try:
            if get_database is None:
                return HealthCheck(
                    name="scheduler",
                    status=HealthStatus.DEGRADED,
                    message="Scheduler health check not available (no database access)",
                    duration_ms=0,
                    timestamp=timestamp
                )
            
            async with get_database() as conn:
                # Check for recent scheduler activity
                result = await conn.execute(text("""
                    SELECT 
                        COUNT(*) as recent_runs,
                        MAX(extract(epoch from (now() - created_at))) as max_run_age
                    FROM task_run 
                    WHERE created_at > now() - interval '5 minutes'
                """))
                row = result.fetchone()
                
                recent_runs = row[0] if row else 0
                max_run_age = row[1] if row and row[1] is not None else 999
                
                # Check for overdue tasks (scheduler lag)
                result = await conn.execute(text("""
                    SELECT 
                        COUNT(*) as overdue_tasks,
                        COALESCE(MAX(extract(epoch from (now() - run_at))), 0) as max_lag_seconds
                    FROM due_work 
                    WHERE run_at <= now() - interval '1 minute'
                      AND (locked_until IS NULL OR locked_until < now())
                """))
                lag_row = result.fetchone()
                overdue_tasks = lag_row[0] if lag_row else 0
                max_lag_seconds = lag_row[1] if lag_row and lag_row[1] is not None else 0
                
                duration = (time.time() - start_time) * 1000
                
                # Determine scheduler status
                if max_lag_seconds > 300:  # 5+ minutes lag
                    status = HealthStatus.UNHEALTHY
                    message = f"Critical scheduler lag: {max_lag_seconds:.0f}s"
                elif max_lag_seconds > 60 or overdue_tasks > 50:  # 1+ minute lag or many overdue
                    status = HealthStatus.DEGRADED
                    message = f"Scheduler lag detected: {max_lag_seconds:.0f}s, {overdue_tasks} overdue"
                else:
                    status = HealthStatus.HEALTHY
                    message = "Scheduler operating normally"
                
                # Update metrics
                try:
                    orchestrator_metrics.update_scheduler_lag(max_lag_seconds)
                except Exception as metrics_error:
                    self.logger.warning(f"Failed to update scheduler lag metric: {metrics_error}")
                
                return HealthCheck(
                    name="scheduler",
                    status=status,
                    message=message,
                    duration_ms=duration,
                    timestamp=timestamp,
                    details={
                        "recent_runs": recent_runs,
                        "overdue_tasks": overdue_tasks,
                        "max_lag_seconds": max_lag_seconds,
                        "lag_test": "passed"
                    }
                )
                    
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            
            return HealthCheck(
                name="scheduler",
                status=HealthStatus.UNHEALTHY,
                message="Scheduler health check failed",
                duration_ms=duration,
                timestamp=timestamp,
                error=str(e),
                details={"lag_test": "failed"}
            )
    
    async def check_api_health(self) -> HealthCheck:
        """Check API server health (internal)."""
        start_time = time.time()
        timestamp = datetime.utcnow().isoformat() + 'Z'
        
        try:
            # This is a simple internal health check since we're already in the API
            duration = (time.time() - start_time) * 1000
            uptime = time.time() - self.start_time
            
            return HealthCheck(
                name="api",
                status=HealthStatus.HEALTHY,
                message="API server is responding",
                duration_ms=duration,
                timestamp=timestamp,
                details={
                    "uptime_seconds": uptime,
                    "response_test": "passed"
                }
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            
            return HealthCheck(
                name="api",
                status=HealthStatus.UNHEALTHY,
                message="API health check failed",
                duration_ms=duration,
                timestamp=timestamp,
                error=str(e),
                details={"response_test": "failed"}
            )
    
    async def get_system_health(self, request_id: Optional[str] = None) -> SystemHealthReport:
        """Get comprehensive system health status."""
        if request_id:
            set_request_context(request_id=request_id)
        
        start_time = time.time()
        timestamp = datetime.utcnow().isoformat() + 'Z'
        
        # Run all health checks concurrently
        self.logger.info("Starting comprehensive system health check")
        
        checks = await asyncio.gather(
            self.check_api_health(),
            self.check_database_health(),
            self.check_redis_health(),
            self.check_worker_health(),
            self.check_scheduler_health(),
            return_exceptions=True
        )
        
        # Handle any exceptions in health checks
        valid_checks = []
        for check in checks:
            if isinstance(check, Exception):
                self.logger.error(f"Health check failed with exception: {check}")
                valid_checks.append(HealthCheck(
                    name="unknown",
                    status=HealthStatus.UNHEALTHY,
                    message="Health check failed with exception",
                    duration_ms=0,
                    timestamp=timestamp,
                    error=str(check)
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
        total_duration = (time.time() - start_time) * 1000
        summary = {
            "overall_status": overall_status.value,
            "total_checks": len(valid_checks),
            "healthy_checks": len([c for c in valid_checks if c.status == HealthStatus.HEALTHY]),
            "degraded_checks": len([c for c in valid_checks if c.status == HealthStatus.DEGRADED]),
            "unhealthy_checks": len([c for c in valid_checks if c.status == HealthStatus.UNHEALTHY]),
            "total_duration_ms": total_duration,
            "uptime_seconds": time.time() - self.start_time
        }
        
        # Create health report
        report = SystemHealthReport(
            status=overall_status,
            timestamp=timestamp,
            request_id=request_id,
            checks=valid_checks,
            summary=summary
        )
        
        # Log health status
        self.logger.info(
            f"System health check completed: {overall_status.value}",
            overall_status=overall_status.value,
            total_checks=len(valid_checks),
            healthy_checks=summary["healthy_checks"],
            duration_ms=total_duration,
            event_type="system_health_check"
        )
        
        return report
    
    async def get_quick_health(self) -> Dict[str, bool]:
        """Get quick health status for readiness/liveness probes."""
        cache_key = "quick_health"
        current_time = time.time()
        
        # Check cache first
        if cache_key in self._last_check_cache:
            cache_entry = self._last_check_cache[cache_key]
            if current_time - cache_entry['timestamp'] < self._cache_ttl:
                return cache_entry['result']
        
        try:
            health_status = {
                "api": True,  # We're responding, so API is healthy
                "database": False,
                "redis": False,
                "workers": False
            }
            
            # Quick database check
            if get_database:
                try:
                    async with get_database() as conn:
                        result = await conn.execute(text("SELECT 1"))
                        result.fetchone()
                        health_status["database"] = True
                except:
                    pass
            
            # Quick Redis check
            if get_redis_connection:
                try:
                    redis = await get_redis_connection()
                    await redis.ping()
                    health_status["redis"] = True
                except:
                    pass
            
            # Quick worker check
            if get_database:
                try:
                    async with get_database() as conn:
                        result = await conn.execute(text("""
                            SELECT COUNT(*) as active_workers
                            FROM worker_heartbeat 
                            WHERE last_seen > now() - interval '2 minutes'
                        """))
                        row = result.fetchone()
                        active_workers = row[0] if row else 0
                        health_status["workers"] = active_workers > 0
                except:
                    pass
            
            # Cache the result
            self._last_check_cache[cache_key] = {
                'result': health_status,
                'timestamp': current_time
            }
            
            return health_status
            
        except Exception as e:
            self.logger.error(f"Quick health check failed: {e}")
            return {
                "api": True,
                "database": False,
                "redis": False,
                "workers": False
            }
    
    def get_uptime(self) -> float:
        """Get service uptime in seconds."""
        return time.time() - self.start_time


# Global instance
system_health_monitor = SystemHealthMonitor()