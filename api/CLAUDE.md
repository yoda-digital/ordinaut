# Personal Agent Orchestrator - FastAPI Application Layer

## Purpose & Mission

The **FastAPI Application Layer** serves as the REST API gateway for the Personal Agent Orchestrator, providing AI agents with a comprehensive HTTP interface for task management, pipeline execution, and system monitoring. This layer transforms the orchestrator's core capabilities into accessible, well-documented API endpoints that agents can integrate with using standard HTTP protocols.

**Core Responsibilities:**
- **Task Lifecycle Management** - Create, read, update, delete, and control scheduled tasks
- **Execution Monitoring** - Track pipeline runs, view logs, and analyze performance
- **Agent Authentication** - Scope-based access control and rate limiting
- **System Health** - Health checks, metrics, and operational status
- **Input Validation** - JSON Schema validation for all agent requests
- **Error Handling** - Structured error responses with actionable debugging information

---

## Architecture Overview

The FastAPI application follows a layered architecture pattern with clear separation of concerns:

```
api/
├── main.py                 # FastAPI app initialization and middleware
├── routes/                 # API endpoint implementations
│   ├── __init__.py
│   ├── tasks.py           # Task CRUD operations
│   ├── runs.py            # Execution monitoring and logs
│   ├── system.py          # Health checks and metrics
│   ├── agents.py          # Agent authentication and scopes
│   └── tools.py           # Tool catalog and validation
├── models.py              # SQLAlchemy ORM models
├── schemas.py             # Pydantic request/response models
├── dependencies.py        # Common dependencies and auth
├── exceptions.py          # Custom exception handlers
└── middleware.py          # Request logging and CORS
```

### Key Architectural Patterns

**Dependency Injection Pattern:**
```python
# Common dependencies injected into route handlers
async def get_current_agent(token: str = Depends(oauth2_scheme)) -> Agent:
    # JWT validation and scope verification
    pass

async def get_database() -> AsyncSession:
    # Database session management with proper cleanup
    pass
```

**Repository Pattern:**
```python
# Data access abstraction layer
class TaskRepository:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_task(self, task_data: TaskCreate) -> Task:
        # Implementation with proper error handling
        pass
```

**Request/Response Schema Validation:**
```python
# Strict validation using Pydantic models
class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    schedule_kind: ScheduleKind
    schedule_expr: str = Field(validate_schedule_expression=True)
    timezone: str = Field(validate_timezone=True)
    payload: PipelinePayload
```

---

## Core Components

### 1. Application Initialization (main.py)

**FastAPI Application Setup:**
```python
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError

app = FastAPI(
    title="Personal Agent Orchestrator API",
    description="REST API for AI agent task scheduling and coordination",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request Logging Middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    
    logger.info(
        f"{request.method} {request.url.path} - "
        f"Status: {response.status_code} - "
        f"Duration: {process_time:.3f}s"
    )
    return response
```

**Error Handling:**
```python
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": "ValidationError",
            "message": "Request validation failed",
            "details": [
                {
                    "field": ".".join(str(x) for x in error["loc"]),
                    "message": error["msg"],
                    "invalid_value": error.get("input")
                }
                for error in exc.errors()
            ]
        }
    )

@app.exception_handler(AgentAuthenticationError)
async def auth_exception_handler(request: Request, exc: AgentAuthenticationError):
    return JSONResponse(
        status_code=401,
        content={
            "error": "AuthenticationError",
            "message": str(exc),
            "required_scopes": getattr(exc, 'required_scopes', [])
        }
    )
```

### 2. Route Implementations

#### Task Management Routes (routes/tasks.py)

**Create Task Endpoint:**
```python
@router.post("/tasks", response_model=TaskResponse, status_code=201)
async def create_task(
    task_data: TaskCreateRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_database)
):
    """
    Create a new scheduled task.
    
    Validates schedule expressions, timezone settings, and pipeline definitions
    before persisting to database and registering with scheduler.
    """
    # Validate agent has required scopes
    require_scopes(agent, ["tasks:write"])
    
    # Validate schedule expression
    validate_schedule(task_data.schedule_kind, task_data.schedule_expr, task_data.timezone)
    
    # Validate pipeline definition
    await validate_pipeline(task_data.payload.pipeline)
    
    # Create task in database
    task_repo = TaskRepository(db)
    task = await task_repo.create_task(task_data, agent_id=agent.id)
    
    # Register with scheduler
    scheduler_client = get_scheduler_client()
    await scheduler_client.register_task(task)
    
    return TaskResponse.from_orm(task)
```

