# Ordinaut - Test Infrastructure

## Purpose & Mission
Comprehensive test infrastructure ensuring >99.9% reliability of the Ordinaut through systematic testing at all architectural layers. **CURRENT STATE**: Tool and MCP-related tests are disabled due to removal of these components from the core system. Tests will be re-enabled when tools are implemented as extensions.

## \u26a0\ufe0f **Current Test State (August 2025)**

### **Active Testing (Working)**
- \u2705 **Pure Scheduler**: RRULE processing, timezone handling, APScheduler integration
- \u2705 **Database Operations**: PostgreSQL SKIP LOCKED patterns, task/run persistence  
- \u2705 **Pipeline Processing**: Template resolution (${steps.x.y}), conditional logic, structure validation
- \u2705 **Tool Simulation**: Proper context preservation, logging, metrics collection
- \u2705 **Worker Coordination**: Concurrent processing, job leasing, fault tolerance
- \u2705 **API Endpoints**: FastAPI routes, authentication, health checks
- \u2705 **Observability**: Monitoring, metrics, structured logging

### **Disabled Testing (Awaiting Extensions)**
- \u274c **Tool Catalog**: Registry, validation, scope checking (registry.py simplified)
- \u274c **MCP Integration**: Client transports, tool discovery, JSON-RPC calls (mcp_client.py deleted)
- \u274c **Real Tool Execution**: HTTP/stdio/MCP transports (replaced with simulation)
- \u274c **Tool Schema Validation**: Input/output validation for external tools
- \u274c **MCP Server Communication**: Protocol compliance, error handling

### **Test Files Status**
```python
# tests/test_pipeline_engine.py - PARTIALLY DISABLED
# Lines 30-32: Commented out imports
# TODO: Tool and MCP functionality removed - re-enable when implemented as extensions
# from engine.registry import ToolRegistry, ToolNotFoundError  # DISABLED
# from engine.mcp_client import MCPClient, MCPError           # DISABLED

# Tests now focus on:
# - Pipeline structure processing \u2705
# - Template variable resolution \u2705  
# - Conditional execution logic \u2705
# - Tool simulation behavior \u2705
```

**Re-enablement Plan**: When MCP and tool functionality are implemented as extensions, these test imports will be updated to reference the extension modules instead of the removed core modules.

## Test Architecture & Organization

### Directory Structure (Enforced)
```
tests/
├── CLAUDE.md                    # This file - test infrastructure documentation
├── conftest.py                  # Shared pytest fixtures and configuration
├── requirements.txt             # Test-specific dependencies
├── unit/                        # Fast, isolated unit tests (<1s each)
│   ├── test_engine/             # Pipeline execution engine tests
│   │   ├── test_executor.py     # Deterministic pipeline execution
│   │   ├── test_template.py     # ${steps.x.y} variable resolution
│   │   ├── test_registry.py     # Database task loading (tool catalog removed)
│   │   └── test_rruler.py       # RRULE → next occurrence calculation
│   ├── test_api/                # FastAPI service tests
│   │   ├── test_routes.py       # HTTP endpoint behavior
│   │   ├── test_models.py       # Database model validation
│   │   └── test_schemas.py      # Pydantic schema validation
│   ├── test_scheduler/          # APScheduler service tests
│   │   └── test_tick.py         # Scheduler daemon logic
│   └── test_workers/            # Job processor tests
│       └── test_runner.py       # SKIP LOCKED work leasing
├── integration/                 # Multi-component integration tests
│   ├── test_database_ops.py     # PostgreSQL ACID compliance testing
│   ├── test_scheduler_integration.py  # APScheduler + PostgreSQL integration
│   ├── test_worker_coordination.py   # Multi-worker concurrency safety
│   ├── test_mcp_integration.py  # Model Context Protocol bridge testing
│   ├── test_pipeline_execution.py    # End-to-end pipeline workflows
│   └── test_api_integration.py  # FastAPI + database integration
├── load/                        # Performance and load testing
│   ├── test_concurrent_workers.py    # Worker scaling and throughput
│   ├── test_database_performance.py  # PostgreSQL query performance
│   ├── test_scheduler_accuracy.py    # Timing precision under load
│   └── test_memory_usage.py     # Resource consumption profiling
├── e2e/                         # End-to-end system testing
│   ├── test_complete_workflows.py    # Full agent orchestration scenarios
│   ├── test_failure_scenarios.py     # Chaos engineering and fault injection
│   └── test_production_scenarios.py  # Real-world usage patterns
├── fixtures/                    # Test data and reusable test components
│   ├── database/                # Database test fixtures and schemas
│   ├── pipelines/               # Sample pipeline definitions
│   ├── schedules/               # RRULE and cron test cases
│   └── tools/                   # Mock MCP tool implementations
└── utils/                       # Testing utilities and helpers
    ├── db_utils.py              # Database setup/teardown helpers
    ├── mock_tools.py            # Mock MCP tool implementations
    ├── time_utils.py            # Time manipulation for schedule testing
    └── assertions.py            # Custom assertion helpers
```

