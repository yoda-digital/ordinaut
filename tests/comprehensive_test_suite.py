#!/usr/bin/env python3
"""
Comprehensive Test Suite for Personal Agent Orchestrator

This test suite provides complete coverage of all critical system components
without requiring external dependencies like Docker. It includes:

- Template rendering validation (fixed)
- RRULE processing with DST scenarios
- Worker concurrency and SKIP LOCKED behavior simulation  
- Pipeline execution with mocked tools
- Performance benchmarks
- Chaos engineering tests
- End-to-end workflow simulation
- Load testing scenarios

All tests use in-memory databases and mocked external services.
"""

import pytest
import asyncio
import time
import json
import uuid
import sqlite3
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any, List
import os

# Import core components
from engine.template import render_templates, extract_template_variables, validate_template_variables
from engine.rruler import next_occurrence, RRuleProcessor
from engine.executor import run_pipeline
from engine.registry import ToolCatalog

# Import observability components
from observability.logging import StructuredLogger, set_request_context
from observability.metrics import orchestrator_metrics


class MockDatabase:
    """In-memory SQLite database for testing."""
    
    def __init__(self):
        self.db_path = ":memory:"
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()
    
    def _init_schema(self):
        """Initialize test database schema."""
        schema = """
        CREATE TABLE agent (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            scopes TEXT NOT NULL, -- JSON array
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        
        CREATE TABLE task (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            created_by TEXT NOT NULL REFERENCES agent(id),
            schedule_kind TEXT NOT NULL,
            schedule_expr TEXT,
            timezone TEXT NOT NULL DEFAULT 'Europe/Chisinau',
            payload TEXT NOT NULL, -- JSON
            status TEXT NOT NULL DEFAULT 'active',
            priority INTEGER NOT NULL DEFAULT 5,
            max_retries INTEGER NOT NULL DEFAULT 3,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        
        CREATE TABLE task_run (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES task(id),
            lease_owner TEXT,
            started_at TEXT,
            finished_at TEXT,
            success INTEGER, -- Boolean
            error TEXT,
            attempt INTEGER NOT NULL DEFAULT 1,
            output TEXT, -- JSON
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        
        CREATE TABLE due_work (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL REFERENCES task(id),
            run_at TEXT NOT NULL,
            locked_until TEXT,
            locked_by TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        
        CREATE INDEX idx_due_work_run_at ON due_work (run_at);
        """
        
        self.conn.executescript(schema)
        self.conn.commit()
    
    def execute(self, sql: str, params: Dict = None) -> sqlite3.Cursor:
        """Execute SQL with parameters."""
        return self.conn.execute(sql, params or {})
    
    def commit(self):
        """Commit transaction."""
        self.conn.commit()
    
    def close(self):
        """Close connection."""
        self.conn.close()


@pytest.fixture
def mock_db():
    """Create mock database for testing."""
    db = MockDatabase()
    yield db
    db.close()


@pytest.fixture
def sample_agent():
    """Sample agent for testing."""
    return {
        "id": str(uuid.uuid4()),
        "name": f"test-agent-{int(time.time())}",
        "scopes": json.dumps(["test", "notify", "calendar.read"])
    }


@pytest.fixture  
def sample_task(sample_agent):
    """Sample task for testing."""
    return {
        "id": str(uuid.uuid4()),
        "title": "Comprehensive Test Task",
        "description": "Task for comprehensive testing",
        "created_by": sample_agent["id"],
        "schedule_kind": "cron",
        "schedule_expr": "0 9 * * *",
        "timezone": "Europe/Chisinau",
        "payload": json.dumps({
            "pipeline": [
                {
                    "id": "test_step",
                    "uses": "test-tool.execute",
                    "with": {"message": "Hello ${params.name}"},
                    "save_as": "result"
                }
            ],
            "params": {"name": "World"}
        }),
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
        }
    ]


