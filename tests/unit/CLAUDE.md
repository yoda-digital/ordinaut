# Unit Tests - Ordinaut

## Purpose and Testing Scope

Unit tests verify individual components in isolation, ensuring each module behaves correctly under all conditions. These tests run quickly (< 5 seconds total) and provide immediate feedback during development.

**Core Testing Principles:**
- **Isolation**: Each component tested independently with mocked dependencies
- **Deterministic**: Tests produce consistent results across environments
- **Fast**: Complete unit test suite runs in under 5 seconds
- **Comprehensive**: >95% code coverage for all core modules

## Test Organization and Patterns

### Directory Structure
```
tests/unit/
├── CLAUDE.md                   # This file
├── conftest.py                 # Shared fixtures and test configuration
├── test_api/                   # FastAPI endpoint testing
│   ├── test_tasks.py           # Task CRUD operations
│   ├── test_runs.py            # Execution run management
│   └── test_auth.py            # Authentication and authorization
├── test_engine/                # Pipeline execution engine
│   ├── test_executor.py        # Pipeline step execution
│   ├── test_template.py        # Variable resolution and rendering
│   ├── test_registry.py        # Tool catalog management
│   └── test_mcp_client.py      # MCP protocol implementation
├── test_scheduler/             # Temporal scheduling system
│   ├── test_tick.py            # APScheduler integration
│   └── test_rruler.py          # RRULE processing
├── test_workers/               # Job processing workers
│   └── test_runner.py          # Work leasing and execution
└── utils/                      # Test utilities and helpers
    ├── fixtures.py             # Common test data and objects
    ├── mocks.py                # Mock implementations
    └── assertions.py           # Custom assertion helpers
```

### Testing Patterns

#### 1. Component Isolation Pattern
```python
# test_engine/test_executor.py
import pytest
from unittest.mock import Mock, patch
from engine.executor import PipelineExecutor

class TestPipelineExecutor:
    @pytest.fixture
    def executor(self):
        """Create executor with mocked dependencies."""
        mock_registry = Mock()
        mock_mcp_client = Mock()
        return PipelineExecutor(
            tool_registry=mock_registry,
            mcp_client=mock_mcp_client
        )
    
    def test_execute_single_step_success(self, executor):
        """Test successful single step execution."""
        # Arrange
        step = {"id": "test", "uses": "test-tool", "with": {"arg": "value"}}
        executor.tool_registry.get_tool.return_value = {
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"}
        }
        executor.mcp_client.call_tool.return_value = {"result": "success"}
        
        # Act
        result = executor.execute_step(step, {})
        
        # Assert
        assert result["result"] == "success"
        executor.mcp_client.call_tool.assert_called_once()
```

#### 2. Data-Driven Testing Pattern
```python
# test_scheduler/test_rruler.py
import pytest
from datetime import datetime
import pytz
from scheduler.rruler import RRuleProcessor

class TestRRuleProcessor:
    @pytest.mark.parametrize("rrule,timezone,expected_count", [
        ("FREQ=DAILY;COUNT=5", "UTC", 5),
        ("FREQ=WEEKLY;BYDAY=MO,WE,FR;COUNT=12", "America/New_York", 12),
        ("FREQ=MONTHLY;BYMONTHDAY=15;COUNT=6", "Europe/London", 6),
    ])
    def test_get_next_occurrences(self, rrule, timezone, expected_count):
        """Test RRULE expansion with various patterns."""
        processor = RRuleProcessor()
        start = datetime(2025, 1, 1, tzinfo=pytz.UTC)
        
        occurrences = processor.get_next_occurrences(
            rrule, timezone, start, count=expected_count
        )
        
        assert len(occurrences) == expected_count
        assert all(isinstance(dt, datetime) for dt in occurrences)
```

#### 3. Error Handling Pattern
```python
# test_api/test_tasks.py
import pytest
from fastapi.testclient import TestClient
from api.main import app

class TestTasksAPI:
    @pytest.fixture
    def client(self):
        return TestClient(app)
    
    def test_create_task_invalid_schedule(self, client):
        """Test task creation with invalid schedule expression."""
        invalid_task = {
            "title": "Test Task",
            "description": "Test description",
            "schedule_kind": "cron",
            "schedule_expr": "invalid cron",  # Invalid
            "payload": {"pipeline": []}
        }
        
        response = client.post("/v1/tasks", json=invalid_task)
        
        assert response.status_code == 422
        error_detail = response.json()["detail"]
        assert "schedule_expr" in str(error_detail)
        assert "invalid cron" in str(error_detail)
```

