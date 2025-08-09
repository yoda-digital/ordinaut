# Workers System - Distributed Job Processing

## Purpose and Architecture

The Workers system is the **distributed job processing backbone** of the Personal Agent Orchestrator. It provides concurrent, fault-tolerant execution of scheduled tasks using PostgreSQL's `SKIP LOCKED` pattern for safe work distribution across multiple worker processes.

### Core Responsibilities
- **Concurrent Job Processing**: Multiple workers safely lease and process work items without conflicts
- **SKIP LOCKED Work Leasing**: Database-level coordination using PostgreSQL's advanced locking mechanisms
- **Worker Coordination**: Health monitoring, heartbeat tracking, and load balancing
- **Crash Recovery**: Automatic cleanup of abandoned leases from crashed or stuck workers
- **Performance Monitoring**: Comprehensive metrics collection and operational visibility

### Architecture Overview
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   due_work      │    │  WorkerRunner    │    │ Pipeline        │
│   Table         │◄──►│  (runner.py)     │───►│ Executor        │
│                 │    │                  │    │ (engine/)       │
│ SKIP LOCKED     │    │ • Lease work     │    │                 │
│ FOR UPDATE      │    │ • Process tasks  │    │ • Tool calls    │
│                 │    │ • Heartbeat      │    │ • MCP bridge    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         ▲                       │                       
         │              ┌────────▼────────┐              
         │              │ WorkerCoordinator│              
         │              │ (coordinator.py) │              
         │              │                  │              
         └──────────────│ • Health monitor │              
                        │ • Lease cleanup  │              
                        │ • Load balancing │              
                        └──────────────────┘              
```

---

## Core Components

### 1. runner.py - Primary Worker Process

**Purpose**: The main worker process that leases work items, executes pipeline tasks, and maintains worker health.

**Key Features**:
- **Safe Work Leasing**: Uses `SELECT ... FOR UPDATE SKIP LOCKED` to prevent multiple workers from processing the same task
- **Pipeline Execution**: Integrates with the engine system to run task pipelines with tool calls
- **Retry Logic**: Implements exponential backoff with jitter for failed tasks
- **Graceful Shutdown**: Handles SIGTERM/SIGINT signals for clean worker termination
- **Heartbeat Management**: Regular health reporting to coordinator systems
- **Lease Management**: Automatic lease renewal for long-running tasks

**Core Methods**:
```python
class WorkerRunner:
    def lease_one(self) -> dict:
        """Lease single work item using SKIP LOCKED pattern"""
        
    def process_work_item(self, lease: dict) -> bool:
        """Execute pipeline with retry logic and error handling"""
        
    def heartbeat(self):
        """Send worker liveness signal with queue metrics"""
        
    def cleanup_expired_leases(self):
        """Clean up abandoned leases from crashed workers"""
```

**Database Interaction Pattern**:
```sql
-- Safe work leasing query (PostgreSQL SKIP LOCKED)
SELECT id, task_id, run_at
FROM due_work
WHERE run_at <= now()
  AND (locked_until IS NULL OR locked_until < now())
ORDER BY run_at
FOR UPDATE SKIP LOCKED
LIMIT 1;

-- Lease acquisition
UPDATE due_work
SET locked_until = :locked_until, locked_by = :worker_id
WHERE id = :work_id;
```

### 2. config.py - Configuration Management

**Purpose**: Centralized configuration system for worker processes with environment variable support.

**Configuration Domains**:
- **Database Connection**: Connection pooling and timeout settings
- **Work Leasing**: Lease duration and renewal intervals  
- **Processing Behavior**: Retry logic, backoff strategies, and concurrency limits
- **Health Monitoring**: Heartbeat intervals and cleanup thresholds
- **Operational Limits**: Processing timeouts and graceful shutdown

**Key Classes**:
```python
@dataclass
class WorkerConfig:
    database_url: str
    worker_id: str
    lease_seconds: int = 60
    max_concurrent_leases: int = 1
    heartbeat_interval: int = 30
    backoff_base_delay: float = 1.0
    backoff_max_delay: float = 60.0
    
    @classmethod
    def from_environment(cls, worker_id: str) -> "WorkerConfig"