## Testing Philosophy & Standards

### Quality Gates (Non-Negotiable)
- **>95% test coverage** across all components
- **100% critical path coverage** for scheduling and execution
- **Zero flaky tests** - all tests pass consistently
- **Performance regression detection** with automated benchmarks
- **Security vulnerability scanning** in all test runs

### Test Categorization

#### Unit Tests (`tests/unit/`)
**Purpose**: Fast, isolated testing of individual components
- **Execution time**: <1 second per test
- **Dependencies**: None (fully mocked)
- **Coverage target**: >98% line coverage
- **Test count**: ~200 active tests (tool/MCP tests disabled, ~300 tests to re-enable with extensions)

```python
# Example: tests/unit/test_engine/test_template.py
def test_template_variable_resolution():
    context = {
        "steps": {"weather": {"temp": 22, "condition": "sunny"}},
        "params": {"user": "alice"}
    }
    
    template = "Weather is ${steps.weather.condition} at ${steps.weather.temp}°C for ${params.user}"
    result = render_template(template, context)
    
    assert result == "Weather is sunny at 22°C for alice"
```

#### Integration Tests (`tests/integration/`)
**Purpose**: Multi-component interaction validation
- **Execution time**: <10 seconds per test
- **Dependencies**: Real database, Redis (test instances)
- **Coverage target**: >90% integration scenario coverage
- **Test count**: ~50 active integration scenarios (tool/MCP integration tests disabled)

```python
# Example: tests/integration/test_worker_coordination.py
@pytest.mark.integration
async def test_multiple_workers_no_duplicate_processing():
    # Create 10 due tasks
    tasks = await create_test_tasks(count=10)
    
    # Start 5 workers simultaneously
    workers = [WorkerProcess() for _ in range(5)]
    await asyncio.gather(*[w.start() for w in workers])
    
    # Wait for all tasks to complete
    await wait_for_completion(tasks, timeout=30)
    
    # Verify each task processed exactly once
    for task in tasks:
        runs = await get_task_runs(task.id)
        assert len(runs) == 1, f"Task {task.id} processed {len(runs)} times"
```

#### Load Tests (`tests/load/`)
**Purpose**: Performance characteristics and scaling behavior
- **Execution time**: 1-5 minutes per test
- **Dependencies**: Production-like environment
- **Performance targets**: Document SLA compliance
- **Test scenarios**: Scale, stress, endurance, spike testing

```python
# Example: tests/load/test_concurrent_workers.py
@pytest.mark.load
async def test_thousand_concurrent_tasks():
    """Verify system handles 1000 concurrent tasks within performance SLA"""
    
    # Create 1000 tasks scheduled for immediate execution
    tasks = await create_test_tasks(
        count=1000,
        schedule_time=datetime.now(),
        complexity="medium"
    )
    
    start_time = time.time()
    
    # Start 20 workers
    workers = [WorkerProcess() for _ in range(20)]
    await asyncio.gather(*[w.start() for w in workers])
    
    # Wait for all tasks to complete
    await wait_for_completion(tasks, timeout=300)  # 5 minute timeout
    
    execution_time = time.time() - start_time
    
    # Performance assertions
    assert execution_time < 120, f"Took {execution_time}s, expected <120s"
    assert all(r.success for r in await get_all_runs()), "All tasks must succeed"
    
    # Verify throughput SLA
    throughput = len(tasks) / execution_time
    assert throughput >= 10, f"Throughput {throughput} tasks/s, expected >=10"
```

