# Load Tests - Personal Agent Orchestrator

## Purpose and Testing Scope

Load tests validate system performance, scalability, and reliability under realistic production workloads. These tests ensure the Personal Agent Orchestrator meets performance SLAs and handles high-volume scenarios gracefully without degradation.

**Core Testing Principles:**
- **Production Realism**: Tests simulate actual agent usage patterns and loads
- **Performance SLAs**: Validate specific latency and throughput requirements
- **Scalability Validation**: Verify system scales linearly with added resources
- **Reliability Under Load**: Ensure no data loss or corruption under stress

## Performance Benchmarks and Requirements

### System Performance SLAs

#### API Response Times
- **Task Creation**: < 200ms (p95), < 100ms (p50)
- **Task Retrieval**: < 100ms (p95), < 50ms (p50)
- **Task Updates**: < 150ms (p95), < 75ms (p50)
- **Run History**: < 300ms (p95), < 150ms (p50)

#### Execution Performance
- **Pipeline Startup**: < 5 seconds from scheduled time
- **Step Execution**: < 30 seconds per step (tool-dependent)
- **Work Leasing**: < 50ms (p95), < 25ms (p50)
- **Schedule Processing**: < 1000 schedules per second

#### System Throughput
- **Task Execution**: 1000 concurrent executions
- **API Throughput**: 500 requests per second sustained
- **Schedule Evaluation**: 10,000 schedules per minute
- **Database Operations**: 5000 transactions per second

#### Resource Utilization
- **Memory Usage**: < 2GB per worker process under normal load
- **CPU Usage**: < 80% average under sustained load
- **Database Connections**: < 20 active connections per worker
- **Storage Growth**: < 1GB per million completed tasks

## Test Organization and Patterns

### Directory Structure
```
tests/load/
├── CLAUDE.md                   # This file
├── conftest.py                 # Load test configuration and utilities
├── test_api_load/              # API endpoint load testing
│   ├── test_task_operations.py # CRUD operations under load
│   ├── test_concurrent_reads.py # High-volume read scenarios
│   └── test_mixed_workload.py  # Realistic mixed API usage
├── test_execution_load/        # Pipeline execution load testing
│   ├── test_worker_scaling.py  # Worker count vs throughput
│   ├── test_pipeline_volume.py # High-volume pipeline execution
│   └── test_concurrent_tasks.py # Many simultaneous task executions
├── test_scheduling_load/       # Schedule processing performance
│   ├── test_schedule_volume.py # Large numbers of scheduled tasks
│   ├── test_cron_evaluation.py # CRON expression processing speed
│   └── test_rrule_complexity.py # Complex RRULE pattern performance
├── test_database_load/         # Database performance under load
│   ├── test_skip_locked_scale.py # SKIP LOCKED contention testing
│   ├── test_query_performance.py # Query optimization validation
│   └── test_transaction_load.py # High-volume transaction processing
├── test_scenarios/             # Realistic load scenarios
│   ├── test_agent_simulation.py # Simulated agent behavior
│   ├── test_peak_load.py       # Peak usage simulation
│   └── test_sustained_load.py  # Long-duration load testing
└── utils/                      # Load testing utilities
    ├── generators.py           # Load pattern and data generators
    ├── metrics.py              # Performance measurement utilities
    └── reporting.py            # Load test results and analysis
```

### Testing Patterns

