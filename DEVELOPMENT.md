# Ordinaut - Development Guide

Complete guide for setting up, extending, and contributing to the Ordinaut system.

## Quick Development Setup

Get a local development environment running in 5 minutes:

```bash
# Clone the repository
git clone https://github.com/yoda-digital/ordinaut.git
cd ordinaut

# Start development environment
cd ops/
./start.sh dev --build --logs

# Run tests to verify setup
python -m pytest tests/ -v

# Access development tools
open http://localhost:8080/docs  # API documentation
open http://localhost:3000       # Grafana dashboards (admin/admin)
open http://localhost:9090       # Prometheus metrics
```

## Development Environment

### Prerequisites

- **Python 3.12+** with pip and venv
- **Docker 24.0+** and Docker Compose plugin
- **Git** for version control
- **Make** (optional, for convenience commands)
- **PostgreSQL client tools** (optional, for database access)

### Local Python Environment

```bash
# Create virtual environment
python3.12 -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Install in development mode
pip install -e .
```

### Environment Variables

Create `.env` file for development:

```bash
# Core services
DATABASE_URL=postgresql://orchestrator:orchestrator_pw@localhost:5432/orchestrator
REDIS_URL=redis://localhost:6379/0

# API configuration
UVICORN_HOST=0.0.0.0
UVICORN_PORT=8080
DEBUG=true
LOG_LEVEL=debug

# Worker configuration
WORKER_LEASE_SECONDS=60
WORKER_POLL_INTERVAL=0.5
WORKER_MAX_RETRIES=3

# Scheduler configuration
SCHEDULER_MISFIRE_GRACE_TIME=30
SCHEDULER_MAX_WORKERS=10

# Timezone
TZ=Europe/Chisinau
```

### IDE Configuration

**VS Code Settings** (`.vscode/settings.json`):
```json
{
  "python.defaultInterpreterPath": "./venv/bin/python",
  "python.testing.pytestEnabled": true,
  "python.testing.pytestArgs": ["tests/"],
  "python.linting.enabled": true,
  "python.linting.flake8Enabled": true,
  "python.formatting.provider": "black",
  "python.sortImports.args": ["--profile", "black"]
}
```

**PyCharm Configuration:**
- Set project interpreter to `venv/bin/python`
- Enable pytest as test runner
- Configure code style: Black with line length 88
- Enable type checking with mypy

## Architecture Deep Dive

### System Components

```
yoda-tasker/
├── api/                         # FastAPI REST service
│   ├── main.py                  # Application entry and middleware
│   ├── dependencies.py          # Database, auth, and injection
│   ├── models.py                # SQLAlchemy ORM models
│   ├── schemas.py               # Pydantic request/response schemas
│   └── routes/                  # Modular route handlers
│       ├── tasks.py             # Task CRUD and management
│       ├── runs.py              # Execution history and monitoring
│       ├── events.py            # Event publishing and streams
│       └── agents.py            # Agent management (admin only)
├── engine/                      # Pipeline execution core
│   ├── executor.py              # Deterministic pipeline runner
│   ├── template.py              # ${var} template rendering
│   ├── registry.py              # Tool catalog management
│   ├── mcp_client.py            # Model Context Protocol bridge
│   └── rruler.py                # RFC-5545 RRULE processing
├── scheduler/                   # APScheduler temporal logic
│   └── tick.py                  # Schedule evaluation and due_work creation
├── workers/                     # Distributed job processors
│   ├── runner.py                # SKIP LOCKED work leasing
│   ├── coordinator.py           # Worker health and coordination
│   ├── cli.py                   # Worker management commands
│   └── config.py                # Worker configuration
├── observability/               # Monitoring and alerting
│   ├── metrics.py               # Prometheus metrics collection
│   ├── logging.py               # Structured JSON logging
│   ├── health.py                # System health monitoring
│   └── alerts.py                # Alert rule management
├── migrations/                  # Database schema management
│   └── version_0001.sql         # Initial PostgreSQL schema
└── tests/                       # Comprehensive test suite
    ├── unit/                    # Unit tests for individual components
    ├── integration/             # End-to-end workflow tests
    └── load/                    # Performance and scaling tests
```

### Key Architectural Patterns

#### 1. SKIP LOCKED Job Distribution

Safe concurrent job processing using PostgreSQL's `FOR UPDATE SKIP LOCKED`:

