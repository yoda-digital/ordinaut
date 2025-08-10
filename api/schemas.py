"""
Pydantic schemas for API request/response models.

These schemas provide input validation, serialization, and automatic OpenAPI
documentation generation for the Ordinaut API.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any, Union
from uuid import UUID
from pydantic import BaseModel, Field, validator
from enum import Enum


class ScheduleKind(str, Enum):
    """Schedule types supported by the orchestrator."""
    cron = "cron"
    rrule = "rrule"
    once = "once"
    event = "event"
    condition = "condition"


class TaskStatus(str, Enum):
    """Task status values."""
    active = "active"
    paused = "paused"
    canceled = "canceled"


class BackoffStrategy(str, Enum):
    """Backoff strategies for retry logic."""
    exponential_jitter = "exponential_jitter"
    linear = "linear"
    fixed = "fixed"


# Request Schemas

class TaskCreateRequest(BaseModel):
    """
    Schema for creating new tasks.
    Matches the TaskIn specification from plan.md section 8.
    """
    title: str = Field(..., min_length=1, max_length=200, description="Human-readable task title")
    description: str = Field(..., min_length=1, max_length=2000, description="Detailed task description")
    schedule_kind: ScheduleKind = Field(..., description="Type of schedule: cron, rrule, once, event, or condition")
    schedule_expr: Optional[str] = Field(None, description="Schedule expression (cron string, RRULE, ISO timestamp, or event topic)")
    timezone: str = Field(default="Europe/Chisinau", pattern=r'^[A-Za-z]+/[A-Za-z_]+$', description="IANA timezone name")
    payload: Dict[str, Any] = Field(..., description="Declarative pipeline definition", example={"pipeline": []})
    priority: int = Field(default=5, ge=1, le=9, description="Task priority (1=highest, 9=lowest)")
    dedupe_key: Optional[str] = Field(None, max_length=100, description="Deduplication key to prevent duplicate runs")
    dedupe_window_seconds: int = Field(default=0, ge=0, description="Deduplication window in seconds")
    max_retries: int = Field(default=3, ge=0, le=10, description="Maximum number of retry attempts")
    backoff_strategy: BackoffStrategy = Field(default=BackoffStrategy.exponential_jitter, description="Retry backoff strategy")
    concurrency_key: Optional[str] = Field(None, max_length=100, description="Concurrency control key")
    created_by: UUID = Field(..., description="UUID of the creating agent")

    @validator('schedule_expr')
    def validate_schedule_expr(cls, v, values):
        """Validate that schedule_expr is provided when required."""
        kind = values.get('schedule_kind')
        if kind in ['cron', 'rrule', 'once'] and not v:
            raise ValueError(f'{kind} schedule requires schedule_expr')
        return v

    @validator('payload')
    def validate_payload_structure(cls, v):
        """Validate that payload contains required pipeline structure."""
        if not isinstance(v, dict):
            raise ValueError('payload must be a dict')
        if 'pipeline' not in v:
            raise ValueError('payload must contain a pipeline array')
        if not isinstance(v['pipeline'], list):
            raise ValueError('payload.pipeline must be an array')
        return v

    class Config:
        schema_extra = {
            "example": {
                "title": "Morning Briefing",
                "description": "Daily morning briefing with calendar, weather, and email summary",
                "schedule_kind": "rrule",
                "schedule_expr": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=30",
                "timezone": "Europe/Chisinau",
                "payload": {
                    "pipeline": [
                        {"id": "calendar", "uses": "google-calendar-mcp.list_events", "with": {"start": "${now}", "end": "${now+24h}"}, "save_as": "events"},
                        {"id": "weather", "uses": "weather-mcp.forecast", "with": {"city": "Chisinau"}, "save_as": "weather"},
                        {"id": "brief", "uses": "llm.plan", "with": {"instruction": "Create morning briefing", "calendar": "${steps.events}", "weather": "${steps.weather}"}, "save_as": "summary"},
                        {"id": "notify", "uses": "telegram-mcp.send_message", "with": {"chat_id": 12345, "text": "${steps.summary.text}"}}
                    ]
                },
                "priority": 4,
                "created_by": "550e8400-e29b-41d4-a716-446655440000"
            }
        }


class TaskUpdateRequest(BaseModel):
    """Schema for updating existing tasks."""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, min_length=1, max_length=2000)
    schedule_kind: Optional[ScheduleKind] = None
    schedule_expr: Optional[str] = None
    timezone: Optional[str] = Field(None, pattern=r'^[A-Za-z]+/[A-Za-z_]+$')
    payload: Optional[Dict[str, Any]] = None
    priority: Optional[int] = Field(None, ge=1, le=9)
    status: Optional[TaskStatus] = None
    max_retries: Optional[int] = Field(None, ge=0, le=10)
    backoff_strategy: Optional[BackoffStrategy] = None
    concurrency_key: Optional[str] = Field(None, max_length=100)


class SnoozeRequest(BaseModel):
    """Schema for snoozing task execution."""
    delay_seconds: int = Field(..., ge=1, le=86400 * 7, description="Delay in seconds (max 1 week)")
    reason: Optional[str] = Field(None, max_length=200, description="Optional reason for snoozing")


class EventPublishRequest(BaseModel):
    """Schema for publishing external events."""
    topic: str = Field(..., min_length=1, max_length=100, description="Event topic/type")
    payload: Dict[str, Any] = Field(..., description="Event payload data")
    source_agent_id: UUID = Field(..., description="UUID of the publishing agent")
    
    class Config:
        schema_extra = {
            "example": {
                "topic": "email.received",
                "payload": {
                    "from": "user@example.com",
                    "subject": "Important Update",
                    "priority": "high"
                },
                "source_agent_id": "550e8400-e29b-41d4-a716-446655440000"
            }
        }


# Response Schemas

class TaskResponse(BaseModel):
    """Schema for task response data."""
    id: UUID
    title: str
    description: str
    created_by: UUID
    schedule_kind: ScheduleKind
    schedule_expr: Optional[str]
    timezone: str
    payload: Dict[str, Any]
    status: TaskStatus
    priority: int
    dedupe_key: Optional[str]
    dedupe_window_seconds: int
    max_retries: int
    backoff_strategy: BackoffStrategy
    concurrency_key: Optional[str]
    created_at: datetime

    class Config:
        orm_mode = True
        schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "title": "Morning Briefing",
                "description": "Daily morning briefing with calendar, weather, and email summary",
                "created_by": "660e8400-e29b-41d4-a716-446655440001",
                "schedule_kind": "rrule",
                "schedule_expr": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=30",
                "timezone": "Europe/Chisinau",
                "payload": {"pipeline": []},
                "status": "active",
                "priority": 4,
                "dedupe_key": "morning-briefing",
                "dedupe_window_seconds": 1800,
                "max_retries": 3,
                "backoff_strategy": "exponential_jitter",
                "concurrency_key": "briefing",
                "created_at": "2025-01-10T10:00:00Z"
            }
        }


class TaskRunResponse(BaseModel):
    """Schema for task run response data."""
    id: UUID
    task_id: UUID
    lease_owner: Optional[str]
    leased_until: Optional[datetime]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    success: Optional[bool]
    error: Optional[str]
    attempt: int
    output: Optional[Dict[str, Any]]
    created_at: datetime

    class Config:
        orm_mode = True


class AgentResponse(BaseModel):
    """Schema for agent response data."""
    id: UUID
    name: str
    scopes: List[str]
    webhook_url: Optional[str]
    created_at: datetime

    class Config:
        orm_mode = True


class DueWorkResponse(BaseModel):
    """Schema for due work response data."""
    id: int
    task_id: UUID
    run_at: datetime
    locked_until: Optional[datetime]
    locked_by: Optional[str]
    created_at: datetime

    class Config:
        orm_mode = True


# Utility Response Schemas

class TaskListResponse(BaseModel):
    """Paginated list of tasks."""
    items: List[TaskResponse]
    total: int
    limit: int
    offset: int
    has_more: bool


class TaskRunListResponse(BaseModel):
    """Paginated list of task runs."""
    items: List[TaskRunResponse]
    total: int
    limit: int
    offset: int
    has_more: bool


class OperationResponse(BaseModel):
    """Standard response for operations that don't return data."""
    success: bool
    message: str
    details: Optional[Dict[str, Any]] = None

    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "message": "Task paused successfully",
                "details": {"task_id": "550e8400-e29b-41d4-a716-446655440000"}
            }
        }


class ErrorResponse(BaseModel):
    """Standard error response format."""
    error: str
    message: str
    details: Optional[Dict[str, Any]] = None
    request_id: Optional[str] = None
    timestamp: datetime

    class Config:
        schema_extra = {
            "example": {
                "error": "ValidationError",
                "message": "Invalid schedule expression for rrule schedule",
                "details": {"field": "schedule_expr", "value": "invalid-rrule"},
                "request_id": "req-123456789",
                "timestamp": "2025-01-10T10:00:00Z"
            }
        }


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    timestamp: datetime
    version: str
    database: bool
    redis: bool
    
    class Config:
        schema_extra = {
            "example": {
                "status": "healthy",
                "timestamp": "2025-01-10T10:00:00Z",
                "version": "1.0.0",
                "database": True,
                "redis": True
            }
        }