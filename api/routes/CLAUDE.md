# Personal Agent Orchestrator API Routes

## Purpose and Architecture

The `/api/routes/` directory contains the **FastAPI route implementations** for the Personal Agent Orchestrator REST API. This directory organizes API endpoints by functional domain, providing a clean separation of concerns and maintainable code structure.

### Core Design Principles

**RESTful Resource Organization:**
- Each route file represents a distinct resource domain
- Standard HTTP verbs (GET, POST, PUT, DELETE) for predictable operations
- Consistent URL patterns with resource hierarchies
- Proper HTTP status codes and error responses

**Security and Authentication:**
- All endpoints require authentication via dependency injection
- Scope-based authorization for granular access control
- Comprehensive audit logging for all state-changing operations
- Input validation at the API boundary with detailed error messages

**Reliability and Error Handling:**
- Database transactions with proper rollback on errors
- Structured error responses with actionable debugging information
- Consistent response formatting across all endpoints
- Graceful handling of concurrent access patterns

## Route File Organization

```
api/routes/
├── __init__.py          # Route module initialization and exports
├── tasks.py             # Task CRUD operations and lifecycle management
├── runs.py              # Task execution history and performance monitoring
├── events.py            # External event publishing and stream management
└── agents.py            # Agent management and administrative operations
```

---

## tasks.py - Task Management Routes

**Purpose:** Complete CRUD operations for scheduled tasks including creation, status management, and immediate execution controls.

### Key Endpoints

#### Task Creation and Management
```python
POST   /tasks              # Create new scheduled task
GET    /tasks              # List tasks with filtering and pagination  
GET    /tasks/{task_id}    # Get specific task details
PUT    /tasks/{task_id}    # Update existing task configuration
```

#### Task Execution Control
```python
POST   /tasks/{task_id}/run_now    # Trigger immediate task execution
POST   /tasks/{task_id}/snooze     # Delay next execution by specified time
POST   /tasks/{task_id}/pause      # Pause task scheduling
POST   /tasks/{task_id}/resume     # Resume paused task scheduling
POST   /tasks/{task_id}/cancel     # Permanently cancel task
```

### Implementation Patterns

**Authentication and Authorization:**
```python
@router.post("/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    task_request: TaskCreateRequest,
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent)
) -> TaskResponse:
```

**Database Transaction Management:**
```python
try:
    db.add(task)
    db.commit()
    db.refresh(task)
    
    # Log the creation
    audit_log = AuditLog(
        actor_agent_id=current_agent.id,
        action="task.created",
        subject_id=task.id,
        details={"title": task.title, "schedule_kind": task.schedule_kind.value}
    )
    db.add(audit_log)
    db.commit()
    
    return TaskResponse.from_orm(task)
    
except IntegrityError as e:
    db.rollback()
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Failed to create task: {str(e)}"
    )
```

**Concurrency-Safe Work Scheduling:**
```python
# Create immediate work item for run_now
due_work = DueWork(
    task_id=task.id,
    run_at=datetime.now(timezone.utc)
)

# Snooze implementation with SQL UPDATE
result = db.execute(
    text("""
        UPDATE due_work 
        SET run_at = run_at + INTERVAL :delay_seconds * INTERVAL '1 second'
        WHERE task_id = :task_id 
          AND run_at > now() 
          AND (locked_until IS NULL OR locked_until < now())
    """),
    {"task_id": task_id, "delay_seconds": snooze_request.delay_seconds}
)
```

### Key Features

- **Complete task lifecycle management** from creation to cancellation
- **Immediate execution triggers** bypassing normal scheduling
- **Flexible snoozing** with reason tracking and audit trails  
- **Status management** with pause/resume capabilities
- **Comprehensive audit logging** for all operations
- **Agent-scoped access control** with proper permission validation

---

## runs.py - Execution History Routes

**Purpose:** Access to task execution history, performance monitoring, and debugging information for failed or slow executions.

### Key Endpoints

#### Run History and Monitoring
```python
GET    /runs                        # List runs with filtering and pagination
GET    /runs/{run_id}               # Get detailed run information
GET    /runs/task/{task_id}/latest  # Get most recent run for specific task
```

