#!/usr/bin/env python3
"""
Global pytest configuration and fixtures for Personal Agent Orchestrator tests.

Provides comprehensive test fixtures for unit, integration, and load testing including:
- Database setup with testcontainers
- Redis setup for event streams
- Mock tool catalogs and MCP bridges
- Performance testing utilities
- DST transition testing scenarios
"""

import os
import sys
import pytest
import asyncio
import uuid
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from unittest.mock import Mock, AsyncMock

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Database and container testing imports
import pytest_asyncio
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
try:
    from testcontainers.postgres import PostgresContainer
    from testcontainers.redis import RedisContainer
    TESTCONTAINERS_AVAILABLE = True
except ImportError:
    TESTCONTAINERS_AVAILABLE = False
    PostgresContainer = None
    RedisContainer = None

# Redis for event streams
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

import pytz


class TestEnvironmentManager:
    """Manages complete test environment with real dependencies."""
    
    def __init__(self):
        self.postgres_container = None
        self.redis_container = None
        self.db_engine = None
        self.async_db_engine = None
        self.redis_client = None
        self.db_url = None
        self.redis_url = None
        self._cleanup_tasks = []
    
    async def setup(self):
        """Start test containers and initialize connections."""
        
        if TESTCONTAINERS_AVAILABLE:
            # Start PostgreSQL container
            self.postgres_container = PostgresContainer("postgres:16")
            self.postgres_container.start()
            self.db_url = self.postgres_container.get_connection_url()
            
            # Start Redis container
            if REDIS_AVAILABLE:
                self.redis_container = RedisContainer("redis:7")
                self.redis_container.start()
                self.redis_url = self.redis_container.get_connection_url()
        else:
            # Fallback to environment variables for CI/CD
            self.db_url = os.getenv("TEST_DATABASE_URL", "postgresql://test:test@localhost:5432/test_orchestrator")
            self.redis_url = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/1")
        
        # Initialize database engines
        self.db_engine = create_engine(self.db_url, echo=False, future=True)
        self.async_db_engine = create_async_engine(
            self.db_url.replace("postgresql://", "postgresql+asyncpg://"), 
            echo=False
        )
        
        # Initialize Redis client
        if REDIS_AVAILABLE and self.redis_url:
            self.redis_client = redis.from_url(self.redis_url)
        
        # Apply test schema
        await self.apply_test_schema()
    
    async def apply_test_schema(self):
        """Apply complete database schema for testing."""
        schema_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
            "migrations", "version_0001.sql"
        )
        
        if os.path.exists(schema_path):
            with open(schema_path, "r") as f:
                schema_sql = f.read()
            
            with self.db_engine.begin() as conn:
                conn.execute(text(schema_sql))
        else:
            # Minimal schema for testing if migration file not found
            with self.db_engine.begin() as conn:
                conn.execute(text("""
                    CREATE EXTENSION IF NOT EXISTS pgcrypto;
                    CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
                    
                    CREATE TABLE IF NOT EXISTS agent (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        name TEXT NOT NULL UNIQUE,
                        scopes TEXT[] NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    );
                    
                    CREATE TYPE schedule_kind AS ENUM ('cron','rrule','once','event','condition');
                    
                    CREATE TABLE IF NOT EXISTS task (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        title TEXT NOT NULL,
                        description TEXT NOT NULL,
                        created_by UUID NOT NULL REFERENCES agent(id),
                        schedule_kind schedule_kind NOT NULL,
                        schedule_expr TEXT,
                        timezone TEXT NOT NULL DEFAULT 'Europe/Chisinau',
                        payload JSONB NOT NULL,
                        status TEXT NOT NULL DEFAULT 'active',
                        priority INT NOT NULL DEFAULT 5,
                        max_retries INT NOT NULL DEFAULT 3,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    );
                    
                    CREATE TABLE IF NOT EXISTS task_run (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        task_id UUID NOT NULL REFERENCES task(id),
                        lease_owner TEXT,
                        started_at TIMESTAMPTZ,
                        finished_at TIMESTAMPTZ,
                        success BOOLEAN,
                        error TEXT,
                        attempt INT NOT NULL DEFAULT 1,
                        output JSONB,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    );
                    
                    CREATE TABLE IF NOT EXISTS due_work (
                        id BIGSERIAL PRIMARY KEY,
                        task_id UUID NOT NULL REFERENCES task(id),
                        run_at TIMESTAMPTZ NOT NULL,
                        locked_until TIMESTAMPTZ,
                        locked_by TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    );
                    
                    CREATE INDEX IF NOT EXISTS idx_due_work_run_at ON due_work (run_at);
                    CREATE INDEX IF NOT EXISTS idx_due_work_ready ON due_work (run_at, locked_until) 
                    WHERE locked_until IS NULL OR locked_until < now();
                    
                    INSERT INTO agent (id, name, scopes) VALUES 
                    ('00000000-0000-0000-0000-000000000001', 'test-system', ARRAY['admin', 'test'])
                    ON CONFLICT (name) DO NOTHING;
                """))
    
    async def cleanup(self):
        """Clean up test environment."""
        
        # Execute cleanup tasks
        for cleanup_task in self._cleanup_tasks:
            try:
                if asyncio.iscoroutinefunction(cleanup_task):
                    await cleanup_task()
                else:
                    cleanup_task()
            except Exception as e:
                print(f"Error in cleanup task: {e}")
        
        # Close connections
        if self.db_engine:
            self.db_engine.dispose()
        if self.async_db_engine:
            await self.async_db_engine.dispose()
        if self.redis_client:
            self.redis_client.close()
        
        # Stop containers
        if self.postgres_container:
            self.postgres_container.stop()
        if self.redis_container:
            self.redis_container.stop()
    
    def add_cleanup_task(self, task):
        """Add a cleanup task to be executed during teardown."""
        self._cleanup_tasks.append(task)
    
    async def clean_database(self):
        """Ensure clean database state for each test."""
        with self.db_engine.begin() as conn:
            # Clear all tables in reverse dependency order, preserving system data
            conn.execute(text("DELETE FROM task_run WHERE task_id NOT IN (SELECT id FROM task WHERE created_by = '00000000-0000-0000-0000-000000000001')"))
            conn.execute(text("DELETE FROM due_work WHERE task_id NOT IN (SELECT id FROM task WHERE created_by = '00000000-0000-0000-0000-000000000001')"))
            conn.execute(text("DELETE FROM task WHERE created_by != '00000000-0000-0000-0000-000000000001'"))
            conn.execute(text("DELETE FROM agent WHERE name != 'test-system'"))


