#!/usr/bin/env python3
"""
Comprehensive unit tests for API endpoints.

Tests all FastAPI routes with authentication, validation, error handling,
and edge cases. Uses mocked dependencies for isolated unit testing.
"""

import pytest
import uuid
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, patch
from fastapi.testclient import TestClient
from fastapi import HTTPException

from api.main import app
from api.schemas import TaskCreate, TaskUpdate, AgentCreate
from api.models import Task, Agent, TaskRun
from api.dependencies import get_database, get_current_agent


@pytest.fixture
def mock_db_session():
    """Mock database session."""
    mock_session = Mock()
    mock_session.execute = Mock()
    mock_session.commit = Mock()
    mock_session.rollback = Mock()
    mock_session.close = Mock()
    return mock_session


@pytest.fixture
def mock_current_agent():
    """Mock authenticated agent."""
    return {
        "id": str(uuid.uuid4()),
        "name": "test-agent",
        "scopes": ["task.create", "task.read", "task.update", "task.delete"]
    }


@pytest.fixture
def api_client(mock_db_session, mock_current_agent):
    """Create test client with mocked dependencies."""
    
    app.dependency_overrides[get_database] = lambda: mock_db_session
    app.dependency_overrides[get_current_agent] = lambda: mock_current_agent
    
    yield TestClient(app)
    
    # Clean up
    app.dependency_overrides.clear()


@pytest.mark.unit
@pytest.mark.api
class TestHealthEndpoints:
    """Test health and status endpoints."""
    
    def test_health_check_success(self, api_client, mock_db_session):
        """Test successful health check."""
        
        # Mock database health check
        mock_result = Mock()
        mock_result.scalar.return_value = 1
        mock_db_session.execute.return_value = mock_result
        
        response = api_client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["timestamp"]
        assert data["version"]
        assert "database" in data["checks"]
        assert data["checks"]["database"]["status"] == "healthy"
    
    def test_health_check_database_failure(self, api_client, mock_db_session):
        """Test health check with database failure."""
        
        # Mock database failure
        mock_db_session.execute.side_effect = Exception("Database connection failed")
        
        response = api_client.get("/health")
        
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["checks"]["database"]["status"] == "unhealthy"
        assert "Database connection failed" in data["checks"]["database"]["error"]
    
    def test_ready_endpoint(self, api_client):
        """Test readiness endpoint."""
        response = api_client.get("/ready")
        assert response.status_code == 200
        assert response.json()["ready"] is True