#### Performance Analytics
```python
GET    /runs/task/{task_id}/stats   # Task-specific execution statistics
GET    /runs/stats/summary          # System-wide performance metrics
```

### Implementation Patterns

**Flexible Filtering and Pagination:**
```python
@router.get("/", response_model=TaskRunListResponse)
async def list_runs(
    task_id: Optional[UUID] = Query(None, description="Filter by specific task ID"),
    success: Optional[bool] = Query(None, description="Filter by success status"),
    include_errors: bool = Query(False, description="Include error details in response"),
    start_time: Optional[datetime] = Query(None, description="Filter runs after this timestamp"),
    end_time: Optional[datetime] = Query(None, description="Filter runs before this timestamp"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of runs to return"),
    offset: int = Query(0, ge=0, description="Number of runs to skip"),
    # ... dependencies
) -> TaskRunListResponse:
```

**Statistical Analysis:**
```python
# Calculate success rates and performance metrics
total_runs = len(runs)
successful_runs = [r for r in runs if r.success is True]
failed_runs = [r for r in runs if r.success is False]

success_rate = len(successful_runs) / total_runs if total_runs > 0 else 0.0
failure_rate = len(failed_runs) / total_runs if total_runs > 0 else 0.0

# Calculate average execution time (only for completed runs)
completed_runs = [r for r in runs if r.started_at and r.finished_at]
avg_execution_time = 0.0
if completed_runs:
    total_time = sum(
        (r.finished_at - r.started_at).total_seconds() 
        for r in completed_runs
    )
    avg_execution_time = total_time / len(completed_runs)
```

**Privacy-Conscious Error Reporting:**
```python
# Optionally exclude error details for cleaner responses
if not include_errors and run_data.error:
    run_data.error = "[Error details hidden - use include_errors=true]"
```

### Key Features

- **Comprehensive execution history** with filtering by task, status, and time range
- **Performance analytics** including success rates and execution times
- **System-wide monitoring** for operational visibility
- **Privacy controls** for sensitive error information
- **Debugging support** with detailed execution context

---

## events.py - External Event Management Routes

**Purpose:** Publishing external events to trigger event-based tasks through Redis Streams with durable, ordered processing.

### Key Endpoints

#### Event Publishing and Management
```python
POST   /events               # Publish external event to trigger tasks
GET    /events/topics        # List active event topics and listener counts
GET    /events/stream/recent # Get recent events for monitoring
DELETE /events/stream/cleanup # Clean up old events to prevent growth
```

### Implementation Patterns

**Event Publishing with Redis Streams:**
```python
@router.post("/", response_model=OperationResponse, status_code=status.HTTP_202_ACCEPTED)
async def publish_event(
    event_request: EventPublishRequest,
    db: Session = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
    current_agent: Agent = Depends(get_current_agent)
) -> OperationResponse:
    
    # Generate unique event ID and prepare payload
    event_id = str(uuid4())
    timestamp = datetime.now(timezone.utc)
    
    stream_data = {
        "event_id": event_id,
        "topic": event_request.topic,
        "payload": json.dumps(event_request.payload),
        "source_agent_id": str(event_request.source_agent_id),
        "published_at": timestamp.isoformat(),
        "published_by": str(current_agent.id)
    }
    
    # Publish to Redis Stream
    stream_id = redis_client.xadd("events", stream_data)
```

**Event-Triggered Task Discovery:**
```python
# Find and trigger event-based tasks
event_tasks = db.query(Task).filter(
    Task.schedule_kind == "event",
    Task.schedule_expr == event_request.topic,
    Task.status == "active"
).all()

triggered_tasks = []
for task in event_tasks:
    # Create due work item with event context
    due_work = DueWork(
        task_id=task.id,
        run_at=timestamp
    )
    db.add(due_work)
    triggered_tasks.append(str(task.id))
```

