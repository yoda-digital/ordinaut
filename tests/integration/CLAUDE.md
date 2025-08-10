# Integration Tests - Ordinaut

## Purpose and Testing Scope

Integration tests verify system components work correctly together, ensuring end-to-end workflows function as expected in realistic environments. These tests validate component interactions, data flow, and system behavior under production-like conditions.

**Core Testing Principles:**
- **Realistic Environment**: Tests run against actual databases and external services
- **End-to-End Workflows**: Complete user journeys from API to execution
- **Component Interaction**: Verify interfaces between major system components
- **Data Consistency**: Ensure data integrity across component boundaries

## Test Organization and Patterns

### Directory Structure
```
tests/integration/
├── CLAUDE.md                   # This file
├── conftest.py                 # Integration test configuration and fixtures
├── test_workflows/             # Complete end-to-end workflows
│   ├── test_task_lifecycle.py  # Task creation → scheduling → execution → completion
│   ├── test_scheduling_flow.py # Schedule processing and trigger execution
│   └── test_pipeline_flow.py   # Pipeline execution with real tools
├── test_components/            # Component integration testing
│   ├── test_api_database.py    # API ↔ Database integration
│   ├── test_scheduler_worker.py # Scheduler ↔ Worker coordination
│   ├── test_engine_mcp.py      # Engine ↔ MCP tool integration
│   └── test_worker_database.py # Worker ↔ Database SKIP LOCKED patterns
├── test_external/              # External service integration
│   ├── test_mcp_servers.py     # Real MCP server communication
│   ├── test_database_ops.py    # PostgreSQL advanced operations
│   └── test_redis_streams.py   # Redis Streams event processing
├── test_scenarios/             # Complex business scenarios
│   ├── test_error_recovery.py  # Error handling and retry scenarios
│   ├── test_concurrency.py     # Multi-worker coordination
│   └── test_performance.py     # Performance under realistic load
└── utils/                      # Integration test utilities
    ├── fixtures.py             # Database seeding and cleanup
    ├── servers.py              # Test server management
    └── assertions.py           # End-to-end assertion helpers
```

### Testing Patterns

#### 1. End-to-End Workflow Pattern
```python
# test_workflows/test_task_lifecycle.py
import pytest
from datetime import datetime, timedelta
import asyncio
from httpx import AsyncClient
from tests.integration.utils.fixtures import integration_db, test_redis

class TestTaskLifecycle:
    @pytest.mark.asyncio
    async def test_complete_task_lifecycle(self, integration_db, test_redis):
        """Test complete task from creation to execution completion."""
        async with AsyncClient(base_url="http://localhost:8080") as client:
            # 1. Create task via API
            task_data = {
                "title": "Integration Test Task",
                "description": "End-to-end workflow test",
                "schedule_kind": "once",
                "schedule_expr": (datetime.now() + timedelta(seconds=5)).isoformat(),
                "payload": {
                    "pipeline": [
                        {
                            "id": "test_step",
                            "uses": "echo-tool",
                            "with": {"message": "Hello Integration"},
                            "save_as": "echo_result"
                        }
                    ]
                }
            }
            
            # Create task
            create_response = await client.post("/v1/tasks", json=task_data)
            assert create_response.status_code == 201
            task = create_response.json()
            task_id = task["id"]
            
            # 2. Verify task is scheduled
            await asyncio.sleep(1)
            get_response = await client.get(f"/v1/tasks/{task_id}")
            assert get_response.status_code == 200
            task_status = get_response.json()
            assert task_status["status"] == "active"
            assert task_status["next_run"] is not None
            
            # 3. Wait for execution
            await asyncio.sleep(10)  # Wait for execution
            
            # 4. Verify execution completed
            runs_response = await client.get(f"/v1/tasks/{task_id}/runs")
            assert runs_response.status_code == 200
            runs = runs_response.json()
            assert len(runs) == 1
            
            run = runs[0]
            assert run["status"] == "success"
            assert run["finished_at"] is not None
            assert "echo_result" in run["outputs"]
            assert run["outputs"]["echo_result"]["message"] == "Hello Integration"
            
            # 5. Verify task status updated
            final_response = await client.get(f"/v1/tasks/{task_id}")
            final_task = final_response.json()
            assert final_task["status"] == "completed"
```

