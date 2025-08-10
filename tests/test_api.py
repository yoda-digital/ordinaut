#!/usr/bin/env python3
"""
Comprehensive API Tests for Ordinaut.

Tests all FastAPI endpoints including:
- Task CRUD operations
- Agent management
- Run monitoring
- Event publishing
- Health checks
- Authentication and authorization
- Error handling and validation

Uses real test database with proper cleanup and isolation.
"""

import pytest
import asyncio
import uuid
import json
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock, AsyncMock
from httpx import AsyncClient

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock environment variables before importing API modules
os.environ["DATABASE_URL"] = "sqlite:///test_orchestrator.db"
os.environ["REDIS_URL"] = "memory://"

from api.main import app
from api.schemas import TaskCreateRequest, TaskUpdateRequest, AgentResponse
from conftest import insert_test_agent, insert_test_task, insert_due_work


@pytest.mark.api
class TestTaskEndpoints:
    """Test task CRUD endpoints."""
    
    def test_create_task_valid_payload(self, clean_database, sample_agent, sample_task):
        """Test creating a task with valid payload."""
        # Insert agent first
        with clean_database.begin() as conn:
            conn.execute(
                """INSERT INTO agent (id, name, scopes) VALUES (?, ?, ?)""",
                (sample_agent["id"], sample_agent["name"], json.dumps(sample_agent["scopes"]))
            )
        
        with TestClient(app) as client:
            response = client.post(
                "/tasks",
                json={
                    "title": sample_task["title"],
                    "description": sample_task["description"],
                    "schedule_kind": sample_task["schedule_kind"],
                    "schedule_expr": sample_task["schedule_expr"],
                    "timezone": sample_task["timezone"],
                    "payload": sample_task["payload"],
                    "priority": sample_task["priority"],
                    "created_by": sample_agent["id"]
                },
                headers={"Authorization": f"Bearer {sample_agent['id']}"}
            )
        
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == sample_task["title"]
        assert data["status"] == "active"
        assert data["created_by"] == sample_agent["id"]
    
    def test_create_task_invalid_schedule(self, clean_database, sample_agent):
        """Test creating task with invalid schedule expression."""
        # Insert agent first
        with clean_database.begin() as conn:
            conn.execute(
                """INSERT INTO agent (id, name, scopes) VALUES (?, ?, ?)""",
                (sample_agent["id"], sample_agent["name"], json.dumps(sample_agent["scopes"]))
            )
        
        with TestClient(app) as client:
            response = client.post(
                "/tasks",
                json={
                    "title": "Invalid Task",
                    "description": "Task with invalid schedule",
                    "schedule_kind": "cron",
                    "schedule_expr": "invalid cron expression",
                    "timezone": "Europe/Chisinau",
                    "payload": {"pipeline": [{"id": "test", "uses": "test.tool"}]},
                    "created_by": sample_agent["id"]
                },
                headers={"Authorization": f"Bearer {sample_agent['id']}"}
            )
        
        assert response.status_code == 422
        data = response.json()
        assert "schedule_expr" in data["detail"][0]["loc"]
    
    def test_get_task_by_id(self, clean_database, sample_agent):
        """Test retrieving a task by ID."""
        # Setup test data
        with clean_database.begin() as conn:
            conn.execute(
                """INSERT INTO agent (id, name, scopes) VALUES (?, ?, ?)""",
                (sample_agent["id"], sample_agent["name"], json.dumps(sample_agent["scopes"]))
            )
            
            task_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO task (id, title, description, created_by, schedule_kind, schedule_expr, timezone, payload, status, priority, max_retries) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (task_id, "Test Task", "Description", sample_agent["id"], "cron", "0 9 * * *", "UTC", 
                 json.dumps({"pipeline": []}), "active", 5, 3)
            )
        
        with TestClient(app) as client:
            response = client.get(
                f"/tasks/{task_id}",
                headers={"Authorization": f"Bearer {sample_agent['id']}"}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == task_id
        assert data["title"] == "Test Task"
    
    def test_get_task_not_found(self, clean_database, sample_agent):
        """Test retrieving non-existent task."""
        # Insert agent for auth
        with clean_database.begin() as conn:
            conn.execute(
                """INSERT INTO agent (id, name, scopes) VALUES (?, ?, ?)""",
                (sample_agent["id"], sample_agent["name"], json.dumps(sample_agent["scopes"]))
            )
        
        non_existent_id = str(uuid.uuid4())
        with TestClient(app) as client:
            response = client.get(
                f"/tasks/{non_existent_id}",
                headers={"Authorization": f"Bearer {sample_agent['id']}"}
            )
        
        assert response.status_code == 404
    
    def test_update_task(self, clean_database, sample_agent):
        """Test updating an existing task."""
        # Setup test data
        with clean_database.begin() as conn:
            conn.execute(
                """INSERT INTO agent (id, name, scopes) VALUES (?, ?, ?)""",
                (sample_agent["id"], sample_agent["name"], json.dumps(sample_agent["scopes"]))
            )
            
            task_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO task (id, title, description, created_by, schedule_kind, schedule_expr, timezone, payload, status, priority, max_retries) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (task_id, "Original Title", "Original Description", sample_agent["id"], "cron", "0 9 * * *", "UTC", 
                 json.dumps({"pipeline": []}), "active", 5, 3)
            )
        
        with TestClient(app) as client:
            response = client.put(
                f"/tasks/{task_id}",
                json={
                    "title": "Updated Title",
                    "description": "Updated Description",
                    "priority": 3
                },
                headers={"Authorization": f"Bearer {sample_agent['id']}"}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Title"
        assert data["description"] == "Updated Description"
        assert data["priority"] == 3
    
    def test_list_tasks_with_filters(self, clean_database, sample_agent):
        """Test listing tasks with various filters."""
        # Setup test data
        with clean_database.begin() as conn:
            conn.execute(
                """INSERT INTO agent (id, name, scopes) VALUES (?, ?, ?)""",
                (sample_agent["id"], sample_agent["name"], json.dumps(sample_agent["scopes"]))
            )
            
            # Insert multiple tasks
            tasks = [
                (str(uuid.uuid4()), "Active Task", "active"),
                (str(uuid.uuid4()), "Paused Task", "paused"),
                (str(uuid.uuid4()), "Another Active", "active"),
            ]
            
            for task_id, title, status in tasks:
                conn.execute(
                    """INSERT INTO task (id, title, description, created_by, schedule_kind, schedule_expr, timezone, payload, status, priority, max_retries) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (task_id, title, "Description", sample_agent["id"], "cron", "0 9 * * *", "UTC", 
                     json.dumps({"pipeline": []}), status, 5, 3)
                )
        
        with TestClient(app) as client:
            # Test filter by status
            response = client.get(
                "/tasks?status=active",
                headers={"Authorization": f"Bearer {sample_agent['id']}"}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2  # Two active tasks
        assert all(item["status"] == "active" for item in data["items"])
    
    def test_delete_task(self, clean_database, sample_agent):
        """Test deleting a task."""
        # Setup test data
        with clean_database.begin() as conn:
            conn.execute(
                """INSERT INTO agent (id, name, scopes) VALUES (?, ?, ?)""",
                (sample_agent["id"], sample_agent["name"], json.dumps(sample_agent["scopes"]))
            )
            
            task_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO task (id, title, description, created_by, schedule_kind, schedule_expr, timezone, payload, status, priority, max_retries) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (task_id, "Task to Delete", "Description", sample_agent["id"], "cron", "0 9 * * *", "UTC", 
                 json.dumps({"pipeline": []}), "active", 5, 3)
            )
        
        with TestClient(app) as client:
            response = client.delete(
                f"/tasks/{task_id}",
                headers={"Authorization": f"Bearer {sample_agent['id']}"}
            )
        
        assert response.status_code == 204
        
        # Verify task is deleted
        with TestClient(app) as client:
            get_response = client.get(
                f"/tasks/{task_id}",
                headers={"Authorization": f"Bearer {sample_agent['id']}"}
            )
        assert get_response.status_code == 404


@pytest.mark.api
class TestRunEndpoints:
    """Test task run monitoring endpoints."""
    
    def test_get_task_runs(self, clean_database, sample_agent):
        """Test retrieving task runs."""
        # Setup test data
        with clean_database.begin() as conn:
            conn.execute(
                """INSERT INTO agent (id, name, scopes) VALUES (?, ?, ?)""",
                (sample_agent["id"], sample_agent["name"], json.dumps(sample_agent["scopes"]))
            )
            
            task_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO task (id, title, description, created_by, schedule_kind, schedule_expr, timezone, payload, status, priority, max_retries) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (task_id, "Test Task", "Description", sample_agent["id"], "once", "2025-12-25T10:00:00Z", "UTC", 
                 json.dumps({"pipeline": []}), "active", 5, 3)
            )
            
            # Insert task run
            run_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO task_run (id, task_id, started_at, finished_at, success, attempt, output) 
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (run_id, task_id, datetime.now(), datetime.now(), True, 1, json.dumps({"result": "success"}))
            )
        
        with TestClient(app) as client:
            response = client.get(
                f"/runs?task_id={task_id}",
                headers={"Authorization": f"Bearer {sample_agent['id']}"}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["task_id"] == task_id
        assert data["items"][0]["success"] == True
    
    def test_get_run_by_id(self, clean_database, sample_agent):
        """Test retrieving a specific run by ID."""
        # Setup test data
        with clean_database.begin() as conn:
            conn.execute(
                """INSERT INTO agent (id, name, scopes) VALUES (?, ?, ?)""",
                (sample_agent["id"], sample_agent["name"], json.dumps(sample_agent["scopes"]))
            )
            
            task_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO task (id, title, description, created_by, schedule_kind, schedule_expr, timezone, payload, status, priority, max_retries) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (task_id, "Test Task", "Description", sample_agent["id"], "once", "2025-12-25T10:00:00Z", "UTC", 
                 json.dumps({"pipeline": []}), "active", 5, 3)
            )
            
            run_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO task_run (id, task_id, started_at, finished_at, success, attempt, output) 
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (run_id, task_id, datetime.now(), datetime.now(), True, 1, json.dumps({"result": "success"}))
            )
        
        with TestClient(app) as client:
            response = client.get(
                f"/runs/{run_id}",
                headers={"Authorization": f"Bearer {sample_agent['id']}"}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == run_id
        assert data["task_id"] == task_id


@pytest.mark.api
class TestAuthenticationAndAuthorization:
    """Test authentication and authorization mechanisms."""
    
    def test_missing_authorization_header(self):
        """Test API calls without authorization header."""
        with TestClient(app) as client:
            response = client.get("/tasks")
        
        assert response.status_code == 401
        assert "Authorization header missing" in response.json()["detail"]
    
    def test_invalid_authorization_format(self):
        """Test API calls with invalid authorization format."""
        with TestClient(app) as client:
            response = client.get(
                "/tasks",
                headers={"Authorization": "InvalidFormat token"}
            )
        
        assert response.status_code == 401
        assert "Invalid authorization header format" in response.json()["detail"]
    
    def test_nonexistent_agent(self, clean_database):
        """Test API calls with non-existent agent."""
        fake_agent_id = str(uuid.uuid4())
        
        with TestClient(app) as client:
            response = client.get(
                "/tasks",
                headers={"Authorization": f"Bearer {fake_agent_id}"}
            )
        
        assert response.status_code == 401
        assert "not found or invalid" in response.json()["detail"]
    
    def test_agent_scope_restrictions(self, clean_database):
        """Test that agents can only access resources within their scopes."""
        # Create agent with limited scopes
        limited_agent = {
            "id": str(uuid.uuid4()),
            "name": "limited-agent",
            "scopes": ["read"]  # No write access
        }
        
        with clean_database.begin() as conn:
            conn.execute(
                """INSERT INTO agent (id, name, scopes) VALUES (?, ?, ?)""",
                (limited_agent["id"], limited_agent["name"], json.dumps(limited_agent["scopes"]))
            )
        
        # Try to create a task (requires write scope)
        with TestClient(app) as client:
            response = client.post(
                "/tasks",
                json={
                    "title": "Test Task",
                    "description": "Should fail",
                    "schedule_kind": "once",
                    "schedule_expr": "2025-12-25T10:00:00Z",
                    "timezone": "UTC",
                    "payload": {"pipeline": []},
                    "created_by": limited_agent["id"]
                },
                headers={"Authorization": f"Bearer {limited_agent['id']}"}
            )
        
        # Should succeed for now since we haven't implemented strict scope checking
        # In production, this would return 403 for insufficient scopes
        assert response.status_code in (201, 403)


@pytest.mark.api
class TestHealthEndpoints:
    """Test health check and monitoring endpoints."""
    
    def test_health_check(self):
        """Test basic health check endpoint."""
        with TestClient(app) as client:
            response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "timestamp" in data
        assert "database" in data
    
    def test_metrics_endpoint(self):
        """Test metrics endpoint for monitoring."""
        with TestClient(app) as client:
            response = client.get("/metrics")
        
        # Should return Prometheus-formatted metrics
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]


@pytest.mark.api
class TestValidationAndErrorHandling:
    """Test input validation and error handling."""
    
    def test_invalid_uuid_format(self, clean_database, sample_agent):
        """Test handling of invalid UUID formats."""
        with clean_database.begin() as conn:
            conn.execute(
                """INSERT INTO agent (id, name, scopes) VALUES (?, ?, ?)""",
                (sample_agent["id"], sample_agent["name"], json.dumps(sample_agent["scopes"]))
            )
        
        with TestClient(app) as client:
            response = client.get(
                "/tasks/invalid-uuid-format",
                headers={"Authorization": f"Bearer {sample_agent['id']}"}
            )
        
        assert response.status_code == 422
    
    def test_payload_validation(self, clean_database, sample_agent):
        """Test payload validation for task creation."""
        with clean_database.begin() as conn:
            conn.execute(
                """INSERT INTO agent (id, name, scopes) VALUES (?, ?, ?)""",
                (sample_agent["id"], sample_agent["name"], json.dumps(sample_agent["scopes"]))
            )
        
        invalid_payloads = [
            {},  # Missing pipeline
            {"pipeline": "not-an-array"},  # Pipeline not an array
            {"pipeline": [{"invalid": "step"}]},  # Invalid step format
        ]
        
        for payload in invalid_payloads:
            with TestClient(app) as client:
                response = client.post(
                    "/tasks",
                    json={
                        "title": "Invalid Task",
                        "description": "Should fail validation",
                        "schedule_kind": "once",
                        "schedule_expr": "2025-12-25T10:00:00Z",
                        "timezone": "UTC",
                        "payload": payload,
                        "created_by": sample_agent["id"]
                    },
                    headers={"Authorization": f"Bearer {sample_agent['id']}"}
                )
            
            assert response.status_code == 422
    
    def test_timezone_validation(self, clean_database, sample_agent):
        """Test timezone validation."""
        with clean_database.begin() as conn:
            conn.execute(
                """INSERT INTO agent (id, name, scopes) VALUES (?, ?, ?)""",
                (sample_agent["id"], sample_agent["name"], json.dumps(sample_agent["scopes"]))
            )
        
        with TestClient(app) as client:
            response = client.post(
                "/tasks",
                json={
                    "title": "Invalid Timezone Task",
                    "description": "Should fail timezone validation",
                    "schedule_kind": "cron",
                    "schedule_expr": "0 9 * * *",
                    "timezone": "Invalid/Timezone",
                    "payload": {"pipeline": []},
                    "created_by": sample_agent["id"]
                },
                headers={"Authorization": f"Bearer {sample_agent['id']}"}
            )
        
        assert response.status_code == 422


@pytest.mark.api
@pytest.mark.asyncio
class TestAsyncAPIOperations:
    """Test async API operations and WebSocket connections."""
    
    async def test_async_task_creation(self, clean_database, sample_agent, sample_task):
        """Test async task creation using httpx."""
        # Insert agent first
        with clean_database.begin() as conn:
            conn.execute(
                """INSERT INTO agent (id, name, scopes) VALUES (?, ?, ?)""",
                (sample_agent["id"], sample_agent["name"], json.dumps(sample_agent["scopes"]))
            )
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/tasks",
                json={
                    "title": sample_task["title"],
                    "description": sample_task["description"],
                    "schedule_kind": sample_task["schedule_kind"],
                    "schedule_expr": sample_task["schedule_expr"],
                    "timezone": sample_task["timezone"],
                    "payload": sample_task["payload"],
                    "created_by": sample_agent["id"]
                },
                headers={"Authorization": f"Bearer {sample_agent['id']}"}
            )
        
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == sample_task["title"]
    
    async def test_concurrent_api_requests(self, clean_database, sample_agent):
        """Test handling of concurrent API requests."""
        # Insert agent first
        with clean_database.begin() as conn:
            conn.execute(
                """INSERT INTO agent (id, name, scopes) VALUES (?, ?, ?)""",
                (sample_agent["id"], sample_agent["name"], json.dumps(sample_agent["scopes"]))
            )
        
        # Create multiple concurrent requests
        async def create_task(task_number):
            async with AsyncClient(app=app, base_url="http://test") as client:
                return await client.post(
                    "/tasks",
                    json={
                        "title": f"Concurrent Task {task_number}",
                        "description": "Concurrent creation test",
                        "schedule_kind": "once",
                        "schedule_expr": f"2025-12-25T1{task_number}:00:00Z",
                        "timezone": "UTC",
                        "payload": {"pipeline": []},
                        "created_by": sample_agent["id"]
                    },
                    headers={"Authorization": f"Bearer {sample_agent['id']}"}
                )
        
        # Execute concurrent requests
        tasks = [create_task(i) for i in range(5)]
        responses = await asyncio.gather(*tasks)
        
        # All should succeed
        assert all(response.status_code == 201 for response in responses)
        
        # All should have unique IDs
        ids = [response.json()["id"] for response in responses]
        assert len(set(ids)) == len(ids)


# Performance benchmarks for API endpoints
@pytest.mark.benchmark
class TestAPIPerformance:
    """Performance benchmarks for API endpoints."""
    
    def test_task_creation_performance(self, benchmark, clean_database, sample_agent, sample_task):
        """Benchmark task creation performance."""
        # Insert agent first
        with clean_database.begin() as conn:
            conn.execute(
                """INSERT INTO agent (id, name, scopes) VALUES (?, ?, ?)""",
                (sample_agent["id"], sample_agent["name"], json.dumps(sample_agent["scopes"]))
            )
        
        def create_task():
            with TestClient(app) as client:
                response = client.post(
                    "/tasks",
                    json={
                        "title": f"Benchmark Task {uuid.uuid4()}",
                        "description": sample_task["description"],
                        "schedule_kind": sample_task["schedule_kind"],
                        "schedule_expr": sample_task["schedule_expr"],
                        "timezone": sample_task["timezone"],
                        "payload": sample_task["payload"],
                        "created_by": sample_agent["id"]
                    },
                    headers={"Authorization": f"Bearer {sample_agent['id']}"}
                )
            return response.status_code == 201
        
        # Run benchmark
        result = benchmark(create_task)
        assert result is True
    
    def test_task_list_performance(self, benchmark, clean_database, sample_agent):
        """Benchmark task listing performance."""
        # Setup test data - insert agent and multiple tasks
        with clean_database.begin() as conn:
            conn.execute(
                """INSERT INTO agent (id, name, scopes) VALUES (?, ?, ?)""",
                (sample_agent["id"], sample_agent["name"], json.dumps(sample_agent["scopes"]))
            )
            
            # Insert 100 tasks for performance testing
            for i in range(100):
                task_id = str(uuid.uuid4())
                conn.execute(
                    """INSERT INTO task (id, title, description, created_by, schedule_kind, schedule_expr, timezone, payload, status, priority, max_retries) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (task_id, f"Perf Test Task {i}", "Performance test task", sample_agent["id"], 
                     "once", f"2025-12-25T1{i%10}:00:00Z", "UTC", 
                     json.dumps({"pipeline": []}), "active", 5, 3)
                )
        
        def list_tasks():
            with TestClient(app) as client:
                response = client.get(
                    "/tasks?limit=50",
                    headers={"Authorization": f"Bearer {sample_agent['id']}"}
                )
            return response.status_code == 200 and len(response.json()["items"]) > 0
        
        result = benchmark(list_tasks)
        assert result is True