```python
# workers/runner.py
def lease_one():
    with engine.begin() as tx:
        row = tx.execute(text("""
            SELECT id, task_id, run_at
            FROM due_work
            WHERE run_at <= now()
              AND (locked_until IS NULL OR locked_until < now())
            ORDER BY run_at ASC
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        """)).fetchone()
        
        if not row:
            return None
            
        # Lease the work item
        locked_until = datetime.now(timezone.utc) + timedelta(seconds=LEASE_SECONDS)
        tx.execute(text("""
            UPDATE due_work
            SET locked_until=:lu, locked_by=:lb
            WHERE id=:id
        """), {"lu": locked_until, "lb": WORKER_ID, "id": row.id})
        
        return dict(row._mapping)
```

#### 2. Template Variable Resolution

Centralized template rendering with JMESPath expressions:

```python
# engine/template.py
def render_templates(obj, context):
    """Recursively render ${variable.path} expressions."""
    if isinstance(obj, dict):
        return {k: render_templates(v, context) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [render_templates(x, context) for x in obj]
    elif isinstance(obj, str):
        def replace_var(match):
            expr = match.group(1)
            return str(jmespath.search(expr, context))
        return TEMPLATE_PATTERN.sub(replace_var, obj)
    return obj
```

#### 3. Pipeline Execution Engine

Deterministic step-by-step execution with validation:

```python
# engine/executor.py
def run_pipeline(task: dict) -> dict:
    payload = task["payload"]
    pipeline = payload.get("pipeline", [])
    context = {"now": datetime.now(timezone.utc).isoformat() + 'Z', 
               "params": payload.get("params", {}), 
               "steps": {}}

    for step in pipeline:
        # Skip conditional steps
        if "if" in step and not evaluate_condition(step["if"], context):
            continue

        # Resolve template variables  
        args = render_templates(step.get("with", {}), context)
        
        # Validate input schema
        tool = get_tool(step["uses"])
        validate(instance=args, schema=tool["input_schema"])
        
        # Execute tool via MCP
        result = call_tool(step["uses"], args, timeout=step.get("timeout_seconds", 30))
        
        # Validate output schema
        validate(instance=result, schema=tool["output_schema"])
        
        # Save result for future steps
        if "save_as" in step:
            context["steps"][step["save_as"]] = result

    return context
```

## Development Workflows

### Running Individual Components

**API Server (Development Mode):**
```bash
# With hot reload
uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload

# Or using the convenience script
python run_api.py
```

**Scheduler Service:**
```bash
# Run scheduler with debug logging
export LOG_LEVEL=debug
python scheduler/tick.py
```

**Worker Processes:**
```bash
# Single worker with debug output
export LOG_LEVEL=debug
python workers/runner.py

# Multiple workers for testing concurrency
for i in {1..3}; do python workers/runner.py & done
```

**Pipeline Testing:**
```bash
# Test pipeline execution directly
python -c "
from engine.executor import run_pipeline
task = {
    'payload': {
        'pipeline': [
            {'id': 'test', 'uses': 'echo.message', 'with': {'text': 'Hello World'}}
        ]
    }
}
result = run_pipeline(task)
print(result)
"
```

### Database Development

**Schema Management:**
```bash
# Apply migrations
docker compose exec postgres psql -U orchestrator orchestrator < migrations/version_0001.sql

# Create new migration
# 1. Make schema changes in new migration file
# 2. Test with clean database
# 3. Update version in filename

# Database console access
docker compose exec postgres psql -U orchestrator orchestrator
```

**Common Database Operations:**
```sql
-- Check queue status
SELECT COUNT(*) as pending, 
       MIN(run_at) as oldest,
       MAX(run_at) as newest
FROM due_work 
WHERE run_at <= now();

-- View active tasks
SELECT id, title, status, schedule_kind, next_run
FROM task 
WHERE status = 'active'
ORDER BY priority DESC, created_at ASC;

-- Monitor execution history
SELECT t.title, tr.success, tr.started_at, tr.duration_ms
FROM task_run tr
JOIN task t ON tr.task_id = t.id
ORDER BY tr.started_at DESC
LIMIT 10;

-- Clean up test data
TRUNCATE TABLE task_run, due_work, task RESTART IDENTITY CASCADE;
```

### Testing Framework

**Test Structure:**
```
tests/
├── conftest.py              # Pytest fixtures and configuration
├── unit/                    # Fast, isolated unit tests
│   ├── test_template_rendering.py
│   ├── test_rrule_processing.py
│   └── test_worker_concurrency.py
├── integration/             # End-to-end workflow tests
│   └── test_end_to_end_workflows.py
├── load/                    # Performance and scaling tests
│   └── test_performance_benchmarks.py
└── comprehensive_test_suite.py  # Full system validation
```