#### 2. Component Integration Pattern
```python
# test_components/test_scheduler_worker.py
import pytest
import asyncio
from datetime import datetime, timedelta
from scheduler.tick import SchedulerService
from workers.runner import WorkRunner
from tests.integration.utils.fixtures import integration_db

class TestSchedulerWorkerIntegration:
    @pytest.mark.asyncio
    async def test_scheduler_creates_work_worker_executes(self, integration_db):
        """Test scheduler creates due work that workers can process."""
        # Create scheduler and worker
        scheduler = SchedulerService(database=integration_db)
        worker = WorkRunner(database=integration_db)
        
        # Create a task due now
        task_id = await self._create_test_task(integration_db, due_in_seconds=1)
        
        # Start scheduler (it should create work items)
        scheduler_task = asyncio.create_task(scheduler.run_once())
        
        # Wait for scheduler to process
        await asyncio.sleep(2)
        
        # Verify work was created in database
        work_items = await integration_db.fetch(
            "SELECT * FROM due_work WHERE task_id = $1", task_id
        )
        assert len(work_items) == 1
        assert work_items[0]["status"] == "pending"
        
        # Worker should be able to lease this work
        leased_work = await worker.lease_work()
        assert leased_work is not None
        assert leased_work["task_id"] == task_id
        assert leased_work["status"] == "running"
        
        # Execute work
        result = await worker.execute_work(leased_work)
        assert result["status"] == "completed"
        
        # Verify work is marked complete in database
        completed_work = await integration_db.fetchrow(
            "SELECT * FROM due_work WHERE id = $1", leased_work["id"]
        )
        assert completed_work["status"] == "completed"
        assert completed_work["finished_at"] is not None
```

#### 3. Real Service Integration Pattern
```python
# test_external/test_mcp_servers.py
import pytest
import json
from engine.mcp_client import MCPClient
from tests.integration.utils.servers import EchoMCPServer

class TestMCPIntegration:
    @pytest.fixture
    async def mcp_server(self):
        """Start real MCP server for testing."""
        server = EchoMCPServer()
        await server.start()
        yield server
        await server.stop()
    
    @pytest.fixture
    async def mcp_client(self, mcp_server):
        """Create MCP client connected to test server."""
        client = MCPClient(server_uri=mcp_server.uri)
        await client.connect()
        yield client
        await client.disconnect()
    
    @pytest.mark.asyncio
    async def test_tool_discovery_and_execution(self, mcp_client):
        """Test discovering and executing tools via MCP."""
        # Discover available tools
        tools = await mcp_client.list_tools()
        assert len(tools) > 0
        
        echo_tool = next(tool for tool in tools if tool["name"] == "echo")
        assert echo_tool is not None
        assert "input_schema" in echo_tool
        
        # Execute tool with valid input
        result = await mcp_client.call_tool("echo", {"message": "test message"})
        assert result["message"] == "test message"
        assert "timestamp" in result
        
        # Test error handling with invalid input
        with pytest.raises(ValueError, match="missing required parameter"):
            await mcp_client.call_tool("echo", {})  # Missing required 'message'
```

