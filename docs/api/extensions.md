# Extensions API Reference

The Extensions API provides endpoints for managing and interacting with Ordinaut extensions. This includes extension discovery, health monitoring, and access to extension-specific functionality.

## Core Extension Endpoints

### Extension Status

Get information about all discovered extensions.

**Endpoint**: `GET /ext/status`  
**Authentication**: None required  
**Scopes**: None

**Response**:
```json
{
  "extensions": {
    "observability": {
      "state": "loaded",
      "info": {
        "id": "observability", 
        "name": "Observability",
        "version": "0.1.0",
        "description": "Prometheus metrics and monitoring"
      },
      "capabilities": ["ROUTES"],
      "loaded_ms": 45,
      "metrics": {
        "requests_total": 150.0,
        "errors_total": 2.0,
        "latency_ms_sum": 1250.5
      }
    }
  },
  "discovery_sources": ["builtin", "env_dir"],
  "total_extensions": 4,
  "loaded_extensions": 3,
  "failed_extensions": 0
}
```

**Example**:
```bash
curl http://localhost:8080/ext/status
```

## Built-in Extensions

### Observability Extension

Provides Prometheus-compatible metrics for system monitoring.

#### Get Metrics
**Endpoint**: `GET /ext/observability/metrics`  
**Authentication**: None required  
**Content-Type**: `text/plain; version=0.0.4`

Returns Prometheus-format metrics including:
- HTTP request/response metrics
- Task execution statistics
- Extension performance metrics  
- System resource usage

**Example**:
```bash
curl http://localhost:8080/ext/observability/metrics
```

**Sample Response**:
```
# HELP http_requests_total Total number of HTTP requests
# TYPE http_requests_total counter
http_requests_total{method="GET",endpoint="/health"} 45.0

# HELP task_executions_total Total number of task executions
# TYPE task_executions_total counter
task_executions_total{status="success"} 123.0
task_executions_total{status="failed"} 5.0

# HELP extension_requests_total Extension request counts
# TYPE extension_requests_total counter
extension_requests_total{extension="webui"} 89.0
```

### Web UI Extension

Provides a web-based interface for task management and system monitoring.

#### Get Web Interface
**Endpoint**: `GET /ext/webui/`  
**Authentication**: None required (configurable)  
**Content-Type**: `text/html`

Returns the main web interface HTML page.

**Example**:
```bash
curl http://localhost:8080/ext/webui/
```

#### API Endpoints

**Get Tasks**: `GET /ext/webui/api/tasks`
```json
{
  "tasks": [
    {
      "id": "uuid-1234",
      "title": "Morning Briefing", 
      "status": "active",
      "next_run": "2025-08-26T08:30:00Z"
    }
  ]
}
```

**Create Task**: `POST /ext/webui/api/tasks`
```json
{
  "title": "New Task",
  "schedule_kind": "cron",
  "schedule_expr": "0 9 * * *",
  "payload": {
    "pipeline": []
  }
}
```

### MCP HTTP Extension

Model Context Protocol over HTTP for AI assistant integration.

#### MCP Metadata
**Endpoint**: `GET /ext/mcp_http/meta`  
**Authentication**: None required

```json
{
  "server": "ordinaut-mcp-http",
  "version": "0.2.0", 
  "capabilities": ["handshake", "list_tools", "invoke", "schema", "sse"]
}
```

#### MCP Handshake
**Endpoint**: `POST /ext/mcp_http/handshake`  
**Content-Type**: `application/json`

**Request**:
```json
{
  "client": {
    "name": "ChatGPT",
    "version": "1.0"
  }
}
```

**Response**:
```json
{
  "server": {
    "name": "ordinaut-mcp-http",
    "version": "0.2.0"
  },
  "session_id": "sess-uuid-5678"
}
```

#### List Available Tools
**Endpoint**: `GET /ext/mcp_http/tools`

```json
{
  "tools": [
    {
      "name": "create_task",
      "description": "Create a new scheduled task",
      "parameters": {
        "type": "object", 
        "properties": {
          "title": {"type": "string"},
          "schedule": {"type": "string"}
        }
      }
    }
  ]
}
```

#### Invoke Tool
**Endpoint**: `POST /ext/mcp_http/invoke`

**Request**:
```json
{
  "tool": "create_task",
  "parameters": {
    "title": "Daily Report",
    "schedule": "0 18 * * *"
  }
}
```

**Response**:
```json
{
  "success": true,
  "result": {
    "task_id": "uuid-9876",
    "message": "Task created successfully"
  }
}
```

### Events Demo Extension

Demonstrates the Redis Streams event system.

#### Publish Event
**Endpoint**: `POST /ext/events_demo/publish/{stream}`  
**Content-Type**: `application/json`

**Example**:
```bash
curl -X POST http://localhost:8080/ext/events_demo/publish/test \\
  -H "Content-Type: application/json" \\
  -d '{"message": "Hello Events", "timestamp": "2025-08-26T10:00:00Z"}'
```

**Response**:
```json
{
  "success": true,
  "stream": "test",
  "event_id": "1692873600000-0",
  "message": "Event published successfully"
}
```

#### Subscribe to Events (Server-Sent Events)
**Endpoint**: `GET /ext/events_demo/subscribe/{stream}`  
**Content-Type**: `text/event-stream`

Establishes an SSE connection to receive real-time events.

**Example**:
```bash
curl -N http://localhost:8080/ext/events_demo/subscribe/test
```

**Response Stream**:
```
data: {"stream": "test", "id": "1692873600000-0", "data": {"message": "Hello Events"}}

data: {"stream": "test", "id": "1692873600001-0", "data": {"message": "Another event"}}
```