#### End-to-End Tests (`tests/e2e/`)
**Purpose**: Complete system validation with real scenarios
- **Execution time**: 5-30 minutes per test
- **Dependencies**: Full system deployment
- **Coverage target**: All critical user journeys
- **Test scenarios**: Real agent workflows and failure recovery

```python
# Example: tests/e2e/test_complete_workflows.py
@pytest.mark.e2e
async def test_morning_briefing_workflow():
    """Complete morning briefing pipeline execution"""
    
    # Create morning briefing task with real schedule
    task = await create_task({
        "title": "Morning Briefing",
        "schedule_kind": "rrule",
        "schedule_expr": "FREQ=DAILY;BYHOUR=8;BYMINUTE=0",
        "timezone": "America/New_York",
        "payload": {
            "pipeline": [
                {"id": "weather", "uses": "weather.forecast", "with": {"city": "New York"}},
                {"id": "calendar", "uses": "calendar.today", "with": {}},
                {"id": "brief", "uses": "llm.summarize", "with": {
                    "weather": "${steps.weather}",
                    "calendar": "${steps.calendar}"
                }},
                {"id": "notify", "uses": "telegram.send", "with": {
                    "message": "${steps.brief.summary}"
                }}
            ]
        }
    })
    
    # Trigger immediate execution
    run = await trigger_task(task.id)
    
    # Wait for completion with detailed monitoring
    result = await wait_for_run_completion(run.id, timeout=60)
    
    # Verify successful execution
    assert result.success, f"Run failed: {result.error}"
    assert len(result.step_results) == 4, "All pipeline steps executed"
    
    # Verify each step succeeded
    for step_name in ["weather", "calendar", "brief", "notify"]:
        step_result = result.step_results[step_name]
        assert step_result.success, f"Step {step_name} failed: {step_result.error}"
    
    # Verify output quality
    brief_output = result.step_results["brief"].output
    assert "weather" in brief_output["summary"].lower()
    assert "calendar" in brief_output["summary"].lower()
```

## Testing Patterns & Best Practices

### Database Testing Pattern
```python
# conftest.py - Shared database fixture
@pytest.fixture(scope="function")
async def test_db():
    """Isolated test database for each test"""
    db_name = f"test_orchestrator_{uuid.uuid4().hex[:8]}"
    
    # Create test database
    await create_database(db_name)
    
    # Run migrations
    await run_migrations(db_name)
    
    # Provide database connection
    db = await connect_database(db_name)
    
    yield db
    
    # Cleanup
    await db.close()
    await drop_database(db_name)

# Test using database
async def test_task_creation(test_db):
    task_id = await create_task(test_db, {
        "title": "Test Task",
        "schedule_kind": "once", 
        "schedule_expr": "2024-01-01T10:00:00Z"
    })
    
    task = await get_task(test_db, task_id)
    assert task.title == "Test Task"
```

### Time Manipulation Pattern
```python
# utils/time_utils.py
class TimeController:
    """Control time for deterministic schedule testing"""
    
    def __init__(self):
        self.frozen_time = None
    
    def freeze_at(self, timestamp: datetime):
        self.frozen_time = timestamp
        
    def advance_by(self, delta: timedelta):
        if self.frozen_time:
            self.frozen_time += delta
            
    def now(self) -> datetime:
        return self.frozen_time or datetime.now()

# Test using time control
async def test_schedule_accuracy():
    time_controller = TimeController()
    time_controller.freeze_at(datetime(2024, 1, 1, 8, 0, 0))
    
    # Create task scheduled for 8:30 AM
    task = await create_task({
        "schedule_kind": "once",
        "schedule_expr": "2024-01-01T08:30:00Z"
    })
    
    # Verify not due yet
    due_tasks = await get_due_tasks(time_controller.now())
    assert task.id not in [t.id for t in due_tasks]
    
    # Advance time to 8:30 AM
    time_controller.advance_by(timedelta(minutes=30))
    
    # Verify now due
    due_tasks = await get_due_tasks(time_controller.now())
    assert task.id in [t.id for t in due_tasks]
```