**List Tasks Endpoint:**
```python
@router.get("/tasks", response_model=List[TaskResponse])
async def list_tasks(
    status: Optional[TaskStatus] = None,
    schedule_kind: Optional[ScheduleKind] = None,
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_database)
):
    """
    List tasks owned by the authenticated agent.
    
    Supports filtering by status, schedule type, and pagination.
    """
    require_scopes(agent, ["tasks:read"])
    
    task_repo = TaskRepository(db)
    tasks = await task_repo.list_tasks(
        agent_id=agent.id,
        status=status,
        schedule_kind=schedule_kind,
        limit=limit,
        offset=offset
    )
    
    return [TaskResponse.from_orm(task) for task in tasks]
```

**Task Control Operations:**
```python
@router.patch("/tasks/{task_id}/pause", response_model=TaskResponse)
async def pause_task(
    task_id: UUID,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_database)
):
    """Pause a scheduled task, preventing future executions."""
    task = await get_task_or_404(task_id, agent.id, db)
    
    task_repo = TaskRepository(db)
    updated_task = await task_repo.update_status(task_id, TaskStatus.PAUSED)
    
    # Unregister from scheduler
    scheduler_client = get_scheduler_client()
    await scheduler_client.unregister_task(task_id)
    
    return TaskResponse.from_orm(updated_task)

@router.patch("/tasks/{task_id}/resume", response_model=TaskResponse)
async def resume_task(task_id: UUID, ...):
    """Resume a paused task, re-enabling scheduled executions."""
    # Similar implementation with scheduler re-registration

@router.post("/tasks/{task_id}/execute", response_model=TaskRunResponse)
async def execute_task_immediately(task_id: UUID, ...):
    """Trigger immediate execution of a task, bypassing schedule."""
    # Queue immediate execution in due_work table
```

#### Execution Monitoring Routes (routes/runs.py)

**List Task Runs:**
```python
@router.get("/runs", response_model=List[TaskRunResponse])
async def list_runs(
    task_id: Optional[UUID] = None,
    status: Optional[RunStatus] = None,
    since: Optional[datetime] = None,
    limit: int = Query(100, ge=1, le=1000),
    include_logs: bool = Query(False),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_database)
):
    """
    List task execution runs with filtering and pagination.
    
    Optionally include detailed execution logs and step results.
    """
    require_scopes(agent, ["runs:read"])
    
    run_repo = TaskRunRepository(db)
    runs = await run_repo.list_runs(
        agent_id=agent.id,
        task_id=task_id,
        status=status,
        since=since,
        limit=limit,
        include_logs=include_logs
    )
    
    return [TaskRunResponse.from_orm(run) for run in runs]
```

**Get Run Details:**
```python
@router.get("/runs/{run_id}", response_model=TaskRunDetailResponse)
async def get_run(
    run_id: UUID,
    include_step_details: bool = Query(True),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_database)
):
    """
    Get detailed information about a specific task run.
    
    Includes pipeline step results, error details, and execution timeline.
    """
    run = await get_run_or_404(run_id, agent.id, db)
    
    if include_step_details:
        step_repo = StepResultRepository(db)
        steps = await step_repo.get_steps_for_run(run_id)
        run.step_results = steps
    
    return TaskRunDetailResponse.from_orm(run)
```

#### System Health Routes (routes/system.py)

**Health Check Endpoint:**
```python
@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    System health check with component status.
    
    Returns overall health and individual component statuses.
    """
    checks = {}
    
    # Database connectivity
    try:
        async with get_database() as db:
            await db.execute("SELECT 1")
        checks["database"] = {"status": "healthy", "latency_ms": 12}
    except Exception as e:
        checks["database"] = {"status": "unhealthy", "error": str(e)}
    
    # Redis connectivity
    try:
        redis_client = get_redis_client()
        await redis_client.ping()
        checks["redis"] = {"status": "healthy", "latency_ms": 8}
    except Exception as e:
        checks["redis"] = {"status": "unhealthy", "error": str(e)}
    
    # Scheduler status
    try:
        scheduler_client = get_scheduler_client()
        status = await scheduler_client.get_status()
        checks["scheduler"] = {"status": "healthy", "jobs_count": status.job_count}
    except Exception as e:
        checks["scheduler"] = {"status": "unhealthy", "error": str(e)}
    
    # Worker system status
    try:
        worker_stats = await get_worker_statistics()
        checks["workers"] = {
            "status": "healthy",
            "active_workers": worker_stats.active_count,
            "queue_depth": worker_stats.queue_depth
        }
    except Exception as e:
        checks["workers"] = {"status": "unhealthy", "error": str(e)}
    
    overall_status = "healthy" if all(
        check["status"] == "healthy" for check in checks.values()
    ) else "unhealthy"
    
    return HealthResponse(
        status=overall_status,
        timestamp=datetime.utcnow(),
        checks=checks
    )
```