#### 4. State Management Pattern
```python
# test_workers/test_runner.py
import pytest
from unittest.mock import Mock, patch
from workers.runner import WorkRunner

class TestWorkRunner:
    @pytest.fixture
    def runner(self):
        mock_db = Mock()
        mock_executor = Mock()
        return WorkRunner(database=mock_db, executor=mock_executor)
    
    def test_lease_work_skip_locked(self, runner):
        """Test work leasing uses SKIP LOCKED correctly."""
        # Mock database response
        mock_work = Mock(id="work-123", task_id="task-456")
        runner.database.execute.return_value.fetchone.return_value = mock_work
        
        work = runner.lease_work()
        
        # Verify SKIP LOCKED query used
        query_call = runner.database.execute.call_args[0][0]
        assert "FOR UPDATE SKIP LOCKED" in query_call
        assert work.id == "work-123"
```

## Key Test Files and Coverage

### Core Component Tests

#### API Layer Tests (`test_api/`)
- **test_tasks.py** - Task CRUD operations, validation, filtering
- **test_runs.py** - Execution tracking, status updates, error handling
- **test_auth.py** - Authentication, authorization, scope validation

**Coverage Requirements:**
- All FastAPI endpoints (100%)
- Request/response validation (100%)
- Error scenarios and status codes (100%)
- Authentication and authorization logic (100%)

#### Engine Tests (`test_engine/`)
- **test_executor.py** - Pipeline execution, step orchestration, error handling
- **test_template.py** - Variable resolution, JMESPath expressions, context building
- **test_registry.py** - Tool catalog, schema validation, tool discovery
- **test_mcp_client.py** - MCP protocol, tool communication, error mapping

**Coverage Requirements:**
- Pipeline execution logic (100%)
- Template rendering edge cases (100%)
- Tool registry operations (100%)
- MCP client protocol handling (100%)

#### Scheduler Tests (`test_scheduler/`)
- **test_tick.py** - APScheduler integration, job persistence, trigger handling
- **test_rruler.py** - RRULE parsing, timezone handling, DST transitions

**Coverage Requirements:**
- Schedule expression validation (100%)
- Timezone conversion logic (100%)
- DST transition handling (100%)
- Job queue operations (100%)

#### Worker Tests (`test_workers/`)
- **test_runner.py** - Work leasing, execution coordination, concurrency control

**Coverage Requirements:**
- SKIP LOCKED job leasing (100%)
- Concurrent execution safety (100%)
- Error recovery and retry logic (100%)
- Work distribution algorithms (100%)

### Test Utilities (`utils/`)

#### fixtures.py - Common Test Data
```python
import pytest
from datetime import datetime, timezone

@pytest.fixture
def sample_task():
    """Standard task for testing."""
    return {
        "id": "task-123",
        "title": "Sample Task",
        "description": "Test task description",
        "schedule_kind": "cron",
        "schedule_expr": "0 9 * * 1-5",
        "timezone": "America/New_York",
        "status": "active",
        "created_at": datetime.now(timezone.utc),
        "payload": {
            "pipeline": [
                {
                    "id": "step1",
                    "uses": "test-tool",
                    "with": {"param": "value"},
                    "save_as": "result1"
                }
            ]
        }
    }

@pytest.fixture
def sample_pipeline():
    """Standard pipeline for testing."""
    return [
        {
            "id": "fetch_data",
            "uses": "http-client.get",
            "with": {"url": "https://api.example.com/data"},
            "save_as": "raw_data"
        },
        {
            "id": "process_data",
            "uses": "json-processor.transform",
            "with": {
                "data": "${steps.fetch_data.body}",
                "transformation": "extract_key_fields"
            },
            "save_as": "processed_data"
        }
    ]
```

#### mocks.py - Mock Implementations
```python
from unittest.mock import Mock, AsyncMock

class MockMCPClient:
    """Mock MCP client for testing."""
    
    def __init__(self):
        self.call_tool = AsyncMock()
        self.list_tools = AsyncMock()
        self.connected = True
    
    async def call_tool(self, tool_name, arguments):
        """Mock tool call with configurable responses."""
        if tool_name == "test-tool":
            return {"status": "success", "data": arguments}
        raise ValueError(f"Unknown tool: {tool_name}")

class MockDatabase:
    """Mock database for testing."""
    
    def __init__(self):
        self.execute = Mock()
        self.begin = Mock()
        self.rollback = Mock()
        self.commit = Mock()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()
```