#### 1. Throughput Testing Pattern
```python
# test_api_load/test_task_operations.py
import pytest
import asyncio
import time
from httpx import AsyncClient
from tests.load.utils.generators import TaskGenerator
from tests.load.utils.metrics import PerformanceCollector

class TestAPIThroughput:
    @pytest.mark.load
    @pytest.mark.asyncio
    async def test_task_creation_throughput(self, load_test_client):
        """Test task creation throughput under high load."""
        # Test parameters
        target_rps = 500  # requests per second
        duration_seconds = 60
        total_requests = target_rps * duration_seconds
        
        # Performance tracking
        metrics = PerformanceCollector()
        task_generator = TaskGenerator()
        
        async def create_task(session_id: int, task_num: int):
            """Create a single task and measure performance."""
            start_time = time.time()
            
            task_data = task_generator.generate_task(
                title=f"Load Test Task {session_id}-{task_num}"
            )
            
            async with AsyncClient(base_url="http://localhost:8080") as client:
                try:
                    response = await client.post("/v1/tasks", json=task_data)
                    response_time = (time.time() - start_time) * 1000  # ms
                    
                    metrics.record_response(
                        operation="create_task",
                        response_time_ms=response_time,
                        status_code=response.status_code,
                        success=response.status_code == 201
                    )
                    
                    if response.status_code == 201:
                        return response.json()["id"]
                    else:
                        return None
                        
                except Exception as e:
                    metrics.record_error("create_task", str(e))
                    return None
        
        # Execute load test
        start_time = time.time()
        semaphore = asyncio.Semaphore(100)  # Limit concurrent connections
        
        async def bounded_create_task(session_id: int, task_num: int):
            async with semaphore:
                return await create_task(session_id, task_num)
        
        # Create tasks in batches to maintain target RPS
        tasks = []
        for second in range(duration_seconds):
            batch_tasks = [
                bounded_create_task(second, i) 
                for i in range(target_rps)
            ]
            tasks.extend(batch_tasks)
            
            # Wait until the second is up to maintain RPS
            elapsed = time.time() - start_time
            sleep_time = (second + 1) - elapsed
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
        
        # Execute all tasks
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Analyze results
        successful_tasks = [r for r in results if isinstance(r, str)]
        
        # Performance assertions
        assert len(successful_tasks) >= total_requests * 0.95  # 95% success rate
        assert metrics.get_p95_response_time("create_task") < 200  # SLA requirement
        assert metrics.get_p50_response_time("create_task") < 100  # SLA requirement
        assert metrics.get_error_rate("create_task") < 0.05  # < 5% error rate
        
        # Log performance summary
        metrics.print_summary("Task Creation Throughput Test")
```