**Metrics Endpoint:**
```python
@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(
    since: Optional[datetime] = Query(None),
    agent: Agent = Depends(get_current_agent)
):
    """
    System and agent-specific metrics.
    
    Returns task execution statistics, performance metrics, and usage data.
    """
    require_scopes(agent, ["metrics:read"])
    
    metrics_service = MetricsService()
    
    return MetricsResponse(
        tasks_created_24h=await metrics_service.count_tasks_created(hours=24, agent_id=agent.id),
        runs_completed_24h=await metrics_service.count_runs_completed(hours=24, agent_id=agent.id),
        success_rate_24h=await metrics_service.calculate_success_rate(hours=24, agent_id=agent.id),
        avg_execution_time_24h=await metrics_service.avg_execution_time(hours=24, agent_id=agent.id),
        active_tasks=await metrics_service.count_active_tasks(agent_id=agent.id),
        queue_depth=await metrics_service.get_queue_depth(),
        system_uptime=await metrics_service.get_system_uptime()
    )
```

### 3. Data Models and Schemas

#### SQLAlchemy Models (models.py)

**Task Model:**
```python
class Task(Base):
    __tablename__ = "task"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agent.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    
    # Scheduling
    schedule_kind = Column(Enum(ScheduleKind), nullable=False)
    schedule_expr = Column(String(500))
    timezone = Column(String(50), nullable=False, default="UTC")
    
    # Status and control
    status = Column(Enum(TaskStatus), nullable=False, default=TaskStatus.ACTIVE, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Pipeline definition
    payload = Column(JSONB, nullable=False)
    
    # Execution tracking
    last_run_at = Column(DateTime(timezone=True), index=True)
    next_run_at = Column(DateTime(timezone=True), index=True)
    run_count = Column(Integer, nullable=False, default=0)
    success_count = Column(Integer, nullable=False, default=0)
    
    # Relationships
    agent = relationship("Agent", back_populates="tasks")
    runs = relationship("TaskRun", back_populates="task", cascade="all, delete-orphan")
    
    # Indexes for efficient queries
    __table_args__ = (
        Index("ix_task_agent_status", agent_id, status),
        Index("ix_task_next_run", next_run_at, status),
        Index("ix_task_schedule_kind", schedule_kind, status),
    )
```

**TaskRun Model:**
```python
class TaskRun(Base):
    __tablename__ = "task_run"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("task.id"), nullable=False, index=True)
    
    # Execution details
    started_at = Column(DateTime(timezone=True), nullable=False, index=True)
    finished_at = Column(DateTime(timezone=True), index=True)
    success = Column(Boolean, index=True)
    error = Column(Text)
    
    # Pipeline execution context
    input_context = Column(JSONB)  # Variables available at start
    output_context = Column(JSONB)  # Final context with all results
    
    # Performance metrics
    duration_ms = Column(Integer)
    steps_completed = Column(Integer, nullable=False, default=0)
    steps_total = Column(Integer, nullable=False, default=0)
    
    # Relationships
    task = relationship("Task", back_populates="runs")
    step_results = relationship("StepResult", back_populates="run", cascade="all, delete-orphan")
```

#### Pydantic Schemas (schemas.py)

**Request Schemas:**
```python
class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200, description="Human-readable task title")
    description: str = Field(max_length=2000, description="Detailed task description")
    
    schedule_kind: ScheduleKind = Field(description="Type of schedule")
    schedule_expr: str = Field(description="Schedule expression (cron, rrule, etc.)")
    timezone: str = Field(default="UTC", description="Timezone for schedule evaluation")
    
    payload: PipelinePayload = Field(description="Pipeline definition and parameters")
    
    @validator("schedule_expr")
    def validate_schedule_expression(cls, v, values):
        """Validate schedule expression matches schedule_kind."""
        kind = values.get("schedule_kind")
        timezone = values.get("timezone", "UTC")
        
        if kind == ScheduleKind.CRON:
            validate_cron_expression(v)
        elif kind == ScheduleKind.RRULE:
            validate_rrule_expression(v, timezone)
        elif kind == ScheduleKind.ONCE:
            validate_datetime_expression(v, timezone)
        
        return v
    
    @validator("timezone")
    def validate_timezone(cls, v):
        """Validate timezone name."""
        try:
            pytz.timezone(v)
        except pytz.exceptions.UnknownTimeZoneError:
            raise ValueError(f"Unknown timezone: {v}")
        return v

class PipelinePayload(BaseModel):
    pipeline: List[PipelineStep] = Field(min_items=1, max_items=50)
    params: Dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=300, ge=1, le=3600)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)

class PipelineStep(BaseModel):
    id: str = Field(min_length=1, max_length=50, regex="^[a-zA-Z0-9_-]+$")
    uses: str = Field(description="Tool address (e.g., 'weather-api.forecast')")
    with_: Dict[str, Any] = Field(alias="with", default_factory=dict)
    save_as: Optional[str] = Field(description="Variable name to save result")
    if_: Optional[str] = Field(alias="if", description="JMESPath condition")
    timeout_seconds: Optional[int] = Field(ge=1, le=1800)
```