### Mock Tool Pattern
```python
# utils/mock_tools.py
class MockTool:
    """Deterministic tool for testing"""
    
    def __init__(self, name: str, output: dict, delay: float = 0):
        self.name = name
        self.output = output  
        self.delay = delay
        self.call_count = 0
        self.call_history = []
    
    async def __call__(self, **kwargs):
        self.call_count += 1
        self.call_history.append(kwargs)
        
        if self.delay:
            await asyncio.sleep(self.delay)
            
        return self.output

# Test using mock tools
async def test_pipeline_execution_with_mocks():
    # Setup mock tools
    weather_tool = MockTool("weather.forecast", {"temp": 22, "condition": "sunny"})
    notify_tool = MockTool("telegram.send", {"message_id": 12345})
    
    tool_registry = {"weather.forecast": weather_tool, "telegram.send": notify_tool}
    
    # Execute pipeline
    result = await execute_pipeline([
        {"id": "weather", "uses": "weather.forecast", "with": {"city": "NYC"}},
        {"id": "notify", "uses": "telegram.send", "with": {"message": "Weather: ${steps.weather.condition}"}}
    ], tool_registry)
    
    # Verify tool calls
    assert weather_tool.call_count == 1
    assert weather_tool.call_history[0] == {"city": "NYC"}
    
    assert notify_tool.call_count == 1
    assert notify_tool.call_history[0] == {"message": "Weather: sunny"}
```

### Concurrency Testing Pattern
```python
async def test_concurrent_worker_safety():
    """Verify SKIP LOCKED prevents duplicate processing"""
    
    # Create 100 tasks ready for processing
    tasks = await create_test_tasks(count=100)
    
    # Track processed task IDs across all workers
    processed_tasks = set()
    processing_lock = asyncio.Lock()
    
    async def worker_process():
        while True:
            # Lease work using SKIP LOCKED
            work = await lease_work()
            if not work:
                break
                
            # Track this task as processed
            async with processing_lock:
                assert work.task_id not in processed_tasks, f"Duplicate processing of task {work.task_id}"
                processed_tasks.add(work.task_id)
            
            # Simulate work execution
            await asyncio.sleep(0.1)
            await mark_work_complete(work.id)
    
    # Run 10 workers concurrently
    workers = [worker_process() for _ in range(10)]
    await asyncio.gather(*workers)
    
    # Verify all tasks processed exactly once
    assert len(processed_tasks) == 100, f"Expected 100 tasks, processed {len(processed_tasks)}"
```

## Performance Benchmarks & SLAs

### Service Level Agreements
```python
# Performance targets enforced by load tests
PERFORMANCE_SLAS = {
    "api_response_time": {
        "p50": 50,    # 50ms median response time
        "p95": 200,   # 200ms 95th percentile
        "p99": 500    # 500ms 99th percentile
    },
    "task_scheduling_accuracy": {
        "drift_tolerance": 1000,  # 1 second maximum drift
        "success_rate": 0.999     # 99.9% successful scheduling
    },
    "pipeline_execution": {
        "simple_pipeline": 2000,   # 2s for simple pipelines
        "complex_pipeline": 10000, # 10s for complex pipelines
        "timeout_handling": 30000  # 30s maximum with timeouts
    },
    "worker_throughput": {
        "tasks_per_second": 10,    # 10 tasks/second minimum
        "concurrent_workers": 50,  # Support 50 concurrent workers
        "queue_processing": 1000   # 1000 queued tasks within 2 minutes
    },
    "database_performance": {
        "skip_locked_latency": 10, # 10ms SKIP LOCKED queries
        "connection_pool": 100,    # 100 concurrent connections
        "query_timeout": 5000      # 5s maximum query time
    }
}

# Load test enforcement example
@pytest.mark.load
async def test_api_response_time_sla():
    """Verify API endpoints meet response time SLA under load"""
    
    # Generate load: 100 concurrent requests
    tasks = []
    for _ in range(100):
        tasks.append(make_api_request("/tasks", method="GET"))
    
    start_time = time.time()
    responses = await asyncio.gather(*tasks)
    execution_time = time.time() - start_time
    
    # Calculate response time percentiles
    response_times = [r.response_time_ms for r in responses]
    p50 = np.percentile(response_times, 50)
    p95 = np.percentile(response_times, 95)
    p99 = np.percentile(response_times, 99)
    
    # Assert SLA compliance
    assert p50 <= PERFORMANCE_SLAS["api_response_time"]["p50"]
    assert p95 <= PERFORMANCE_SLAS["api_response_time"]["p95"] 
    assert p99 <= PERFORMANCE_SLAS["api_response_time"]["p99"]
    
    # All requests must succeed
    assert all(r.status_code == 200 for r in responses)
```

