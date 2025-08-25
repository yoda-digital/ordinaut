"""
Ordinaut FastAPI Application.

Main application that provides the complete REST API for task scheduling,
execution monitoring, and event publishing. Includes automatic OpenAPI
documentation, error handling, and health checks.
"""

import os
import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi

from .dependencies import check_database_health, check_redis_health
from .schemas import HealthResponse, ErrorResponse
from .routes import tasks, runs, events, agents
from .security import (
    security_middleware, limiter, rate_limit_handler,
    SecurityHeaders, security_config
)
from slowapi.errors import RateLimitExceeded

# Import observability components
from ordinaut.plugins import ExtensionLoader
from ordinaut.engine.registry import ToolRegistry
from observability.logging import (
    api_logger, set_request_context, generate_request_id,
    track_http_requests, log_with_context
)
from observability.health import SystemHealthMonitor

# Environment configuration
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
VERSION = os.getenv("VERSION", "1.0.0")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# Initialize observability components
health_monitor = SystemHealthMonitor()
logger = api_logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info(f"Starting Ordinaut API v{VERSION}")
    logger.info(f"Environment: {ENVIRONMENT}")
    
    # Verify connections on startup
    db_healthy = await check_database_health()
    redis_healthy = await check_redis_health()
    
    if not db_healthy:
        logger.error("Database connection failed on startup")
        raise RuntimeError("Database connection failed")
    
    if not redis_healthy:
        logger.warning("Redis connection failed on startup - event features may be limited")
    
    logger.info("Application startup complete")
    yield
    
    # Shutdown
    logger.info("Shutting down Ordinaut API")


# Create FastAPI application
app = FastAPI(
    title="Ordinaut",
    description="""
    A production-ready Ordinaut that provides AI agents with a shared backbone 
    for time, state, and discipline.

    ## Features

    * **Task Scheduling**: Create cron, RRULE, one-time, and event-based tasks
    * **Pipeline Execution**: Deterministic pipeline execution with template rendering
    * **Event Publishing**: Publish events to trigger event-based tasks
    * **Execution Monitoring**: Complete audit trail and execution history
    * **Status Management**: Pause, resume, cancel, and snooze tasks
    * **Authentication**: Agent-based authentication with scope validation

    ## Architecture

    Built on PostgreSQL for durability, Redis Streams for events, and APScheduler for timing.
    Uses SELECT ... FOR UPDATE SKIP LOCKED for safe concurrent job distribution.

    ## Getting Started

    1. Create an agent: `POST /agents`
    2. Create a task: `POST /tasks`
    3. Monitor execution: `GET /runs`
    4. Publish events: `POST /events`
    """,
    version=VERSION,
    lifespan=lifespan,
    openapi_tags=[
        {
            "name": "tasks",
            "description": "Task creation, management, and execution control"
        },
        {
            "name": "runs", 
            "description": "Task execution history and monitoring"
        },
        {
            "name": "events",
            "description": "External event publishing and stream management"
        },
        {
            "name": "agents",
            "description": "Agent management and authentication"
        },
        {
            "name": "health",
            "description": "System health and monitoring endpoints"
        }
    ]
)

# Initialize extension system (lazy loading)
_ext_tool_registry = ToolRegistry()
_ext_loader = ExtensionLoader(app)
_ext_loader.load_all(tool_registry=_ext_tool_registry, context={})
try:
    _ext_tool_registry.freeze()
except Exception:
    pass

# Add security middleware stack (order matters!)
if ENVIRONMENT == "production":
    # Trusted host middleware for production
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["localhost", "127.0.0.1", "*.example.com"]
    )