**Running Tests:**
```bash
# All tests with coverage
python -m pytest tests/ -v --cov=./ --cov-report=html

# Specific test categories
python -m pytest tests/unit/ -v              # Unit tests only
python -m pytest tests/integration/ -v       # Integration tests
python -m pytest tests/load/ -v             # Performance tests

# Test with different configurations
pytest tests/ -v --log-level=DEBUG          # Verbose logging
pytest tests/ -v -x                         # Stop on first failure
pytest tests/ -v -k "test_pipeline"         # Run specific test pattern
```

**Writing Tests:**

**Unit Test Example:**
```python
# tests/unit/test_template_rendering.py
import pytest
from engine.template import render_templates

class TestTemplateRendering:
    def test_simple_variable_substitution(self):
        template = {"message": "Hello ${name}!"}
        context = {"name": "World"}
        result = render_templates(template, context)
        assert result == {"message": "Hello World!"}

    def test_nested_object_access(self):
        template = {"temp": "${weather.temperature}°C"}
        context = {"weather": {"temperature": 15, "conditions": "sunny"}}
        result = render_templates(template, context)
        assert result == {"temp": "15°C"}

    def test_step_output_access(self):
        template = {"summary": "${steps.weather.summary}"}
        context = {"steps": {"weather": {"summary": "Partly cloudy"}}}
        result = render_templates(template, context)
        assert result == {"summary": "Partly cloudy"}
```

**Integration Test Example:**
```python
# tests/integration/test_end_to_end_workflows.py
import pytest
from datetime import datetime, timezone
from api.main import app
from fastapi.testclient import TestClient

@pytest.fixture
def client():
    return TestClient(app)

class TestTaskWorkflow:
    def test_create_and_execute_task(self, client, db_session):
        # Create a simple task
        task_data = {
            "title": "Test Task",
            "description": "Integration test task",
            "schedule_kind": "once", 
            "schedule_expr": datetime.now(timezone.utc).isoformat(),
            "payload": {
                "pipeline": [
                    {"id": "echo", "uses": "echo.message", "with": {"text": "test"}}
                ]
            },
            "created_by": "00000000-0000-0000-0000-000000000001"
        }
        
        # Create task via API
        response = client.post("/tasks", json=task_data,
                             headers={"Authorization": "Bearer system-agent"})
        assert response.status_code == 201
        task_id = response.json()["id"]
        
        # Trigger immediate execution
        response = client.post(f"/tasks/{task_id}/run_now",
                             headers={"Authorization": "Bearer system-agent"})
        assert response.status_code == 200
        
        # Wait for execution and check results
        # (Implementation depends on test execution strategy)
```

### Code Quality and Standards

**Code Formatting:**
```bash
# Format code with Black
black api/ engine/ scheduler/ workers/ tests/

# Sort imports with isort
isort api/ engine/ scheduler/ workers/ tests/ --profile black

# Check formatting
black --check api/ engine/ scheduler/ workers/ tests/
```

**Type Checking:**
```bash
# Run mypy type checking
mypy api/ engine/ scheduler/ workers/

# Check specific module
mypy api/main.py --strict
```

**Linting:**
```bash
# Run flake8 linting  
flake8 api/ engine/ scheduler/ workers/ tests/

# Check specific issues
flake8 api/ --select=E9,F63,F7,F82  # Critical errors only
```

**Pre-commit Hooks:**
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/psf/black
    rev: 23.3.0
    hooks:
      - id: black
  - repo: https://github.com/PyCQA/isort
    rev: 5.12.0
    hooks:
      - id: isort
        args: ["--profile", "black"]
  - repo: https://github.com/PyCQA/flake8
    rev: 6.0.0
    hooks:
      - id: flake8
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.3.0
    hooks:
      - id: mypy
```

## Extending the System

### Adding New API Endpoints

**1. Define Pydantic Schemas:**
```python
# api/schemas.py
class CustomOperationRequest(BaseModel):
    operation_type: str
    parameters: Dict[str, Any]
    timeout_seconds: int = 30

class CustomOperationResponse(BaseModel):
    success: bool
    result: Dict[str, Any]
    duration_ms: float
```

**2. Create Route Handler:**
```python
# api/routes/custom.py
from fastapi import APIRouter, Depends, HTTPException
from ..dependencies import get_db, get_current_agent
from ..schemas import CustomOperationRequest, CustomOperationResponse

router = APIRouter(prefix="/custom", tags=["custom"])