**Response Schemas:**
```python
class TaskResponse(BaseModel):
    id: UUID
    title: str
    description: str
    
    schedule_kind: ScheduleKind
    schedule_expr: str
    timezone: str
    
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    
    last_run_at: Optional[datetime]
    next_run_at: Optional[datetime]
    run_count: int
    success_count: int
    
    # Computed properties
    success_rate: Optional[float] = None
    
    class Config:
        from_attributes = True
        
    @validator("success_rate", always=True)
    def calculate_success_rate(cls, v, values):
        run_count = values.get("run_count", 0)
        success_count = values.get("success_count", 0)
        
        if run_count == 0:
            return None
        return round(success_count / run_count * 100, 2)

class TaskRunResponse(BaseModel):
    id: UUID
    task_id: UUID
    
    started_at: datetime
    finished_at: Optional[datetime]
    success: Optional[bool]
    error: Optional[str]
    
    duration_ms: Optional[int]
    steps_completed: int
    steps_total: int
    
    class Config:
        from_attributes = True
```

### 4. Authentication and Authorization

#### JWT Token Validation (dependencies.py)

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer
from jose import JWTError, jwt

security = HTTPBearer()

async def get_current_agent(token: str = Depends(security)) -> Agent:
    """
    Validate JWT token and return authenticated agent.
    
    Verifies token signature, expiration, and loads agent with scopes.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # Decode and validate JWT
        payload = jwt.decode(
            token.credentials, 
            settings.JWT_SECRET_KEY, 
            algorithms=[settings.JWT_ALGORITHM]
        )
        
        agent_id: str = payload.get("sub")
        if agent_id is None:
            raise credentials_exception
            
        # Load agent from database
        async with get_database() as db:
            agent = await db.get(Agent, UUID(agent_id))
            if agent is None or not agent.is_active:
                raise credentials_exception
                
        return agent
        
    except JWTError:
        raise credentials_exception

def require_scopes(agent: Agent, required_scopes: List[str]):
    """
    Verify agent has all required scopes for operation.
    
    Raises HTTPException if any required scope is missing.
    """
    agent_scopes = set(agent.scopes)
    required_scopes_set = set(required_scopes)
    
    missing_scopes = required_scopes_set - agent_scopes
    if missing_scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions. Missing scopes: {list(missing_scopes)}",
            headers={"X-Required-Scopes": ",".join(required_scopes)}
        )
```

#### Rate Limiting Middleware

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.middleware("http")
async def rate_limit_by_agent(request: Request, call_next):
    """
    Apply rate limits based on authenticated agent.
    
    Different limits for different endpoint categories.
    """
    # Extract agent from token if present
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        try:
            token = auth_header.split(" ")[1]
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            agent_id = payload.get("sub")
            
            # Apply agent-specific rate limits
            path = request.url.path
            if path.startswith("/tasks"):
                # 100 task operations per minute per agent
                await limiter.check_rate_limit(f"tasks:{agent_id}", "100/minute")
            elif path.startswith("/runs"):
                # 500 monitoring requests per minute per agent
                await limiter.check_rate_limit(f"runs:{agent_id}", "500/minute")
                
        except Exception:
            # Fall back to IP-based limiting for invalid tokens
            pass
    
    response = await call_next(request)
    return response
```

---

## Integration Patterns

### Database Integration

**Connection Management:**
```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Database engine with connection pooling
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=20,
    max_overflow=30,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=settings.DEBUG
)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def get_database() -> AsyncSession:
    """Dependency to get database session with proper cleanup."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

**Repository Pattern Implementation:**
```python
class TaskRepository:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_task(self, task_data: TaskCreateRequest, agent_id: UUID) -> Task:
        """Create new task with validation and audit logging."""
        task = Task(
            agent_id=agent_id,
            title=task_data.title,
            description=task_data.description,
            schedule_kind=task_data.schedule_kind,
            schedule_expr=task_data.schedule_expr,
            timezone=task_data.timezone,
            payload=task_data.payload.dict(),
            status=TaskStatus.ACTIVE
        )
        
        # Calculate next run time
        next_run = calculate_next_run(
            task_data.schedule_kind,
            task_data.schedule_expr,
            task_data.timezone
        )
        task.next_run_at = next_run
        
        self.db.add(task)
        await self.db.flush()  # Get ID without committing
        
        # Log creation event
        await self.log_task_event(task.id, "created", {"agent_id": agent_id})
        
        return task
    
    async def list_tasks(
        self, 
        agent_id: UUID,
        status: Optional[TaskStatus] = None,
        schedule_kind: Optional[ScheduleKind] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Task]:
        """List tasks with filtering and pagination."""
        query = select(Task).where(Task.agent_id == agent_id)
        
        if status is not None:
            query = query.where(Task.status == status)
        if schedule_kind is not None:
            query = query.where(Task.schedule_kind == schedule_kind)
            
        query = query.order_by(Task.created_at.desc()).limit(limit).offset(offset)
        
        result = await self.db.execute(query)
        return result.scalars().all()
```

