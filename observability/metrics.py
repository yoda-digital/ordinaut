"""
Prometheus metrics collection for Ordinaut.

Provides comprehensive metrics for all system components including
task execution, pipeline steps, scheduler performance, worker health,
and system resources according to plan.md section 11 requirements.
"""

import time
import functools
from typing import Dict, Any, Optional
from prometheus_client import (
    Counter, Histogram, Gauge, CollectorRegistry, generate_latest,
    CONTENT_TYPE_LATEST
)

# Global metrics registry
metrics_registry = CollectorRegistry()


class OrchestrationMetrics:
    """Comprehensive metrics for Ordinaut."""
    
    def __init__(self, registry: CollectorRegistry = None):
        self.registry = registry or metrics_registry
        self._setup_metrics()
    
    def _setup_metrics(self):
        """Initialize all Prometheus metrics per plan.md requirements."""
        
        # Core metrics from plan.md section 11
        self.step_duration = Histogram(
            'orchestrator_step_duration_seconds',
            'Pipeline step execution duration in seconds', 
            ['tool_addr', 'step_id', 'task_id'],
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, float('inf')),
            registry=self.registry
        )
        
        self.step_success_total = Counter(
            'orchestrator_step_success_total',
            'Total successful pipeline step executions',
            ['tool_addr', 'step_id'],
            registry=self.registry
        )
        
        self.step_failure_total = Counter(
            'orchestrator_step_failure_total', 
            'Total failed pipeline step executions',
            ['tool_addr', 'step_id', 'error_type'],
            registry=self.registry
        )
        
        self.runs_total = Counter(
            'orchestrator_runs_total',
            'Total task run attempts',
            ['status', 'task_id', 'agent_id'],
            registry=self.registry
        )
        
        self.scheduler_lag_seconds = Gauge(
            'orchestrator_scheduler_lag_seconds',
            'Time lag between scheduled run_at and current time for oldest due work',
            registry=self.registry
        )
        
        # Additional comprehensive metrics for production observability
        self.worker_heartbeat_total = Counter(
            'orchestrator_worker_heartbeat_total',
            'Total worker heartbeats recorded',
            ['worker_id'],
            registry=self.registry
        )
        
        self.due_work_queue_depth = Gauge(
            'orchestrator_due_work_queue_depth',
            'Number of tasks waiting in due_work queue',
            ['priority'],
            registry=self.registry
        )
        
        self.task_duration = Histogram(
            'orchestrator_task_duration_seconds',
            'Complete task execution duration',
            ['task_id', 'agent_id', 'success'],
            buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 300.0, 600.0, float('inf')),
            registry=self.registry
        )
        
        self.tasks_created_total = Counter(
            'orchestrator_tasks_created_total',
            'Total tasks created',
            ['schedule_kind', 'agent_id'],
            registry=self.registry
        )
        
        self.pipeline_executions_total = Counter(
            'orchestrator_pipeline_executions_total',
            'Total pipeline executions attempted',
            ['task_id', 'status'],
            registry=self.registry
        )
        
        # Worker and system metrics
        self.active_workers = Gauge(
            'orchestrator_active_workers',
            'Number of active workers by state',
            ['worker_id', 'state'],
            registry=self.registry
        )
        
        self.lease_duration = Histogram(
            'orchestrator_lease_duration_seconds',
            'Duration of work item leases',
            ['worker_id'],
            buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 300.0, 600.0, float('inf')),
            registry=self.registry
        )
        
        self.database_connections = Gauge(
            'orchestrator_database_connections',
            'Active database connections',
            ['pool', 'state'],
            registry=self.registry
        )
        
        self.redis_operations_total = Counter(
            'orchestrator_redis_operations_total',
            'Redis operations count',
            ['operation', 'result'],
            registry=self.registry
        )
        
        # API endpoint metrics
        self.http_requests_total = Counter(
            'orchestrator_http_requests_total',
            'Total HTTP requests received',
            ['method', 'endpoint', 'status_code'],
            registry=self.registry
        )
        
        self.http_request_duration = Histogram(
            'orchestrator_http_request_duration_seconds',
            'HTTP request duration',
            ['method', 'endpoint'],
            buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, float('inf')),
            registry=self.registry
        )

        # Plugin HTTP metrics
        self.plugin_http_requests_total = Counter(
            'orchestrator_plugin_http_requests_total',
            'Total HTTP requests per plugin',
            ['plugin_id', 'status_code'],
            registry=self.registry
        )
        self.plugin_http_request_duration = Histogram(
            'orchestrator_plugin_http_request_duration_seconds',
            'HTTP request duration per plugin',
            ['plugin_id'],
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, float('inf')),
            registry=self.registry
        )
        
        # External tool metrics
        self.external_tool_calls_total = Counter(
            'orchestrator_external_tool_calls_total',
            'External tool invocations',
            ['tool_address', 'status_code'],
            registry=self.registry
        )
        
        self.external_tool_duration = Histogram(
            'orchestrator_external_tool_duration_seconds',
            'External tool call duration',
            ['tool_address', 'method'],
            buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, float('inf')),
            registry=self.registry
        )
        
        # Scheduler metrics
        self.scheduler_ticks_total = Counter(
            'orchestrator_scheduler_ticks_total',
            'Total scheduler tick executions',
            ['result'],
            registry=self.registry
        )
        
        self.scheduler_jobs_created_total = Counter(
            'orchestrator_scheduler_jobs_created_total', 
            'Jobs created by scheduler',
            ['schedule_kind'],
            registry=self.registry
        )
        
        # Security metrics
        self.security_events_total = Counter(
            'orchestrator_security_events_total',
            'Total security events detected',
            ['event_type', 'severity'],
            registry=self.registry
        )
        
        self.authentication_attempts_total = Counter(
            'orchestrator_authentication_attempts_total',
            'Total authentication attempts',
            ['method', 'result'],
            registry=self.registry
        )
        
        self.jwt_tokens_issued_total = Counter(
            'orchestrator_jwt_tokens_issued_total',
            'Total JWT tokens issued',
            ['agent_id', 'token_type'],
            registry=self.registry
        )
        
        self.jwt_tokens_revoked_total = Counter(
            'orchestrator_jwt_tokens_revoked_total',
            'Total JWT tokens revoked',
            ['reason'],
            registry=self.registry
        )
        
        self.rate_limit_violations_total = Counter(
            'orchestrator_rate_limit_violations_total',
            'Rate limit violations by client',
            ['client_ip', 'endpoint'],
            registry=self.registry
        )
        
        self.blocked_requests_total = Counter(
            'orchestrator_blocked_requests_total',
            'Requests blocked by security middleware',
            ['reason', 'client_ip'],
            registry=self.registry
        )
    
    def record_step_execution(self, tool_addr: str, step_id: str, task_id: str, 
                            duration: float, success: bool, error_type: Optional[str] = None):
        """Record pipeline step execution metrics."""
        self.step_duration.labels(
            tool_addr=tool_addr, 
            step_id=step_id, 
            task_id=task_id
        ).observe(duration)
        
        if success:
            self.step_success_total.labels(
                tool_addr=tool_addr,
                step_id=step_id
            ).inc()
        else:
            self.step_failure_total.labels(
                tool_addr=tool_addr,
                step_id=step_id,
                error_type=error_type or "unknown"
            ).inc()
    
    def record_task_run(self, task_id: str, agent_id: str, status: str, duration: float):
        """Record complete task execution metrics."""
        self.runs_total.labels(
            status=status,
            task_id=task_id, 
            agent_id=agent_id
        ).inc()
        
        self.task_duration.labels(
            task_id=task_id,
            agent_id=agent_id,
            success=str(status == "success").lower()
        ).observe(duration)
    
    def record_pipeline_execution(self, task_id: str, status: str):
        """Record pipeline execution attempt."""
        self.pipeline_executions_total.labels(
            task_id=task_id,
            status=status
        ).inc()
    
    def record_task_created(self, schedule_kind: str, agent_id: str):
        """Record task creation."""
        self.tasks_created_total.labels(
            schedule_kind=schedule_kind,
            agent_id=agent_id
        ).inc()
    
    def record_worker_heartbeat(self, worker_id: str):
        """Record worker heartbeat."""
        self.worker_heartbeat_total.labels(worker_id=worker_id).inc()
    
    def update_scheduler_lag(self, lag_seconds: float):
        """Update scheduler lag gauge."""
        self.scheduler_lag_seconds.set(lag_seconds)
    
    def update_queue_depth(self, depth: int, priority: str = "all"):
        """Update due work queue depth."""
        self.due_work_queue_depth.labels(priority=priority).set(depth)
    
    def update_active_workers(self, worker_id: str, state: str, count: int = 1):
        """Update active worker count."""
        self.active_workers.labels(worker_id=worker_id, state=state).set(count)
    
    def record_lease_duration(self, worker_id: str, duration: float):
        """Record work item lease duration."""
        self.lease_duration.labels(worker_id=worker_id).observe(duration)
    
    def update_database_connections(self, pool: str, state: str, count: int):
        """Update database connection metrics."""
        self.database_connections.labels(pool=pool, state=state).set(count)
    
    def record_redis_operation(self, operation: str, result: str):
        """Record Redis operation."""
        self.redis_operations_total.labels(operation=operation, result=result).inc()
    
    def record_http_request(self, method: str, endpoint: str, status_code: int, duration: float):
        """Record HTTP request metrics."""
        self.http_requests_total.labels(
            method=method,
            endpoint=endpoint, 
            status_code=str(status_code)
        ).inc()
        
        self.http_request_duration.labels(
            method=method,
            endpoint=endpoint
        ).observe(duration)

    def record_plugin_http_request(self, plugin_id: str, status_code: int, duration: float):
        self.plugin_http_requests_total.labels(
            plugin_id=plugin_id,
            status_code=str(status_code)
        ).inc()
        self.plugin_http_request_duration.labels(
            plugin_id=plugin_id
        ).observe(duration)
    
    def record_external_tool_call(self, tool_address: str, method: str, 
                                 status_code: int, duration: float):
        """Record external tool call metrics."""
        self.external_tool_calls_total.labels(
            tool_address=tool_address,
            status_code=str(status_code)
        ).inc()
        
        self.external_tool_duration.labels(
            tool_address=tool_address,
            method=method
        ).observe(duration)
    
    def record_scheduler_tick(self, result: str):
        """Record scheduler tick execution."""
        self.scheduler_ticks_total.labels(result=result).inc()
    
    def record_scheduler_job_created(self, schedule_kind: str):
        """Record scheduler job creation."""
        self.scheduler_jobs_created_total.labels(schedule_kind=schedule_kind).inc()
    
    def record_security_event(self, event_type: str, severity: str):
        """Record security event."""
        self.security_events_total.labels(
            event_type=event_type,
            severity=severity
        ).inc()
    
    def record_authentication_attempt(self, method: str, result: str):
        """Record authentication attempt."""
        self.authentication_attempts_total.labels(
            method=method,
            result=result
        ).inc()
    
    def record_jwt_token_issued(self, agent_id: str, token_type: str):
        """Record JWT token issuance."""
        self.jwt_tokens_issued_total.labels(
            agent_id=agent_id,
            token_type=token_type
        ).inc()
    
    def record_jwt_token_revoked(self, reason: str = "manual"):
        """Record JWT token revocation."""
        self.jwt_tokens_revoked_total.labels(reason=reason).inc()
    
    def record_rate_limit_violation(self, client_ip: str, endpoint: str):
        """Record rate limit violation."""
        self.rate_limit_violations_total.labels(
            client_ip=client_ip,
            endpoint=endpoint
        ).inc()
    
    def record_blocked_request(self, reason: str, client_ip: str):
        """Record blocked request."""
        self.blocked_requests_total.labels(
            reason=reason,
            client_ip=client_ip
        ).inc()