#### 2. Concurrency Testing Pattern
```python
# test_execution_load/test_concurrent_tasks.py
import pytest
import asyncio
from datetime import datetime, timedelta
from tests.load.utils.generators import PipelineGenerator
from tests.load.utils.metrics import ExecutionMetrics

class TestConcurrentExecution:
    @pytest.mark.load
    @pytest.mark.asyncio
    async def test_1000_concurrent_task_executions(self, load_test_db):
        """Test system handles 1000 concurrent task executions."""
        concurrent_tasks = 1000
        pipeline_gen = PipelineGenerator()
        metrics = ExecutionMetrics()
        
        async def create_and_schedule_task(task_id: int):
            """Create task and schedule for immediate execution."""
            pipeline = pipeline_gen.generate_simple_pipeline(steps=3)
            
            task_data = {
                "id": f"load-test-{task_id}",
                "title": f"Concurrent Load Test {task_id}",
                "description": "Load test concurrent execution",
                "schedule_kind": "once",
                "schedule_expr": (datetime.now() + timedelta(seconds=1)).isoformat(),
                "payload": {"pipeline": pipeline}
            }
            
            # Insert task directly into database for faster setup
            await load_test_db.execute("""
                INSERT INTO task (id, title, description, schedule_kind, 
                                schedule_expr, timezone, status, created_at, next_run, payload)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """, task_data["id"], task_data["title"], task_data["description"],
                task_data["schedule_kind"], task_data["schedule_expr"], "UTC",
                "active", datetime.now(), datetime.now() + timedelta(seconds=1),
                task_data["payload"])
            
            return task_data["id"]
        
        # Create all tasks
        task_creation_start = time.time()
        task_ids = await asyncio.gather(*[
            create_and_schedule_task(i) for i in range(concurrent_tasks)
        ])
        task_creation_time = time.time() - task_creation_start
        
        assert len(task_ids) == concurrent_tasks
        print(f"Created {concurrent_tasks} tasks in {task_creation_time:.2f}s")
        
        # Wait for all executions to complete
        max_wait_time = 300  # 5 minutes
        execution_start = time.time()
        
        completed_tasks = set()
        while len(completed_tasks) < concurrent_tasks:
            if time.time() - execution_start > max_wait_time:
                break
                
            # Check completion status
            completed_runs = await load_test_db.fetch("""
                SELECT task_id, status, started_at, finished_at, 
                       EXTRACT(EPOCH FROM (finished_at - started_at)) as duration_seconds
                FROM task_run 
                WHERE task_id = ANY($1) AND status IN ('success', 'failed')
            """, task_ids)
            
            completed_tasks = {run["task_id"] for run in completed_runs}
            await asyncio.sleep(1)  # Check every second
        
        execution_time = time.time() - execution_start
        
        # Analyze execution performance
        success_count = sum(1 for run in completed_runs if run["status"] == "success")
        failed_count = len(completed_runs) - success_count
        
        avg_duration = sum(run["duration_seconds"] for run in completed_runs) / len(completed_runs)
        max_duration = max(run["duration_seconds"] for run in completed_runs)
        
        # Performance assertions
        assert success_count >= concurrent_tasks * 0.95  # 95% success rate
        assert failed_count < concurrent_tasks * 0.05    # < 5% failure rate
        assert avg_duration < 30                         # Average execution < 30s
        assert max_duration < 60                         # No execution > 60s
        assert execution_time < 120                      # All complete within 2 minutes
        
        print(f"Concurrent Execution Results:")
        print(f"  Total tasks: {concurrent_tasks}")
        print(f"  Successful: {success_count} ({success_count/concurrent_tasks*100:.1f}%)")
        print(f"  Failed: {failed_count} ({failed_count/concurrent_tasks*100:.1f}%)")
        print(f"  Average duration: {avg_duration:.2f}s")
        print(f"  Max duration: {max_duration:.2f}s")
        print(f"  Total execution time: {execution_time:.2f}s")
```

