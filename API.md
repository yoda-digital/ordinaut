# Ordinaut - REST API Reference

Complete REST API documentation for Ordinaut with request/response examples, authentication patterns, and error handling.

## Authentication

All API endpoints (except health checks) require **Agent-based authentication** using Bearer tokens:

```bash
curl -H "Authorization: Bearer 00000000-0000-0000-0000-000000000001" \
     https://api.orchestrator.example.com/v1/tasks
```

**Agent ID Format**: Standard UUID format identifying the calling agent  
**Default System Agent**: `00000000-0000-0000-0000-000000000001` (admin scopes)

## Base URL

**Development**: `http://localhost:8080`  
**Production**: `https://api.orchestrator.example.com/v1`

## Tasks Management

### POST /tasks

Create a new scheduled task with pipeline configuration.

**Request Body:**
```json
{
  "title": "Morning Weather Alert",
  "description": "Daily weather summary at 8 AM",
  "schedule_kind": "cron",
  "schedule_expr": "0 8 * * *",
  "timezone": "Europe/Chisinau",
  "payload": {
    "pipeline": [
      {
        "id": "get_weather",
        "uses": "weather-api.get_forecast",
        "with": {"location": "Chisinau", "days": 1},
        "save_as": "weather"
      },
      {
        "id": "send_alert",
        "uses": "telegram.send_message", 
        "with": {
          "chat_id": 12345,
          "message": "Today's weather: ${steps.weather.summary}"
        }
      }
    ]
  },
  "priority": 5,
  "max_retries": 3,
  "created_by": "00000000-0000-0000-0000-000000000001"
}
```

**Response (201 Created):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "Morning Weather Alert",
  "description": "Daily weather summary at 8 AM",
  "created_by": "00000000-0000-0000-0000-000000000001",
  "schedule_kind": "cron",
  "schedule_expr": "0 8 * * *",
  "timezone": "Europe/Chisinau",
  "payload": { /* full pipeline */ },
  "status": "active",
  "priority": 5,
  "max_retries": 3,
  "created_at": "2025-01-10T15:30:00Z"
}
```

**Schedule Types:**

| Type | Description | Example |
|------|-------------|---------|
| `cron` | Standard cron expressions | `"0 8 * * 1-5"` (weekdays 8 AM) |
| `rrule` | RFC-5545 recurrence rules | `"FREQ=WEEKLY;BYDAY=MO;BYHOUR=9"` |
| `once` | Single execution at timestamp | `"2025-01-11T14:30:00+02:00"` |
| `event` | Triggered by external events | `"user.email.received"` |

**RRULE Examples:**
```json
{
  "schedule_kind": "rrule",
  "schedule_expr": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=30",
  "timezone": "Europe/Chisinau"
}
```

### GET /tasks

List tasks with optional filtering and pagination.

**Query Parameters:**
- `status` - Filter by status: `active`, `paused`, `canceled`
- `created_by` - Filter by agent UUID  
- `schedule_kind` - Filter by schedule type
- `limit` - Max results (default: 50, max: 200)
- `offset` - Pagination offset (default: 0)

**Example Request:**
```bash
curl -H "Authorization: Bearer agent-uuid" \
     "http://localhost:8080/tasks?status=active&limit=10"
```

**Response (200 OK):**
```json
{
  "tasks": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "title": "Morning Weather Alert",
      "status": "active",
      "schedule_kind": "cron",
      "schedule_expr": "0 8 * * *",
      "timezone": "Europe/Chisinau",
      "priority": 5,
      "created_at": "2025-01-10T15:30:00Z",
      "next_run": "2025-01-11T08:00:00+02:00"
    }
  ],
  "total": 1,
  "limit": 10,
  "offset": 0
}
```

### GET /tasks/{id}

Get detailed information about a specific task.

**Response (200 OK):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "Morning Weather Alert",
  "description": "Daily weather summary at 8 AM",
  "created_by": "00000000-0000-0000-0000-000000000001",
  "schedule_kind": "cron",
  "schedule_expr": "0 8 * * *", 
  "timezone": "Europe/Chisinau",
  "payload": {
    "pipeline": [
      {
        "id": "get_weather",
        "uses": "weather-api.get_forecast",
        "with": {"location": "Chisinau", "days": 1},
        "save_as": "weather"
      },
      {
        "id": "send_alert",
        "uses": "telegram.send_message",
        "with": {
          "chat_id": 12345,
          "message": "Today's weather: ${steps.weather.summary}"
        }
      }
    ]
  },
  "status": "active",
  "priority": 5,
  "dedupe_key": null,
  "dedupe_window_seconds": 0,
  "max_retries": 3,
  "backoff_strategy": "exponential_jitter",
  "concurrency_key": null,
  "created_at": "2025-01-10T15:30:00Z",
  "next_run": "2025-01-11T08:00:00+02:00"
}
```

