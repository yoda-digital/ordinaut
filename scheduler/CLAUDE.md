# Scheduler Service - Personal Agent Orchestrator

## Mission Statement

The **Scheduler Service** is the temporal brain of the Personal Agent Orchestrator, providing bulletproof task scheduling with PostgreSQL persistence, RRULE processing, and timezone-aware execution. It transforms time-based intentions into reliable work items that workers can process safely and concurrently.

## Core Architecture

```
APScheduler (Blocking) → SQLAlchemyJobStore (PostgreSQL) → due_work Table → Workers (SKIP LOCKED)
```

The scheduler operates as a **push model** where APScheduler reliably calculates *when* to run tasks and creates `due_work` rows for independent workers to lease concurrently. This decouples scheduling accuracy from execution capacity.

## Key Components

### Primary Service: `tick.py`
- **Purpose**: Main scheduler daemon that converts task definitions into timed work items
- **Core Function**: `SchedulerService` class orchestrating the entire scheduling lifecycle
- **Dependencies**: APScheduler, SQLAlchemy, PostgreSQL, dateutil, observability systems

### Schedule Types Supported
1. **Cron**: Traditional Unix cron expressions (`"0 8 * * 1-5"`)
2. **RRULE**: RFC-5545 recurrence rules for complex patterns (`"FREQ=WEEKLY;BYDAY=MO,TU"`)
3. **Once**: One-time execution at specific datetime
4. **Event**: Triggered by external events (handled elsewhere)
5. **Condition**: Triggered by condition polling (handled elsewhere)

## Database Integration

### due_work Table Schema
```sql
CREATE TABLE due_work (
  id BIGSERIAL PRIMARY KEY,
  task_id UUID NOT NULL REFERENCES task(id),
  run_at TIMESTAMPTZ NOT NULL,
  locked_until TIMESTAMPTZ,
  locked_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON due_work (run_at);
CREATE INDEX ON due_work (task_id);
```

### Safe Concurrent Processing Pattern
The scheduler creates `due_work` rows that workers lease using PostgreSQL's `FOR UPDATE SKIP LOCKED`:

```python
def enqueue_due_work(self, task_id: str, scheduled_time: datetime = None):
    """Create a due_work row for worker processing with conflict handling."""
    with self.engine.begin() as conn:
        result = conn.execute(text("""
            INSERT INTO due_work (task_id, run_at)
            VALUES (:task_id, :run_at)
            ON CONFLICT DO NOTHING
            RETURNING id
        """), {"task_id": task_id, "run_at": run_at})
```

## APScheduler Configuration

### Production-Ready Settings
```python
jobstores = {
    'default': SQLAlchemyJobStore(url=database_url)
}

job_defaults = {
    'coalesce': True,           # Combine missed executions
    'max_instances': 1,         # Prevent concurrent job instances
    'misfire_grace_time': 30    # Grace period for late jobs (seconds)
}

scheduler = BlockingScheduler(
    jobstores=jobstores,
    job_defaults=job_defaults,
    timezone="Europe/Chisinau"  # Configurable default timezone
)
```

## RRULE Processing and Timezone Handling

### RFC-5545 Compliance
The scheduler uses `dateutil.rrule` for full RFC-5545 RRULE support:

```python
def _schedule_rrule_task(self, task_id: str, rrule_expr: str, task_timezone: str):
    """Schedule RRULE task for next occurrence only."""
    next_time = next_occurrence(rrule_expr, task_timezone)
    
    if next_time:
        trigger = DateTrigger(run_date=next_time, timezone=next_time.tzinfo)
        self.scheduler.add_job(
            self.enqueue_due_work,
            trigger,
            args=[task_id, next_time],
            id=f"rrule-{task_id}",
            replace_existing=True
        )
```

### DST Transition Handling
- All timestamps stored as UTC in database
- Timezone-aware scheduling prevents DST edge cases
- RRULE processing handles impossible/ambiguous times gracefully
- Scheduler lag monitoring detects timing drift

### RRULE Rescheduling Strategy
RRULE tasks use a **"rolling schedule"** approach:
1. Schedule only the **next occurrence**
2. After execution, automatically calculate and schedule the **following occurrence**
3. This prevents infinite job accumulation and handles long-term schedule changes

```python
def _reschedule_rrule_task_if_needed(self, task_id: str):
    """Called after each RRULE execution to schedule next occurrence."""
    next_time = next_occurrence(rrule_expr, task_timezone)
    if next_time:
        self.scheduler.add_job(/* schedule next occurrence */)
```

## Integration with Worker Coordination