class WorkerMetrics:
    """Performance and operational metrics collection"""
    def record_task_completed(self, success: bool, duration: float, retries: int)
    def record_lease_acquired(self)
    def record_heartbeat_sent(self)
    def get_summary(self) -> dict
```

**Environment Variables**:
```bash
DATABASE_URL="postgresql://user:pass@localhost/orchestrator"
WORKER_LEASE_SECONDS=60
WORKER_MAX_LEASES=1
WORKER_HEARTBEAT_INTERVAL=30
WORKER_CLEANUP_INTERVAL=300
WORKER_LOG_LEVEL=INFO
```

### 3. coordinator.py - Worker Coordination System

**Purpose**: Manages worker coordination, health monitoring, and load balancing across the distributed worker fleet.

**Core Responsibilities**:
- **Health Monitoring**: Track worker heartbeats and detect unhealthy instances
- **Lease Management**: Clean up stale leases from crashed/disconnected workers
- **Load Balancing**: Redistribute work when workers become overloaded
- **Queue Analytics**: Provide comprehensive statistics about work distribution
- **Operational Alerts**: Detect and report system anomalies

**Key Methods**:
```python
class WorkerCoordinator:
    def get_active_workers(self, since_minutes: int = 5) -> List[Dict[str, Any]]
    def get_worker_stats(self, worker_id: str) -> Optional[Dict[str, Any]]
    def cleanup_stale_leases(self, stale_threshold_minutes: int = 10) -> int
    def get_queue_stats(self) -> Dict[str, Any]
    def rebalance_work(self, max_lease_per_worker: int = 5) -> Dict[str, Any]
```

**Health Monitoring Logic**:
```sql
-- Detect workers that haven't sent heartbeat recently
SELECT worker_id, last_seen, 
       EXTRACT(EPOCH FROM (now() - last_seen)) as seconds_since_heartbeat
FROM worker_heartbeat
WHERE last_seen < now() - interval '5 minutes';

-- Clean up their abandoned leases
UPDATE due_work 
SET locked_until = NULL, locked_by = NULL
WHERE locked_by NOT IN (
  SELECT worker_id FROM worker_heartbeat 
  WHERE last_seen > now() - interval '10 minutes'
);
```

### 4. cli.py - Worker Management Interface

**Purpose**: Command-line interface for operational management and monitoring of the distributed worker system.

**Available Commands**:

#### System Status
```bash
python workers/cli.py status
```
Shows comprehensive system overview including:
- Active workers with heartbeat status
- Queue depth and processing statistics  
- Pending work distribution by priority
- Recent success/failure rates

#### Worker Management
```bash
python workers/cli.py workers --worker-id worker-abc123
python workers/cli.py workers --minutes 60  # All workers in last hour
```
Provides detailed worker information including:
- Current lease assignments and expiry times
- Processing statistics and performance metrics
- Recent task execution history

#### Operational Maintenance
```bash
python workers/cli.py cleanup --stale-minutes 10
python workers/cli.py rebalance --max-leases 5
```
Performs system maintenance operations:
- Clean up expired leases from crashed workers
- Rebalance work distribution across healthy workers

#### Continuous Monitoring
```bash
python workers/cli.py monitor --interval 30
```
Real-time monitoring with automated alerting for:
- Unhealthy workers (missed heartbeats)
- Expired lease accumulation
- Work queue age and depth issues

---

## SKIP LOCKED Concurrency Control

### The Problem: Safe Distributed Work Processing

When multiple worker processes compete for the same work items, race conditions can occur:
- **Double Processing**: Two workers process the same task
- **Lost Work**: Work items disappear during concurrent access
- **Deadlocks**: Workers block each other indefinitely

### The Solution: PostgreSQL SKIP LOCKED

PostgreSQL's `SKIP LOCKED` modifier provides lock-free concurrency:

```sql
-- Standard approach (problematic with concurrency)
SELECT * FROM due_work WHERE run_at <= now() ORDER BY run_at LIMIT 1;
-- Race condition: multiple workers can select same row