**Stream Management and Cleanup:**
```python
# Clean up old events to prevent unbounded growth
cutoff_timestamp = int((datetime.now(timezone.utc).timestamp() - (max_age_hours * 3600)) * 1000)
cutoff_id = f"{cutoff_timestamp}-0"

# Use XTRIM to remove old events  
deleted_count = redis_client.xtrim("events", maxlen=None, approximate=False, minid=cutoff_id)
```

### Key Features

- **Durable event publishing** through Redis Streams with guaranteed ordering
- **Automatic task triggering** for event-based schedules
- **Event topic management** with active listener monitoring
- **Stream cleanup utilities** to prevent unbounded growth
- **Comprehensive audit trails** for all event publishing activities

---

## agents.py - Agent Administration Routes

**Purpose:** Administrative operations for agent management including creation, scope management, and lifecycle control.

### Key Endpoints

#### Agent Management
```python
POST   /agents              # Create new agent with specified scopes
GET    /agents              # List all agents with filtering
GET    /agents/{agent_id}   # Get specific agent details
PUT    /agents/{agent_id}   # Update agent configuration
DELETE /agents/{agent_id}   # Delete agent (admin only)
```

### Implementation Patterns

**Administrative Access Control:**
```python
@router.post("/", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    agent_request: AgentCreateRequest,
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(require_scopes("admin"))  # Admin-only operation
) -> AgentResponse:
```

**Scope-Based Filtering:**
```python
# Apply filters for agent discovery
if name_filter:
    query = query.filter(Agent.name.ilike(f"%{name_filter}%"))
if scope_filter:
    query = query.filter(Agent.scopes.contains([scope_filter]))
```

**Safety Checks for Critical Operations:**
```python
# Prevent deletion of system agent
if agent.name == "system":
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Cannot delete the system agent"
    )

# Prevent self-deletion
if agent.id == current_agent.id:
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Agents cannot delete themselves"
    )
```

### Key Features

- **Complete agent lifecycle management** from creation to deletion
- **Scope-based access control** with granular permission management
- **Administrative safeguards** preventing accidental system damage
- **Comprehensive audit logging** for all administrative actions
- **Advanced filtering** for agent discovery and management

---

## Common Implementation Patterns

### Authentication and Authorization

**Dependency Injection Pattern:**
All routes use FastAPI's dependency injection for consistent authentication:
```python
from ..dependencies import get_db, get_current_agent, require_scopes

# Standard authentication
current_agent: Agent = Depends(get_current_agent)

# Scope-based authorization
current_agent: Agent = Depends(require_scopes("admin"))
```

**Authentication Flow:**
1. Extract bearer token from Authorization header
2. Validate token format and expiration
3. Look up agent in database by token
4. Verify agent status and scopes
5. Inject authenticated agent into route handler

### Database Transaction Management

**Standard Transaction Pattern:**
```python
try:
    # Perform database operations
    db.add(entity)
    db.commit()
    db.refresh(entity)
    
    # Add audit logging
    audit_log = AuditLog(
        actor_agent_id=current_agent.id,
        action="entity.created",
        subject_id=entity.id,
        details={"relevant": "data"}
    )
    db.add(audit_log)
    db.commit()
    
    return success_response
    
except IntegrityError as e:
    db.rollback()
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Operation failed: {str(e)}"
    )
except Exception as e:
    db.rollback()
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Unexpected error: {str(e)}"
    )
```

### Input Validation and Error Handling

**Pydantic Schema Validation:**
```python
# Request schemas provide automatic validation
class TaskCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200, description="Human-readable task title")
    schedule_kind: ScheduleKind = Field(..., description="Type of schedule")
    timezone: str = Field(default="Europe/Chisinau", pattern=r'^[A-Za-z]+/[A-Za-z_]+$')
    
    @validator('schedule_expr')
    def validate_schedule_expr(cls, v, values):
        # Custom validation logic
        schedule_kind = values.get('schedule_kind')
        if schedule_kind in ['cron', 'rrule', 'once'] and not v:
            raise ValueError('schedule_expr required for this schedule_kind')
        return v
```