### Scheduler → Worker Handoff
1. **Scheduler**: Creates `due_work` row with `run_at` timestamp
2. **Workers**: Query using `FOR UPDATE SKIP LOCKED` to lease work safely
3. **No Double Processing**: SKIP LOCKED ensures exactly-one worker gets each work item
4. **Lease Timeout**: Workers must complete work within lease period or lose ownership

### Worker Query Pattern
```sql
SELECT id, task_id, run_at
FROM due_work
WHERE run_at <= now()
  AND (locked_until IS NULL OR locked_until < now())
ORDER BY run_at
FOR UPDATE SKIP LOCKED
LIMIT 1
```

## Scheduler Accuracy and Timing Validation

### Performance Metrics
The scheduler tracks critical timing metrics:

```python
# Scheduler lag (how late jobs fire)
if scheduled_time:
    lag_seconds = (datetime.now(timezone.utc) - scheduled_time).total_seconds()
    orchestrator_metrics.update_scheduler_lag(lag_seconds)

# Job creation rates by type
orchestrator_metrics.record_scheduler_job_created(schedule_kind)

# Scheduler tick success/failure rates
orchestrator_metrics.record_scheduler_tick("success")
```

### Accuracy Requirements
- **Cron Jobs**: Fire within 30 seconds of scheduled time
- **RRULE Jobs**: Handle DST transitions without missing occurrences
- **Once Jobs**: Skip past-due single executions
- **All Jobs**: Gracefully handle system restarts and network partitions

### Monitoring and Alerting
Key metrics to monitor:
- `orchestrator_scheduler_lag_seconds` (should be < 30s)
- `orchestrator_scheduler_tick_total{status="error"}` (should be rare)
- `due_work` table depth (should drain quickly)
- Worker lease timeout frequency

## Error Handling and Resilience

### Graceful Shutdown
```python
def _signal_handler(self, signum, frame):
    """Handle SIGTERM/SIGINT gracefully."""
    logger.info(f"Received signal {signum}, initiating graceful shutdown")
    self._shutdown = True
    if self.scheduler and self.scheduler.running:
        self.scheduler.shutdown(wait=True)  # Wait for jobs to complete
```

### Database Connection Management
- Connection pooling with pre-ping health checks
- Automatic connection recovery after network issues
- Transaction rollback on failures
- Connection pool sizing: `pool_size=5, max_overflow=10`

### Fault Recovery Patterns
1. **Job Store Persistence**: APScheduler jobs survive service restarts via SQLAlchemy job store
2. **Idempotent Work Creation**: `ON CONFLICT DO NOTHING` prevents duplicate work items
3. **Scheduler Restart**: Service reloads active tasks and reschedules on startup
4. **Worker Independence**: Schedulers can restart without affecting in-flight work items

## Observability and Structured Logging

### Structured Event Logging
```python
structured_logger.info(
    "Due work enqueued",
    task_id=task_id,
    scheduled_time=scheduled_time.isoformat() + 'Z',
    run_at=run_at.isoformat() + 'Z',
    lag_seconds=lag_seconds,
    event_type="due_work_enqueued"
)
```

### Key Log Events
- `task_scheduled`: Task successfully added to scheduler
- `due_work_enqueued`: Work item created for worker processing
- `task_schedule_failed`: Scheduling errors with full context
- `tasks_loaded`: Startup task loading summary
- `scheduler_shutdown`: Graceful shutdown events

### Request Context Correlation
Each scheduling operation includes:
- `request_id`: Unique identifier for correlation
- `task_id`: Task being scheduled
- `schedule_duration_ms`: Performance timing
- `event_type`: Structured event classification

## Configuration and Environment

### Environment Variables
```bash
# Required
DATABASE_URL=postgresql://orchestrator:orchestrator_pw@localhost:5432/orchestrator

# Optional (with defaults)
TZ=Europe/Chisinau                    # Default timezone for scheduling
LOG_LEVEL=INFO                        # Logging verbosity
SCHEDULER_POLL_INTERVAL=30            # APScheduler polling interval
```

### APScheduler Job Store Settings
- **Job Store**: `SQLAlchemyJobStore` on PostgreSQL (recommended by APScheduler maintainers)
- **Timezone**: Configurable default, overrideable per task
- **Coalescing**: Enabled to prevent missed job accumulation
- **Max Instances**: 1 per job to prevent overlapping executions
- **Misfire Grace**: 30 seconds for late job tolerance

## Development and Testing Patterns

### Unit Testing Schedule Logic
```python
def test_rrule_next_occurrence():
    """Test RRULE processing across DST transitions."""
    rrule = "FREQ=WEEKLY;BYDAY=MO;BYHOUR=8"
    timezone_name = "Europe/Chisinau"
    
    # Test normal case
    next_time = next_occurrence(rrule, timezone_name)
    assert next_time is not None
    assert next_time.hour == 8
    
    # Test DST transition edge case
    # ... specific DST boundary testing
```