-- SKIP LOCKED approach (safe concurrency)
SELECT * FROM due_work 
WHERE run_at <= now() 
ORDER BY run_at 
FOR UPDATE SKIP LOCKED 
LIMIT 1;
-- Only one worker gets the row, others get different rows or nothing
```

### Implementation Details

**Work Leasing Pattern**:
```python
def lease_one(self):
    """Thread-safe work leasing using SKIP LOCKED"""
    with self.eng.begin() as cx:
        # 1. Find available work (skips locked rows)
        row = cx.execute(text("""
            SELECT id, task_id, run_at
            FROM due_work
            WHERE run_at <= now()
              AND (locked_until IS NULL OR locked_until < now())
            ORDER BY run_at
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        """)).fetchone()
        
        if not row:
            return None  # No work available
        
        # 2. Acquire lease (atomic in same transaction)
        locked_until = datetime.now(timezone.utc) + timedelta(seconds=60)
        cx.execute(text("""
            UPDATE due_work
            SET locked_until = :lu, locked_by = :worker_id
            WHERE id = :id
        """), {"lu": locked_until, "worker_id": self.worker_id, "id": row.id})
        
        return {"id": row.id, "task_id": row.task_id, "locked_until": locked_until}
```

**Advantages**:
- **No Deadlocks**: Workers never block each other
- **High Throughput**: Maximum concurrent processing without conflicts
- **Fairness**: Work distributed evenly across workers
- **Crash Safety**: Abandoned leases automatically expire

**Database Requirements**:
- PostgreSQL 9.5+ (SKIP LOCKED introduction)
- Proper indexes on `(run_at, locked_until)` for performance
- Connection pooling with transaction-level isolation

---

## Worker Lifecycle Management

### Worker States and Transitions

```
    START
      │
      ▼
  ┌─────────┐     ┌─────────┐     ┌─────────────┐
  │ STARTING│────►│  READY  │────►│ PROCESSING  │
  └─────────┘     └─────────┘     └─────────────┘
                       ▲                 │
                       │                 ▼
  ┌─────────┐     ┌─────────┐     ┌─────────────┐
  │ STOPPED │◄────│STOPPING│◄────│   ERROR     │
  └─────────┘     └─────────┘     └─────────────┘
```

### Startup Sequence
1. **Configuration Loading**: Parse environment variables and validate settings
2. **Database Validation**: Test connection and verify schema presence  
3. **Signal Handler Setup**: Register SIGTERM/SIGINT handlers for graceful shutdown
4. **Initial Heartbeat**: Register worker with coordinator system
5. **Work Loop Entry**: Begin processing available work items

### Heartbeat Protocol
Workers send periodic heartbeats to maintain coordination:

```python
def heartbeat(self):
    """Send worker liveness signal with operational metrics"""
    with self.eng.begin() as cx:
        cx.execute(text("""
            INSERT INTO worker_heartbeat (worker_id, last_heartbeat, processed_count, pid, hostname)
            VALUES (:worker_id, now(), :count, :pid, :hostname)
            ON CONFLICT (worker_id) 
            DO UPDATE SET 
                last_heartbeat = now(),
                processed_count = EXCLUDED.processed_count,
                pid = EXCLUDED.pid,
                hostname = EXCLUDED.hostname
        """), {
            "worker_id": self.worker_id,
            "count": self.metrics.tasks_processed,
            "pid": os.getpid(),
            "hostname": os.uname().nodename
        })
```

### Graceful Shutdown
Workers handle shutdown signals cleanly:

1. **Signal Reception**: Catch SIGTERM/SIGINT signals
2. **Work Completion**: Finish current task if possible
3. **Lease Release**: Return any held leases to the pool
4. **Final Metrics**: Report processing statistics
5. **Database Cleanup**: Close connections and release resources

```python
def shutdown(self):
    """Clean worker termination with lease release"""
    self.logger.info("Worker shutting down gracefully")
    
    # Release current lease if any
    if self.current_lease:
        with self.eng.begin() as cx:
            cx.execute(text("""
                UPDATE due_work 
                SET locked_until = NULL, locked_by = NULL
                WHERE id = :id AND locked_by = :worker_id
            """), {"id": self.current_lease["id"], "worker_id": self.worker_id})
    
    # Final metrics report
    self.logger.info(f"Final metrics: {self.metrics.get_summary()}")
