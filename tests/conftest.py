#!/usr/bin/env python3
"""
Simplified pytest configuration for Ordinaut tests.

Provides basic test fixtures without testcontainers for faster testing.

NOTE: Tool and MCP-related tests are currently disabled as these components
have been removed from the core system. They will be re-implemented as 
extensions in the future. Tests referencing ToolRegistry, MCPClient, 
load_catalog, get_tool, etc. will need to be updated when tools are 
re-implemented as extensions.
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

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Database imports
import pytest_asyncio
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker


class SimpleTestEnvironment:
    """Simple test environment using SQLite."""
    
    def __init__(self):
        self.db_engine = None
        self.db_url = "sqlite:///test_simple.db"
        self._cleanup_tasks = []
    
    async def setup(self):
        """Initialize SQLite database."""
        # Create SQLite engine
        self.db_engine = create_engine(self.db_url, echo=False, future=True)
        
        # Apply minimal test schema
        await self.apply_test_schema()
    
    async def apply_test_schema(self):
        """Apply minimal database schema for testing."""
        
        # Execute each statement separately for SQLite compatibility
        statements = [
            """CREATE TABLE IF NOT EXISTS agent (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                scopes TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS task (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                created_by TEXT NOT NULL,
                schedule_kind TEXT NOT NULL,
                schedule_expr TEXT,
                timezone TEXT NOT NULL DEFAULT 'UTC',
                payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                priority INTEGER NOT NULL DEFAULT 5,
                max_retries INTEGER NOT NULL DEFAULT 3,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES agent(id)
            )""",
            """CREATE TABLE IF NOT EXISTS task_run (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                lease_owner TEXT,
                started_at TIMESTAMP,
                finished_at TIMESTAMP,
                success BOOLEAN,
                error TEXT,
                attempt INTEGER NOT NULL DEFAULT 1,
                output TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES task(id)
            )""",
            """CREATE TABLE IF NOT EXISTS due_work (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                run_at TIMESTAMP NOT NULL,
                locked_until TIMESTAMP,
                locked_by TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES task(id)
            )""",
            """CREATE INDEX IF NOT EXISTS idx_due_work_run_at ON due_work (run_at)""",
            """INSERT OR REPLACE INTO agent (id, name, scopes) VALUES 
               ('00000000-0000-0000-0000-000000000001', 'test-system', '["admin", "test"]')"""
        ]
        
        with self.db_engine.begin() as conn:
            for statement in statements:
                conn.execute(text(statement))
    
    async def cleanup(self):
        """Clean up test environment."""
        if self.db_engine:
            self.db_engine.dispose()
        
        # Remove test database file
        if os.path.exists("test_simple.db"):
            os.remove("test_simple.db")
    
    async def clean_database(self):
        """Clean database state for each test."""
        with self.db_engine.begin() as conn:
            # Clear all tables except system data
            conn.execute(text("DELETE FROM task_run"))
            conn.execute(text("DELETE FROM due_work"))
            conn.execute(text("DELETE FROM task WHERE created_by != '00000000-0000-0000-0000-000000000001'"))
            conn.execute(text("DELETE FROM agent WHERE name != 'test-system'"))


# Global test environment instance
_test_env = None


@pytest_asyncio.fixture(scope="session")
async def test_environment():
    """Session-scoped simple test environment."""
    global _test_env
    _test_env = SimpleTestEnvironment()
    await _test_env.setup()
    yield _test_env
    await _test_env.cleanup()


@pytest_asyncio.fixture
async def clean_database(test_environment):
    """Ensure clean database state for each test."""
    await test_environment.clean_database()
    yield test_environment.db_engine


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
        "timezone": "UTC",
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
        }
    ]


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
        }
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
        """), {
            **agent_data,
            "scopes": json.dumps(agent_data["scopes"])
        })
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
            "timezone": "UTC",
            "payload": {"pipeline": [{"id": "test", "uses": "test-tool.execute", "with": {"message": "test"}}]},
            "status": "active",
            "priority": 5,
            "max_retries": 3
        }
    
    task_id = task_data.get("id", str(uuid.uuid4()))
    
    with db_engine.begin() as conn:
        result = conn.execute(text("""
            INSERT INTO task (id, title, description, created_by, schedule_kind, schedule_expr, timezone, payload, status, priority, max_retries)
            VALUES (:id, :title, :description, :created_by, :schedule_kind, :schedule_expr, :timezone, :payload, :status, :priority, :max_retries)
            RETURNING *
        """), {
            "id": task_id,
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


# Configure pytest-asyncio
pytest_asyncio.fixture(scope="session")