# Global metrics instance
orchestrator_metrics = OrchestrationMetrics()


def track_step_execution(metrics: OrchestrationMetrics = None):
    """Decorator to track pipeline step execution metrics."""
    if metrics is None:
        metrics = orchestrator_metrics
        
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(tool_addr: str, step_id: str, task_id: str, *args, **kwargs):
            start_time = time.time()
            success = False
            error_type = None
            
            try:
                result = await func(tool_addr, step_id, task_id, *args, **kwargs)
                success = True
                return result
                
            except Exception as e:
                error_type = e.__class__.__name__
                raise
                
            finally:
                duration = time.time() - start_time
                metrics.record_step_execution(
                    tool_addr=tool_addr,
                    step_id=step_id, 
                    task_id=task_id,
                    duration=duration,
                    success=success,
                    error_type=error_type
                )
        
        @functools.wraps(func)
        def sync_wrapper(tool_addr: str, step_id: str, task_id: str, *args, **kwargs):
            start_time = time.time()
            success = False
            error_type = None
            
            try:
                result = func(tool_addr, step_id, task_id, *args, **kwargs)
                success = True
                return result
                
            except Exception as e:
                error_type = e.__class__.__name__
                raise
                
            finally:
                duration = time.time() - start_time
                metrics.record_step_execution(
                    tool_addr=tool_addr,
                    step_id=step_id,
                    task_id=task_id,
                    duration=duration,
                    success=success,
                    error_type=error_type
                )
        
        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
            
    return decorator