@pytest.mark.unit 
@pytest.mark.api
class TestTaskEndpoints:
    """Test task CRUD endpoints."""
    
    def test_create_task_success(self, api_client, mock_db_session, mock_current_agent):
        """Test successful task creation."""
        
        task_data = {
            "title": "Test Task",
            "description": "Test task description",
            "schedule_kind": "cron",
            "schedule_expr": "0 9 * * *",
            "timezone": "Europe/Chisinau",
            "payload": {
                "pipeline": [
                    {
                        "id": "test_step",
                        "uses": "test.action",
                        "with": {"param": "value"}
                    }
                ]
            },
            "priority": 5
        }
        
        # Mock successful insertion
        mock_result = Mock()
        mock_result.scalar.return_value = str(uuid.uuid4())
        mock_db_session.execute.return_value = mock_result
        
        response = api_client.post("/tasks", json=task_data)
        
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == task_data["title"]
        assert data["description"] == task_data["description"]
        assert data["status"] == "active"
        assert "id" in data
        assert "created_at" in data
        
        # Verify database call
        mock_db_session.execute.assert_called()
        mock_db_session.commit.assert_called_once()
    
    def test_create_task_invalid_schedule(self, api_client):
        """Test task creation with invalid schedule expression."""
        
        task_data = {
            "title": "Invalid Task",
            "description": "Task with invalid schedule",
            "schedule_kind": "cron",
            "schedule_expr": "invalid cron expression",
            "timezone": "Europe/Chisinau",
            "payload": {"pipeline": []},
            "priority": 5
        }
        
        response = api_client.post("/tasks", json=task_data)
        
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data
        assert "schedule_expr" in str(data["detail"]).lower()
    
    def test_create_task_missing_fields(self, api_client):
        """Test task creation with missing required fields."""
        
        task_data = {
            "title": "Incomplete Task"
            # Missing required fields
        }
        
        response = api_client.post("/tasks", json=task_data)
        
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data
        
        # Check specific missing fields
        error_messages = str(data["detail"])
        assert "description" in error_messages
        assert "schedule_kind" in error_messages
        assert "payload" in error_messages
    
    def test_get_task_success(self, api_client, mock_db_session):
        """Test retrieving a task by ID."""
        
        task_id = str(uuid.uuid4())
        
        # Mock database response
        mock_result = Mock()
        mock_task_data = {
            "id": task_id,
            "title": "Retrieved Task",
            "description": "Test task retrieval",
            "created_by": str(uuid.uuid4()),
            "schedule_kind": "once",
            "schedule_expr": "2025-08-10T10:00:00+00:00",
            "timezone": "Europe/Chisinau",
            "payload": {"pipeline": []},
            "status": "active",
            "priority": 5,
            "max_retries": 3,
            "created_at": datetime.now(timezone.utc)
        }
        mock_result.mappings.return_value.first.return_value = mock_task_data
        mock_db_session.execute.return_value = mock_result
        
        response = api_client.get(f"/tasks/{task_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == task_id
        assert data["title"] == "Retrieved Task"
        assert data["status"] == "active"
    
    def test_get_task_not_found(self, api_client, mock_db_session):
        """Test retrieving non-existent task."""
        
        task_id = str(uuid.uuid4())
        
        # Mock no results
        mock_result = Mock()
        mock_result.mappings.return_value.first.return_value = None
        mock_db_session.execute.return_value = mock_result
        
        response = api_client.get(f"/tasks/{task_id}")
        
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()
    
    def test_list_tasks_with_filters(self, api_client, mock_db_session):
        """Test listing tasks with status and pagination filters."""
        
        # Mock multiple tasks
        mock_result = Mock()
        mock_tasks = [
            {
                "id": str(uuid.uuid4()),
                "title": f"Task {i}",
                "description": f"Description {i}",
                "status": "active" if i % 2 == 0 else "paused",
                "priority": i,
                "created_at": datetime.now(timezone.utc)
            }
            for i in range(5)
        ]
        mock_result.mappings.return_value.all.return_value = mock_tasks[:3]  # limit=3
        mock_db_session.execute.return_value = mock_result
        
        response = api_client.get("/tasks?status=active&limit=3&offset=0")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 3
        
        # Verify database query parameters
        mock_db_session.execute.assert_called()
        call_args = mock_db_session.execute.call_args[1]  # Get keyword args
        assert call_args["status"] == "active"
        assert call_args["limit"] == 3
        assert call_args["offset"] == 0
    
    def test_update_task_success(self, api_client, mock_db_session, mock_current_agent):
        """Test successful task update."""
        
        task_id = str(uuid.uuid4())
        update_data = {
            "title": "Updated Task Title",
            "priority": 8,
            "status": "paused"
        }
        
        # Mock existing task check
        mock_check_result = Mock()
        mock_check_result.scalar.return_value = task_id
        
        # Mock update result
        mock_update_result = Mock()
        mock_updated_task = {
            "id": task_id,
            "title": "Updated Task Title", 
            "description": "Original description",
            "status": "paused",
            "priority": 8,
            "created_at": datetime.now(timezone.utc)
        }
        mock_update_result.mappings.return_value.first.return_value = mock_updated_task
        
        mock_db_session.execute.side_effect = [mock_check_result, Mock(), mock_update_result]
        
        response = api_client.put(f"/tasks/{task_id}", json=update_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == task_id
        assert data["title"] == "Updated Task Title"
        assert data["status"] == "paused"
        assert data["priority"] == 8
        
        # Verify update was called
        assert mock_db_session.execute.call_count == 3  # check, update, fetch
        mock_db_session.commit.assert_called_once()
    
    def test_update_task_not_found(self, api_client, mock_db_session):
        """Test updating non-existent task."""
        
        task_id = str(uuid.uuid4())
        update_data = {"title": "Updated Title"}
        
        # Mock no task found
        mock_result = Mock()
        mock_result.scalar.return_value = None
        mock_db_session.execute.return_value = mock_result
        
        response = api_client.put(f"/tasks/{task_id}", json=update_data)
        
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()
    
    def test_delete_task_success(self, api_client, mock_db_session):
        """Test successful task deletion."""
        
        task_id = str(uuid.uuid4())
        
        # Mock task exists and deletion succeeds
        mock_result = Mock()
        mock_result.rowcount = 1
        mock_db_session.execute.return_value = mock_result
        
        response = api_client.delete(f"/tasks/{task_id}")
        
        assert response.status_code == 204
        
        # Verify deletion was called
        mock_db_session.execute.assert_called()
        mock_db_session.commit.assert_called_once()
    
    def test_delete_task_not_found(self, api_client, mock_db_session):
        """Test deleting non-existent task."""
        
        task_id = str(uuid.uuid4())
        
        # Mock no rows affected
        mock_result = Mock()
        mock_result.rowcount = 0
        mock_db_session.execute.return_value = mock_result
        
        response = api_client.delete(f"/tasks/{task_id}")
        
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()


@pytest.mark.unit
@pytest.mark.api
class TestTaskRunEndpoints:
    """Test task run and execution history endpoints."""
    
    def test_get_task_runs(self, api_client, mock_db_session):
        """Test retrieving task execution history."""
        
        task_id = str(uuid.uuid4())
        
        # Mock task runs
        mock_result = Mock()
        mock_runs = [
            {
                "id": str(uuid.uuid4()),
                "task_id": task_id,
                "started_at": datetime.now(timezone.utc) - timedelta(minutes=10),
                "finished_at": datetime.now(timezone.utc) - timedelta(minutes=9),
                "success": True,
                "attempt": 1,
                "output": {"result": "success"},
                "error": None,
                "lease_owner": "worker-1"
            },
            {
                "id": str(uuid.uuid4()),
                "task_id": task_id,
                "started_at": datetime.now(timezone.utc) - timedelta(hours=1),
                "finished_at": datetime.now(timezone.utc) - timedelta(hours=1),
                "success": False,
                "attempt": 1,
                "output": None,
                "error": "Tool execution failed",
                "lease_owner": "worker-2"
            }
        ]
        mock_result.mappings.return_value.all.return_value = mock_runs
        mock_db_session.execute.return_value = mock_result
        
        response = api_client.get(f"/runs?task_id={task_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["success"] is True
        assert data[1]["success"] is False
        assert data[1]["error"] == "Tool execution failed"
    
    def test_get_task_runs_with_filters(self, api_client, mock_db_session):
        """Test retrieving task runs with success/failure filters."""
        
        # Mock successful runs only
        mock_result = Mock()
        mock_runs = [
            {
                "id": str(uuid.uuid4()),
                "task_id": str(uuid.uuid4()),
                "success": True,
                "attempt": 1,
                "finished_at": datetime.now(timezone.utc)
            }
        ]
        mock_result.mappings.return_value.all.return_value = mock_runs
        mock_db_session.execute.return_value = mock_result
        
        response = api_client.get("/runs?success=true&limit=10")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["success"] is True
        
        # Verify filter parameters
        call_args = mock_db_session.execute.call_args[1]
        assert call_args.get("success") is True
        assert call_args.get("limit") == 10


@pytest.mark.unit
@pytest.mark.api 
class TestAgentEndpoints:
    """Test agent management endpoints."""
    
    def test_create_agent_success(self, api_client, mock_db_session):
        """Test successful agent creation."""
        
        agent_data = {
            "name": "new-test-agent",
            "scopes": ["task.read", "notify", "calendar.read"]
        }
        
        # Mock successful creation
        mock_result = Mock()
        mock_result.scalar.return_value = str(uuid.uuid4())
        mock_db_session.execute.return_value = mock_result
        
        response = api_client.post("/agents", json=agent_data)
        
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == agent_data["name"]
        assert data["scopes"] == agent_data["scopes"]
        assert "id" in data
        assert "created_at" in data
    
    def test_create_agent_duplicate_name(self, api_client, mock_db_session):
        """Test agent creation with duplicate name."""
        
        agent_data = {
            "name": "existing-agent",
            "scopes": ["test"]
        }
        
        # Mock unique constraint violation
        from sqlalchemy.exc import IntegrityError
        mock_db_session.execute.side_effect = IntegrityError("", "", "")
        
        response = api_client.post("/agents", json=agent_data)
        
        assert response.status_code == 400
        data = response.json()
        assert "already exists" in data["detail"].lower()
    
    def test_list_agents(self, api_client, mock_db_session):
        """Test listing agents."""
        
        # Mock agents
        mock_result = Mock()
        mock_agents = [
            {
                "id": str(uuid.uuid4()),
                "name": f"agent-{i}",
                "scopes": ["test", "notify"],
                "created_at": datetime.now(timezone.utc)
            }
            for i in range(3)
        ]
        mock_result.mappings.return_value.all.return_value = mock_agents
        mock_db_session.execute.return_value = mock_result
        
        response = api_client.get("/agents")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        assert all("name" in agent for agent in data)
        assert all("scopes" in agent for agent in data)


@pytest.mark.unit
@pytest.mark.api
class TestAuthenticationAndAuthorization:
    """Test API authentication and authorization."""
    
    def test_missing_authentication(self):
        """Test request without authentication."""
        
        # Create client without auth overrides
        client = TestClient(app)
        
        response = client.get("/tasks")
        
        assert response.status_code == 401
        data = response.json()
        assert "not authenticated" in data["detail"].lower()
    
    def test_insufficient_scopes(self, mock_db_session):
        """Test request with insufficient scopes."""
        
        # Mock agent with limited scopes
        limited_agent = {
            "id": str(uuid.uuid4()),
            "name": "limited-agent",
            "scopes": ["task.read"]  # Missing task.create
        }
        
        app.dependency_overrides[get_database] = lambda: mock_db_session
        app.dependency_overrides[get_current_agent] = lambda: limited_agent
        
        client = TestClient(app)
        
        task_data = {
            "title": "Test Task",
            "description": "Test",
            "schedule_kind": "once",
            "schedule_expr": "2025-08-10T10:00:00+00:00",
            "timezone": "UTC",
            "payload": {"pipeline": []}
        }
        
        response = client.post("/tasks", json=task_data)
        
        assert response.status_code == 403
        data = response.json()
        assert "insufficient privileges" in data["detail"].lower()
        
        # Clean up
        app.dependency_overrides.clear()


@pytest.mark.unit
@pytest.mark.api
class TestErrorHandling:
    """Test API error handling and edge cases."""
    
    def test_invalid_uuid_format(self, api_client):
        """Test endpoints with invalid UUID format."""
        
        response = api_client.get("/tasks/invalid-uuid-format")
        
        assert response.status_code == 422
        data = response.json()
        assert "invalid" in data["detail"][0]["msg"].lower()
    
    def test_database_error_handling(self, api_client, mock_db_session):
        """Test handling of database errors."""
        
        # Mock database failure
        mock_db_session.execute.side_effect = Exception("Database connection lost")
        
        response = api_client.get("/tasks")
        
        assert response.status_code == 500
        data = response.json()
        assert "internal server error" in data["detail"].lower()
    
    def test_request_validation_errors(self, api_client):
        """Test comprehensive request validation."""
        
        invalid_task_data = {
            "title": "",  # Empty title
            "description": "x" * 10000,  # Too long description
            "schedule_kind": "invalid_kind",  # Invalid enum
            "priority": 15,  # Out of range (0-10)
            "timezone": "Invalid/Timezone",  # Invalid timezone
            "payload": "not an object"  # Invalid type
        }
        
        response = api_client.post("/tasks", json=invalid_task_data)
        
        assert response.status_code == 422
        data = response.json()
        errors = data["detail"]
        
        # Check specific validation errors
        error_fields = [error["loc"][-1] for error in errors]
        assert "title" in error_fields
        assert "description" in error_fields
        assert "schedule_kind" in error_fields
        assert "priority" in error_fields
    
    def test_rate_limiting_simulation(self, api_client):
        """Test rate limiting (simulated)."""
        
        # Note: This would require actual rate limiting middleware
        # For now, test that multiple rapid requests are handled
        
        responses = []
        for _ in range(5):
            response = api_client.get("/health")
            responses.append(response)
        
        # All should succeed (no rate limiting configured yet)
        assert all(r.status_code == 200 for r in responses)


@pytest.mark.unit
@pytest.mark.api
@pytest.mark.benchmark
class TestAPIPerformance:
    """Test API endpoint performance."""
    
    def test_task_creation_performance(self, api_client, mock_db_session, benchmark):
        """Benchmark task creation endpoint performance."""
        
        task_data = {
            "title": "Performance Test Task",
            "description": "Task for performance testing",
            "schedule_kind": "cron",
            "schedule_expr": "0 9 * * *",
            "timezone": "Europe/Chisinau",
            "payload": {"pipeline": []},
            "priority": 5
        }
        
        # Mock fast database response
        mock_result = Mock()
        mock_result.scalar.return_value = str(uuid.uuid4())
        mock_db_session.execute.return_value = mock_result
        
        def create_task():
            response = api_client.post("/tasks", json=task_data)
            return response
        
        response = benchmark(create_task)
        
        assert response.status_code == 201
        # Should complete in under 100ms
        assert benchmark.stats.mean < 0.1
    
    def test_task_list_performance(self, api_client, mock_db_session, benchmark):
        """Benchmark task listing endpoint performance."""
        
        # Mock large task list
        mock_result = Mock()
        mock_tasks = [
            {
                "id": str(uuid.uuid4()),
                "title": f"Task {i}",
                "description": f"Description {i}",
                "status": "active",
                "priority": 5,
                "created_at": datetime.now(timezone.utc)
            }
            for i in range(100)
        ]
        mock_result.mappings.return_value.all.return_value = mock_tasks
        mock_db_session.execute.return_value = mock_result
        
        def list_tasks():
            response = api_client.get("/tasks?limit=100")
            return response
        
        response = benchmark(list_tasks)
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 100
        # Should complete in under 200ms
        assert benchmark.stats.mean < 0.2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--benchmark-skip"])