**Structured Error Responses:**
```python
# Consistent error response format
{
    "detail": "Human-readable error message",
    "error_code": "SPECIFIC_ERROR_CODE",  # When applicable
    "validation_errors": [...],           # For input validation failures
    "request_id": "uuid-for-tracing"     # For debugging support
}
```

### Response Formatting and Pagination

**Standardized List Responses:**
```python
class TaskListResponse(BaseModel):
    items: List[TaskResponse]
    total: int
    limit: int 
    offset: int
    has_more: bool

# Usage in endpoints
return TaskListResponse(
    items=task_responses,
    total=total,
    limit=limit,
    offset=offset,
    has_more=(offset + len(tasks)) < total
)
```

**Resource Response Models:**
```python
class TaskResponse(BaseModel):
    id: UUID
    title: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    # ... additional fields
    
    class Config:
        orm_mode = True  # Enable from_orm() for SQLAlchemy models
```

### Audit Logging

**Comprehensive Audit Trail:**
Every state-changing operation includes detailed audit logging:
```python
audit_log = AuditLog(
    actor_agent_id=current_agent.id,        # Who performed the action
    action="task.created",                   # What action was taken
    subject_id=task.id,                      # What entity was affected
    details={                                # Relevant context data
        "title": task.title,
        "schedule_kind": task.schedule_kind.value,
        "created_by": str(task.created_by)
    }
)
```

**Action Naming Convention:**
- `{resource}.{action}` format (e.g., `task.created`, `agent.updated`)
- Standard actions: `created`, `updated`, `deleted`, `paused`, `resumed`, `canceled`
- Special actions: `run_now`, `snoozed`, `published`

---

## Integration with Other Components

### Database Layer Integration

**SQLAlchemy Models:**
Routes interact with database through SQLAlchemy ORM models defined in `../models.py`:
```python
from ..models import Task, DueWork, Agent, AuditLog, TaskRun

# Standard query patterns
task = db.query(Task).filter(Task.id == task_id).first()
runs = db.query(TaskRun).join(Task).filter(...).all()
```

**Concurrent Access Patterns:**
Critical operations use database-level concurrency control:
```python
# Safe work item updates with row-level locking
db.execute(
    text("""
        UPDATE due_work 
        SET run_at = run_at + INTERVAL :delay_seconds * INTERVAL '1 second'
        WHERE task_id = :task_id 
          AND run_at > now() 
          AND (locked_until IS NULL OR locked_until < now())
    """),
    {"task_id": task_id, "delay_seconds": delay_seconds}
)
```

### Schema Layer Integration

**Pydantic Schemas:**
Routes use schemas from `../schemas.py` for validation and serialization:
```python
from ..schemas import (
    TaskCreateRequest, TaskUpdateRequest, TaskResponse, TaskListResponse,
    OperationResponse, SnoozeRequest, EventPublishRequest
)

# Automatic validation and serialization
@router.post("/", response_model=TaskResponse)
async def create_task(task_request: TaskCreateRequest) -> TaskResponse:
    # TaskCreateRequest automatically validates input
    # TaskResponse automatically serializes output
```

### Dependency Layer Integration

**Shared Dependencies:**
Routes use common dependencies from `../dependencies.py`:
```python
from ..dependencies import get_db, get_current_agent, require_scopes, get_redis

# Standard dependency injection
db: Session = Depends(get_db)                          # Database session
current_agent: Agent = Depends(get_current_agent)     # Authenticated agent
admin_agent: Agent = Depends(require_scopes("admin")) # Scope validation
redis_client: redis.Redis = Depends(get_redis)        # Redis connection
```

---

## Testing and Validation

### Route Testing Strategy

**Unit Testing:**
Each route should have comprehensive unit tests covering:
- Successful operations with valid inputs
- Input validation and error cases
- Authentication and authorization scenarios
- Database transaction rollback behavior
- Audit logging verification

**Integration Testing:**
Routes should be tested in combination to verify:
- Cross-route data consistency
- Event triggering and processing flows
- Performance under concurrent access
- Error propagation and handling