### Integration Testing
```python
def test_scheduler_worker_integration():
    """Test end-to-end scheduler → worker flow."""
    # Create test task
    task = create_test_task(schedule_kind="once", schedule_expr="2025-01-01T12:00:00")
    
    # Run scheduler
    scheduler.schedule_task_job(task)
    
    # Verify due_work created
    work_items = query_due_work()
    assert len(work_items) == 1
    
    # Verify worker can lease work
    work = worker.lease_one()
    assert work is not None
    assert work["task_id"] == task["id"]
```

### Performance Testing
- **Load Testing**: Create 1000+ concurrent cron tasks, verify no timing drift
- **DST Testing**: Schedule tasks around Spring/Fall DST transitions
- **Restart Testing**: Kill scheduler during active scheduling, verify recovery
- **Database Partition Testing**: Simulate PostgreSQL connection issues

## Production Deployment Considerations

### Container Configuration
```dockerfile
FROM python:3.12-slim
# ... dependencies installation ...

# Copy scheduler module
COPY scheduler /app/scheduler
COPY engine/rruler.py /app/engine/rruler.py
COPY engine/registry.py /app/engine/registry.py

# Set timezone (important for cron scheduling)
ENV TZ=Europe/Chisinau

CMD ["python", "scheduler/tick.py"]
```

### Resource Requirements
- **Memory**: ~100MB base + 10MB per 1000 scheduled tasks
- **CPU**: Low (event-driven, mostly idle)
- **Database Connections**: 5-15 connections (APScheduler job store + application pool)
- **Network**: Minimal (database-only communication)

### High Availability Patterns
- **Single Instance**: APScheduler job store prevents multiple schedulers from conflicts
- **Leader Election**: Can implement leader election for multi-instance deployments
- **Database Failover**: Scheduler tolerates PostgreSQL failover with connection retry
- **Service Discovery**: No external dependencies beyond PostgreSQL

## Common Operational Scenarios

### Adding New Schedule Types
1. Extend `schedule_kind` enum in database schema
2. Add parsing logic in `schedule_task_job()`
3. Implement specific `_schedule_*_task()` method
4. Add metrics collection for new type
5. Update documentation and tests

### Timezone Changes
```python
# Update task timezone
UPDATE task SET timezone = 'America/New_York' WHERE id = 'task-uuid';

# Scheduler will automatically use new timezone on next schedule cycle
# No manual intervention required
```

### Schedule Expression Updates
```python
# Update schedule expression
UPDATE task SET schedule_expr = '0 9 * * 1-5' WHERE id = 'task-uuid';

# For immediate effect, restart scheduler or use API to reload tasks
curl -X POST http://api:8080/admin/reload-schedules
```

### Debugging Scheduler Issues
```bash
# Check APScheduler job store
psql -c "SELECT * FROM apscheduler_jobs WHERE id LIKE 'cron-%';"

# Check due_work queue depth
psql -c "SELECT COUNT(*) FROM due_work WHERE run_at <= now();"

# Check scheduler lag metrics
curl -s http://metrics:9090/metrics | grep orchestrator_scheduler_lag_seconds

# Check recent scheduler logs
docker logs scheduler --tail=100 | grep "due_work_enqueued\|task_scheduled"
```

## Security and Authorization

### Scheduler Security Model
- **Database Access**: Read-only access to `task` table, write access to `due_work` table
- **Job Store Access**: Full APScheduler job store access for persistence
- **No External Network**: Scheduler communicates only with PostgreSQL
- **No User Input**: Schedules validated at API layer, not in scheduler

### Audit Trail
All scheduler operations logged with:
- Task ID and schedule details
- Timing information (scheduled vs actual)
- Success/failure status with error details
- Request correlation IDs for debugging

## Future Enhancements

### Planned Features
- **Dynamic Rescheduling**: Update schedules without service restart
- **Schedule Conflicts**: Detect and resolve overlapping execution windows
- **Advanced RRULE**: Support for EXDATE, RDATE, and complex rule combinations
- **Multi-Region**: Cross-timezone scheduling with region awareness
- **Schedule Templates**: Reusable schedule patterns (morning, evening, weekends)

### Migration Path to Temporal
When ready for human-in-the-loop workflows and complex sagas:
1. Keep existing APScheduler for simple recurring tasks
2. Migrate complex workflows to Temporal Workers
3. Use same `due_work` table as unified queue
4. Maintain tool contracts and MCP interfaces

The scheduler provides the rock-solid temporal foundation that transforms agent intentions into reliable, observable, and maintainable execution. It handles the complexity of time so your agents can focus on getting work done.