@router.post("/operation", response_model=CustomOperationResponse)
async def execute_custom_operation(
    request: CustomOperationRequest,
    db: Session = Depends(get_db),
    agent: Agent = Depends(get_current_agent)
) -> CustomOperationResponse:
    # Implementation here
    return CustomOperationResponse(
        success=True,
        result={"message": "Operation completed"},
        duration_ms=150.0
    )
```

**3. Register Router:**
```python
# api/main.py
from .routes import custom

app.include_router(custom.router)
```

### Adding New Pipeline Tools

**1. Update Tool Catalog:**
```json
// catalogs/tools.json
{
  "address": "my-service.my-tool",
  "transport": "http",
  "endpoint": "http://my-service:8080/tools/my-tool",
  "input_schema": {
    "type": "object",
    "required": ["param1"],
    "properties": {
      "param1": {"type": "string"},
      "param2": {"type": "integer", "default": 100}
    }
  },
  "output_schema": {
    "type": "object", 
    "required": ["result"],
    "properties": {
      "result": {"type": "string"},
      "metadata": {"type": "object"}
    }
  },
  "timeout_seconds": 30,
  "scopes": ["my-service.read"]
}
```

**2. Implement MCP Tool Service:**
```python
# Example external MCP service
from mcp import Tool, ToolResult

class MyCustomTool(Tool):
    name = "my-tool"
    description = "Custom tool for specific operations"
    
    async def execute(self, param1: str, param2: int = 100) -> ToolResult:
        # Tool implementation
        result = f"Processed {param1} with factor {param2}"
        
        return ToolResult(
            success=True,
            data={"result": result, "metadata": {"param1": param1, "param2": param2}}
        )
```

**3. Test Tool Integration:**
```python
# Test pipeline using new tool
test_pipeline = {
    "pipeline": [
        {
            "id": "custom_step",
            "uses": "my-service.my-tool", 
            "with": {"param1": "test-value", "param2": 200},
            "save_as": "custom_result"
        },
        {
            "id": "use_result",
            "uses": "echo.message",
            "with": {"text": "Result: ${steps.custom_result.result}"}
        }
    ]
}
```

### Adding Metrics and Monitoring

**1. Define Custom Metrics:**
```python
# observability/metrics.py
from prometheus_client import Counter, Histogram, Gauge

class CustomMetrics:
    def __init__(self, registry):
        self.custom_operations = Counter(
            'orchestrator_custom_operations_total',
            'Total custom operations executed',
            ['operation_type', 'agent_id'],
            registry=registry
        )
        
        self.custom_duration = Histogram(
            'orchestrator_custom_duration_seconds',
            'Duration of custom operations',
            ['operation_type'],
            registry=registry
        )

# Add to main metrics class
orchestrator_metrics.custom = CustomMetrics(orchestrator_metrics.registry)
```

**2. Record Metrics:**
```python
# In your custom route handler
from observability.metrics import orchestrator_metrics

@router.post("/operation")
async def execute_custom_operation(request, agent):
    start_time = time.time()
    
    try:
        # Execute operation
        result = await perform_operation(request)
        
        # Record success metric
        orchestrator_metrics.custom.custom_operations.labels(
            operation_type=request.operation_type,
            agent_id=str(agent.id)
        ).inc()
        
        return result
        
    finally:
        # Record duration
        duration = time.time() - start_time
        orchestrator_metrics.custom.custom_duration.labels(
            operation_type=request.operation_type
        ).observe(duration)
```

**3. Create Grafana Dashboard:**
```json
{
  "title": "Custom Operations",
  "panels": [
    {
      "title": "Operation Rate",
      "type": "graph",
      "targets": [
        {
          "expr": "rate(orchestrator_custom_operations_total[5m])",
          "legendFormat": "{{operation_type}}"
        }
      ]
    },
    {
      "title": "Operation Duration",
      "type": "graph", 
      "targets": [
        {
          "expr": "histogram_quantile(0.95, rate(orchestrator_custom_duration_seconds_bucket[5m]))",
          "legendFormat": "95th percentile"
        }
      ]
    }
  ]
}
```

## Contributing Guidelines

### Development Process

1. **Fork Repository:** Create your own fork for development
2. **Create Branch:** Use descriptive branch names: `feature/add-custom-tool` or `fix/worker-memory-leak`
3. **Development:** Write code following established patterns
4. **Testing:** Ensure all tests pass and add tests for new features  
5. **Documentation:** Update relevant documentation
6. **Pull Request:** Submit PR with detailed description

### Commit Message Format

```
type(scope): brief description