### Scheduler Integration

**Scheduler Client:**
```python
class SchedulerClient:
    def __init__(self, redis_client):
        self.redis = redis_client
    
    async def register_task(self, task: Task):
        """Register task with APScheduler via Redis commands."""
        command = {
            "action": "add_job",
            "job_id": str(task.id),
            "func": "workers.runner:execute_task",
            "args": [str(task.id)],
            "trigger": self._build_trigger(task),
            "max_instances": 1,
            "coalesce": True,
            "misfire_grace_time": 300
        }
        
        await self.redis.xadd("scheduler:commands", command)
    
    async def unregister_task(self, task_id: UUID):
        """Remove task from scheduler."""
        command = {
            "action": "remove_job",
            "job_id": str(task_id)
        }
        
        await self.redis.xadd("scheduler:commands", command)
    
    def _build_trigger(self, task: Task) -> Dict[str, Any]:
        """Build APScheduler trigger from task schedule."""
        if task.schedule_kind == ScheduleKind.CRON:
            return {
                "type": "cron",
                "cron_string": task.schedule_expr,
                "timezone": task.timezone
            }
        elif task.schedule_kind == ScheduleKind.RRULE:
            return {
                "type": "rrule",
                "rrule_string": task.schedule_expr,
                "timezone": task.timezone
            }
        elif task.schedule_kind == ScheduleKind.ONCE:
            run_time = parse_datetime(task.schedule_expr, task.timezone)
            return {
                "type": "date",
                "run_date": run_time
            }
```

### Worker System Integration

**Immediate Execution:**
```python
async def queue_immediate_execution(task_id: UUID, agent_id: UUID):
    """Queue task for immediate execution by workers."""
    async with get_database() as db:
        # Insert into due_work table for worker processing
        work_item = DueWork(
            task_id=task_id,
            agent_id=agent_id,
            run_at=datetime.utcnow(),
            priority=ExecutionPriority.MANUAL,  # Higher priority for manual executions
            context={"triggered_by": "api", "manual": True}
        )
        
        db.add(work_item)
        await db.commit()
        
        # Notify workers via Redis
        redis_client = get_redis_client()
        await redis_client.publish("work:available", json.dumps({
            "work_id": str(work_item.id),
            "task_id": str(task_id),
            "priority": work_item.priority.value
        }))
```

---

## Validation and Error Handling

### Input Validation Framework

**Schedule Expression Validation:**
```python
def validate_cron_expression(expr: str):
    """Validate cron expression using croniter."""
    try:
        from croniter import croniter
        croniter(expr)
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid cron expression: {e}")

def validate_rrule_expression(expr: str, timezone: str):
    """Validate RRULE expression and timezone compatibility."""
    try:
        from dateutil.rrule import rrulestr
        import pytz
        
        # Parse RRULE
        rule = rrulestr(expr)
        tz = pytz.timezone(timezone)
        
        # Test next occurrence calculation
        now = datetime.now(tz)
        next_occurrence = rule.after(now, inc=False)
        
        if next_occurrence is None:
            raise ValueError("RRULE expression produces no future occurrences")
            
    except Exception as e:
        raise ValueError(f"Invalid RRULE expression: {e}")

async def validate_pipeline(pipeline: List[PipelineStep]):
    """Validate pipeline definition and tool availability."""
    tool_registry = get_tool_registry()
    
    step_ids = set()
    for step in pipeline:
        # Check for duplicate step IDs
        if step.id in step_ids:
            raise ValueError(f"Duplicate step ID: {step.id}")
        step_ids.add(step.id)
        
        # Validate tool exists and is available
        tool = await tool_registry.get_tool(step.uses)
        if not tool:
            raise ValueError(f"Tool not found: {step.uses}")
        
        # Validate tool input schema if provided
        if step.with_:
            try:
                jsonschema.validate(step.with_, tool.input_schema)
            except jsonschema.ValidationError as e:
                raise ValueError(f"Invalid input for tool {step.uses}: {e.message}")
```

### Error Response Standards