# Global test environment instance
_test_env = None


@pytest_asyncio.fixture(scope="session")
async def test_environment():
    """Session-scoped test environment with real dependencies."""
    global _test_env
    _test_env = TestEnvironmentManager()
    await _test_env.setup()
    yield _test_env
    await _test_env.cleanup()


@pytest_asyncio.fixture
async def clean_database(test_environment):
    """Ensure clean database state for each test."""
    await test_environment.clean_database()
    yield test_environment.db_engine
    # Post-test cleanup if needed


@pytest_asyncio.fixture
async def async_db_session(test_environment):
    """Async database session for testing."""
    async_session = sessionmaker(
        test_environment.async_db_engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session


@pytest.fixture
def redis_client(test_environment):
    """Redis client for event stream testing."""
    if test_environment.redis_client:
        test_environment.redis_client.flushdb()  # Clean Redis state
        yield test_environment.redis_client
    else:
        yield None


@pytest.fixture
def sample_agent():
    """Create sample agent for testing."""
    return {
        "id": str(uuid.uuid4()),
        "name": f"test-agent-{int(time.time())}",
        "scopes": ["notify", "calendar.read", "weather.read"],
        "created_at": datetime.now(timezone.utc)
    }


@pytest.fixture
def sample_task(sample_agent):
    """Create sample task for testing."""
    return {
        "id": str(uuid.uuid4()),
        "title": "Test Task",
        "description": "Test task for unit testing",
        "created_by": sample_agent["id"],
        "schedule_kind": "cron",
        "schedule_expr": "0 9 * * *",  # Daily at 9 AM
        "timezone": "Europe/Chisinau",
        "payload": {
            "pipeline": [
                {
                    "id": "test_step",
                    "uses": "test-tool.execute",
                    "with": {"message": "Hello World"},
                    "save_as": "result"
                }
            ]
        },
        "status": "active",
        "priority": 5,
        "max_retries": 3
    }


@pytest.fixture
def mock_tool_catalog():
    """Mock tool catalog for testing."""
    return [
        {
            "address": "test-tool.execute",
            "transport": "http",
            "endpoint": "http://localhost:8090/test",
            "input_schema": {
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"]
            },
            "output_schema": {
                "type": "object",
                "properties": {"result": {"type": "string"}},
                "required": ["result"]
            },
            "timeout_seconds": 30,
            "scopes": ["test"]
        },
        {
            "address": "echo.test",
            "transport": "http",
            "endpoint": "http://localhost:8090/echo",
            "input_schema": {
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"]
            },
            "output_schema": {
                "type": "object",
                "properties": {"echoed": {"type": "string"}},
                "required": ["echoed"]
            },
            "timeout_seconds": 10,
            "scopes": ["test"]
        },
        {
            "address": "weather.forecast",
            "transport": "http",
            "endpoint": "http://localhost:8091/weather",
            "input_schema": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"]
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "temp": {"type": "number"},
                    "condition": {"type": "string"},
                    "humidity": {"type": "number"}
                },
                "required": ["temp", "condition"]
            },
            "timeout_seconds": 20,
            "scopes": ["weather.read"]
        },
        {
            "address": "telegram.send_message",
            "transport": "http",
            "endpoint": "http://localhost:8092/telegram",
            "input_schema": {
                "type": "object",
                "properties": {
                    "chat_id": {"type": "integer"},
                    "text": {"type": "string"}
                },
                "required": ["chat_id", "text"]
            },
            "output_schema": {
                "type": "object",
                "properties": {"message_id": {"type": "integer"}},
                "required": ["message_id"]
            },
            "timeout_seconds": 15,
            "scopes": ["notify"]
        }
    ]