### POST /tasks/{id}/run_now

Trigger immediate execution of a task (bypasses schedule).

**Response (200 OK):**
```json
{
  "success": true,
  "message": "Task queued for immediate execution",
  "run_id": "7f3e4d2c-1a9b-4c8d-9e6f-2b5a8c7d4e9f",
  "enqueued_at": "2025-01-10T16:45:00Z"
}
```

### POST /tasks/{id}/snooze

Delay the next scheduled execution by specified seconds.

**Request Body:**
```json
{
  "seconds": 3600,
  "reason": "User is unavailable"
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "message": "Task snoozed for 1 hour",
  "previous_next_run": "2025-01-11T08:00:00+02:00",
  "new_next_run": "2025-01-11T09:00:00+02:00"
}
```

### POST /tasks/{id}/pause

Pause task execution (stops all future scheduled runs).

**Response (200 OK):**
```json
{
  "success": true,
  "message": "Task paused successfully",
  "status": "paused",
  "paused_at": "2025-01-10T16:45:00Z"
}
```

### POST /tasks/{id}/resume

Resume a paused task.

**Response (200 OK):**
```json
{
  "success": true, 
  "message": "Task resumed successfully",
  "status": "active",
  "resumed_at": "2025-01-10T16:50:00Z",
  "next_run": "2025-01-11T08:00:00+02:00"
}
```

### POST /tasks/{id}/cancel

Permanently cancel a task (cannot be resumed).

**Response (200 OK):**
```json
{
  "success": true,
  "message": "Task canceled permanently", 
  "status": "canceled",
  "canceled_at": "2025-01-10T16:55:00Z"
}
```

## Execution Monitoring

### GET /runs

List task execution history with filtering and pagination.

**Query Parameters:**
- `task_id` - Filter by specific task UUID
- `success` - Filter by execution result: `true`, `false`
- `agent_id` - Filter by executing agent
- `limit` - Max results (default: 50, max: 200)
- `offset` - Pagination offset

**Example Request:**
```bash
curl -H "Authorization: Bearer agent-uuid" \
     "http://localhost:8080/runs?task_id=550e8400-e29b-41d4-a716-446655440000&limit=5"
```

**Response (200 OK):**
```json
{
  "runs": [
    {
      "id": "7f3e4d2c-1a9b-4c8d-9e6f-2b5a8c7d4e9f",
      "task_id": "550e8400-e29b-41d4-a716-446655440000",
      "started_at": "2025-01-11T08:00:00+02:00",
      "finished_at": "2025-01-11T08:00:02+02:00", 
      "success": true,
      "attempt": 1,
      "duration_ms": 2150,
      "created_at": "2025-01-11T08:00:00+02:00"
    },
    {
      "id": "8a4f5e3d-2b0c-5d9e-0f7a-3c6b9d8e5f0a",
      "task_id": "550e8400-e29b-41d4-a716-446655440000", 
      "started_at": "2025-01-10T08:00:00+02:00",
      "finished_at": "2025-01-10T08:00:01+02:00",
      "success": true,
      "attempt": 1,
      "duration_ms": 1850,
      "created_at": "2025-01-10T08:00:00+02:00"
    }
  ],
  "total": 2,
  "limit": 5,
  "offset": 0
}
```

### GET /runs/{id}

Get detailed execution information including pipeline step results.