```

---

## Crash Recovery and Fault Tolerance

### Automatic Lease Recovery

When workers crash or become unresponsive, their work leases are automatically recovered:

**Coordinator-Based Cleanup**:
```python
def cleanup_stale_leases(self, stale_threshold_minutes: int = 10) -> int:
    """Recover work from crashed workers"""
    with self.eng.begin() as cx:
        result = cx.execute(text("""
            UPDATE due_work 
            SET locked_until = NULL, locked_by = NULL
            WHERE locked_by NOT IN (
                SELECT worker_id FROM worker_heartbeat 
                WHERE last_heartbeat > now() - interval '%s minutes'
            )
        """ % stale_threshold_minutes))
        
        return result.rowcount  # Number of recovered leases
```

**Lease Expiration Recovery**:
```python
def cleanup_expired_leases(self):
    """Clean up leases past their timeout"""
    with self.eng.begin() as cx:
        result = cx.execute(text("""
            UPDATE due_work 
            SET locked_until = NULL, locked_by = NULL
            WHERE locked_until < now() - interval '60 seconds'
        """))
```

### Retry Logic and Error Handling

Tasks are retried using exponential backoff with jitter:

```python
def exponential_backoff_with_jitter(self, attempt: int) -> float:
    """Calculate retry delay with randomization"""
    base_delay = self.config.backoff_base_delay  # 1.0 seconds
    max_delay = self.config.backoff_max_delay    # 60.0 seconds
    
    # Exponential: 1s, 2s, 4s, 8s, 16s, 32s, 60s (capped)
    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
    
    # Add jitter: 50-100% of calculated delay
    if self.config.backoff_jitter:
        jitter = delay * (0.5 + random.random() * 0.5)
        return jitter
    else:
        return delay
```

**Error Classification**:
- **Retryable Errors**: Network timeouts, temporary service unavailability
- **Non-Retryable Errors**: Schema validation failures, authentication errors
- **Fatal Errors**: Worker crashes, database connection loss

### Network Partition Handling

Workers handle network partitions gracefully:
- **Connection Loss**: Database connections are automatically retried with exponential backoff
- **Partial Connectivity**: Workers continue processing local work until connectivity is restored
- **Split-Brain Prevention**: Lease timeouts prevent multiple workers from processing the same work

---

## Performance Metrics and Monitoring

### Worker-Level Metrics

Each worker collects comprehensive performance data:

```python
class WorkerMetrics:
    def __init__(self):
        # Task processing metrics
        self.tasks_processed = 0
        self.tasks_succeeded = 0
        self.tasks_failed = 0
        self.tasks_retried = 0
        self.total_processing_time = 0.0
        
        # Lease management metrics
        self.leases_acquired = 0
        self.leases_renewed = 0
        self.leases_expired = 0
        
        # System health metrics
        self.heartbeats_sent = 0
        self.errors_encountered = 0
```

**Key Performance Indicators**:
- **Success Rate**: Percentage of tasks completed successfully
- **Average Processing Time**: Mean duration for task execution
- **Lease Efficiency**: Ratio of acquired to expired leases
- **Error Rate**: Frequency of processing failures

### System-Wide Analytics

The coordinator provides fleet-wide visibility:

```python
def get_queue_stats(self) -> Dict[str, Any]:
    """Comprehensive system performance metrics"""
    with self.eng.begin() as cx:
        queue_stats = cx.execute(text("""
            SELECT 
                COUNT(*) as total_pending,
                COUNT(*) FILTER (WHERE run_at <= now()) as ready_now,
                COUNT(*) FILTER (WHERE locked_until > now()) as currently_leased,
                COUNT(*) FILTER (WHERE locked_until <= now()) as expired_leases,
                EXTRACT(EPOCH FROM (now() - MIN(run_at))) as oldest_age_seconds
            FROM due_work
        """)).mappings().first()
        
        processing_stats = cx.execute(text("""
            SELECT 
                COUNT(*) as total_runs,
                COUNT(*) FILTER (WHERE success = true) as successful_runs,
                AVG(EXTRACT(EPOCH FROM (finished_at - started_at))) as avg_duration,
                COUNT(DISTINCT lease_owner) as active_workers
            FROM task_run
            WHERE started_at > now() - interval '1 hour'
        """)).mappings().first()