#### 4. Concurrency and Race Condition Testing
```python
# test_scenarios/test_concurrency.py
import pytest
import asyncio
from workers.runner import WorkRunner
from tests.integration.utils.fixtures import integration_db

class TestConcurrencyScenarios:
    @pytest.mark.asyncio
    async def test_multiple_workers_no_double_processing(self, integration_db):
        """Test multiple workers don't process the same work twice."""
        # Create 5 workers
        workers = [WorkRunner(database=integration_db) for _ in range(5)]
        
        # Create 10 work items
        task_ids = []
        for i in range(10):
            task_id = await self._create_test_work(integration_db, f"work-{i}")
            task_ids.append(task_id)
        
        # Start all workers simultaneously
        work_results = await asyncio.gather(*[
            worker.lease_and_execute_work() for worker in workers
        ])
        
        # Count successful executions
        successful_executions = sum(1 for result in work_results if result)
        
        # Each work item should be processed exactly once
        assert successful_executions == 10
        
        # Verify no work items are still pending
        pending_work = await integration_db.fetch(
            "SELECT COUNT(*) as count FROM due_work WHERE status = 'pending'"
        )
        assert pending_work[0]["count"] == 0
        
        # Verify all work items are completed
        completed_work = await integration_db.fetch(
            "SELECT COUNT(*) as count FROM due_work WHERE status = 'completed'"
        )
        assert completed_work[0]["count"] == 10
```

## Key Test Files and Coverage

### Workflow Tests (`test_workflows/`)

#### test_task_lifecycle.py - Complete Task Journey
**Coverage:**
- Task creation via API
- Schedule processing and next run calculation
- Work item generation by scheduler
- Work execution by workers
- Status updates and completion tracking
- Error scenarios and recovery

#### test_scheduling_flow.py - Schedule Processing
**Coverage:**
- CRON schedule evaluation and next run calculation
- RRULE schedule processing with timezone handling
- DST transition scenarios
- Schedule conflict detection and resolution
- Manual task execution and snoozing

#### test_pipeline_flow.py - Pipeline Execution
**Coverage:**
- Multi-step pipeline execution order
- Template variable resolution between steps
- Conditional step execution with JMESPath
- Error handling and pipeline rollback
- Tool output validation and schema compliance

### Component Integration Tests (`test_components/`)

#### test_api_database.py - API and Database Layer
```python
class TestAPIDatabaseIntegration:
    @pytest.mark.asyncio
    async def test_task_crud_operations_with_database(self, integration_db):
        """Test API operations persist correctly to database."""
        async with AsyncClient() as client:
            # Create task via API
            task_data = self._sample_task_data()
            create_response = await client.post("/v1/tasks", json=task_data)
            task = create_response.json()
            
            # Verify task exists in database
            db_task = await integration_db.fetchrow(
                "SELECT * FROM task WHERE id = $1", task["id"]
            )
            assert db_task["title"] == task_data["title"]
            assert db_task["schedule_kind"] == task_data["schedule_kind"]
            
            # Update task via API
            update_data = {"title": "Updated Title"}
            update_response = await client.patch(f"/v1/tasks/{task['id']}", json=update_data)
            
            # Verify update in database
            updated_db_task = await integration_db.fetchrow(
                "SELECT * FROM task WHERE id = $1", task["id"]
            )
            assert updated_db_task["title"] == "Updated Title"
            assert updated_db_task["updated_at"] > updated_db_task["created_at"]
```

#### test_worker_database.py - Worker Database Operations
```python
class TestWorkerDatabaseIntegration:
    @pytest.mark.asyncio
    async def test_skip_locked_work_leasing(self, integration_db):
        """Test SKIP LOCKED prevents work item conflicts."""
        worker1 = WorkRunner(database=integration_db)
        worker2 = WorkRunner(database=integration_db)
        
        # Create work item
        work_id = await self._create_work_item(integration_db)
        
        # Both workers attempt to lease simultaneously
        results = await asyncio.gather(
            worker1.lease_work(),
            worker2.lease_work(),
            return_exceptions=True
        )
        
        # Only one should succeed
        successful_leases = [r for r in results if r is not None and not isinstance(r, Exception)]
        assert len(successful_leases) == 1
        
        # Verify work item is locked to the successful worker
        locked_work = await integration_db.fetchrow(
            "SELECT * FROM due_work WHERE id = $1", work_id
        )
        assert locked_work["status"] == "running"
        assert locked_work["locked_until"] is not None
```

### External Integration Tests (`test_external/`)

#### test_database_ops.py - Advanced PostgreSQL Operations
**Coverage:**
- Complex queries with SKIP LOCKED semantics
- Transaction isolation levels and rollback scenarios
- JSONB operations for payload storage and querying
- Index performance and query optimization
- Connection pooling and recovery