**Response (200 OK):**
```json
{
  "id": "7f3e4d2c-1a9b-4c8d-9e6f-2b5a8c7d4e9f",
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "task_title": "Morning Weather Alert",
  "lease_owner": "worker-1",
  "leased_until": "2025-01-11T08:01:00+02:00",
  "started_at": "2025-01-11T08:00:00+02:00",
  "finished_at": "2025-01-11T08:00:02+02:00",
  "success": true,
  "error": null,
  "attempt": 1,
  "output": {
    "steps": {
      "weather": {
        "temperature": 15,
        "summary": "Partly cloudy, 15°C",
        "humidity": 65
      }
    },
    "final_status": "completed"
  },
  "duration_ms": 2150,
  "created_at": "2025-01-11T08:00:00+02:00"
}
```

**Failed Execution Example:**
```json
{
  "id": "9b5g6f4e-3c1d-6e0f-1a8b-4d7c0e9f6a1b",
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "started_at": "2025-01-11T08:00:00+02:00",
  "finished_at": "2025-01-11T08:00:05+02:00",
  "success": false,
  "error": "Tool 'weather-api.get_forecast' timeout after 30 seconds",
  "attempt": 2,
  "output": {
    "failed_step": "get_weather",
    "partial_results": {}
  },
  "duration_ms": 30500
}
```

## Event Publishing

### POST /events

Publish external events to trigger event-based tasks.

**Request Body:**
```json
{
  "event_type": "user.email.received",
  "data": {
    "from": "colleague@example.com",
    "subject": "Project Update Required",
    "priority": "high",
    "received_at": "2025-01-11T10:30:00Z"
  },
  "source": "email-monitor-agent"
}
```

**Response (202 Accepted):**
```json
{
  "success": true,
  "message": "Event published successfully",
  "event_id": "evt_abc123def456",
  "published_at": "2025-01-11T10:30:01Z",
  "matched_tasks": 2,
  "enqueued_runs": 2
}
```

**Event Types:**
- `user.email.received` - New email notifications
- `calendar.event.starting` - Calendar event reminders  
- `system.maintenance.window` - Scheduled maintenance
- `external.webhook.*` - Generic webhook events
- Custom event types as defined by your agents

## Agent Management

### POST /agents

Create a new agent (admin scope required).

**Request Body:**
```json
{
  "name": "weather-bot",
  "scopes": ["weather.read", "notify.telegram"],
  "webhook_url": "https://bot.example.com/webhooks/orchestrator"
}
```

**Response (201 Created):**
```json
{
  "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "name": "weather-bot",
  "scopes": ["weather.read", "notify.telegram"],
  "webhook_url": "https://bot.example.com/webhooks/orchestrator",
  "created_at": "2025-01-10T15:30:00Z"
}
```

## System Health

### GET /health

Comprehensive system health check with detailed component status.

**Response (200 OK):**
```json
{
  "status": "healthy",
  "timestamp": "2025-01-11T10:45:00Z",
  "uptime_seconds": 86400,
  "version": "1.0.0",
  "checks": [
    {
      "name": "database",
      "status": "healthy",
      "message": "PostgreSQL connection pool healthy", 
      "duration_ms": 12,
      "details": {
        "pool_size": 20,
        "active_connections": 3,
        "idle_connections": 17
      }
    },
    {
      "name": "redis",
      "status": "healthy",
      "message": "Redis connection active",
      "duration_ms": 5,
      "details": {
        "memory_usage": "45MB",
        "connected_clients": 8
      }
    },
    {
      "name": "scheduler",
      "status": "healthy", 
      "message": "APScheduler running normally",
      "duration_ms": 8,
      "details": {
        "active_jobs": 15,
        "next_run": "2025-01-11T11:00:00Z"
      }
    },
    {
      "name": "workers",
      "status": "healthy",
      "message": "2 workers active",
      "duration_ms": 15,
      "details": {
        "active_workers": 2,
        "queue_depth": 0,
        "processing_rate": "12.5 tasks/min"
      }
    }
  ]
}
```

### GET /health/ready

Kubernetes readiness probe - returns 200 if service can accept requests.

**Response (200 OK):**
```json
{
  "status": "ready",
  "database": true,
  "redis": true,
  "timestamp": "2025-01-11T10:45:00Z"
}
```

### GET /health/live

Kubernetes liveness probe - returns 200 if service is alive.

**Response (200 OK):**
```json
{
  "status": "alive",
  "timestamp": "2025-01-11T10:45:00Z",
  "uptime_seconds": 86400
}
```