**Structured Error Responses:**
```python
class ErrorResponse(BaseModel):
    error: str = Field(description="Error category")
    message: str = Field(description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(description="Additional error context")
    request_id: Optional[str] = Field(description="Request correlation ID")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

# Common error patterns
class ValidationErrorDetail(BaseModel):
    field: str
    message: str
    invalid_value: Any
    expected: Optional[str] = None

class AuthenticationErrorResponse(ErrorResponse):
    required_scopes: Optional[List[str]] = None
    token_status: Optional[str] = None

class RateLimitErrorResponse(ErrorResponse):
    retry_after_seconds: int
    current_usage: int
    limit: int
```

**Exception Handler Examples:**
```python
@app.exception_handler(TaskNotFoundError)
async def task_not_found_handler(request: Request, exc: TaskNotFoundError):
    return JSONResponse(
        status_code=404,
        content=ErrorResponse(
            error="TaskNotFound",
            message=f"Task {exc.task_id} not found or not accessible",
            details={"task_id": str(exc.task_id)},
            request_id=get_request_id(request)
        ).dict()
    )

@app.exception_handler(SchedulerError)
async def scheduler_error_handler(request: Request, exc: SchedulerError):
    return JSONResponse(
        status_code=503,
        content=ErrorResponse(
            error="SchedulerUnavailable", 
            message="Task scheduling service temporarily unavailable",
            details={"retry_after": "30s"},
            request_id=get_request_id(request)
        ).dict()
    )
```

---

## Performance and Monitoring

### Response Time Optimization

**Database Query Optimization:**
```python
# Use database indexes effectively
class TaskRepository:
    async def get_due_tasks(self, limit: int = 100) -> List[Task]:
        """Optimized query for due tasks using composite index."""
        query = select(Task).where(
            and_(
                Task.status == TaskStatus.ACTIVE,
                Task.next_run_at <= datetime.utcnow()
            )
        ).order_by(
            Task.next_run_at.asc()
        ).limit(limit)
        
        # Uses index: ix_task_next_run_status
        result = await self.db.execute(query)
        return result.scalars().all()

# Connection pooling optimization
engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,  # Adjust based on expected concurrent requests
    max_overflow=30,  # Allow burst capacity
    pool_pre_ping=True,  # Validate connections before use
    pool_recycle=3600,  # Recycle connections hourly
)
```

**Response Caching:**
```python
from functools import lru_cache
import asyncio

class CachedResponseService:
    def __init__(self):
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes
    
    async def get_system_metrics(self) -> MetricsResponse:
        """Cache expensive metrics calculations."""
        cache_key = "system_metrics"
        now = time.time()
        
        # Check cache
        if cache_key in self._cache:
            data, timestamp = self._cache[cache_key]
            if now - timestamp < self._cache_ttl:
                return data
        
        # Calculate fresh metrics
        metrics = await self._calculate_metrics()
        self._cache[cache_key] = (metrics, now)
        
        return metrics
```

### Request Logging and Tracing

**Structured Logging:**
```python
import structlog

logger = structlog.get_logger()

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests with structured data."""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    
    # Log request start
    logger.info(
        "request_started",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        query_params=dict(request.query_params),
        user_agent=request.headers.get("user-agent"),
        remote_addr=request.client.host
    )
    
    start_time = time.time()
    
    try:
        response = await call_next(request)
        
        # Log successful completion
        logger.info(
            "request_completed",
            request_id=request_id,
            status_code=response.status_code,
            duration_ms=round((time.time() - start_time) * 1000, 2)
        )
        
        return response
        
    except Exception as exc:
        # Log errors
        logger.error(
            "request_failed",
            request_id=request_id,
            error_type=type(exc).__name__,
            error_message=str(exc),
            duration_ms=round((time.time() - start_time) * 1000, 2)
        )
        raise

def get_request_id(request: Request) -> str:
    """Extract request ID from request state."""
    return getattr(request.state, "request_id", "unknown")
```

### Metrics Collection

**Prometheus Metrics:**
```python
from prometheus_client import Counter, Histogram, Gauge

# Define metrics
request_count = Counter(
    "api_requests_total", 
    "Total API requests", 
    ["method", "endpoint", "status"]
)

request_duration = Histogram(
    "api_request_duration_seconds",
    "Request duration in seconds",
    ["method", "endpoint"]
)

active_tasks_gauge = Gauge(
    "active_tasks_total",
    "Number of active tasks",
    ["agent_id"]
)

@app.middleware("http") 
async def metrics_middleware(request: Request, call_next):
    """Collect request metrics."""
    start_time = time.time()
    
    response = await call_next(request)
    
    # Record metrics
    request_count.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code
    ).inc()
    
    request_duration.labels(
        method=request.method,
        endpoint=request.url.path
    ).observe(time.time() - start_time)
    
    return response
```