def track_task_execution(metrics: OrchestrationMetrics = None):
    """Decorator to track complete task execution metrics."""
    if metrics is None:
        metrics = orchestrator_metrics
        
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(task_id: str, agent_id: str, *args, **kwargs):
            start_time = time.time()
            status = "failed"
            
            try:
                result = await func(task_id, agent_id, *args, **kwargs)
                status = "success"
                return result
                
            except Exception:
                raise
                
            finally:
                duration = time.time() - start_time
                metrics.record_task_run(
                    task_id=task_id,
                    agent_id=agent_id,
                    status=status,
                    duration=duration
                )
        
        @functools.wraps(func)
        def sync_wrapper(task_id: str, agent_id: str, *args, **kwargs):
            start_time = time.time()
            status = "failed"
            
            try:
                result = func(task_id, agent_id, *args, **kwargs)
                status = "success"
                return result
                
            except Exception:
                raise
                
            finally:
                duration = time.time() - start_time
                metrics.record_task_run(
                    task_id=task_id,
                    agent_id=agent_id,
                    status=status,
                    duration=duration
                )
        
        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
            
    return decorator


def track_http_requests(metrics: OrchestrationMetrics = None):
    """Decorator to track HTTP request metrics."""
    if metrics is None:
        metrics = orchestrator_metrics
        
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(request, *args, **kwargs):
            start_time = time.time()
            
            try:
                response = await func(request, *args, **kwargs)
                status_code = getattr(response, 'status_code', 200)
                
                duration = time.time() - start_time
                metrics.record_http_request(
                    method=request.method,
                    endpoint=request.url.path,
                    status_code=status_code,
                    duration=duration
                )
                
                return response
                
            except Exception as e:
                duration = time.time() - start_time
                status_code = getattr(e, 'status_code', 500)
                
                metrics.record_http_request(
                    method=request.method,
                    endpoint=request.url.path,
                    status_code=status_code,
                    duration=duration
                )
                
                raise
        
        return wrapper
    return decorator


def get_metrics_handler(registry: CollectorRegistry = None):
    """Get HTTP handler for Prometheus metrics endpoint."""
    if registry is None:
        registry = metrics_registry
        
    def metrics_handler():
        return generate_latest(registry), {"Content-Type": CONTENT_TYPE_LATEST}
    
    return metrics_handler