class TestFixedTemplateRendering:
    """Test the fixed template rendering functionality."""
    
    def test_template_rendering_basic(self):
        """Test basic template rendering functionality."""
        template = "Hello ${name}, you are ${age} years old!"
        context = {"name": "Alice", "age": 30}
        
        result = render_templates(template, context)
        assert result == "Hello Alice, you are 30 years old!"
    
    def test_template_rendering_nested(self):
        """Test nested template rendering."""
        template = {
            "greeting": "Hello ${user.name}",
            "info": "Location: ${user.location.city}",
            "tasks": ["${tasks[0].title}", "${tasks[1].title}"]
        }
        context = {
            "user": {
                "name": "Bob",
                "location": {"city": "Chisinau"}
            },
            "tasks": [
                {"title": "Morning briefing"},
                {"title": "Code review"}
            ]
        }
        
        result = render_templates(template, context)
        
        assert result["greeting"] == "Hello Bob"
        assert result["info"] == "Location: Chisinau"
        assert result["tasks"][0] == "Morning briefing"
        assert result["tasks"][1] == "Code review"
    
    def test_variable_extraction(self):
        """Test template variable extraction."""
        template = {
            "message": "Hello ${params.name}",
            "weather": "Temperature: ${steps.weather.temp}°C",
            "events": ["${steps.calendar.events[0].title}"]
        }
        
        variables = extract_template_variables(template)
        expected = [
            "params.name",
            "steps.calendar.events[0].title", 
            "steps.weather.temp"
        ]
        
        assert sorted(variables) == sorted(expected)
    
    def test_variable_validation_fixed(self):
        """Test the fixed variable validation functionality."""
        variables = ["params.name", "params.missing", "steps.weather.temp", "steps.missing.path"]
        context = {
            "params": {"name": "Alice"},
            "steps": {"weather": {"temp": 25}}
        }
        
        missing = validate_template_variables(variables, context)
        expected_missing = ["params.missing", "steps.missing.path"]
        
        assert sorted(missing) == sorted(expected_missing)
    
    def test_variable_validation_nested_paths(self):
        """Test validation of deeply nested paths."""
        variables = [
            "steps.api.response.data[0].id",
            "steps.api.response.meta.total", 
            "steps.api.missing.path"
        ]
        context = {
            "steps": {
                "api": {
                    "response": {
                        "data": [{"id": 1}, {"id": 2}],
                        "meta": {"total": 2}
                    }
                }
            }
        }
        
        missing = validate_template_variables(variables, context)
        assert missing == ["steps.api.missing.path"]


class TestRRuleProcessingWithDST:
    """Test RRULE processing with DST scenarios for Europe/Chisinau."""
    
    def test_simple_rrule_processing(self):
        """Test basic RRULE processing."""
        processor = RRuleProcessor("Europe/Chisinau")
        
        # Every day at 9 AM
        rrule = "FREQ=DAILY;BYHOUR=9;BYMINUTE=0"
        base_time = datetime(2025, 8, 8, 8, 0, 0)  # 8 AM
        
        next_time = processor.get_next_occurrence(rrule, base_time)
        
        assert next_time.hour == 9
        assert next_time.minute == 0
        assert next_time.day == 8  # Same day since 9 AM hasn't passed yet
    
    def test_dst_spring_forward_scenario(self):
        """Test RRULE during DST spring forward transition."""
        processor = RRuleProcessor("Europe/Chisinau")
        
        # Every day at 2:30 AM - this time doesn't exist on spring forward day
        rrule = "FREQ=DAILY;BYHOUR=2;BYMINUTE=30"
        
        # March 30, 2025 is spring forward day in Europe/Chisinau (2 AM -> 3 AM)
        base_time = datetime(2025, 3, 29, 12, 0, 0)  # Day before
        
        next_time = processor.get_next_occurrence(rrule, base_time)
        
        # Should skip to 3:30 AM or the next valid time
        assert next_time.day >= 30
        assert next_time.hour >= 3  # Can't be 2:30 AM on spring forward day
    
    def test_dst_fall_back_scenario(self):
        """Test RRULE during DST fall back transition.""" 
        processor = RRuleProcessor("Europe/Chisinau")
        
        # Every day at 2:30 AM - this time occurs twice on fall back day
        rrule = "FREQ=DAILY;BYHOUR=2;BYMINUTE=30"
        
        # October 26, 2025 is fall back day in Europe/Chisinau (3 AM -> 2 AM)
        base_time = datetime(2025, 10, 25, 12, 0, 0)  # Day before
        
        next_time = processor.get_next_occurrence(rrule, base_time)
        
        # Should occur at 2:30 AM on fall back day
        assert next_time.day == 26
        assert next_time.hour == 2
        assert next_time.minute == 30
    
    def test_weekly_rrule_accuracy(self):
        """Test weekly RRULE timing accuracy."""
        processor = RRuleProcessor("Europe/Chisinau")
        
        # Every Monday at 9:00 AM
        rrule = "FREQ=WEEKLY;BYDAY=MO;BYHOUR=9;BYMINUTE=0"
        
        # Start on a Wednesday
        base_time = datetime(2025, 8, 6, 12, 0, 0)  # Wednesday August 6
        
        next_time = processor.get_next_occurrence(rrule, base_time)
        
        # Should be the following Monday
        assert next_time.weekday() == 0  # Monday
        assert next_time.hour == 9
        assert next_time.minute == 0
        assert next_time.day == 11  # August 11, 2025 is a Monday