**Example Test Structure:**
```python
@pytest.mark.asyncio
async def test_create_task_success(client, auth_headers, sample_task_data):
    response = await client.post("/tasks", 
                                json=sample_task_data,
                                headers=auth_headers)
    assert response.status_code == 201
    assert response.json()["title"] == sample_task_data["title"]
    
    # Verify audit log was created
    audit_log = db.query(AuditLog).filter(
        AuditLog.action == "task.created"
    ).first()
    assert audit_log is not None
```

### Performance Considerations

**Database Query Optimization:**
- Use appropriate indexes for common filter patterns
- Implement pagination to limit result set sizes
- Avoid N+1 query problems with proper eager loading
- Monitor slow queries and optimize as needed

**Caching Strategy:**
- Cache frequently accessed data (agent profiles, task configurations)
- Use Redis for temporary data and rate limiting
- Implement cache invalidation for data consistency

**Concurrent Access:**
- Use database row-level locking for critical sections
- Implement proper transaction isolation levels
- Handle deadlock scenarios with appropriate retry logic
- Monitor lock contention and optimize as needed

---

## Operational Monitoring

### Health Check Integration

**Route Health Endpoints:**
Each route module should provide health check capabilities:
```python
@router.get("/health")
async def health_check(
    db: Session = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis)
) -> dict:
    """Health check for route module dependencies."""
    return {
        "database": "healthy" if db.execute("SELECT 1").scalar() == 1 else "unhealthy",
        "redis": "healthy" if redis_client.ping() else "unhealthy",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
```

### Metrics and Observability

**Request Metrics:**
- Request count by endpoint and status code
- Response time percentiles for each route
- Error rate tracking and alerting
- Authentication failure monitoring

**Business Metrics:**
- Task creation and execution rates
- Agent activity and usage patterns
- Event publishing and processing volumes
- System resource utilization

### Logging and Debugging

**Structured Logging:**
All routes should implement structured logging for operational visibility:
```python
import structlog

logger = structlog.get_logger(__name__)

@router.post("/tasks")
async def create_task(...):
    logger.info("task.create.started",
               agent_id=str(current_agent.id),
               task_title=task_request.title)
    
    try:
        # ... operation logic
        logger.info("task.create.success",
                   agent_id=str(current_agent.id),
                   task_id=str(task.id))
        return result
    except Exception as e:
        logger.error("task.create.failed",
                    agent_id=str(current_agent.id),
                    error=str(e))
        raise
```

---

## Security Considerations

### Input Sanitization

**SQL Injection Prevention:**
- Use parameterized queries exclusively
- Validate all input through Pydantic schemas
- Implement size limits on string inputs
- Sanitize user-provided data before database storage

### Access Control

**Authorization Model:**
- Scope-based permissions for all operations
- Agent-level isolation for data access
- Administrative operations restricted to admin scope
- Resource ownership validation where applicable

### Audit and Compliance

**Complete Audit Trail:**
- Log all state-changing operations with actor identification
- Include relevant context data in audit logs
- Maintain immutable audit log records
- Provide audit log querying and export capabilities

### Rate Limiting and Abuse Prevention

**Resource Protection:**
```python
# Implement rate limiting by agent
@router.post("/tasks")
@rate_limit(requests=100, window=3600)  # 100 requests per hour
async def create_task(...):
```

---

## Future Enhancements

### API Versioning Strategy

**Backward Compatibility:**
- Implement API versioning in URL paths (`/v1/tasks`, `/v2/tasks`)
- Maintain backward compatibility for existing endpoints
- Provide migration guides for breaking changes
- Use feature flags for gradual rollout of new functionality

### Performance Optimizations

**Scaling Considerations:**
- Implement read replicas for query-heavy operations
- Add caching layers for frequently accessed data
- Consider async processing for long-running operations
- Implement connection pooling and resource management

### Enhanced Monitoring

**Advanced Observability:**
- Distributed tracing across route operations
- Custom metrics for business logic monitoring
- Performance profiling and bottleneck identification
- Automated alerting for operational issues

The Personal Agent Orchestrator API routes provide a robust, secure, and maintainable foundation for agent coordination and task management. Each route module follows consistent patterns while addressing the specific requirements of its functional domain.