@pytest.fixture
def chisinau_dst_scenarios():
    """DST transition scenarios for Europe/Chisinau testing."""
    return {
        "spring_forward_2025": {
            "before": datetime(2025, 3, 30, 1, 30, 0),  # Before spring forward
            "during": datetime(2025, 3, 30, 3, 0, 0),   # After spring forward (3 AM)
            "transition_time": datetime(2025, 3, 30, 2, 0, 0),  # Non-existent time
            "timezone": "Europe/Chisinau"
        },
        "fall_back_2025": {
            "before": datetime(2025, 10, 26, 1, 30, 0),  # Before fall back
            "ambiguous": datetime(2025, 10, 26, 2, 30, 0),  # Ambiguous time (occurs twice)
            "after": datetime(2025, 10, 26, 4, 0, 0),    # After fall back
            "timezone": "Europe/Chisinau"
        }
    }


@pytest.fixture
def performance_benchmarks():
    """Performance benchmark expectations."""
    return {
        "template_rendering": {
            "simple_substitution_max_ms": 1,
            "complex_nested_max_ms": 5,
            "large_payload_max_ms": 50
        },
        "pipeline_execution": {
            "single_step_max_ms": 100,
            "multi_step_max_ms": 500,
            "validation_max_ms": 10
        },
        "database_operations": {
            "lease_work_max_ms": 50,
            "record_run_max_ms": 25,
            "task_crud_max_ms": 100
        },
        "rrule_processing": {
            "next_occurrence_max_ms": 20,
            "complex_rrule_max_ms": 100,
            "dst_transition_max_ms": 50
        }
    }


@pytest.fixture
def load_test_config():
    """Configuration for load testing scenarios."""
    return {
        "concurrent_workers": 10,
        "tasks_per_worker": 100,
        "test_duration_seconds": 30,
        "expected_throughput_tasks_per_second": 50,
        "max_queue_depth": 1000,
        "acceptable_failure_rate": 0.01  # 1%
    }


# Utility functions for test helpers