#### test_redis_streams.py - Redis Streams Event Processing
**Coverage:**
- Event publishing with XADD
- Consumer group processing with XREADGROUP
- Event acknowledgment and retry logic
- Stream trimming and memory management
- Connection failover and recovery

### Scenario Tests (`test_scenarios/`)

#### test_error_recovery.py - Error Handling Scenarios
```python
class TestErrorRecovery:
    @pytest.mark.asyncio
    async def test_pipeline_step_failure_recovery(self, integration_db):
        """Test pipeline recovers from step failures with retry logic."""
        # Create pipeline with failing step
        pipeline = [
            {"id": "fail_step", "uses": "failing-tool", "retry_count": 3},
            {"id": "success_step", "uses": "echo-tool", "with": {"message": "success"}}
        ]
        
        task_id = await self._create_task_with_pipeline(integration_db, pipeline)
        worker = WorkRunner(database=integration_db)
        
        # Execute work (should retry failing step 3 times)
        result = await worker.execute_task(task_id)
        
        # Verify retry attempts were made
        run_logs = await integration_db.fetch(
            "SELECT * FROM run_log WHERE task_id = $1 ORDER BY created_at", task_id
        )
        
        fail_attempts = [log for log in run_logs if log["step_id"] == "fail_step"]
        assert len(fail_attempts) == 3  # Original + 3 retries
        
        # Verify pipeline marked as failed after exhausting retries
        final_run = await integration_db.fetchrow(
            "SELECT * FROM task_run WHERE task_id = $1", task_id
        )
        assert final_run["status"] == "failed"
        assert "Max retries exhausted" in final_run["error_message"]
```

## Testing Infrastructure and Utilities

### Integration Test Configuration (`conftest.py`)
```python
import pytest
import asyncio
import asyncpg
import redis.asyncio as redis
from sqlalchemy import create_engine
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for integration tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
async def postgres_container():
    """Start PostgreSQL container for integration tests."""
    with PostgresContainer("postgres:16") as postgres:
        # Apply migrations
        engine = create_engine(postgres.get_connection_url())
        with open("migrations/version_0001.sql") as f:
            engine.execute(f.read())
        
        yield postgres

@pytest.fixture(scope="session") 
async def redis_container():
    """Start Redis container for integration tests."""
    with RedisContainer("redis:7") as redis_container:
        yield redis_container

@pytest.fixture
async def integration_db(postgres_container):
    """Create database connection for test."""
    conn = await asyncpg.connect(postgres_container.get_connection_url())
    
    # Clean database before test
    await conn.execute("TRUNCATE task, task_run, due_work, run_log CASCADE")
    
    yield conn
    
    # Cleanup after test
    await conn.execute("TRUNCATE task, task_run, due_work, run_log CASCADE")
    await conn.close()

@pytest.fixture
async def test_redis(redis_container):
    """Create Redis connection for test."""
    redis_client = redis.from_url(redis_container.get_connection_url())
    
    # Clean Redis before test
    await redis_client.flushall()
    
    yield redis_client
    
    # Cleanup after test
    await redis_client.flushall()
    await redis_client.close()
```

### Test Utilities (`utils/`)

#### fixtures.py - Database Seeding
```python
import uuid
from datetime import datetime, timezone, timedelta

async def create_test_task(db, title="Test Task", due_in_seconds=60):
    """Create a test task in the database."""
    task_id = str(uuid.uuid4())
    
    await db.execute("""
        INSERT INTO task (id, title, description, schedule_kind, schedule_expr, 
                         timezone, status, created_at, next_run, payload)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
    """, task_id, title, "Test description", "once",
         (datetime.now(timezone.utc) + timedelta(seconds=due_in_seconds)).isoformat(),
         "UTC", "active", datetime.now(timezone.utc),
         datetime.now(timezone.utc) + timedelta(seconds=due_in_seconds),
         {"pipeline": [{"id": "test", "uses": "echo-tool", "with": {"message": "test"}}]})
    
    return task_id

async def create_work_item(db, task_id, due_now=True):
    """Create a work item for testing."""
    work_id = str(uuid.uuid4())
    
    run_at = datetime.now(timezone.utc) if due_now else datetime.now(timezone.utc) + timedelta(minutes=5)
    
    await db.execute("""
        INSERT INTO due_work (id, task_id, run_at, priority, status, payload)
        VALUES ($1, $2, $3, $4, $5, $6)
    """, work_id, task_id, run_at, 5, "pending", {"pipeline": []})
    
    return work_id
```