```

**Operational Dashboards**:
- **Queue Depth**: Number of pending work items over time
- **Processing Throughput**: Tasks completed per minute/hour
- **Worker Health**: Active worker count and heartbeat status
- **Error Trends**: Failure rates and error pattern analysis

### Alerting and Anomaly Detection

**Automated Alerts**:
- **Worker Unavailability**: No heartbeat received within threshold
- **Queue Stagnation**: Work items pending beyond acceptable time limits
- **High Error Rate**: Processing failures exceed baseline
- **Resource Exhaustion**: Database connection or memory limits approached

**Alert Implementation**:
```python
def monitor_worker_health(db_url: str, unhealthy_threshold_minutes: int = 5):
    """Detect and alert on unhealthy workers"""
    coordinator = WorkerCoordinator(db_url)
    
    unhealthy_workers = []
    all_workers = coordinator.get_active_workers(since_minutes=60)
    
    for worker in all_workers:
        if worker["seconds_since_heartbeat"] > (unhealthy_threshold_minutes * 60):
            unhealthy_workers.append(worker)
            logging.warning(f"Worker {worker['worker_id']} unhealthy: "
                          f"last seen {worker['seconds_since_heartbeat']:.0f}s ago")
    
    # Trigger cleanup if unhealthy workers detected
    if unhealthy_workers:
        cleaned = coordinator.cleanup_stale_leases(unhealthy_threshold_minutes)
        logging.info(f"Cleaned up {cleaned} stale leases")
```

---

## Operational Procedures

### Deployment and Scaling

**Single Worker Deployment**:
```bash
# Set environment variables
export DATABASE_URL="postgresql://user:pass@localhost/orchestrator"
export WORKER_LEASE_SECONDS=60
export WORKER_HEARTBEAT_INTERVAL=30

# Start worker process
python workers/runner.py
```

**Multi-Worker Scaling**:
```bash
# Start multiple workers (automatically get unique IDs)
for i in {1..5}; do
    python workers/runner.py &
done

# Monitor worker fleet
python workers/cli.py status
```

**Container Deployment**:
```dockerfile
# Dockerfile.worker
FROM python:3.12
COPY . /app
WORKDIR /app
RUN pip install -r requirements.txt
CMD ["python", "workers/runner.py"]
```

```yaml
# docker-compose.yml
version: '3.8'
services:
  worker:
    build: .
    environment:
      - DATABASE_URL=postgresql://user:pass@db/orchestrator
      - WORKER_LEASE_SECONDS=60
    deploy:
      replicas: 3
      restart_policy:
        condition: on-failure
        delay: 5s
```

### Health Monitoring

**System Status Check**:
```bash
python workers/cli.py status
# Shows:
# - Active workers and their heartbeat status
# - Queue depth and processing statistics
# - Recent success/failure rates
# - Work distribution by priority
```

**Worker Detail Inspection**:
```bash
python workers/cli.py workers --worker-id worker-abc123
# Shows:
# - Current lease assignments
# - Processing performance metrics
# - Recent task execution history
```

**Continuous Monitoring**:
```bash
python workers/cli.py monitor --interval 30
# Real-time monitoring with alerts for:
# - Unhealthy workers
# - Queue stagnation
# - High error rates
```

### Troubleshooting Procedures

**Common Issues and Solutions**:

**Workers Not Processing Work**:
```bash
# Check worker status
python workers/cli.py status

# Check for stale leases
python workers/cli.py cleanup --stale-minutes 10

# Verify database connectivity
python workers/cli.py queue
```

**High Error Rates**:
```bash
# Get detailed worker stats
python workers/cli.py workers --worker-id problematic-worker

# Check recent task execution logs
tail -f /var/log/orchestrator/worker.log | grep ERROR

# Review task retry patterns
SELECT task_id, COUNT(*) as attempts, AVG(attempt) as avg_attempts
FROM task_run 
WHERE started_at > now() - interval '1 hour' 
GROUP BY task_id 
HAVING AVG(attempt) > 2;
```

**Worker Memory Leaks**:
```bash
# Monitor worker memory usage
ps aux | grep "python workers/runner.py"

# Restart workers with memory limits
docker update --memory 512m worker-container-id

# Implement worker rotation
python workers/cli.py workers | jq -r '.[] | select(.seconds_since_heartbeat < 60) | .worker_id' | \
  xargs -I {} docker restart worker-{}