### Memory Usage Testing
```python
@pytest.mark.load
async def test_memory_usage_under_load():
    """Verify memory usage stays within acceptable bounds"""
    
    initial_memory = get_process_memory()
    
    # Create and process 10,000 tasks
    tasks = await create_test_tasks(count=10000)
    await process_all_tasks(tasks)
    
    peak_memory = get_process_memory()
    memory_growth = peak_memory - initial_memory
    
    # Memory growth should be reasonable (less than 500MB for 10k tasks)
    assert memory_growth < 500 * 1024 * 1024, f"Memory grew by {memory_growth / 1024 / 1024:.1f}MB"
    
    # Force garbage collection and measure cleanup
    gc.collect()
    await asyncio.sleep(1)
    final_memory = get_process_memory()
    
    # Memory should be reclaimed
    memory_retained = final_memory - initial_memory
    assert memory_retained < 50 * 1024 * 1024, f"Retained {memory_retained / 1024 / 1024:.1f}MB after cleanup"
```

## Continuous Integration & Test Execution

### Test Execution Strategy
```yaml
# .github/workflows/tests.yml (CI/CD integration)
name: Test Suite
on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run Unit Tests
        run: pytest tests/unit/ -v --cov=. --cov-report=xml
        timeout-minutes: 5
      
  integration-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      redis:
        image: redis:7
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v3
      - name: Run Integration Tests  
        run: pytest tests/integration/ -v
        timeout-minutes: 15
        
  load-tests:
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v3
      - name: Run Load Tests
        run: pytest tests/load/ -v --benchmark-json=benchmark.json
        timeout-minutes: 30
        
  e2e-tests:
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v3
      - name: Deploy Test Environment
        run: docker-compose -f ops/docker-compose.test.yml up -d
      - name: Run E2E Tests
        run: pytest tests/e2e/ -v
        timeout-minutes: 45
```

### Local Test Execution
```bash
# Run all tests with coverage
pytest --cov=. --cov-report=html --cov-report=term

# Run only unit tests (fast feedback)
pytest tests/unit/ -v

# Run integration tests with database
pytest tests/integration/ -v --db-url=postgresql://test:test@localhost/test_db

# Run load tests with benchmarks
pytest tests/load/ -v --benchmark-only

# Run specific test category
pytest -m "not slow" -v  # Skip slow tests
pytest -m "load" -v      # Run only load tests
pytest -m "e2e" -v       # Run only end-to-end tests

# Run tests with specific fixtures
pytest --fixtures test_db  # Show available fixtures
pytest -k "test_worker"     # Run tests matching pattern

# Debug failing tests
pytest --pdb -x tests/unit/test_engine/test_executor.py::test_pipeline_execution
```

### Test Configuration
```python
# conftest.py - Global test configuration
import pytest
import asyncio
import os
from pathlib import Path

# Configure test database
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "postgresql://test:test@localhost/test_orchestrator")
TEST_REDIS_URL = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/1")

# Global fixtures
@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(autouse=True)
async def cleanup_database():
    """Clean database after each test"""
    yield
    # Cleanup logic runs after each test
    await cleanup_test_data()

# Test markers
pytest_markers = [
    "unit: Fast unit tests (<1s)",
    "integration: Multi-component tests (<10s)", 
    "load: Performance and scaling tests (1-5min)",
    "e2e: End-to-end system tests (5-30min)",
    "slow: Long-running tests (>30s)",
    "requires_network: Tests needing internet access"
]

# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers"""
    for marker in pytest_markers:
        config.addinivalue_line("markers", marker)
```

## Chaos Engineering & Fault Injection