#### 3. Sustained Load Testing Pattern
```python
# test_scenarios/test_sustained_load.py
import pytest
import asyncio
import time
from datetime import datetime, timedelta
from tests.load.utils.generators import AgentBehaviorSimulator
from tests.load.utils.metrics import SystemMetrics

class TestSustainedLoad:
    @pytest.mark.load
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_24_hour_sustained_load(self, load_test_environment):
        """Test system stability under 24-hour sustained load."""
        # Load test configuration
        duration_hours = 24
        agents_count = 100
        tasks_per_agent_per_hour = 10
        
        system_metrics = SystemMetrics()
        behavior_simulator = AgentBehaviorSimulator()
        
        async def simulate_agent(agent_id: int):
            """Simulate single agent behavior over test duration."""
            agent_metrics = {
                "tasks_created": 0,
                "tasks_completed": 0,
                "errors": 0,
                "avg_response_time": 0
            }
            
            start_time = time.time()
            
            while time.time() - start_time < duration_hours * 3600:
                try:
                    # Agent creates tasks periodically
                    await behavior_simulator.create_periodic_tasks(
                        agent_id, count=tasks_per_agent_per_hour
                    )
                    
                    # Agent checks task status
                    await behavior_simulator.check_task_status(agent_id)
                    
                    # Agent updates some tasks
                    if agent_metrics["tasks_created"] > 5:
                        await behavior_simulator.update_random_tasks(agent_id)
                    
                    agent_metrics["tasks_created"] += tasks_per_agent_per_hour
                    
                    # Wait until next hour
                    await asyncio.sleep(3600)  # 1 hour
                    
                except Exception as e:
                    agent_metrics["errors"] += 1
                    print(f"Agent {agent_id} error: {e}")
            
            return agent_metrics
        
        # Start system monitoring
        monitoring_task = asyncio.create_task(
            system_metrics.monitor_system_continuously(duration_hours * 3600)
        )
        
        # Run agent simulations
        agent_tasks = [
            simulate_agent(agent_id) for agent_id in range(agents_count)
        ]
        
        # Execute sustained load test
        print(f"Starting {duration_hours}h sustained load test with {agents_count} agents...")
        start_time = time.time()
        
        agent_results = await asyncio.gather(*agent_tasks, return_exceptions=True)
        system_stats = await monitoring_task
        
        execution_time = time.time() - start_time
        
        # Analyze sustained load results
        successful_agents = [r for r in agent_results if isinstance(r, dict)]
        total_tasks_created = sum(a["tasks_created"] for a in successful_agents)
        total_errors = sum(a["errors"] for a in successful_agents)
        
        # Performance assertions for sustained load
        assert len(successful_agents) >= agents_count * 0.95  # 95% agent success
        assert total_errors < total_tasks_created * 0.01     # < 1% error rate
        assert system_stats["max_memory_usage"] < 8 * 1024**3  # < 8GB max memory
        assert system_stats["avg_cpu_usage"] < 0.8            # < 80% average CPU
        assert system_stats["max_db_connections"] < 100       # < 100 DB connections
        
        # System stability assertions
        assert system_stats["system_restarts"] == 0           # No system restarts
        assert system_stats["db_connection_errors"] == 0      # No DB connection issues
        assert system_stats["memory_leaks_detected"] == 0     # No memory leaks
        
        print(f"Sustained Load Test Results ({execution_time/3600:.1f}h):")
        print(f"  Successful agents: {len(successful_agents)}/{agents_count}")
        print(f"  Total tasks created: {total_tasks_created:,}")
        print(f"  Total errors: {total_errors}")
        print(f"  Error rate: {total_errors/total_tasks_created*100:.3f}%")
        print(f"  Peak memory usage: {system_stats['max_memory_usage']/(1024**3):.2f}GB")
        print(f"  Average CPU usage: {system_stats['avg_cpu_usage']*100:.1f}%")
```