Detailed explanation of changes, why they were made,
and any breaking changes or migration requirements.

Fixes #123
```

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`  
**Scopes:** `api`, `engine`, `scheduler`, `workers`, `observability`, `tests`

**Examples:**
```
feat(api): add custom operation endpoints with validation

Add new /custom/operation endpoint to support specialized
agent operations with timeout configuration and result caching.

Includes input/output validation, metrics collection, and
comprehensive test coverage.

fix(workers): resolve memory leak in pipeline execution

Pipeline context objects were not being properly cleaned up
after execution, causing gradual memory growth in long-running
worker processes.

Fixes #456
```

### Code Review Checklist

**Functionality:**
- [ ] Code works as intended and handles edge cases
- [ ] All tests pass and new tests added for new features
- [ ] Error handling is comprehensive and user-friendly
- [ ] Performance impact is acceptable

**Code Quality:**
- [ ] Follows established architectural patterns  
- [ ] Code is readable and well-documented
- [ ] Type hints are used appropriately
- [ ] No security vulnerabilities introduced

**Integration:**
- [ ] Database migrations are backward-compatible
- [ ] API changes maintain backward compatibility
- [ ] Observability (logging/metrics) is properly implemented
- [ ] Documentation is updated

### Release Process

**Version Numbering:** Semantic versioning (MAJOR.MINOR.PATCH)

**Release Steps:**
1. **Feature Complete:** All planned features implemented and tested
2. **Quality Gate:** All tests pass, code review completed
3. **Documentation:** All documentation updated
4. **Version Bump:** Update version in `pyproject.toml` and documentation
5. **Tag Release:** Create Git tag with version number
6. **Build Images:** Create Docker images for release
7. **Deploy:** Deploy to staging environment for final validation
8. **Production:** Deploy to production with monitoring

## Performance Considerations

### Database Optimization

**Query Performance:**
```sql
-- Analyze query performance
EXPLAIN ANALYZE SELECT * FROM due_work 
WHERE run_at <= now() AND locked_until IS NULL
ORDER BY run_at ASC LIMIT 10;

-- Update statistics after bulk operations
ANALYZE due_work;
ANALYZE task_run;

-- Monitor index usage
SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read
FROM pg_stat_user_indexes 
ORDER BY idx_scan DESC;
```

**Connection Pool Tuning:**
```python
# api/dependencies.py - Optimize for your workload
engine = create_engine(
    DATABASE_URL,
    pool_size=20,        # Base connections
    max_overflow=30,     # Additional connections under load
    pool_pre_ping=True,  # Validate connections
    pool_recycle=3600,   # Refresh connections hourly
    echo=False           # Set True for SQL debugging
)
```

### Worker Scaling Guidelines

**Horizontal Scaling:**
- **CPU-bound workloads:** Workers = CPU cores
- **I/O-bound workloads:** Workers = 2-4x CPU cores  
- **Mixed workloads:** Start with 2x CPU cores, monitor queue depth

**Vertical Scaling:**
- **Memory:** 1GB base + 256MB per concurrent pipeline
- **CPU:** 1 core per 10-20 concurrent simple operations
- **Network:** Consider latency to external services

### API Performance

**Response Time Targets:**
- **Health checks:** < 10ms
- **Task CRUD:** < 100ms
- **Complex queries:** < 500ms
- **Bulk operations:** < 2s

**Optimization Techniques:**
- Use database indexes for common query patterns
- Implement response caching for read-heavy endpoints  
- Paginate large result sets
- Use async database drivers properly

## Security Considerations

### Development Security

**Environment Variables:**
- Never commit secrets to version control
- Use `.env` files for local development
- Use secret management systems in production

**Database Security:**
- Use parameterized queries (SQLAlchemy handles this)
- Validate all inputs at API boundaries
- Implement proper access controls via agent scopes

**API Security:**
- Validate all request payloads with Pydantic
- Implement rate limiting for abuse prevention
- Use HTTPS in production (not handled by application)
- Log security events for audit trails

### Production Security Checklist

- [ ] All services run as non-root users
- [ ] Database credentials use strong, unique passwords  
- [ ] API implements proper authentication and authorization
- [ ] Rate limiting prevents abuse
- [ ] Security headers configured in reverse proxy
- [ ] Regular security updates for base images
- [ ] Audit logging enabled and monitored
- [ ] Network access properly restricted

This development guide provides the foundation for extending and contributing to the Ordinaut. Follow these patterns and guidelines to maintain system reliability, performance, and security.