---

## Development and Testing Patterns

### API Testing Framework

**Test Client Setup:**
```python
import pytest
from httpx import AsyncClient
from fastapi.testclient import TestClient

@pytest.fixture
async def test_client():
    """Create test client with database isolation."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

@pytest.fixture
async def authenticated_agent():
    """Create test agent with valid JWT token."""
    agent = Agent(
        id=uuid.uuid4(),
        name="test-agent",
        scopes=["tasks:read", "tasks:write", "runs:read"],
        is_active=True
    )
    
    # Generate test JWT
    token_data = {"sub": str(agent.id), "exp": datetime.utcnow() + timedelta(hours=1)}
    token = jwt.encode(token_data, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    
    return agent, f"Bearer {token}"
```

**Integration Test Examples:**
```python
@pytest.mark.asyncio
async def test_create_task_success(test_client: AsyncClient, authenticated_agent):
    """Test successful task creation."""
    agent, auth_header = authenticated_agent
    
    task_data = {
        "title": "Test Task",
        "description": "Test task description",
        "schedule_kind": "cron",
        "schedule_expr": "0 9 * * 1-5",
        "timezone": "UTC",
        "payload": {
            "pipeline": [
                {
                    "id": "test_step",
                    "uses": "test-tool.echo",
                    "with": {"message": "Hello World"}
                }
            ]
        }
    }
    
    response = await test_client.post(
        "/tasks",
        json=task_data,
        headers={"Authorization": auth_header}
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test Task"
    assert data["status"] == "active"
    assert "next_run_at" in data

@pytest.mark.asyncio
async def test_create_task_validation_error(test_client: AsyncClient, authenticated_agent):
    """Test task creation with invalid data."""
    agent, auth_header = authenticated_agent
    
    invalid_task_data = {
        "title": "",  # Invalid: empty title
        "schedule_kind": "cron",
        "schedule_expr": "invalid cron",  # Invalid: bad cron expression
        "payload": {"pipeline": []}  # Invalid: empty pipeline
    }
    
    response = await test_client.post(
        "/tasks",
        json=invalid_task_data,
        headers={"Authorization": auth_header}
    )
    
    assert response.status_code == 422
    data = response.json()
    assert data["error"] == "ValidationError"
    assert len(data["details"]) >= 3  # Multiple validation errors
```

### Load Testing

**Performance Test Setup:**
```python
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor

async def load_test_create_tasks(concurrent_requests: int = 100):
    """Load test task creation endpoint."""
    
    async def create_task_request(session, auth_token):
        task_data = {
            "title": f"Load Test Task {uuid.uuid4()}",
            "description": "Generated by load test",
            "schedule_kind": "once",
            "schedule_expr": (datetime.utcnow() + timedelta(minutes=5)).isoformat(),
            "payload": {
                "pipeline": [{"id": "test", "uses": "test-tool.noop"}]
            }
        }
        
        async with session.post(
            "http://localhost:8080/tasks",
            json=task_data,
            headers={"Authorization": f"Bearer {auth_token}"}
        ) as response:
            return response.status, await response.json()
    
    # Execute concurrent requests
    async with aiohttp.ClientSession() as session:
        auth_token = generate_test_token()
        
        tasks = [
            create_task_request(session, auth_token)
            for _ in range(concurrent_requests)
        ]
        
        start_time = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        duration = time.time() - start_time
        
        # Analyze results
        success_count = sum(1 for status, _ in results if status == 201)
        error_count = len(results) - success_count
        
        print(f"Load Test Results:")
        print(f"  Requests: {concurrent_requests}")
        print(f"  Duration: {duration:.2f}s") 
        print(f"  Success: {success_count}")
        print(f"  Errors: {error_count}")
        print(f"  Rate: {concurrent_requests/duration:.2f} req/s")
```

---

## Security Considerations

### Authentication Security

**JWT Token Security:**
```python
# Strong JWT configuration
JWT_ALGORITHM = "HS256"
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")  # 256-bit random key
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 60

# Token validation with proper error handling
async def validate_jwt_token(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={
                "verify_exp": True,
                "verify_iat": True,
                "verify_signature": True
            }
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Token has expired")
    except jwt.InvalidTokenError:
        raise AuthenticationError("Invalid token")
```

### Input Sanitization

**SQL Injection Prevention:**
```python
# Always use parameterized queries
async def get_tasks_by_title(title_pattern: str) -> List[Task]:
    # SECURE: Parameterized query
    query = select(Task).where(Task.title.ilike(f"%{title_pattern}%"))
    
    # NEVER DO THIS: Direct string interpolation
    # query = f"SELECT * FROM task WHERE title ILIKE '%{title_pattern}%'"
```