#### assertions.py - Custom Assertions
```python
from datetime import datetime, timezone

def assert_valid_task(task_dict):
    """Assert task dictionary has valid structure."""
    required_fields = ["id", "title", "description", "schedule_kind", "status"]
    for field in required_fields:
        assert field in task_dict, f"Missing required field: {field}"
    
    assert isinstance(task_dict["created_at"], datetime)
    assert task_dict["status"] in ["active", "paused", "completed", "failed"]

def assert_pipeline_execution_order(execution_log, expected_order):
    """Assert pipeline steps executed in correct order."""
    actual_order = [step["id"] for step in execution_log]
    assert actual_order == expected_order, f"Expected {expected_order}, got {actual_order}"

def assert_schedule_next_run(task, expected_next_run_approx):
    """Assert next run time is approximately correct."""
    next_run = task["next_run"]
    assert isinstance(next_run, datetime)
    
    # Allow 5 minute tolerance for schedule calculations
    diff = abs((next_run - expected_next_run_approx).total_seconds())
    assert diff < 300, f"Next run time {next_run} not within 5 minutes of expected {expected_next_run_approx}"
```

## Testing Infrastructure and Utilities

### Test Configuration (`conftest.py`)
```python
import pytest
import asyncio
from unittest.mock import Mock
import tempfile
import os

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def mock_redis():
    """Mock Redis client for testing."""
    redis_mock = Mock()
    redis_mock.xadd = Mock(return_value=b'1641024000000-0')
    redis_mock.xreadgroup = Mock(return_value=[])
    redis_mock.xack = Mock(return_value=1)
    return redis_mock

@pytest.fixture
def temp_config_file():
    """Create temporary configuration file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        config = {
            "database_url": "postgresql://test:test@localhost:5432/test_db",
            "redis_url": "redis://localhost:6379/1",
            "log_level": "DEBUG"
        }
        import json
        json.dump(config, f)
        f.flush()
        yield f.name
    os.unlink(f.name)

@pytest.fixture(autouse=True)
def isolate_tests():
    """Ensure test isolation by clearing global state."""
    # Clear any global registries or caches
    from engine.registry import ToolRegistry
    if hasattr(ToolRegistry, '_instance'):
        ToolRegistry._instance = None
    
    yield
    
    # Cleanup after test
    # Reset any global state if needed
```

### Running Unit Tests

#### Basic Test Execution
```bash
# Run all unit tests
pytest tests/unit/ -v

# Run with coverage
pytest tests/unit/ --cov=api --cov=engine --cov=scheduler --cov=workers --cov-report=html

# Run specific test file
pytest tests/unit/test_engine/test_executor.py -v

# Run tests matching pattern
pytest tests/unit/ -k "test_schedule" -v

# Run with debugging output
pytest tests/unit/ -v -s --tb=long
```

#### Performance Requirements
- **Total execution time**: < 5 seconds for complete unit test suite
- **Individual test time**: < 100ms per test (excluding setup/teardown)
- **Memory usage**: < 100MB peak during test execution
- **Parallelization**: Tests must be safe to run with `pytest-xdist`

#### Continuous Integration
```bash
# CI pipeline unit test stage
pytest tests/unit/ \
    --cov=api --cov=engine --cov=scheduler --cov=workers \
    --cov-report=xml \
    --junitxml=unit-test-results.xml \
    --cov-fail-under=95
```

## Quality Standards

### Coverage Requirements
- **Minimum coverage**: 95% for all production code
- **Critical path coverage**: 100% for core execution paths
- **Error handling coverage**: 100% for all exception scenarios
- **Edge case coverage**: 100% for boundary conditions

### Test Quality Metrics
- **Test speed**: All unit tests complete in < 5 seconds
- **Test reliability**: 0% flaky tests (must be deterministic)
- **Test maintainability**: Each test focuses on single behavior
- **Test readability**: Clear arrange/act/assert structure

### Code Quality Gates
- All tests must pass before merge
- Coverage threshold must be met (95%)
- No test warnings or deprecation messages
- All tests must be properly categorized with pytest marks

This unit testing framework ensures comprehensive coverage of all Ordinaut components while maintaining fast execution and reliable results for continuous development feedback.