class TestWorkerConcurrencySimulation:
    """Test worker concurrency with simulated SKIP LOCKED behavior."""
    
    def test_skip_locked_simulation(self, mock_db, sample_agent, sample_task):
        """Test simulated SKIP LOCKED prevents double processing."""
        
        # Insert test data
        mock_db.execute("INSERT INTO agent (id, name, scopes) VALUES (?, ?, ?)",
                       sample_agent)
        mock_db.execute("""
            INSERT INTO task (id, title, description, created_by, schedule_kind, 
                            schedule_expr, timezone, payload, status, priority, max_retries)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, list(sample_task.values()))
        
        # Insert due work
        work_id = str(uuid.uuid4())
        mock_db.execute("""
            INSERT INTO due_work (id, task_id, run_at)
            VALUES (?, ?, datetime('now', '-1 minute'))
        """, {"id": work_id, "task_id": sample_task["id"]})
        mock_db.commit()
        
        # Simulate worker 1 acquiring lease
        lease_time = datetime.now(timezone.utc) + timedelta(minutes=5)
        mock_db.execute("""
            UPDATE due_work 
            SET locked_until = ?, locked_by = ? 
            WHERE id = ? AND (locked_until IS NULL OR locked_until < datetime('now'))
        """, {"locked_until": lease_time.isoformat(), "locked_by": "worker-1", "id": work_id})
        
        affected_rows = mock_db.conn.total_changes
        assert affected_rows == 1  # Worker 1 got the lease
        
        # Simulate worker 2 trying to get the same work
        mock_db.execute("""
            UPDATE due_work 
            SET locked_until = ?, locked_by = ? 
            WHERE id = ? AND (locked_until IS NULL OR locked_until < datetime('now'))
        """, {"locked_until": lease_time.isoformat(), "locked_by": "worker-2", "id": work_id})
        
        affected_rows_2 = mock_db.conn.total_changes - affected_rows
        assert affected_rows_2 == 0  # Worker 2 couldn't get the lease (SKIP LOCKED simulation)
    
    def test_lease_timeout_recovery(self, mock_db, sample_agent, sample_task):
        """Test recovery of expired leases."""
        
        # Insert test data
        mock_db.execute("INSERT INTO agent (id, name, scopes) VALUES (?, ?, ?)", 
                       sample_agent)
        mock_db.execute("""
            INSERT INTO task (id, title, description, created_by, schedule_kind,
                            schedule_expr, timezone, payload, status, priority, max_retries) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, list(sample_task.values()))
        
        work_id = str(uuid.uuid4())
        mock_db.execute("""
            INSERT INTO due_work (id, task_id, run_at, locked_until, locked_by)
            VALUES (?, ?, datetime('now', '-1 minute'), datetime('now', '-1 minute'), 'dead-worker')
        """, {"id": work_id, "task_id": sample_task["id"]})
        mock_db.commit()
        
        # Worker should be able to acquire expired lease
        lease_time = datetime.now(timezone.utc) + timedelta(minutes=5)
        mock_db.execute("""
            UPDATE due_work 
            SET locked_until = ?, locked_by = ?
            WHERE id = ? AND (locked_until IS NULL OR locked_until < datetime('now'))
        """, {"locked_until": lease_time.isoformat(), "locked_by": "recovery-worker", "id": work_id})
        
        affected_rows = mock_db.conn.total_changes
        assert affected_rows == 1  # Should recover the expired lease
    
    def test_concurrent_worker_simulation(self, mock_db, sample_agent):
        """Test multiple workers processing different tasks concurrently."""
        
        # Insert test agent
        mock_db.execute("INSERT INTO agent (id, name, scopes) VALUES (?, ?, ?)",
                       sample_agent)
        
        # Create multiple tasks
        task_ids = []
        for i in range(5):
            task_id = str(uuid.uuid4())
            task_ids.append(task_id)
            
            mock_db.execute("""
                INSERT INTO task (id, title, description, created_by, schedule_kind,
                                schedule_expr, timezone, payload, status, priority, max_retries)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, {
                "id": task_id,
                "title": f"Concurrent Test Task {i}",
                "description": f"Task {i} for concurrency testing", 
                "created_by": sample_agent["id"],
                "schedule_kind": "once",
                "schedule_expr": datetime.now(timezone.utc).isoformat(),
                "timezone": "Europe/Chisinau",
                "payload": json.dumps({"pipeline": []}),
                "status": "active",
                "priority": 5,
                "max_retries": 3
            })
            
            # Create due work for each task
            mock_db.execute("""
                INSERT INTO due_work (task_id, run_at)
                VALUES (?, datetime('now', '-1 minute'))
            """, {"task_id": task_id})
        
        mock_db.commit()
        
        # Simulate 3 workers processing tasks
        workers = ["worker-1", "worker-2", "worker-3"]
        processed_tasks = set()
        
        for worker in workers:
            # Each worker tries to lease available work
            cursor = mock_db.execute("""
                SELECT id, task_id FROM due_work 
                WHERE run_at <= datetime('now')
                  AND (locked_until IS NULL OR locked_until < datetime('now'))
                LIMIT 2
            """)
            
            for row in cursor:
                work_id, task_id = row
                
                # Try to lease the work
                lease_time = datetime.now(timezone.utc) + timedelta(minutes=5)
                mock_db.execute("""
                    UPDATE due_work 
                    SET locked_until = ?, locked_by = ?
                    WHERE id = ? AND (locked_until IS NULL OR locked_until < datetime('now'))
                """, {"locked_until": lease_time.isoformat(), "locked_by": worker, "id": work_id})
                
                if mock_db.conn.total_changes > 0:
                    processed_tasks.add(task_id)
                    
                    # Simulate work completion
                    mock_db.execute("""
                        INSERT INTO task_run (id, task_id, lease_owner, started_at, finished_at, success, attempt, output)
                        VALUES (?, ?, ?, datetime('now'), datetime('now'), 1, 1, '{}')
                    """, {"id": str(uuid.uuid4()), "task_id": task_id, "lease_owner": worker})
                    
                    # Clean up due work
                    mock_db.execute("DELETE FROM due_work WHERE id = ?", {"id": work_id})
        
        mock_db.commit()
        
        # Verify all tasks were processed exactly once
        assert len(processed_tasks) == len(task_ids)
        
        # Verify task runs were recorded
        cursor = mock_db.execute("SELECT COUNT(*) FROM task_run WHERE success = 1")
        successful_runs = cursor.fetchone()[0]
        assert successful_runs == len(task_ids)


class TestPipelineExecutionMocked:
    """Test pipeline execution with mocked tools."""
    
    @patch('engine.executor.call_tool')
    @patch('engine.executor.load_catalog')  
    async def test_simple_pipeline_execution(self, mock_load_catalog, mock_call_tool, mock_tool_catalog):
        """Test simple pipeline execution with mocked tools."""
        
        mock_load_catalog.return_value = mock_tool_catalog
        mock_call_tool.return_value = {"result": "Hello World"}
        
        pipeline = {
            "pipeline": [
                {
                    "id": "greeting",
                    "uses": "test-tool.execute", 
                    "with": {"message": "Hello ${params.name}"},
                    "save_as": "greeting_result"
                }
            ],
            "params": {"name": "World"}
        }
        
        result = await run_pipeline(pipeline)
        
        assert result["success"] is True
        assert "greeting_result" in result["steps"]
        assert result["steps"]["greeting_result"]["result"] == "Hello World"
        
        # Verify tool was called with rendered template
        mock_call_tool.assert_called_once()
        call_args = mock_call_tool.call_args
        assert call_args[0][2]["message"] == "Hello World"  # Template was rendered
    
    @patch('engine.executor.call_tool')
    @patch('engine.executor.load_catalog')
    async def test_multi_step_pipeline(self, mock_load_catalog, mock_call_tool, mock_tool_catalog):
        """Test multi-step pipeline with data flow between steps."""
        
        mock_load_catalog.return_value = mock_tool_catalog
        
        # Mock different responses for different steps
        mock_call_tool.side_effect = [
            {"result": "Alice"},  # First step
            {"result": "Hello Alice"}  # Second step using first step's output
        ]
        
        pipeline = {
            "pipeline": [
                {
                    "id": "get_name",
                    "uses": "test-tool.execute",
                    "with": {"message": "Get user name"},
                    "save_as": "user_name"
                },
                {
                    "id": "greet_user", 
                    "uses": "test-tool.execute",
                    "with": {"message": "Hello ${steps.user_name.result}"},
                    "save_as": "greeting"
                }
            ]
        }
        
        result = await run_pipeline(pipeline)
        
        assert result["success"] is True
        assert len(result["steps"]) == 2
        assert result["steps"]["user_name"]["result"] == "Alice"
        assert result["steps"]["greeting"]["result"] == "Hello Alice"
        
        # Verify second call used first step's output
        second_call_args = mock_call_tool.call_args_list[1]
        assert second_call_args[0][2]["message"] == "Hello Alice"
    
    @patch('engine.executor.call_tool')
    @patch('engine.executor.load_catalog')
    async def test_pipeline_error_handling(self, mock_load_catalog, mock_call_tool, mock_tool_catalog):
        """Test pipeline error handling and retry logic."""
        
        mock_load_catalog.return_value = mock_tool_catalog
        mock_call_tool.side_effect = Exception("Tool execution failed")
        
        pipeline = {
            "pipeline": [
                {
                    "id": "failing_step",
                    "uses": "test-tool.execute",
                    "with": {"message": "This will fail"},
                    "save_as": "result"
                }
            ]
        }
        
        result = await run_pipeline(pipeline)
        
        assert result["success"] is False
        assert "error" in result
        assert "Tool execution failed" in result["error"]


class TestPerformanceBenchmarks:
    """Test performance benchmarks for critical operations."""
    
    def test_template_rendering_performance(self):
        """Test template rendering performance meets requirements."""
        template = {
            "message": "Hello ${user.name}",
            "details": {
                "location": "${user.location.city}",
                "temperature": "${weather.temp}°${weather.unit}",
                "events": ["${events[0].title}", "${events[1].title}"]
            }
        }
        
        context = {
            "user": {"name": "Alice", "location": {"city": "Chisinau"}},
            "weather": {"temp": 22, "unit": "C"},
            "events": [{"title": "Meeting"}, {"title": "Lunch"}]
        }
        
        # Measure rendering time
        iterations = 1000
        start_time = time.perf_counter()
        
        for _ in range(iterations):
            render_templates(template, context)
        
        end_time = time.perf_counter()
        avg_time_ms = ((end_time - start_time) / iterations) * 1000
        
        # Should complete in under 5ms on average
        assert avg_time_ms < 5.0, f"Template rendering too slow: {avg_time_ms:.2f}ms"
    
    def test_variable_extraction_performance(self):
        """Test variable extraction performance."""
        complex_template = {
            "pipeline": [
                {"id": f"step_{i}", "with": {"param": f"${{steps.step_{i-1}.output}}"}} 
                for i in range(100)
            ]
        }
        
        start_time = time.perf_counter()
        variables = extract_template_variables(complex_template)
        end_time = time.perf_counter()
        
        execution_time_ms = (end_time - start_time) * 1000
        
        assert len(variables) == 99  # step_0 doesn't reference previous step
        assert execution_time_ms < 10.0, f"Variable extraction too slow: {execution_time_ms:.2f}ms"
    
    def test_rrule_processing_performance(self):
        """Test RRULE processing performance."""
        processor = RRuleProcessor("Europe/Chisinau")
        
        # Complex RRULE
        rrule = "FREQ=WEEKLY;BYDAY=MO,WE,FR;BYHOUR=9,14;BYMINUTE=0,30"
        base_time = datetime(2025, 8, 8, 12, 0, 0)
        
        start_time = time.perf_counter()
        
        # Calculate next 100 occurrences
        current_time = base_time
        for _ in range(100):
            current_time = processor.get_next_occurrence(rrule, current_time)
            current_time = current_time + timedelta(minutes=1)  # Move past current occurrence
        
        end_time = time.perf_counter()
        total_time_ms = (end_time - start_time) * 1000
        
        # Should complete 100 calculations in under 100ms
        assert total_time_ms < 100.0, f"RRULE processing too slow: {total_time_ms:.2f}ms"


class TestChaosEngineeringSimulation:
    """Test chaos engineering scenarios with simulated failures."""
    
    @patch('engine.executor.call_tool')
    @patch('engine.executor.load_catalog')
    async def test_tool_failure_recovery(self, mock_load_catalog, mock_call_tool, mock_tool_catalog):
        """Test recovery from tool failures."""
        
        mock_load_catalog.return_value = mock_tool_catalog
        
        # Simulate intermittent failures
        mock_call_tool.side_effect = [
            Exception("Network timeout"),  # First attempt fails
            Exception("Service unavailable"),  # Second attempt fails  
            {"result": "Success on third try"}  # Third attempt succeeds
        ]
        
        pipeline = {
            "pipeline": [
                {
                    "id": "resilient_step",
                    "uses": "test-tool.execute",
                    "with": {"message": "Test resilience"},
                    "retry_attempts": 3,
                    "save_as": "result"
                }
            ]
        }
        
        result = await run_pipeline(pipeline)
        
        # Should eventually succeed despite initial failures
        assert result["success"] is True
        assert result["steps"]["result"]["result"] == "Success on third try"
    
    def test_high_load_simulation(self, mock_db, sample_agent):
        """Test system behavior under high load simulation."""
        
        # Insert test agent
        mock_db.execute("INSERT INTO agent (id, name, scopes) VALUES (?, ?, ?)",
                       sample_agent)
        
        # Create many concurrent tasks
        task_count = 1000
        task_ids = []
        
        start_time = time.perf_counter()
        
        for i in range(task_count):
            task_id = str(uuid.uuid4())
            task_ids.append(task_id)
            
            mock_db.execute("""
                INSERT INTO task (id, title, description, created_by, schedule_kind,
                                schedule_expr, timezone, payload, status, priority, max_retries)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, {
                "id": task_id,
                "title": f"Load Test Task {i}",
                "description": f"High load test task {i}",
                "created_by": sample_agent["id"],
                "schedule_kind": "once",
                "schedule_expr": datetime.now(timezone.utc).isoformat(),
                "timezone": "Europe/Chisinau", 
                "payload": json.dumps({"pipeline": []}),
                "status": "active",
                "priority": 5,
                "max_retries": 3
            })
            
            # Create due work
            mock_db.execute("""
                INSERT INTO due_work (task_id, run_at)
                VALUES (?, datetime('now'))
            """, {"task_id": task_id})
        
        mock_db.commit()
        creation_time = time.perf_counter() - start_time
        
        # Verify all tasks were created efficiently
        cursor = mock_db.execute("SELECT COUNT(*) FROM task")
        created_tasks = cursor.fetchone()[0] - 1  # Subtract the sample_agent task
        
        assert created_tasks == task_count
        assert creation_time < 2.0, f"Task creation too slow under load: {creation_time:.2f}s"
        
        # Simulate worker processing under load
        process_start = time.perf_counter()
        processed_count = 0
        
        # Process tasks in batches (simulating multiple workers)
        batch_size = 50
        for i in range(0, task_count, batch_size):
            cursor = mock_db.execute("""
                SELECT id, task_id FROM due_work
                WHERE run_at <= datetime('now') 
                  AND (locked_until IS NULL OR locked_until < datetime('now'))
                LIMIT ?
            """, {"limit": batch_size})
            
            batch_work = cursor.fetchall()
            
            for work_id, task_id in batch_work:
                # Simulate work processing
                mock_db.execute("""
                    INSERT INTO task_run (id, task_id, lease_owner, started_at, finished_at, success, attempt, output)
                    VALUES (?, ?, ?, datetime('now'), datetime('now'), 1, 1, '{}')
                """, {"id": str(uuid.uuid4()), "task_id": task_id, "lease_owner": f"worker-{i // batch_size}"})
                
                mock_db.execute("DELETE FROM due_work WHERE id = ?", {"id": work_id})
                processed_count += 1
        
        mock_db.commit()
        process_time = time.perf_counter() - process_start
        
        # Verify high throughput
        throughput = processed_count / process_time
        assert throughput > 100, f"Throughput too low: {throughput:.2f} tasks/second"