# Rate limiting middleware
if limiter:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    # Note: SlowAPIMiddleware is added automatically when limiter is used

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if DEBUG else ["https://localhost", "https://127.0.0.1"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Custom exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with consistent error format."""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=exc.__class__.__name__,
            message=exc.detail,
            details=getattr(exc, 'details', None),
            request_id=getattr(request.state, 'request_id', None),
            timestamp=datetime.now(timezone.utc)
        ).dict()
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    logger.exception("Unhandled exception in API request")
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error="InternalServerError",
            message="An unexpected error occurred. Please try again later.",
            details={"exception_type": exc.__class__.__name__} if DEBUG else None,
            request_id=getattr(request.state, 'request_id', None),
            timestamp=datetime.now(timezone.utc)
        ).dict()
    )


# Security middleware for request validation and threat protection
@app.middleware("http")
async def security_middleware_handler(request: Request, call_next):
    """Security middleware for comprehensive request validation."""
    return await security_middleware(request, call_next)


# Request middleware for logging, metrics, and request IDs
@app.middleware("http")
async def request_middleware(request: Request, call_next):
    """Add request ID, logging, and metrics for all requests."""
    # Generate request ID and set context
    request_id = generate_request_id()
    request.state.request_id = request_id
    set_request_context(request_id=request_id)
    
    # Log request start
    start_time = datetime.now(timezone.utc)
    logger.api_request(
        method=request.method,
        path=request.url.path,
        status_code=0,  # Will be updated below
        duration_ms=0,  # Will be updated below
    )
    
    # Lazy-load plugin router if hitting /ext/{plugin}/...
    path = request.url.path
    if path.startswith('/ext/'):
        parts = path.split('/', 3)
        if len(parts) >= 3:
            pid = parts[2]
            if pid in getattr(_ext_loader, 'specs', {}) and pid not in getattr(_ext_loader, 'loaded', {}):
                try:
                    logger.info(f"Lazy-loading extension: {pid}")
                    result = _ext_loader._ensure_loaded(pid, tool_registry=_ext_tool_registry, context={})
                    if result:
                        logger.info(f"Extension {pid} loaded successfully: {result}")
                        # Redirect to same URL to trigger the newly mounted router
                        from fastapi.responses import RedirectResponse
                        return RedirectResponse(url=str(request.url), status_code=307)
                    else:
                        logger.warning(f"Extension {pid} failed to load (returned None/False)")
                except Exception as e:
                    logger.error(f"Failed to load extension {pid}: {e}", exc_info=True)

    # Process request
    try:
        response = await call_next(request)
        status_code = getattr(response, 'status_code', 200)
        
        # Calculate duration and record metrics
        duration_seconds = (datetime.now(timezone.utc) - start_time).total_seconds()
        duration_ms = duration_seconds * 1000
        
        # Metrics handled by observability extension
        
        # Log completion
        logger.api_request(
            method=request.method,
            path=request.url.path,
            status_code=status_code,
            duration_ms=duration_ms
        )
        
        # Add headers
        response.headers["X-Request-ID"] = request_id
        
        return response
        
    except Exception as e:
        # Handle exceptions
        duration_seconds = (datetime.now(timezone.utc) - start_time).total_seconds()
        duration_ms = duration_seconds * 1000
        status_code = getattr(e, 'status_code', 500)
        
        # Metrics handled by observability extension
        
        # Log error
        logger.error(
            f"Request failed: {request.method} {request.url.path}",
            status_code=status_code,
            duration_ms=duration_ms,
            exception=str(e)
        )
        
        raise


# Include routers
app.include_router(tasks.router)
app.include_router(runs.router)
app.include_router(events.router)
app.include_router(agents.router)


# Metrics endpoint is served by the observability extension


# Extension system visibility endpoints (mirror ordinaut.api)
@app.get("/extensions")
def list_extensions():
    out = []
    for pid, spec in getattr(_ext_loader, 'specs', {}).items():
        entry = {
            "id": pid,
            "root": str(spec.root),
            "module": spec.module,
            "enabled": spec.enabled,
            "eager": spec.eager,
            "source": getattr(spec, "source", "unknown"),
            "grants": [c.name for c in (spec.grants or set())],
            "status": getattr(_ext_loader, 'status', {}).get(pid, {}),
            "metrics": getattr(_ext_loader, 'metrics', {}).get(pid, {}),
        }
        out.append(entry)
    return out


@app.get("/extensions/{plugin_id}/events/health")
async def extension_events_health(plugin_id: str, namespace: str | None = None):
    em = getattr(_ext_loader, "_events_manager", None)
    if not em:
        raise HTTPException(status_code=404, detail="events manager not enabled")
    try:
        res = await em.health_for_plugin(plugin_id, namespace=namespace)
    except Exception as ex:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(ex))
    return res


@app.get("/tools")
def list_tools():
    try:
        reg = _ext_tool_registry
        return {k: {"description": v.get("description", "")} for k, v in reg.list().items()}
    except Exception:
        return {}


# Health check endpoints
@app.get("/health", tags=["health"])
async def health_check():
    """
    Comprehensive system health check.
    
    Returns detailed health status of all system components including
    database, Redis, workers, scheduler, and overall service status.
    """
    try:
        report = await health_monitor.get_system_health(request_id=generate_request_id())
        return report.to_dict()
    except Exception as e:
        logger.error(f"Health check failed: {e}", exception=str(e))
        return {
            "status": "unhealthy",
            "timestamp": datetime.now(timezone.utc).isoformat() + 'Z',
            "error": "Health check system failure",
            "details": {"exception": str(e)}
        }


@app.get("/health/ready", tags=["health"])
async def readiness_check():
    """
    Kubernetes readiness probe.
    
    Returns 200 if the service is ready to accept requests,
    503 if critical dependencies are unavailable.
    """
    try:
        health_status = await health_monitor.get_quick_health()
        
        if not health_status.get("database", False):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database is not available"
            )
        
        return {"status": "ready", **health_status}
        
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not ready"
        )


@app.get("/health/live", tags=["health"])
async def liveness_check():
    """
    Kubernetes liveness probe.
    
    Returns 200 if the service is alive and should not be restarted.
    This is a simple check that the service is responsive.
    """
    try:
        uptime = health_monitor.start_time if hasattr(health_monitor, 'start_time') else 0
        return {
            "status": "alive", 
            "timestamp": datetime.now(timezone.utc).isoformat() + 'Z',
            "uptime_seconds": uptime
        }
    except Exception:
        # Even if monitoring fails, liveness should succeed if we can respond
        return {
            "status": "alive",
            "timestamp": datetime.now(timezone.utc).isoformat() + 'Z'
        }


# API documentation customization
def custom_openapi():
    """Generate custom OpenAPI schema."""
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags
    )
    
    # Add security schemes for authentication
    openapi_schema["components"]["securitySchemes"] = {
        "AgentJWT": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT token for agent authentication (format: Bearer <jwt-token>)"
        },
        "AgentAuth": {
            "type": "http",
            "scheme": "bearer", 
            "description": "Legacy agent ID authentication (format: Bearer <agent-uuid>)"
        }
    }
    
    # Add security requirement to all endpoints
    for path in openapi_schema["paths"]:
        for method in openapi_schema["paths"][path]:
            if method != "get" or path not in ["/health", "/health/ready", "/health/live", "/metrics"]:
                openapi_schema["paths"][path][method]["security"] = [
                    {"AgentJWT": []}, {"AgentAuth": []}
                ]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


# Root endpoint
@app.get("/", include_in_schema=False)
async def root():
    """Root endpoint with basic service information."""
    return {
        "service": "Ordinaut",
        "version": VERSION,
        "environment": ENVIRONMENT,
        "status": "running",
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "health_url": "/health"
    }


# Custom documentation endpoint for better branding
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    """Custom Swagger UI with enhanced styling."""
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} - Interactive API Documentation",
        swagger_ui_parameters={
            "deepLinking": True,
            "displayRequestDuration": True,
            "docExpansion": "none",
            "operationsSorter": "alpha",
            "filter": True,
            "tagsSorter": "alpha"
        }
    )


if __name__ == "__main__":
    # For local development
    import uvicorn
    
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8080,
        reload=DEBUG,
        log_level="info"
    )