## Error Handling

### Standard Error Response Format

All errors return consistent JSON format with debugging information:

```json
{
  "error": "ValidationError",
  "message": "Invalid schedule expression",
  "details": {
    "field": "schedule_expr",
    "value": "invalid cron",
    "expected": "Valid cron expression (e.g., '0 9 * * 1-5')"
  },
  "request_id": "req_abc123def456",
  "timestamp": "2025-01-11T10:45:00Z"
}
```

### HTTP Status Codes

| Code | Description | Common Causes |
|------|-------------|---------------|
| `400` | Bad Request | Invalid JSON, missing required fields |
| `401` | Unauthorized | Missing or invalid Agent ID in Authorization header |
| `403` | Forbidden | Agent lacks required scopes for operation |
| `404` | Not Found | Task/run/agent ID does not exist |
| `409` | Conflict | Duplicate dedupe_key within window |
| `422` | Unprocessable Entity | Valid JSON but semantic validation errors |
| `429` | Too Many Requests | Rate limit exceeded |
| `500` | Internal Server Error | Database connection, system failures |

### Common Validation Errors

**Invalid Schedule Expression:**
```json
{
  "error": "ValidationError",
  "message": "Invalid cron expression format",
  "details": {
    "field": "schedule_expr", 
    "value": "invalid",
    "expected": "5-field cron: minute hour day month weekday"
  }
}
```

**Missing Pipeline Steps:**
```json
{
  "error": "ValidationError",
  "message": "Pipeline cannot be empty",
  "details": {
    "field": "payload.pipeline",
    "expected": "Array with at least one step"
  }
}
```

**Agent Not Found:**
```json
{
  "error": "NotFoundError",
  "message": "Agent f47ac10b-58cc-4372-a567-0e02b2c3d479 not found",
  "details": {
    "field": "created_by",
    "suggestion": "Verify agent ID exists via GET /agents"
  }
}
```

## Rate Limits

Default rate limits per agent:

| Endpoint Pattern | Limit | Window |
|------------------|-------|---------|
| `POST /tasks` | 100 requests | 1 hour |
| `POST /tasks/*/run_now` | 50 requests | 1 hour |
| `POST /events` | 1000 requests | 1 hour |
| `GET *` | 1000 requests | 5 minutes |

Rate limit headers included in all responses:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 87
X-RateLimit-Reset: 1641825600
```

## Pipeline Template Variables

### Built-in Variables

| Variable | Description | Example Value |
|----------|-------------|---------------|
| `${now}` | Current timestamp (ISO) | `"2025-01-11T10:45:00Z"` |
| `${now+1h}` | Time arithmetic | `"2025-01-11T11:45:00Z"` |
| `${params.key}` | Task parameters | User-defined values |
| `${steps.step_name.field}` | Previous step outputs | Results from `save_as` |

### Step Output Access

```json
{
  "pipeline": [
    {
      "id": "fetch_weather",
      "uses": "weather-api.forecast",
      "with": {"city": "Chisinau"},
      "save_as": "weather"
    },
    {
      "id": "send_notification", 
      "uses": "telegram.send_message",
      "with": {
        "chat_id": 12345,
        "message": "Weather: ${steps.weather.summary} (${steps.weather.temperature}°C)"
      }
    }
  ]
}
```

### Conditional Logic

Using JMESPath expressions for conditional step execution:

```json
{
  "id": "send_urgent_alert",
  "uses": "slack.send_message", 
  "with": {
    "channel": "#alerts",
    "text": "Urgent weather alert: ${steps.weather.alert_message}"
  },
  "if": "${steps.weather.alert_level == 'severe'}"
}
```

## OpenAPI Specification

**Interactive Documentation**: `http://localhost:8080/docs`  
**ReDoc Documentation**: `http://localhost:8080/redoc`  
**OpenAPI JSON**: `http://localhost:8080/openapi.json`

The API provides complete OpenAPI 3.0 specification with:
- Request/response schemas
- Authentication requirements
- Example values
- Error response formats
- Rate limiting information

---

This API provides the foundation for building sophisticated AI agent orchestration systems with reliable scheduling, execution monitoring, and event-driven workflows.