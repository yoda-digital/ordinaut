"""
Structured JSON logging system for Personal Agent Orchestrator.

Provides correlation IDs, request tracing, and performance metrics
embedded in logs according to plan.md section 11 requirements.
"""

import json
import uuid
import logging
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Union
from contextvars import ContextVar
import functools

# Context variables for distributed tracing
REQUEST_ID: ContextVar[str] = ContextVar('request_id', default=None)
TASK_ID: ContextVar[str] = ContextVar('task_id', default=None) 
RUN_ID: ContextVar[str] = ContextVar('run_id', default=None)
STEP_ID: ContextVar[str] = ContextVar('step_id', default=None)
AGENT_ID: ContextVar[str] = ContextVar('agent_id', default=None)
WORKER_ID: ContextVar[str] = ContextVar('worker_id', default=None)


class StructuredLogger:
    """Structured JSON logger with correlation IDs and performance tracking."""
    
    def __init__(self, name: str, level: int = logging.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        
        # Remove any existing handlers to avoid duplicates
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
        
        # JSON formatter
        handler = logging.StreamHandler()
        handler.setFormatter(self.JSONFormatter())
        self.logger.addHandler(handler)
        
        # Prevent propagation to avoid duplicate logs
        self.logger.propagate = False
    
    class JSONFormatter(logging.Formatter):
        """JSON formatter with correlation IDs and structured fields."""
        
        def format(self, record):
            """Format log record as structured JSON."""
            log_entry = {
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'level': record.levelname,
                'logger': record.name,
                'message': record.getMessage(),
                'module': record.module,
                'function': record.funcName,
                'line': record.lineno,
                'thread': record.thread,
                'process': record.process
            }
            
            # Add correlation IDs from context
            if REQUEST_ID.get():
                log_entry['request_id'] = REQUEST_ID.get()
            if TASK_ID.get():
                log_entry['task_id'] = TASK_ID.get()
            if RUN_ID.get():
                log_entry['run_id'] = RUN_ID.get()
            if STEP_ID.get():
                log_entry['step_id'] = STEP_ID.get()
            if AGENT_ID.get():
                log_entry['agent_id'] = AGENT_ID.get()
            if WORKER_ID.get():
                log_entry['worker_id'] = WORKER_ID.get()
            
            # Add extra fields from record
            if hasattr(record, 'extra_fields'):
                log_entry.update(record.extra_fields)
            
            # Add performance metrics if available
            if hasattr(record, 'latency_ms'):
                log_entry['latency_ms'] = record.latency_ms
            if hasattr(record, 'attempt'):
                log_entry['attempt'] = record.attempt
                
            # Add exception info
            if record.exc_info:
                log_entry['exception'] = self.formatException(record.exc_info)
                log_entry['exception_type'] = record.exc_info[0].__name__ if record.exc_info[0] else None
            
            return json.dumps(log_entry, default=str)
    
    def _log_with_extras(self, level: int, message: str, **extra_fields):
        """Log message with extra structured fields."""
        self.logger.log(level, message, extra={'extra_fields': extra_fields})
    
    def debug(self, message: str, **extra_fields):
        """Log debug message with extra fields."""
        self._log_with_extras(logging.DEBUG, message, **extra_fields)
    
    def info(self, message: str, **extra_fields):
        """Log info message with extra fields."""
        self._log_with_extras(logging.INFO, message, **extra_fields)
    
    def warning(self, message: str, **extra_fields):
        """Log warning message with extra fields."""
        self._log_with_extras(logging.WARNING, message, **extra_fields)
    
    def error(self, message: str, **extra_fields):
        """Log error message with extra fields."""
        self._log_with_extras(logging.ERROR, message, **extra_fields)
    
    def critical(self, message: str, **extra_fields):
        """Log critical message with extra fields."""
        self._log_with_extras(logging.CRITICAL, message, **extra_fields)
    
    def exception(self, message: str, **extra_fields):
        """Log exception with traceback and extra fields."""
        self.logger.exception(message, extra={'extra_fields': extra_fields})
    
    # Specialized logging methods for orchestrator events
    def task_created(self, task_id: str, agent_id: str, schedule_kind: str, title: str):
        """Log task creation event."""
        self.info(
            "Task created",
            task_id=task_id,
            agent_id=agent_id,
            schedule_kind=schedule_kind,
            title=title,
            event_type="task_created"
        )
    
    def task_started(self, task_id: str, run_id: str, agent_id: str, attempt: int = 1):
        """Log task execution start."""
        self.info(
            "Task execution started",
            task_id=task_id,
            run_id=run_id,
            agent_id=agent_id,
            attempt=attempt,
            event_type="task_started"
        )
    
    def task_completed(self, task_id: str, run_id: str, success: bool, duration_ms: float):
        """Log task execution completion."""
        self.info(
            f"Task execution {'completed successfully' if success else 'failed'}",
            task_id=task_id,
            run_id=run_id,
            success=success,
            latency_ms=duration_ms,
            event_type="task_completed"
        )
    
    def pipeline_step_started(self, step_id: str, tool_address: str, attempt: int = 1):
        """Log pipeline step start."""
        self.info(
            "Pipeline step started",
            step_id=step_id,
            tool_address=tool_address,
            attempt=attempt,
            event_type="pipeline_step_started"
        )
    
    def pipeline_step_completed(self, step_id: str, tool_address: str, 
                              success: bool, duration_ms: float):
        """Log pipeline step completion."""
        self.info(
            f"Pipeline step {'completed' if success else 'failed'}",
            step_id=step_id,
            tool_address=tool_address,
            success=success,
            latency_ms=duration_ms,
            event_type="pipeline_step_completed"
        )
    
    def external_tool_call(self, tool_address: str, method: str, status_code: int, 
                         duration_ms: float, url: Optional[str] = None):
        """Log external tool call."""
        self.info(
            "External tool call completed",
            tool_address=tool_address,
            method=method,
            status_code=status_code,
            latency_ms=duration_ms,
            url=url,
            event_type="external_tool_call"
        )
    
    def worker_heartbeat(self, worker_id: str, queue_depth: int, active_leases: int):
        """Log worker heartbeat."""
        self.debug(
            "Worker heartbeat",
            worker_id=worker_id,
            queue_depth=queue_depth,
            active_leases=active_leases,
            event_type="worker_heartbeat"
        )
    
    def scheduler_tick(self, jobs_created: int, lag_seconds: float):
        """Log scheduler tick."""
        self.debug(
            "Scheduler tick completed",
            jobs_created=jobs_created,
            lag_seconds=lag_seconds,
            event_type="scheduler_tick"
        )
    
    def lease_acquired(self, worker_id: str, task_id: str, lease_duration_seconds: int):
        """Log work lease acquisition."""
        self.debug(
            "Work lease acquired",
            worker_id=worker_id,
            task_id=task_id,
            lease_duration_seconds=lease_duration_seconds,
            event_type="lease_acquired"
        )
    
    def lease_released(self, worker_id: str, task_id: str, duration_ms: float):
        """Log work lease release."""
        self.debug(
            "Work lease released",
            worker_id=worker_id,
            task_id=task_id,
            latency_ms=duration_ms,
            event_type="lease_released"
        )
    
    def api_request(self, method: str, path: str, status_code: int, 
                   duration_ms: float, agent_id: Optional[str] = None):
        """Log API request."""
        self.info(
            "API request processed",
            method=method,
            path=path,
            status_code=status_code,
            latency_ms=duration_ms,
            agent_id=agent_id,
            event_type="api_request"
        )
    
    def security_event(self, event_type: str, agent_id: Optional[str] = None, 
                      details: Optional[Dict[str, Any]] = None):
        """Log security-related events."""
        self.warning(
            f"Security event: {event_type}",
            security_event_type=event_type,
            agent_id=agent_id,
            details=details or {},
            event_type="security_event"
        )
    
    def performance_alert(self, metric_name: str, current_value: float, 
                         threshold: float, severity: str = "warning"):
        """Log performance alerts."""
        level = logging.WARNING if severity == "warning" else logging.ERROR
        self._log_with_extras(
            level,
            f"Performance alert: {metric_name} = {current_value} (threshold: {threshold})",
            metric_name=metric_name,
            current_value=current_value,
            threshold=threshold,
            severity=severity,
            event_type="performance_alert"
        )


# Context management functions
def set_request_context(request_id: str = None, task_id: str = None, 
                       run_id: str = None, step_id: str = None,
                       agent_id: str = None, worker_id: str = None):
    """Set request context for logging correlation."""
    if request_id:
        REQUEST_ID.set(request_id)
    if task_id:
        TASK_ID.set(task_id)
    if run_id:
        RUN_ID.set(run_id)
    if step_id:
        STEP_ID.set(step_id)
    if agent_id:
        AGENT_ID.set(agent_id)
    if worker_id:
        WORKER_ID.set(worker_id)


def clear_request_context():
    """Clear all request context variables."""
    for ctx_var in [REQUEST_ID, TASK_ID, RUN_ID, STEP_ID, AGENT_ID, WORKER_ID]:
        ctx_var.set(None)


def get_request_context() -> Dict[str, Optional[str]]:
    """Get current request context as dictionary."""
    return {
        'request_id': REQUEST_ID.get(),
        'task_id': TASK_ID.get(),
        'run_id': RUN_ID.get(), 
        'step_id': STEP_ID.get(),
        'agent_id': AGENT_ID.get(),
        'worker_id': WORKER_ID.get()
    }


def generate_request_id() -> str:
    """Generate unique request ID."""
    return f"req-{uuid.uuid4().hex[:8]}"


def generate_run_id() -> str:
    """Generate unique run ID."""
    return f"run-{uuid.uuid4().hex[:8]}"


def generate_step_id(step_name: str) -> str:
    """Generate unique step ID."""
    return f"step-{step_name}-{uuid.uuid4().hex[:6]}"


# Logging decorators for automatic instrumentation
def log_function_call(logger: StructuredLogger = None, level: int = logging.DEBUG):
    """Decorator to log function calls with timing."""
    def decorator(func):
        func_logger = logger or StructuredLogger(func.__module__)
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            func_name = func.__name__
            
            func_logger._log_with_extras(
                level, f"Function {func_name} started",
                function=func_name,
                args_count=len(args),
                kwargs_keys=list(kwargs.keys())
            )
            
            try:
                result = await func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000
                
                func_logger._log_with_extras(
                    level, f"Function {func_name} completed successfully",
                    function=func_name,
                    latency_ms=duration_ms,
                    success=True
                )
                
                return result
                
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                
                func_logger._log_with_extras(
                    logging.ERROR, f"Function {func_name} failed: {e}",
                    function=func_name,
                    latency_ms=duration_ms,
                    success=False,
                    exception_type=e.__class__.__name__
                )
                
                raise
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            func_name = func.__name__
            
            func_logger._log_with_extras(
                level, f"Function {func_name} started",
                function=func_name,
                args_count=len(args),
                kwargs_keys=list(kwargs.keys())
            )
            
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000
                
                func_logger._log_with_extras(
                    level, f"Function {func_name} completed successfully", 
                    function=func_name,
                    latency_ms=duration_ms,
                    success=True
                )
                
                return result
                
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                
                func_logger._log_with_extras(
                    logging.ERROR, f"Function {func_name} failed: {e}",
                    function=func_name,
                    latency_ms=duration_ms,
                    success=False,
                    exception_type=e.__class__.__name__
                )
                
                raise
        
        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
            
    return decorator


def log_with_context(func):
    """Decorator to maintain logging context across function calls."""
    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        # Preserve existing context
        context = get_request_context()
        
        try:
            return await func(*args, **kwargs)
        finally:
            # Restore context
            set_request_context(**context)
    
    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        # Preserve existing context
        context = get_request_context()
        
        try:
            return func(*args, **kwargs)
        finally:
            # Restore context
            set_request_context(**context)
    
    # Return appropriate wrapper based on function type
    import asyncio
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper


def track_http_requests(app):
    """Middleware to track HTTP requests with structured logging."""
    @app.middleware("http")
    async def request_logging_middleware(request, call_next):
        # Generate request ID and set context
        request_id = generate_request_id()
        set_request_context(request_id=request_id)
        
        # Extract agent ID from headers if available
        agent_id = request.headers.get("X-Agent-ID")
        if agent_id:
            set_request_context(agent_id=agent_id)
        
        # Start timing
        start_time = time.time()
        
        # Process request
        try:
            response = await call_next(request)
            duration_ms = (time.time() - start_time) * 1000
            
            # Log successful request
            api_logger.api_request(
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                agent_id=agent_id
            )
            
            return response
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            
            # Log failed request
            api_logger.error(
                "HTTP request failed",
                method=request.method,
                path=request.url.path,
                latency_ms=duration_ms,
                agent_id=agent_id,
                exception_type=e.__class__.__name__,
                error=str(e)
            )
            
            raise
        finally:
            # Clear context after request
            clear_request_context()


# Pre-configured loggers for different components
api_logger = StructuredLogger("orchestrator.api")
worker_logger = StructuredLogger("orchestrator.worker")
scheduler_logger = StructuredLogger("orchestrator.scheduler")
pipeline_logger = StructuredLogger("orchestrator.pipeline")
mcp_logger = StructuredLogger("orchestrator.mcp")
security_logger = StructuredLogger("orchestrator.security")
performance_logger = StructuredLogger("orchestrator.performance")