```

**Database Performance Issues**:
```sql
-- Check for lock contention
SELECT * FROM pg_stat_activity WHERE wait_event_type = 'Lock';

-- Monitor due_work table performance
EXPLAIN ANALYZE SELECT * FROM due_work 
WHERE run_at <= now() 
  AND (locked_until IS NULL OR locked_until < now())
ORDER BY run_at 
FOR UPDATE SKIP LOCKED 
LIMIT 1;

-- Optimize indexes if needed
CREATE INDEX CONCURRENTLY idx_due_work_processing 
ON due_work (run_at, locked_until) 
WHERE run_at <= now();
```

### Performance Tuning

**Database Configuration**:
```sql
-- PostgreSQL configuration for high-concurrency workloads
-- postgresql.conf
max_connections = 200
shared_buffers = 256MB
effective_cache_size = 1GB
maintenance_work_mem = 64MB
checkpoint_completion_target = 0.7
wal_buffers = 16MB
default_statistics_target = 100
random_page_cost = 1.1
effective_io_concurrency = 200
work_mem = 4MB
```

**Worker Tuning**:
```bash
# Optimize for high-throughput processing
export WORKER_LEASE_SECONDS=30           # Shorter leases for faster recovery
export WORKER_HEARTBEAT_INTERVAL=15      # More frequent health checks
export WORKER_CLEANUP_INTERVAL=120       # More aggressive cleanup

# Optimize for long-running tasks
export WORKER_LEASE_SECONDS=300          # Longer leases for complex tasks
export WORKER_MAX_PROCESSING_TIME=7200   # Extended timeout for heavy work
```

**Load Balancing**:
```bash
# Rebalance work across workers
python workers/cli.py rebalance --max-leases 3

# Monitor rebalancing effectiveness
python workers/cli.py queue | jq '.priority_distribution'
```

---

## Integration with Engine Systems

### Pipeline Execution Flow

Workers integrate seamlessly with the pipeline execution engine:

```python
def process_work_item(self, lease: dict) -> bool:
    """Execute task pipeline through engine integration"""
    task = self.fetch_task(lease["task_id"])
    
    try:
        # Execute pipeline through engine system
        from engine.executor import run_pipeline
        context = run_pipeline(task)
        
        # Record successful execution
        self.record_run(task["id"], started_at, True, output=context)
        self.delete_work(lease["id"])
        return True
        
    except Exception as e:
        # Handle failures with retry logic
        self.record_run(task["id"], started_at, False, error=str(e))
        
        if self.should_retry(task, attempt, e):
            # Will be retried after backoff delay
            return False
        else:
            # Permanent failure, remove from queue
            self.delete_work(lease["id"])
            return False
```

### MCP Tool Execution

Workers coordinate with the MCP (Model Context Protocol) system for tool execution:

```python
# Engine integration handles MCP tool calls
def execute_pipeline_step(step, context):
    tool = get_tool(step["uses"])
    
    # Render templates: ${steps.x.y}, ${params.z}
    args = render_templates(step.get("with", {}), context)
    
    # Execute via MCP bridge
    result = call_mcp_tool(tool, args, timeout=step.get("timeout", 30))
    
    return result
```

### Event System Integration

Workers emit events to the Redis Streams event spine:

```python
def emit_execution_event(self, task_id: str, event_type: str, payload: dict):
    """Emit execution event to event spine"""
    event_data = {
        "task_id": task_id,
        "worker_id": self.config.worker_id,
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": json.dumps(payload)
    }
    
    # Redis Streams integration
    self.redis_client.xadd(
        name="orchestrator:events",
        fields=event_data,
        maxlen=10000  # Keep last 10k events
    )
```

---

## Security and Access Control

### Worker Authentication

Workers authenticate using database-level credentials:
- **Connection Security**: SSL/TLS encryption for all database connections
- **Credential Management**: Environment-based configuration with secret management
- **Network Isolation**: Workers communicate only with database and internal services

### Scope-Based Authorization

Workers enforce agent scope limitations:
```python
def validate_task_execution(self, task: dict) -> bool:
    """Verify worker has permission to execute task"""
    agent = self.fetch_agent(task["created_by"])
    required_scopes = extract_required_scopes(task["payload"])
    
    if not all(scope in agent["scopes"] for scope in required_scopes):
        self.logger.error(f"Task {task['id']} requires scopes not granted to agent")
        return False
    
    return True