### Failure Scenario Testing
```python
# tests/e2e/test_failure_scenarios.py
@pytest.mark.e2e
async def test_database_connection_failure_recovery():
    """Verify system recovers from database connection failures"""
    
    # Start system with normal database
    system = await start_orchestrator_system()
    
    # Create tasks and verify normal operation
    tasks = await create_test_tasks(count=10)
    await wait_for_task_scheduling(tasks)
    
    # Simulate database connection failure
    await inject_database_failure(duration=30)  # 30 second outage
    
    # System should handle gracefully
    await verify_no_crashes()
    await verify_error_logging("database_connection_failed")
    
    # Create more tasks during outage (should be queued)
    outage_tasks = await create_test_tasks(count=5)
    
    # Restore database connection
    await restore_database_connection()
    
    # System should recover and process all tasks
    await wait_for_full_recovery(timeout=60)
    await verify_all_tasks_processed(tasks + outage_tasks)

@pytest.mark.e2e 
async def test_worker_crash_resilience():
    """Verify task reassignment when workers crash"""
    
    # Start system with multiple workers
    workers = await start_workers(count=5)
    
    # Create long-running tasks
    tasks = await create_test_tasks(count=20, execution_time=60)
    
    # Wait for tasks to start processing
    await wait_for_processing_start(tasks)
    
    # Randomly crash 2 workers during execution
    crashed_workers = random.sample(workers, 2)
    for worker in crashed_workers:
        await crash_worker(worker)
    
    # Verify tasks are reassigned to healthy workers
    await wait_for_task_reassignment(timeout=120)
    
    # All tasks should eventually complete
    await wait_for_completion(tasks, timeout=300)
    
    # Verify no duplicate processing occurred
    await verify_single_execution(tasks)
```

### Network Fault Testing
```python
@pytest.mark.e2e
async def test_external_api_timeout_handling():
    """Verify graceful handling of slow/failing external APIs"""
    
    # Create pipeline with external API call
    pipeline = {
        "pipeline": [
            {"id": "slow_api", "uses": "external-api.slow_endpoint", "timeout": 5},
            {"id": "fallback", "uses": "local.fallback_data", "if": "${steps.slow_api.failed}"}
        ]
    }
    
    # Configure mock API with 10 second delay (exceeds 5s timeout)
    await setup_slow_mock_api(delay=10)
    
    # Execute pipeline
    result = await execute_pipeline(pipeline)
    
    # Verify timeout handling
    assert result.steps["slow_api"].success == False
    assert "timeout" in result.steps["slow_api"].error.lower()
    
    # Verify fallback executed
    assert result.steps["fallback"].success == True
    
    # Overall pipeline should succeed with fallback
    assert result.success == True
```

## Security & Compliance Testing

### Input Validation Testing
```python
@pytest.mark.security
async def test_malicious_input_rejection():
    """Verify all inputs are properly validated and sanitized"""
    
    malicious_inputs = [
        # SQL injection attempts
        {"title": "'; DROP TABLE tasks; --"},
        
        # Template injection attempts  
        {"payload": {"pipeline": [{"uses": "${env.SECRET_KEY}"}]}},
        
        # XSS attempts in descriptions
        {"description": "<script>alert('xss')</script>"},
        
        # Path traversal in tool names
        {"payload": {"pipeline": [{"uses": "../../secrets/key"}]}},
        
        # Extremely large inputs (DoS attempts)
        {"description": "x" * 10000000},  # 10MB string
        
        # Invalid characters
        {"title": "\x00\x01\x02\x03"},
    ]
    
    for malicious_input in malicious_inputs:
        with pytest.raises(ValidationError):
            await create_task(malicious_input)
```

### Authorization Testing  
```python
@pytest.mark.security
async def test_agent_scope_enforcement():
    """Verify agents can only access resources within their scopes"""
    
    # Create agent with limited scopes
    limited_agent = await create_test_agent(scopes=["read:tasks", "write:tasks"])
    
    # Should be able to create tasks
    task_id = await create_task({"title": "Test"}, agent=limited_agent)
    assert task_id is not None
    
    # Should NOT be able to access admin functions
    with pytest.raises(PermissionError):
        await get_all_agents(agent=limited_agent)
    
    with pytest.raises(PermissionError):  
        await modify_system_settings(agent=limited_agent)
    
    # Should only see own tasks
    tasks = await list_tasks(agent=limited_agent)
    assert all(t.agent_id == limited_agent.id for t in tasks)
```

## Test Data Management