#### 4. Database Load Testing Pattern
```python
# test_database_load/test_skip_locked_scale.py
import pytest
import asyncio
import time
from tests.load.utils.generators import WorkItemGenerator

class TestDatabaseLoad:
    @pytest.mark.load
    @pytest.mark.asyncio
    async def test_skip_locked_contention_scaling(self, load_test_db):
        """Test SKIP LOCKED performance with increasing worker contention."""
        work_generator = WorkItemGenerator()
        
        async def worker_simulation(worker_id: int, work_items_count: int):
            """Simulate worker leasing and processing work items."""
            processed_count = 0
            response_times = []
            
            for _ in range(work_items_count):
                start_time = time.time()
                
                # Lease work using SKIP LOCKED
                work_item = await load_test_db.fetchrow("""
                    SELECT id, task_id, payload, created_at
                    FROM due_work 
                    WHERE status = 'pending'
                      AND run_at <= NOW()
                      AND (locked_until IS NULL OR locked_until < NOW())
                    ORDER BY priority DESC, run_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                """)
                
                if work_item:
                    # Mark as running
                    await load_test_db.execute("""
                        UPDATE due_work 
                        SET status = 'running', 
                            locked_until = NOW() + INTERVAL '5 minutes',
                            started_at = NOW()
                        WHERE id = $1
                    """, work_item["id"])
                    
                    # Simulate work processing
                    await asyncio.sleep(0.1)  # 100ms processing time
                    
                    # Mark as completed
                    await load_test_db.execute("""
                        UPDATE due_work 
                        SET status = 'completed', finished_at = NOW()
                        WHERE id = $1
                    """, work_item["id"])
                    
                    processed_count += 1
                
                response_time = (time.time() - start_time) * 1000  # ms
                response_times.append(response_time)
            
            return {
                "worker_id": worker_id,
                "processed_count": processed_count,
                "avg_response_time": sum(response_times) / len(response_times),
                "max_response_time": max(response_times),
                "response_times": response_times
            }
        
        # Test with increasing worker counts
        worker_counts = [1, 5, 10, 20, 50, 100]
        work_items_per_test = 1000
        
        for worker_count in worker_counts:
            print(f"\nTesting SKIP LOCKED with {worker_count} workers...")
            
            # Create work items for this test
            work_ids = []
            for i in range(work_items_per_test):
                work_id = await work_generator.create_work_item(
                    load_test_db, f"load-test-work-{worker_count}-{i}"
                )
                work_ids.append(work_id)
            
            # Start workers
            start_time = time.time()
            worker_results = await asyncio.gather(*[
                worker_simulation(worker_id, work_items_per_test // worker_count)
                for worker_id in range(worker_count)
            ])
            execution_time = time.time() - start_time
            
            # Analyze results
            total_processed = sum(r["processed_count"] for r in worker_results)
            avg_response_time = sum(r["avg_response_time"] for r in worker_results) / len(worker_results)
            max_response_time = max(r["max_response_time"] for r in worker_results)
            
            # Performance assertions
            assert total_processed == work_items_per_test  # All work processed
            assert avg_response_time < 50                  # Average < 50ms
            assert max_response_time < 200                 # Max < 200ms
            assert execution_time < 60                     # Complete within 1 minute
            
            print(f"  Workers: {worker_count}")
            print(f"  Total processed: {total_processed}")
            print(f"  Average response time: {avg_response_time:.2f}ms") 
            print(f"  Max response time: {max_response_time:.2f}ms")
            print(f"  Execution time: {execution_time:.2f}s")
            print(f"  Throughput: {total_processed/execution_time:.1f} items/sec")
            
            # Cleanup
            await load_test_db.execute("DELETE FROM due_work WHERE id = ANY($1)", work_ids)
```

## Key Test Files and Coverage

### API Load Tests (`test_api_load/`)

#### test_task_operations.py - CRUD Performance
**Coverage:**
- Task creation throughput (500 RPS sustained)
- Task retrieval performance with large datasets
- Bulk operations and batch processing
- Concurrent read/write scenarios

#### test_concurrent_reads.py - Read Scalability
**Coverage:**
- Multiple agents reading task lists simultaneously
- Database query optimization under read load
- Cache effectiveness and hit rates
- Read replica performance (if implemented)

### Execution Load Tests (`test_execution_load/`)

#### test_worker_scaling.py - Worker Performance
**Coverage:**
- Worker count vs throughput scaling
- Queue depth and processing latency
- Resource utilization per worker
- Optimal worker count determination

#### test_pipeline_volume.py - Pipeline Throughput
**Coverage:**
- High-volume pipeline execution
- Complex multi-step pipeline performance
- Template rendering performance at scale
- Tool call latency and timeout handling

### Scheduling Load Tests (`test_scheduling_load/`)

#### test_schedule_volume.py - Schedule Processing
**Coverage:**
- Large numbers of concurrent schedules (10,000+)
- Schedule evaluation performance
- Next run calculation optimization
- Schedule conflict detection at scale

## Testing Infrastructure and Utilities