## Extension Development API

### Extension Registration

Extensions are automatically discovered and registered. No manual registration API is required.

**Discovery Sources**:
1. Built-in: `ordinaut/extensions/` directory
2. Environment: `ORDINAUT_EXT_PATHS` environment variable  
3. Entry points: Python `ordinaut.plugins` entry point group

### Extension Capabilities

Extensions can request the following capabilities:

| Capability | Description | API Access |
|------------|-------------|------------|
| `ROUTES` | HTTP endpoint creation | FastAPI router mounting |
| `TOOLS` | Tool registry access | `tool_registry.register_tool()` |
| `EVENTS_PUB` | Event publishing | `events.publish()` |
| `EVENTS_SUB` | Event subscription | `events.subscribe()` |
| `BACKGROUND_TASKS` | Long-running processes | `background.start_task()` |
| `STATIC` | Static file serving | Automatic static file routing |

### Context Objects

Extensions receive context objects based on granted capabilities:

#### Tool Registry Context
```python
# Available when TOOLS capability granted
tool_registry.register_tool(name: str, func: Callable, schema: dict)
tool_registry.list_tools() -> List[ToolInfo]
tool_registry.get_tool(name: str) -> ToolInfo
```

#### Events Context  
```python
# Available when EVENTS_PUB or EVENTS_SUB granted
await events.publish(stream: str, data: dict) -> str
await events.subscribe(pattern: str, handler: Callable) -> None
await events.unsubscribe(pattern: str) -> None
```

#### Background Tasks Context
```python
# Available when BACKGROUND_TASKS capability granted  
await background.start_task(name: str, coro: Coroutine) -> None
await background.stop_task(name: str) -> None
background.list_tasks() -> List[TaskInfo]
```

## Authentication & Authorization

### Scope-Based Access Control

Extensions can be protected with scope-based authorization:

**Configuration**:
```bash
export ORDINAUT_REQUIRE_SCOPES=true
```

**Request Headers**:
```bash
curl -H "X-Scopes: ext:my_extension:routes" \\
     http://localhost:8080/ext/my_extension/protected
```

**Required Scope Pattern**: `ext:{extension_id}:routes`

### JWT Token Authentication

When JWT authentication is enabled, extensions inherit the same authentication requirements as the core API.

**Request Headers**:
```bash
curl -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..." \\
     http://localhost:8080/ext/my_extension/secure
```

## Error Responses

All extension endpoints follow consistent error response formats:

### 400 Bad Request
```json
{
  "error": "bad_request",
  "message": "Invalid request parameters",
  "details": {
    "field": "schedule_expr", 
    "issue": "Invalid cron expression"
  }
}
```

### 401 Unauthorized
```json
{
  "error": "unauthorized",
  "message": "Authentication required",
  "details": {
    "required_scopes": ["ext:my_extension:routes"]
  }
}
```

### 403 Forbidden  
```json
{
  "error": "forbidden",
  "message": "Insufficient permissions",
  "details": {
    "required_capability": "TOOLS",
    "granted_capabilities": ["ROUTES"]
  }
}
```

### 404 Not Found
```json
{
  "error": "not_found",
  "message": "Extension not found",
  "details": {
    "extension_id": "nonexistent_extension"
  }
}
```

### 500 Internal Server Error
```json
{
  "error": "internal_error",
  "message": "Extension execution failed",
  "details": {
    "extension_id": "my_extension",
    "error_type": "ImportError",
    "traceback": "..."
  }
}
```

## Rate Limiting

Extension endpoints respect the same rate limiting configuration as the core API:

**Headers**:
- `X-RateLimit-Limit`: Request limit per window
- `X-RateLimit-Remaining`: Remaining requests in current window
- `X-RateLimit-Reset`: Window reset timestamp

**429 Too Many Requests**:
```json
{
  "error": "rate_limit_exceeded",
  "message": "Rate limit exceeded", 
  "details": {
    "limit": 100,
    "window": "60s",
    "reset_at": "2025-08-26T10:01:00Z"
  }
}
```

## Health Checks

Extensions can implement health check endpoints for monitoring:

**Convention**: `GET /ext/{extension_id}/health`

**Standard Response**:
```json
{
  "status": "healthy",
  "timestamp": "2025-08-26T10:00:00Z", 
  "version": "1.0.0",
  "checks": {
    "database": "healthy",
    "external_api": "healthy", 
    "background_tasks": "healthy"
  }
}
```

## WebSocket Support

Extensions can implement WebSocket endpoints for real-time communication:

**Endpoint Pattern**: `WS /ext/{extension_id}/ws/{path}`

**Example Implementation**:
```python
from fastapi import WebSocket

@router.websocket("/ws/events")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # Handle WebSocket communication
            data = await websocket.receive_json()
            response = await process_websocket_data(data)
            await websocket.send_json(response)
    except WebSocketDisconnect:
        # Handle client disconnect
        pass
```

## Extension Metrics

All extensions automatically get basic metrics collection:

**Metrics Available**:
- `extension_requests_total{extension, endpoint, method, status}`
- `extension_request_duration_seconds{extension, endpoint, method}`
- `extension_errors_total{extension, endpoint, error_type}`
- `extension_active_connections{extension, endpoint}`

**Access via Observability Extension**:
```bash
curl http://localhost:8080/ext/observability/metrics | grep extension
```

This API reference provides complete documentation for interacting with Ordinaut's extension system, enabling developers to build powerful extensions and integrate external systems effectively.