### Fixture Organization
```python
# fixtures/database/sample_tasks.py
SAMPLE_TASKS = [
    {
        "id": "morning-briefing",
        "title": "Morning Briefing",
        "description": "Daily weather and calendar summary",
        "schedule_kind": "rrule",
        "schedule_expr": "FREQ=DAILY;BYHOUR=8;BYMINUTE=0", 
        "timezone": "America/New_York",
        "payload": {
            "pipeline": [
                {"id": "weather", "uses": "weather.forecast", "with": {"city": "NYC"}},
                {"id": "calendar", "uses": "calendar.today", "with": {}},
                {"id": "notify", "uses": "telegram.send", "with": {"message": "${steps.weather.summary}"}}
            ]
        }
    },
    # ... more sample tasks
]

# fixtures/schedules/rrule_test_cases.py
RRULE_TEST_CASES = [
    {
        "description": "Every weekday at 9 AM",
        "rrule": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=9;BYMINUTE=0",
        "timezone": "America/New_York",
        "expected_occurrences": [
            "2024-01-01T14:00:00Z",  # 9 AM EST = 2 PM UTC
            "2024-01-02T14:00:00Z",
            "2024-01-03T14:00:00Z"
        ]
    },
    # ... more test cases
]
```

### Test Data Generation
```python
# utils/data_generators.py
def generate_random_task(complexity: str = "simple") -> dict:
    """Generate realistic test task data"""
    
    if complexity == "simple":
        return {
            "title": f"Test Task {uuid.uuid4().hex[:8]}",
            "description": "Generated test task",
            "schedule_kind": "once",
            "schedule_expr": (datetime.now() + timedelta(hours=1)).isoformat(),
            "payload": {
                "pipeline": [
                    {"id": "step1", "uses": "mock.tool", "with": {"param": "value"}}
                ]
            }
        }
    elif complexity == "complex":
        return {
            "title": f"Complex Task {uuid.uuid4().hex[:8]}",
            "description": "Multi-step pipeline with conditions",
            "schedule_kind": "rrule", 
            "schedule_expr": "FREQ=HOURLY;INTERVAL=2",
            "payload": {
                "pipeline": [
                    {"id": "check", "uses": "condition.evaluate", "with": {"expr": "time.hour % 2 == 0"}},
                    {"id": "process", "uses": "data.transform", "with": {"input": "${params.data}"}, "if": "${steps.check.result}"},
                    {"id": "notify", "uses": "notification.send", "with": {"message": "Processed: ${steps.process.count}"}}
                ],
                "params": {"data": list(range(100))}
            }
        }

async def create_test_tasks(count: int, complexity: str = "simple") -> List[Task]:
    """Create multiple test tasks for load testing"""
    tasks = []
    for i in range(count):
        task_data = generate_random_task(complexity)
        task_data["title"] = f"{task_data['title']} #{i}"
        task = await create_task(task_data)
        tasks.append(task)
    return tasks
```

## Monitoring & Observability Testing

### Metrics Validation
```python
@pytest.mark.observability
async def test_metrics_collection():
    """Verify all critical metrics are collected accurately"""
    
    # Reset metrics
    await reset_metrics()
    
    # Perform operations that should generate metrics
    tasks = await create_test_tasks(count=5)
    await process_all_tasks(tasks)
    
    # Wait for metrics collection
    await asyncio.sleep(2)
    
    metrics = await get_current_metrics()
    
    # Verify task creation metrics
    assert metrics["tasks_created_total"] == 5
    assert metrics["tasks_processed_total"] == 5
    assert metrics["tasks_succeeded_total"] == 5
    assert metrics["tasks_failed_total"] == 0
    
    # Verify timing metrics exist
    assert "task_execution_duration_seconds" in metrics
    assert metrics["task_execution_duration_seconds"]["count"] == 5
    
    # Verify database metrics
    assert metrics["database_connections_active"] >= 0
    assert metrics["database_queries_total"] > 0
```

### Log Analysis Testing
```python
@pytest.mark.observability
async def test_audit_logging():
    """Verify comprehensive audit logging for all operations"""
    
    # Clear previous logs
    await clear_audit_logs()
    
    # Perform auditable operations
    agent = await create_test_agent()
    task = await create_task({"title": "Audit Test"}, agent=agent)
    await trigger_task(task.id, agent=agent)
    await delete_task(task.id, agent=agent)
    
    # Retrieve audit logs
    logs = await get_audit_logs(since=datetime.now() - timedelta(minutes=1))
    
    # Verify all operations logged
    operations = {log["operation"] for log in logs}
    expected_operations = {"task_created", "task_triggered", "task_deleted"}
    assert expected_operations.issubset(operations)
    
    # Verify log structure
    for log in logs:
        assert "timestamp" in log
        assert "agent_id" in log
        assert "operation" in log
        assert "resource_id" in log
        assert "success" in log
```