```

### Audit Logging

All worker actions are comprehensively logged:
```python
def record_run(self, task_id, started_at, success, output=None, error=None, attempt=1):
    """Audit trail for all task executions"""
    with self.eng.begin() as cx:
        cx.execute(text("""
            INSERT INTO task_run (
                task_id, lease_owner, started_at, finished_at, 
                success, output, error, attempt
            ) VALUES (
                :tid, :owner, :sa, now(), :sc, :out::jsonb, :err, :attempt
            )
        """), {
            "tid": task_id,
            "owner": self.config.worker_id,
            "sa": started_at,
            "sc": success,
            "out": json.dumps(output) if output else None,
            "err": error,
            "attempt": attempt
        })
```

### Input Validation

Workers validate all task inputs using JSON Schema:
```python
def validate_pipeline_payload(self, payload: dict) -> bool:
    """Validate task pipeline against schema"""
    try:
        from jsonschema import validate
        validate(instance=payload, schema=PIPELINE_SCHEMA)
        return True
    except ValidationError as e:
        self.logger.error(f"Pipeline validation failed: {e}")
        return False
```

---

## Testing and Quality Assurance

### Unit Testing

Workers include comprehensive unit tests:

```python
# tests/unit/test_worker_concurrency.py
def test_skip_locked_prevents_double_processing():
    """Verify SKIP LOCKED prevents race conditions"""
    # Start multiple workers simultaneously
    # Verify no work item is processed twice
    # Confirm all work items are processed exactly once

def test_lease_expiration_recovery():
    """Test automatic recovery of expired leases"""
    # Create work item and lease it
    # Simulate worker crash (don't release lease)
    # Verify lease expires and work is recovered

def test_graceful_shutdown():
    """Test clean worker termination"""
    # Start worker with active lease
    # Send shutdown signal
    # Verify lease is released and metrics reported
```

### Integration Testing

```python
# tests/integration/test_worker_coordination.py
def test_multi_worker_coordination():
    """Test multiple workers processing work safely"""
    # Start 5 workers simultaneously
    # Create 100 work items
    # Verify all items processed exactly once
    # Check no deadlocks or race conditions

def test_crash_recovery_scenarios():
    """Test various failure recovery patterns"""
    # Simulate database connection loss
    # Simulate worker process crashes
    # Simulate network partitions
    # Verify system recovers gracefully
```

### Load Testing

```python
# tests/load/test_worker_performance.py
def test_high_concurrency_processing():
    """Benchmark worker performance under load"""
    # Create 10,000 work items
    # Start 10 workers
    # Measure processing throughput
    # Verify no performance degradation

def test_database_connection_scaling():
    """Test database connection pool limits"""
    # Scale workers beyond connection pool size
    # Verify connection sharing works correctly
    # Monitor for connection leaks
```

---

## Best Practices and Conventions

### Configuration Management
- **Environment Variables**: Use environment-based configuration for all deployment-specific settings
- **Validation**: Validate all configuration on startup with clear error messages
- **Defaults**: Provide sensible defaults for optional configuration parameters
- **Documentation**: Document all configuration options with examples

### Error Handling
- **Classification**: Distinguish between retryable and permanent errors
- **Logging**: Include sufficient context in error messages for debugging
- **Metrics**: Track error rates and patterns for operational visibility
- **Recovery**: Implement automatic recovery for transient failures

### Performance Optimization
- **Database Indexes**: Ensure proper indexing on work leasing queries
- **Connection Pooling**: Use appropriate connection pool sizing for workload
- **Batch Processing**: Group related operations to reduce database round-trips
- **Memory Management**: Monitor and limit worker memory usage

### Operational Excellence
- **Monitoring**: Implement comprehensive metrics and alerting
- **Documentation**: Maintain up-to-date operational procedures
- **Testing**: Include chaos engineering tests for failure scenarios
- **Security**: Follow principle of least privilege for all access controls

---

*The Workers system forms the operational backbone of the Personal Agent Orchestrator, providing reliable, scalable, and fault-tolerant execution of agent tasks. Its SKIP LOCKED-based architecture ensures safe concurrent processing while comprehensive monitoring and coordination features enable confident production operations.*