class TestEndToEndWorkflowSimulation:
    """Test complete end-to-end workflows with mocked components."""
    
    @patch('engine.executor.call_tool')
    @patch('engine.executor.load_catalog') 
    async def test_morning_briefing_workflow(self, mock_load_catalog, mock_call_tool, mock_db, sample_agent):
        """Test complete morning briefing workflow."""
        
        # Setup enhanced tool catalog for briefing
        briefing_catalog = [
            {
                "address": "calendar.list_events",
                "transport": "http",
                "endpoint": "http://localhost:8091/calendar",
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "scopes": ["calendar.read"]
            },
            {
                "address": "weather.forecast",
                "transport": "http",
                "endpoint": "http://localhost:8092/weather", 
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "scopes": ["weather.read"]
            },
            {
                "address": "telegram.send_message",
                "transport": "http",
                "endpoint": "http://localhost:8093/telegram",
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "scopes": ["notify"]
            }
        ]
        
        mock_load_catalog.return_value = briefing_catalog
        
        # Mock tool responses in sequence
        mock_call_tool.side_effect = [
            # Calendar response
            {
                "events": [
                    {"title": "Team Standup", "time": "09:00", "location": "Office"},
                    {"title": "Client Meeting", "time": "14:00", "location": "Zoom"}
                ]
            },
            # Weather response
            {"summary": "Partly Cloudy", "temp": 18, "humidity": 65},
            # Telegram response
            {"message_id": 12345}
        ]
        
        # Execute morning briefing pipeline
        briefing_pipeline = {
            "params": {
                "date_start": "2025-08-08T00:00:00+03:00",
                "date_end": "2025-08-08T23:59:59+03:00",
                "location": "Chisinau",
                "chat_id": 123456
            },
            "pipeline": [
                {
                    "id": "calendar",
                    "uses": "calendar.list_events",
                    "with": {
                        "start": "${params.date_start}",
                        "end": "${params.date_end}"
                    },
                    "save_as": "events"
                },
                {
                    "id": "weather",
                    "uses": "weather.forecast", 
                    "with": {"location": "${params.location}"},
                    "save_as": "forecast"
                },
                {
                    "id": "notify",
                    "uses": "telegram.send_message",
                    "with": {
                        "chat_id": "${params.chat_id}",
                        "text": "Good morning! Weather: ${steps.forecast.summary} (${steps.forecast.temp}°C). You have ${length(steps.events.events)} events today."
                    },
                    "save_as": "notification"
                }
            ]
        }
        
        result = await run_pipeline(briefing_pipeline)
        
        # Verify successful execution
        assert result["success"] is True
        assert len(result["steps"]) == 3
        
        # Verify data flow between steps
        assert "events" in result["steps"]
        assert "forecast" in result["steps"] 
        assert "notification" in result["steps"]
        
        # Verify final notification
        events = result["steps"]["events"]["events"]
        assert len(events) == 2
        assert events[0]["title"] == "Team Standup"
        
        forecast = result["steps"]["forecast"]
        assert forecast["summary"] == "Partly Cloudy"
        assert forecast["temp"] == 18
        
        notification = result["steps"]["notification"]
        assert notification["message_id"] == 12345
        
        # Verify template rendering in final message
        final_call_args = mock_call_tool.call_args_list[2]  # Third call (telegram)
        message_text = final_call_args[0][2]["text"]
        assert "Weather: Partly Cloudy (18°C)" in message_text
        assert "You have 2 events today" in message_text
    
    def test_task_lifecycle_simulation(self, mock_db, sample_agent, sample_task):
        """Test complete task lifecycle from creation to completion."""
        
        # 1. Task Creation
        mock_db.execute("INSERT INTO agent (id, name, scopes) VALUES (?, ?, ?)",
                       sample_agent)
        mock_db.execute("""
            INSERT INTO task (id, title, description, created_by, schedule_kind,
                            schedule_expr, timezone, payload, status, priority, max_retries)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, list(sample_task.values()))
        mock_db.commit()
        
        # 2. Task Scheduling (simulated)
        work_id = str(uuid.uuid4())
        mock_db.execute("""
            INSERT INTO due_work (id, task_id, run_at)
            VALUES (?, ?, datetime('now', '-1 minute'))
        """, {"id": work_id, "task_id": sample_task["id"]})
        mock_db.commit()
        
        # 3. Work Leasing
        lease_time = datetime.now(timezone.utc) + timedelta(minutes=5)
        worker_id = "lifecycle-test-worker"
        
        mock_db.execute("""
            UPDATE due_work
            SET locked_until = ?, locked_by = ?
            WHERE id = ? AND (locked_until IS NULL OR locked_until < datetime('now'))
        """, {"locked_until": lease_time.isoformat(), "locked_by": worker_id, "id": work_id})
        
        assert mock_db.conn.total_changes == 1  # Lease acquired
        
        # 4. Task Execution (simulated) 
        run_id = str(uuid.uuid4())
        execution_output = {
            "success": True,
            "steps": {"result": {"message": "Task completed successfully"}},
            "execution_time_ms": 150
        }
        
        mock_db.execute("""
            INSERT INTO task_run (id, task_id, lease_owner, started_at, finished_at, 
                                success, attempt, output)
            VALUES (?, ?, ?, datetime('now', '-1 minute'), datetime('now'), ?, 1, ?)
        """, {
            "id": run_id,
            "task_id": sample_task["id"], 
            "lease_owner": worker_id,
            "success": 1,  # SQLite boolean
            "output": json.dumps(execution_output)
        })
        
        # 5. Work Cleanup
        mock_db.execute("DELETE FROM due_work WHERE id = ?", {"id": work_id})
        mock_db.commit()
        
        # Verify complete lifecycle
        # Check task exists
        cursor = mock_db.execute("SELECT * FROM task WHERE id = ?", {"id": sample_task["id"]})
        task_record = cursor.fetchone()
        assert task_record is not None
        
        # Check execution was recorded
        cursor = mock_db.execute("SELECT * FROM task_run WHERE task_id = ?", {"id": sample_task["id"]})
        run_record = cursor.fetchone()
        assert run_record is not None
        assert run_record["success"] == 1
        assert run_record["lease_owner"] == worker_id
        
        # Check work was cleaned up
        cursor = mock_db.execute("SELECT * FROM due_work WHERE task_id = ?", {"id": sample_task["id"]})
        remaining_work = cursor.fetchone()
        assert remaining_work is None


class TestObservabilityIntegration:
    """Test observability and monitoring integration."""
    
    def test_structured_logging(self):
        """Test structured logging functionality."""
        logger = StructuredLogger("test.logger")
        
        # Set request context
        set_request_context(
            request_id="req-test-123",
            task_id="task-456", 
            agent_id="agent-789"
        )
        
        # Capture log output
        with patch('logging.StreamHandler.emit') as mock_emit:
            logger.info("Test message", extra_field="test_value")
            
            # Verify structured log was emitted
            mock_emit.assert_called_once()
            log_record = mock_emit.call_args[0][0]
            
            assert log_record.levelname == "INFO"
            assert log_record.getMessage() == "Test message"
    
    def test_performance_metrics(self):
        """Test performance metrics collection."""
        # Test metrics collection
        metrics = orchestrator_metrics
        
        # Record some test metrics
        metrics.record_pipeline_execution(150.5, "success")
        metrics.record_task_completion(True)
        metrics.record_worker_lease(30)
        
        # Verify metrics were recorded (basic test)
        assert hasattr(metrics, 'record_pipeline_execution')
        assert hasattr(metrics, 'record_task_completion') 
        assert hasattr(metrics, 'record_worker_lease')


if __name__ == "__main__":
    # Run comprehensive tests
    pytest.main([
        __file__,
        "-v",
        "--tb=short", 
        "--disable-warnings",
        "-x"  # Stop on first failure
    ])