### Load Test Configuration (`conftest.py`)
```python
import pytest
import asyncio
import asyncpg
from datetime import datetime
import psutil
import docker

@pytest.fixture(scope="session")
def load_test_environment():
    """Set up complete load test environment."""
    # Start production-like containers
    client = docker.from_env()
    
    containers = {
        "postgres": client.containers.run(
            "postgres:16",
            environment={
                "POSTGRES_DB": "orchestrator_load",
                "POSTGRES_USER": "orchestrator", 
                "POSTGRES_PASSWORD": "test_password"
            },
            ports={"5432/tcp": 5433},
            detach=True
        ),
        "redis": client.containers.run(
            "redis:7",
            ports={"6379/tcp": 6380},
            detach=True
        )
    }
    
    # Wait for services to be ready
    time.sleep(10)
    
    # Apply production schema
    conn = asyncpg.connect("postgresql://orchestrator:test_password@localhost:5433/orchestrator_load")
    with open("migrations/version_0001.sql") as f:
        conn.execute(f.read())
    conn.close()
    
    yield {
        "postgres_url": "postgresql://orchestrator:test_password@localhost:5433/orchestrator_load",
        "redis_url": "redis://localhost:6380/0"
    }
    
    # Cleanup
    for container in containers.values():
        container.stop()
        container.remove()

@pytest.fixture
async def load_test_db(load_test_environment):
    """Database connection for load testing."""
    conn = await asyncpg.connect(load_test_environment["postgres_url"])
    yield conn
    await conn.close()
```

### Load Generators (`utils/generators.py`)
```python
import random
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any

class TaskGenerator:
    """Generate realistic task data for load testing."""
    
    def __init__(self):
        self.task_titles = [
            "Daily Status Report", "Weather Update", "Email Digest",
            "Calendar Sync", "Backup Notification", "System Health Check",
            "Data Processing", "API Monitoring", "User Analytics",
            "Content Moderation", "Log Analysis", "Performance Check"
        ]
        
        self.schedule_patterns = [
            ("cron", "0 9 * * 1-5"),     # Weekdays at 9 AM
            ("cron", "0 */6 * * *"),     # Every 6 hours
            ("cron", "0 0 * * 0"),       # Weekly on Sunday
            ("rrule", "FREQ=DAILY;BYHOUR=8,12,18"),  # Three times daily
            ("once", None),              # One-time execution
        ]
    
    def generate_task(self, title: str = None) -> Dict[str, Any]:
        """Generate a realistic task configuration."""
        if not title:
            title = f"{random.choice(self.task_titles)} {uuid.uuid4().hex[:8]}"
        
        schedule_kind, schedule_expr = random.choice(self.schedule_patterns)
        
        if schedule_kind == "once":
            schedule_expr = (datetime.now() + timedelta(
                seconds=random.randint(1, 300)
            )).isoformat()
        
        pipeline_complexity = random.choice([
            1,  # Simple single step
            3,  # Medium complexity
            5,  # Complex multi-step
        ])
        
        return {
            "title": title,
            "description": f"Load test task: {title}",
            "schedule_kind": schedule_kind,
            "schedule_expr": schedule_expr,
            "timezone": random.choice(["UTC", "America/New_York", "Europe/London"]),
            "payload": {
                "pipeline": self._generate_pipeline(pipeline_complexity)
            }
        }
    
    def _generate_pipeline(self, step_count: int) -> List[Dict[str, Any]]:
        """Generate realistic pipeline steps."""
        tools = [
            "http-client.get", "json-processor.transform", "llm.summarize",
            "email.send", "slack.post", "database.query", "file.read"
        ]
        
        pipeline = []
        for i in range(step_count):
            step = {
                "id": f"step_{i+1}",
                "uses": random.choice(tools),
                "with": self._generate_step_args(i),
                "save_as": f"result_{i+1}"
            }
            
            if i > 0 and random.random() < 0.3:  # 30% chance of using previous step
                step["with"]["input"] = f"${{steps.step_{i}.output}}"
            
            pipeline.append(step)
        
        return pipeline
    
    def _generate_step_args(self, step_index: int) -> Dict[str, Any]:
        """Generate realistic step arguments."""
        return {
            "param1": f"value_{step_index}",
            "param2": random.randint(1, 100),
            "param3": random.choice([True, False])
        }

class AgentBehaviorSimulator:
    """Simulate realistic agent behavior patterns."""
    
    def __init__(self):
        self.task_generator = TaskGenerator()
        self.agent_tasks = {}  # Track tasks per agent
    
    async def create_periodic_tasks(self, agent_id: int, count: int):
        """Simulate agent creating periodic tasks."""
        if agent_id not in self.agent_tasks:
            self.agent_tasks[agent_id] = []
        
        for _ in range(count):
            task_data = self.task_generator.generate_task(
                title=f"Agent {agent_id} Task"
            )
            # API call simulation would go here
            # For load testing, this would make actual HTTP requests
            self.agent_tasks[agent_id].append(task_data)
    
    async def check_task_status(self, agent_id: int):
        """Simulate agent checking task status."""
        if agent_id in self.agent_tasks and self.agent_tasks[agent_id]:
            # Simulate API calls to check task status
            # This would make actual HTTP requests in load tests
            pass
    
    async def update_random_tasks(self, agent_id: int):
        """Simulate agent updating some tasks."""
        if agent_id in self.agent_tasks and self.agent_tasks[agent_id]:
            # Simulate updating random tasks
            # This would make actual HTTP requests in load tests
            pass
```

