#!/usr/bin/env python3
"""
Simple API Tests for Ordinaut.

Basic smoke tests to validate the test framework setup.
"""

import pytest
import uuid
import json
import os
from datetime import datetime, timezone, timedelta

# Set test environment variables before importing modules
os.environ["DATABASE_URL"] = "sqlite:///test_simple.db"
os.environ["REDIS_URL"] = "memory://"

# Now import after environment is set
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.mark.api
@pytest.mark.smoke
class TestBasicAPIFunctionality:
    """Basic smoke tests for API functionality."""
    
    def test_environment_setup(self):
        """Test that environment variables are properly set."""
        assert os.environ.get("DATABASE_URL") == "sqlite:///test_simple.db"
        assert os.environ.get("REDIS_URL") == "memory://"
    
    def test_database_connection(self, clean_database):
        """Test basic database connectivity."""
        # Should be able to execute simple query
        with clean_database.begin() as conn:
            result = conn.execute("SELECT 1 as test").scalar()
        assert result == 1
    
    def test_insert_test_agent_helper(self, clean_database):
        """Test the insert_test_agent helper function."""
        from conftest import insert_test_agent
        
        agent_data = {
            "id": str(uuid.uuid4()),
            "name": "test-smoke-agent",
            "scopes": ["test", "smoke"]
        }
        
        import asyncio
        agent = asyncio.run(insert_test_agent(clean_database, agent_data))
        
        assert agent["id"] == agent_data["id"]
        assert agent["name"] == agent_data["name"]
    
    def test_insert_test_task_helper(self, clean_database):
        """Test the insert_test_task helper function."""
        from conftest import insert_test_agent, insert_test_task
        
        import asyncio
        
        # Create agent first
        agent = asyncio.run(insert_test_agent(clean_database))
        
        # Create task
        task_data = {
            "title": "Smoke Test Task",
            "description": "Basic test task",
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
        
        assert task["title"] == "Smoke Test Task"
        assert task["status"] == "active"
        assert task["created_by"] == agent["id"]
    
    def test_mock_tool_catalog_fixture(self, mock_tool_catalog):
        """Test the mock tool catalog fixture."""
        assert isinstance(mock_tool_catalog, list)
        assert len(mock_tool_catalog) > 0
        
        # Check structure of first tool
        first_tool = mock_tool_catalog[0]
        required_fields = ["address", "transport", "input_schema", "output_schema", "scopes"]
        
        for field in required_fields:
            assert field in first_tool, f"Tool missing required field: {field}"
    
    def test_performance_benchmarks_fixture(self, performance_benchmarks):
        """Test the performance benchmarks fixture."""
        assert isinstance(performance_benchmarks, dict)
        
        required_sections = ["template_rendering", "pipeline_execution", "database_operations"]
        for section in required_sections:
            assert section in performance_benchmarks, f"Missing benchmark section: {section}"


@pytest.mark.api
@pytest.mark.smoke  
class TestDatabaseSchemaValidation:
    """Test database schema and basic operations."""
    
    def test_agent_table_exists(self, clean_database):
        """Test that agent table exists with correct structure."""
        with clean_database.begin() as conn:
            # Should be able to query agent table
            result = conn.execute("SELECT COUNT(*) FROM agent").scalar()
            assert result >= 0  # Should at least execute without error
    
    def test_task_table_exists(self, clean_database):
        """Test that task table exists with correct structure."""
        with clean_database.begin() as conn:
            result = conn.execute("SELECT COUNT(*) FROM task").scalar() 
            assert result >= 0
    
    def test_task_run_table_exists(self, clean_database):
        """Test that task_run table exists."""
        with clean_database.begin() as conn:
            result = conn.execute("SELECT COUNT(*) FROM task_run").scalar()
            assert result >= 0
    
    def test_due_work_table_exists(self, clean_database):
        """Test that due_work table exists."""
        with clean_database.begin() as conn:
            result = conn.execute("SELECT COUNT(*) FROM due_work").scalar()
            assert result >= 0
    
    def test_foreign_key_relationships(self, clean_database):
        """Test basic foreign key relationships work."""
        from conftest import insert_test_agent, insert_test_task
        import asyncio
        
        # Create agent
        agent = asyncio.run(insert_test_agent(clean_database))
        
        # Create task referencing agent
        task = asyncio.run(insert_test_task(clean_database, agent["id"]))
        
        # Verify relationship
        with clean_database.begin() as conn:
            result = conn.execute("""
                SELECT t.title, a.name 
                FROM task t 
                JOIN agent a ON t.created_by = a.id 
                WHERE t.id = ?
            """, (task["id"],)).fetchone()
            
            assert result is not None
            assert result.title == task["title"]
            assert result.name == agent["name"]


@pytest.mark.smoke
class TestTestFrameworkIntegrity:
    """Test that the test framework itself is working correctly."""
    
    def test_pytest_marks_work(self):
        """Test that pytest markers work."""
        # This test itself should be marked as 'smoke'
        assert True
    
    def test_async_support_works(self):
        """Test that async test support works."""
        import asyncio
        
        async def async_operation():
            await asyncio.sleep(0.001)
            return "async_success"
        
        result = asyncio.run(async_operation())
        assert result == "async_success"
    
    def test_fixtures_load_properly(self, clean_database, mock_tool_catalog, performance_benchmarks):
        """Test that all major fixtures load without errors."""
        # Database fixture
        assert clean_database is not None
        
        # Mock catalog fixture  
        assert isinstance(mock_tool_catalog, list)
        assert len(mock_tool_catalog) > 0
        
        # Performance benchmarks fixture
        assert isinstance(performance_benchmarks, dict)
        
        print("All fixtures loaded successfully")
    
    def test_exception_handling(self):
        """Test that test framework handles exceptions properly."""
        try:
            raise ValueError("Test exception")
        except ValueError as e:
            assert "Test exception" in str(e)
        
        # Test should continue after handled exception
        assert True


if __name__ == "__main__":
    # Allow running this test file directly
    pytest.main([__file__, "-v"])