#### servers.py - Test Server Management
```python
import asyncio
import json
from typing import Optional

class EchoMCPServer:
    """Simple MCP server for testing."""
    
    def __init__(self, port: int = 8081):
        self.port = port
        self.server: Optional[asyncio.Server] = None
        self.uri = f"http://localhost:{port}"
    
    async def start(self):
        """Start the test MCP server."""
        self.server = await asyncio.start_server(
            self._handle_client, 'localhost', self.port
        )
        
    async def stop(self):
        """Stop the test MCP server."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
    
    async def _handle_client(self, reader, writer):
        """Handle MCP client connections."""
        while True:
            try:
                data = await reader.read(1024)
                if not data:
                    break
                    
                request = json.loads(data.decode())
                
                if request["method"] == "tools/list":
                    response = {
                        "jsonrpc": "2.0",
                        "id": request["id"],
                        "result": {
                            "tools": [
                                {
                                    "name": "echo",
                                    "description": "Echo back the input message",
                                    "input_schema": {
                                        "type": "object",
                                        "properties": {
                                            "message": {"type": "string"}
                                        },
                                        "required": ["message"]
                                    }
                                }
                            ]
                        }
                    }
                elif request["method"] == "tools/call":
                    tool_name = request["params"]["name"]
                    arguments = request["params"]["arguments"]
                    
                    if tool_name == "echo":
                        response = {
                            "jsonrpc": "2.0",
                            "id": request["id"],
                            "result": {
                                "content": [
                                    {
                                        "type": "text",
                                        "text": json.dumps({
                                            "message": arguments["message"],
                                            "timestamp": datetime.now().isoformat()
                                        })
                                    }
                                ]
                            }
                        }
                
                writer.write(json.dumps(response).encode())
                await writer.drain()
                
            except Exception as e:
                error_response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "error": {"code": -1, "message": str(e)}
                }
                writer.write(json.dumps(error_response).encode())
                await writer.drain()
```

### Running Integration Tests

#### Test Execution Commands
```bash
# Run all integration tests
pytest tests/integration/ -v --tb=short

# Run with test containers (automatic)
pytest tests/integration/ -v --integration

# Run specific workflow tests
pytest tests/integration/test_workflows/ -v

# Run with verbose output and timing
pytest tests/integration/ -v -s --durations=10

# Run parallel integration tests (careful with containers)
pytest tests/integration/ -n 2 --dist worksteal
```

#### Performance Requirements
- **Test execution time**: < 2 minutes for complete integration test suite
- **Individual test time**: < 30 seconds per test
- **Resource usage**: Tests should clean up containers and connections
- **Reliability**: 100% pass rate on clean environments

## Quality Standards

### Test Environment Requirements
- **Database isolation**: Each test runs with clean database state
- **Service availability**: All external services must be healthy
- **Network stability**: Tests must handle network delays gracefully
- **Resource cleanup**: No resource leaks or container accumulation

### Integration Coverage Goals
- **Component interfaces**: 100% of component boundaries tested
- **Data flow paths**: All major data transformations validated
- **Error scenarios**: Critical failure modes covered
- **Performance scenarios**: Load and concurrency patterns tested

### Success Criteria
- All integration tests pass on clean environment
- No flaky tests or intermittent failures
- Complete data consistency validation
- Realistic load and performance validation
- Proper error handling and recovery verification

This integration testing framework ensures the Ordinaut components work correctly together and handle real-world scenarios reliably.