### Performance Metrics (`utils/metrics.py`)
```python
import time
import statistics
from typing import Dict, List, Any
from dataclasses import dataclass, field
import psutil
import asyncio

@dataclass
class ResponseMetrics:
    operation: str
    response_times: List[float] = field(default_factory=list)
    status_codes: List[int] = field(default_factory=list) 
    errors: List[str] = field(default_factory=list)
    success_count: int = 0
    total_count: int = 0

class PerformanceCollector:
    """Collect and analyze performance metrics."""
    
    def __init__(self):
        self.metrics: Dict[str, ResponseMetrics] = {}
        self.start_time = time.time()
    
    def record_response(self, operation: str, response_time_ms: float, 
                       status_code: int, success: bool):
        """Record API response metrics."""
        if operation not in self.metrics:
            self.metrics[operation] = ResponseMetrics(operation)
        
        metric = self.metrics[operation]
        metric.response_times.append(response_time_ms)
        metric.status_codes.append(status_code)
        metric.total_count += 1
        
        if success:
            metric.success_count += 1
    
    def record_error(self, operation: str, error: str):
        """Record operation error."""
        if operation not in self.metrics:
            self.metrics[operation] = ResponseMetrics(operation)
        
        self.metrics[operation].errors.append(error)
        self.metrics[operation].total_count += 1
    
    def get_p95_response_time(self, operation: str) -> float:
        """Get 95th percentile response time."""
        if operation not in self.metrics or not self.metrics[operation].response_times:
            return 0.0
        
        times = sorted(self.metrics[operation].response_times)
        p95_index = int(len(times) * 0.95)
        return times[p95_index]
    
    def get_p50_response_time(self, operation: str) -> float:
        """Get median response time."""
        if operation not in self.metrics or not self.metrics[operation].response_times:
            return 0.0
        
        return statistics.median(self.metrics[operation].response_times)
    
    def get_error_rate(self, operation: str) -> float:
        """Get error rate as percentage."""
        if operation not in self.metrics or self.metrics[operation].total_count == 0:
            return 0.0
        
        metric = self.metrics[operation]
        error_count = len(metric.errors) + (metric.total_count - metric.success_count)
        return error_count / metric.total_count
    
    def print_summary(self, test_name: str):
        """Print performance summary."""
        total_time = time.time() - self.start_time
        
        print(f"\n=== {test_name} Performance Summary ===")
        print(f"Total test duration: {total_time:.2f}s")
        
        for operation, metric in self.metrics.items():
            if not metric.response_times:
                continue
                
            print(f"\n{operation}:")
            print(f"  Total requests: {metric.total_count}")
            print(f"  Successful: {metric.success_count} ({metric.success_count/metric.total_count*100:.1f}%)")
            print(f"  P50 response time: {self.get_p50_response_time(operation):.2f}ms")
            print(f"  P95 response time: {self.get_p95_response_time(operation):.2f}ms")
            print(f"  Error rate: {self.get_error_rate(operation)*100:.2f}%")
            print(f"  Throughput: {metric.total_count/total_time:.2f} req/sec")

class SystemMetrics:
    """Monitor system resource usage during load tests."""
    
    def __init__(self):
        self.cpu_samples = []
        self.memory_samples = []
        self.disk_samples = []
        self.network_samples = []
    
    async def monitor_system_continuously(self, duration_seconds: int):
        """Monitor system resources continuously."""
        start_time = time.time()
        
        while time.time() - start_time < duration_seconds:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            self.cpu_samples.append(cpu_percent)
            
            # Memory usage
            memory = psutil.virtual_memory()
            self.memory_samples.append(memory.used)
            
            # Disk I/O
            disk_io = psutil.disk_io_counters()
            self.disk_samples.append({
                "read_bytes": disk_io.read_bytes,
                "write_bytes": disk_io.write_bytes
            })
            
            await asyncio.sleep(5)  # Sample every 5 seconds
        
        return self._calculate_system_stats()
    
    def _calculate_system_stats(self) -> Dict[str, Any]:
        """Calculate system performance statistics."""
        return {
            "avg_cpu_usage": statistics.mean(self.cpu_samples) / 100,
            "max_cpu_usage": max(self.cpu_samples) / 100,
            "avg_memory_usage": statistics.mean(self.memory_samples),
            "max_memory_usage": max(self.memory_samples),
            "memory_growth": self.memory_samples[-1] - self.memory_samples[0],
            "system_restarts": 0,  # Would be detected by monitoring
            "db_connection_errors": 0,  # Would be counted from logs
            "memory_leaks_detected": self._detect_memory_leaks()
        }
    
    def _detect_memory_leaks(self) -> int:
        """Detect potential memory leaks from usage patterns."""
        if len(self.memory_samples) < 10:
            return 0
            
        # Simple leak detection: consistent upward trend
        recent_samples = self.memory_samples[-10:]
        growth_rate = (recent_samples[-1] - recent_samples[0]) / len(recent_samples)
        
        # Flag as potential leak if memory grows > 10MB per sample consistently
        return 1 if growth_rate > 10 * 1024 * 1024 else 0
```

