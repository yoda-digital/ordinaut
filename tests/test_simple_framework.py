#!/usr/bin/env python3
"""
Simple framework validation tests.
"""

import pytest
import uuid
import json
import os
from datetime import datetime, timezone, timedelta

# Set test environment
os.environ["DATABASE_URL"] = "sqlite:///test_simple.db"
os.environ["REDIS_URL"] = "memory://"

# Import from the simplified conftest
from conftest_simple import (
    insert_test_agent, 
    insert_test_task, 
    insert_due_work,
    test_environment,
    clean_database,
    sample_agent,
    sample_task,
    mock_tool_catalog,
    performance_benchmarks
)

# Also add project root to path
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestSimpleFramework:
    """Test the simplified test framework."""
    
    def test_environment_setup(self):
        """Test environment variables are set."""
        assert os.environ.get("DATABASE_URL") == "sqlite:///test_simple.db"
    
    def test_database_connection(self, clean_database):
        """Test basic database connectivity."""
        from sqlalchemy import text
        with clean_database.begin() as conn:
            result = conn.execute(text("SELECT 1 as test")).scalar()
        assert result == 1
    
    def test_agent_operations(self, clean_database):
        """Test agent database operations."""
        import asyncio
        
        # Insert agent
        agent_data = {
            "id": str(uuid.uuid4()),
            "name": "test-framework-agent",
            "scopes": ["test", "framework"]
        }
        
        agent = asyncio.run(insert_test_agent(clean_database, agent_data))
        
        assert agent["id"] == agent_data["id"]
        assert agent["name"] == agent_data["name"]
        
        # Verify in database
        from sqlalchemy import text
        with clean_database.begin() as conn:
            result = conn.execute(text("SELECT * FROM agent WHERE id = :id"), {"id": agent["id"]}).fetchone()
            assert result is not None
            assert result.name == "test-framework-agent"
    
    def test_task_operations(self, clean_database):
        """Test task database operations."""
        import asyncio
        
        # Create agent first
        agent = asyncio.run(insert_test_agent(clean_database))
        
        # Create task
        task_data = {
            "title": "Framework Test Task",
            "description": "Test framework task operations",
            "created_by": agent["id"],
            "schedule_kind": "once",
            "schedule_expr": "2025-12-25T10:00:00Z",
            "timezone": "UTC",
            "payload": {"pipeline": [{"id": "test", "uses": "test.tool"}]},
            "status": "active",
            "priority": 5,
            "max_retries": 3
        }
        
        task = asyncio.run(insert_test_task(clean_database, agent["id"], task_data))
        
        assert task["title"] == "Framework Test Task"
        assert task["created_by"] == agent["id"]
        
        # Verify in database
        from sqlalchemy import text
        with clean_database.begin() as conn:
            result = conn.execute(text("SELECT * FROM task WHERE id = :id"), {"id": task["id"]}).fetchone()
            assert result is not None
            assert result.title == "Framework Test Task"
    
    def test_due_work_operations(self, clean_database):
        """Test due work operations."""
        import asyncio
        
        # Setup agent and task
        agent = asyncio.run(insert_test_agent(clean_database))
        task = asyncio.run(insert_test_task(clean_database, agent["id"]))
        
        # Insert due work
        work_id = asyncio.run(insert_due_work(clean_database, task["id"], datetime.now(timezone.utc)))
        
        assert work_id is not None
        
        # Verify in database
        from sqlalchemy import text
        with clean_database.begin() as conn:
            result = conn.execute(text("SELECT * FROM due_work WHERE id = :id"), {"id": work_id}).fetchone()
            assert result is not None
            assert result.task_id == task["id"]
    
    def test_fixtures_work(self, sample_agent, sample_task, mock_tool_catalog, performance_benchmarks):
        """Test that all fixtures work correctly."""
        # Sample agent
        assert sample_agent["name"].startswith("test-agent-")
        assert isinstance(sample_agent["scopes"], list)
        
        # Sample task
        assert sample_task["title"] == "Test Task"
        assert sample_task["created_by"] == sample_agent["id"]
        
        # Mock tool catalog
        assert isinstance(mock_tool_catalog, list)
        assert len(mock_tool_catalog) > 0
        
        # Performance benchmarks
        assert isinstance(performance_benchmarks, dict)
        assert "template_rendering" in performance_benchmarks
    
    def test_database_schema_integrity(self, clean_database):
        """Test database schema integrity."""
        import asyncio
        
        # Test foreign key relationships
        agent = asyncio.run(insert_test_agent(clean_database))
        task = asyncio.run(insert_test_task(clean_database, agent["id"]))
        work_id = asyncio.run(insert_due_work(clean_database, task["id"]))
        
        # Test join query
        from sqlalchemy import text
        with clean_database.begin() as conn:
            result = conn.execute(text("""
                SELECT t.title, a.name, w.id as work_id
                FROM task t
                JOIN agent a ON t.created_by = a.id
                JOIN due_work w ON w.task_id = t.id
                WHERE w.id = :work_id
            """), {"work_id": work_id}).fetchone()
            
            assert result is not None
            assert result.title == task["title"]
            assert result.name == agent["name"]
            assert result.work_id == work_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])