## Test Environment Management

### Docker Test Environment
```yaml
# docker-compose.test.yml
version: '3.8'
services:
  test-postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: test_orchestrator
      POSTGRES_USER: test
      POSTGRES_PASSWORD: test
    ports:
      - "15432:5432"
    tmpfs:
      - /var/lib/postgresql/data  # In-memory for speed
      
  test-redis:
    image: redis:7
    ports:
      - "16379:6379"
    tmpfs:
      - /data  # In-memory for speed
      
  test-orchestrator:
    build: .
    environment:
      DATABASE_URL: postgresql://test:test@test-postgres:5432/test_orchestrator
      REDIS_URL: redis://test-redis:6379/0
      LOG_LEVEL: DEBUG
    depends_on:
      - test-postgres
      - test-redis
    ports:
      - "18080:8080"
```

### Test Environment Scripts
```bash
#!/bin/bash
# scripts/run_tests.sh - Comprehensive test runner

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Starting Ordinaut Test Suite${NC}"

# Start test infrastructure
echo -e "${YELLOW}Starting test environment...${NC}"
docker-compose -f docker-compose.test.yml up -d
sleep 10

# Wait for services to be ready
echo -e "${YELLOW}Waiting for services to be ready...${NC}"
./scripts/wait_for_services.sh

# Run test phases
run_test_phase() {
    phase=$1
    description=$2
    marker=$3
    timeout=$4
    
    echo -e "${YELLOW}Running $description...${NC}"
    if timeout $timeout pytest tests/$phase/ -v -m "$marker" --tb=short; then
        echo -e "${GREEN}✓ $description passed${NC}"
        return 0
    else
        echo -e "${RED}✗ $description failed${NC}"
        return 1
    fi
}

# Execute test phases in order
FAILED=0

run_test_phase "unit" "Unit Tests" "unit" "5m" || FAILED=1
run_test_phase "integration" "Integration Tests" "integration" "15m" || FAILED=1

# Only run expensive tests on main branch or explicit request
if [[ "$GITHUB_REF" == "refs/heads/main" ]] || [[ "$RUN_ALL_TESTS" == "true" ]]; then
    run_test_phase "load" "Load Tests" "load" "30m" || FAILED=1
    run_test_phase "e2e" "End-to-End Tests" "e2e" "45m" || FAILED=1
fi

# Cleanup test environment
echo -e "${YELLOW}Cleaning up test environment...${NC}"
docker-compose -f docker-compose.test.yml down -v

# Report results
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}All tests passed! ✓${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed! ✗${NC}"
    exit 1
fi
```

---

## Success Criteria & Quality Gates

### Coverage Requirements
- **Unit tests**: >98% line coverage
- **Integration tests**: >90% scenario coverage  
- **API endpoints**: 100% endpoint coverage
- **Error paths**: 100% error condition coverage
- **Performance tests**: All SLA targets met

### Automated Quality Gates
```python
# Quality gates enforced in CI/CD
QUALITY_GATES = {
    "test_coverage": {
        "minimum_line_coverage": 95.0,
        "minimum_branch_coverage": 90.0,
        "critical_path_coverage": 100.0
    },
    "performance_benchmarks": {
        "regression_threshold": 0.10,  # 10% performance regression fails build
        "memory_usage_limit": "1GB",   # Maximum memory usage
        "test_execution_time": "45m"   # Maximum total test time
    },
    "reliability_metrics": {
        "flaky_test_tolerance": 0.001, # <0.1% flaky test rate
        "test_success_rate": 0.999,    # 99.9% test success rate
        "max_retry_attempts": 3        # Maximum retries for flaky tests
    }
}
```

Remember: **Comprehensive testing is the foundation of system reliability**. Every test serves a purpose - catching regressions, validating performance, ensuring security, and building confidence in the Ordinaut's ability to reliably coordinate agent workflows in production environments.