### Running Load Tests

#### Basic Load Test Execution
```bash
# Run all load tests
pytest tests/load/ -v --tb=short -m load

# Run specific load test categories
pytest tests/load/test_api_load/ -v -m load
pytest tests/load/test_execution_load/ -v -m load

# Run with custom load parameters
pytest tests/load/ -v -m load --load-duration=300 --load-rps=100

# Run sustained load tests (long duration)
pytest tests/load/ -v -m "load and slow" --maxfail=1
```

#### Performance Monitoring
```bash
# Run with system monitoring
pytest tests/load/ -v -m load --monitor-system --report-resources

# Generate performance report
pytest tests/load/ -v -m load --performance-report=load_test_results.html

# Run with specific SLA validation
pytest tests/load/ -v -m load --validate-sla --sla-config=sla_requirements.json
```

## Quality Standards

### Performance Requirements
- **API Response Times**: Meet documented SLA requirements
- **System Throughput**: Handle target load without degradation
- **Resource Utilization**: Stay within defined resource limits
- **Reliability**: Maintain functionality under sustained load

### Load Test Quality
- **Realistic Scenarios**: Tests reflect actual agent usage patterns  
- **Scalability Validation**: Performance scales linearly with resources
- **Bottleneck Identification**: Tests identify system limitations
- **Regression Prevention**: Performance doesn't degrade between versions

### Success Criteria
- All performance SLAs met under target load
- System remains stable during sustained load testing
- Resource usage stays within acceptable bounds
- No data corruption or loss under high load
- Clear performance bottlenecks identified and documented

This load testing framework ensures the Personal Agent Orchestrator can handle production workloads reliably and meet performance expectations under realistic usage scenarios.