**JSON Schema Validation:**
```python
# Strict validation prevents injection attacks
task_schema = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "minLength": 1, "maxLength": 200},
        "schedule_expr": {"type": "string", "pattern": "^[a-zA-Z0-9\\s\\*\\-/,]+$"}
    },
    "required": ["title"],
    "additionalProperties": False
}

def validate_task_input(data: Dict[str, Any]):
    try:
        jsonschema.validate(data, task_schema)
    except jsonschema.ValidationError as e:
        raise ValueError(f"Invalid input: {e.message}")
```

### Rate Limiting and DoS Protection

**Advanced Rate Limiting:**
```python
class AdaptiveRateLimiter:
    def __init__(self):
        self.rate_limits = {
            "tasks:create": "10/minute",
            "tasks:list": "100/minute", 
            "runs:list": "200/minute"
        }
        self.error_penalties = {}  # Track agents with high error rates
    
    async def check_rate_limit(self, agent_id: str, operation: str):
        # Apply base rate limit
        base_limit = self.rate_limits.get(operation, "50/minute")
        
        # Apply penalty if agent has high error rate
        if agent_id in self.error_penalties:
            penalty_factor = self.error_penalties[agent_id]
            # Reduce rate limit for problematic agents
            adjusted_limit = f"{int(int(base_limit.split('/')[0]) * penalty_factor)}/minute"
        else:
            adjusted_limit = base_limit
            
        await self._check_redis_rate_limit(f"{agent_id}:{operation}", adjusted_limit)
```

---

## Deployment and Operations

### Production Configuration

**Environment-based Settings:**
```python
from pydantic import BaseSettings

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 30
    
    # Security
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    CORS_ORIGINS: List[str] = ["*"]
    
    # Performance
    WORKER_CONCURRENCY: int = 10
    REQUEST_TIMEOUT: int = 30
    RATE_LIMIT_ENABLED: bool = True
    
    # Monitoring
    LOG_LEVEL: str = "INFO"
    METRICS_ENABLED: bool = True
    SENTRY_DSN: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
```

**Health Check Configuration:**
```python
@app.get("/health/live", status_code=200)
async def liveness_probe():
    """Kubernetes liveness probe - basic application health."""
    return {"status": "alive", "timestamp": datetime.utcnow()}

@app.get("/health/ready", status_code=200) 
async def readiness_probe():
    """Kubernetes readiness probe - service dependencies."""
    checks = {}
    overall_healthy = True
    
    # Check database connectivity
    try:
        async with get_database() as db:
            await db.execute("SELECT 1")
        checks["database"] = "healthy"
    except Exception:
        checks["database"] = "unhealthy"
        overall_healthy = False
    
    # Check Redis connectivity
    try:
        redis_client = get_redis_client()
        await redis_client.ping()
        checks["redis"] = "healthy"
    except Exception:
        checks["redis"] = "unhealthy"
        overall_healthy = False
    
    status_code = 200 if overall_healthy else 503
    return JSONResponse(
        status_code=status_code,
        content={"status": "ready" if overall_healthy else "not_ready", "checks": checks}
    )
```

### Docker Integration

**Multi-stage Dockerfile:**
```dockerfile
# Build stage
FROM python:3.12-slim as builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.12-slim
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy application code
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY api/ ./api/
COPY engine/ ./engine/
COPY scheduler/ ./scheduler/
COPY workers/ ./workers/

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health/live || exit 1

EXPOSE 8080
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### Monitoring Integration

**Metrics Endpoint for Prometheus:**
```python
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

@app.get("/metrics")
async def prometheus_metrics():
    """Expose metrics in Prometheus format."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

**Structured Logging for Production:**
```python
import structlog

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

# Request correlation logging
@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    
    with structlog.contextvars.bound_contextvars(
        correlation_id=correlation_id,
        request_path=request.url.path,
        request_method=request.method
    ):
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response
```

---

## Summary

The FastAPI Application Layer serves as the primary interface for AI agents to interact with the Personal Agent Orchestrator. It provides:

**Core Features:**
- Complete REST API for task management and monitoring
- JWT-based authentication with scope-based authorization
- Comprehensive input validation and error handling
- Real-time health monitoring and metrics collection
- Rate limiting and DoS protection

**Integration Points:**
- PostgreSQL database via SQLAlchemy ORM and repositories
- APScheduler coordination via Redis message streams
- Worker system communication for immediate execution
- MCP tool registry for pipeline validation

**Production Ready:**
- Structured logging and distributed tracing
- Prometheus metrics integration
- Docker containerization with health checks
- Comprehensive test coverage with load testing

This layer transforms the orchestrator's powerful backend capabilities into an accessible, reliable, and secure API that AI agents can integrate with confidence.