async def insert_test_agent(db_engine, agent_data=None):
    """Insert test agent into database."""
    if agent_data is None:
        agent_data = {
            "id": str(uuid.uuid4()),
            "name": f"test-agent-{int(time.time())}-{uuid.uuid4().hex[:8]}",
            "scopes": ["test", "notify"]
        }
    
    with db_engine.begin() as conn:
        result = conn.execute(text("""
            INSERT INTO agent (id, name, scopes) 
            VALUES (:id, :name, :scopes) 
            RETURNING *
        """), agent_data)
        return dict(result.fetchone()._mapping)


async def insert_test_task(db_engine, agent_id, task_data=None):
    """Insert test task into database."""
    if task_data is None:
        task_data = {
            "title": f"Test Task {int(time.time())}",
            "description": "Automated test task",
            "created_by": agent_id,
            "schedule_kind": "once",
            "schedule_expr": (datetime.now(timezone.utc) + timedelta(seconds=5)).isoformat(),
            "timezone": "Europe/Chisinau",
            "payload": {"pipeline": [{"id": "test", "uses": "test-tool.execute", "with": {"message": "test"}}]},
            "status": "active",
            "priority": 5,
            "max_retries": 3
        }
    
    with db_engine.begin() as conn:
        result = conn.execute(text("""
            INSERT INTO task (title, description, created_by, schedule_kind, schedule_expr, timezone, payload, status, priority, max_retries)
            VALUES (:title, :description, :created_by, :schedule_kind, :schedule_expr, :timezone, :payload::jsonb, :status, :priority, :max_retries)
            RETURNING *
        """), {
            **task_data,
            "payload": json.dumps(task_data["payload"])
        })
        return dict(result.fetchone()._mapping)


async def insert_due_work(db_engine, task_id, run_at=None):
    """Insert due work item into database."""
    if run_at is None:
        run_at = datetime.now(timezone.utc)
    
    with db_engine.begin() as conn:
        result = conn.execute(text("""
            INSERT INTO due_work (task_id, run_at)
            VALUES (:task_id, :run_at)
            RETURNING id
        """), {"task_id": task_id, "run_at": run_at})
        return result.scalar()


def create_mock_mcp_client():
    """Create mock MCP client for testing."""
    mock_client = Mock()
    
    # Default successful responses
    mock_client.call_tool = AsyncMock()
    mock_client.call_tool.return_value = {"result": "success", "message": "Mock response"}
    
    return mock_client


def measure_performance(func):
    """Decorator to measure function execution time."""
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        execution_time_ms = (end_time - start_time) * 1000
        
        # Add timing to result if it's a dict
        if isinstance(result, dict):
            result["_execution_time_ms"] = execution_time_ms
        
        return result, execution_time_ms
    
    return wrapper


async def wait_for_condition(condition_func, timeout_seconds=30, check_interval=0.1):
    """Wait for a condition to become true with timeout."""
    end_time = time.time() + timeout_seconds
    
    while time.time() < end_time:
        if await condition_func() if asyncio.iscoroutinefunction(condition_func) else condition_func():
            return True
        await asyncio.sleep(check_interval)
    
    return False


# Configure pytest-asyncio
pytest_asyncio.fixture(scope="session")


# pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests for individual components")
    config.addinivalue_line("markers", "integration: Integration tests with real dependencies") 
    config.addinivalue_line("markers", "load: Load and performance testing")
    config.addinivalue_line("markers", "chaos: Chaos engineering and fault injection tests")
    config.addinivalue_line("markers", "slow: Tests that take more than 30 seconds")
    config.addinivalue_line("markers", "dst: DST transition testing scenarios")


def pytest_collection_modifyitems(config, items):
    """Automatically mark tests based on their location."""
    for item in items:
        # Mark tests based on directory structure
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        elif "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        elif "load" in str(item.fspath):
            item.add_marker(pytest.mark.load)
        elif "chaos" in str(item.fspath):
            item.add_marker(pytest.mark.chaos)
        
        # Mark DST tests
        if "dst" in item.name.lower() or "timezone" in item.name.lower():
            item.add_marker(pytest.mark.dst)
        
        # Skip tests that require testcontainers if not available
        if item.get_closest_marker("integration") and not TESTCONTAINERS_AVAILABLE:
            item.add_marker(pytest.mark.skip(reason="testcontainers not available"))