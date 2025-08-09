# Database Migrations - Personal Agent Orchestrator

## Purpose & Mission

The `migrations/` directory contains the complete database schema and migration scripts for the Personal Agent Orchestrator's PostgreSQL backend. This implements a **production-grade, ACID-compliant database** with specialized patterns for:

- **SKIP LOCKED job queues** for safe concurrent work distribution
- **Temporal task scheduling** with timezone and RRULE support
- **Pipeline execution state** with deterministic workflow tracking
- **Agent authorization** with scope-based access control
- **Audit logging** with immutable event trails
- **Performance optimization** with strategic indexing and partitioning

## Core Design Principles

### 1. Concurrency Safety
Every table that represents work items uses `SELECT ... FOR UPDATE SKIP LOCKED` patterns to ensure:
- **Zero work duplication** - no job is ever processed twice
- **Fair work distribution** - workers get balanced job allocation
- **Deadlock prevention** - SKIP LOCKED eliminates lock contention
- **Graceful scaling** - adding workers increases throughput linearly

### 2. ACID Compliance
All operations maintain database consistency:
- **Atomicity** - task creation, updates, and execution are all-or-nothing
- **Consistency** - foreign keys and constraints enforce data integrity
- **Isolation** - concurrent operations don't interfere with each other
- **Durability** - committed work survives system failures

### 3. Temporal Precision
Schedule handling accounts for real-world complexity:
- **Timezone awareness** - all timestamps stored with timezone info
- **DST transitions** - schedule calculations handle time zone changes
- **RRULE processing** - RFC-5545 compliant recurring schedule support
- **Schedule conflicts** - detection and resolution of overlapping executions

### 4. Observability First
Complete audit trails and monitoring support:
- **Immutable logs** - all operations recorded for debugging
- **Performance metrics** - execution times and resource usage tracked
- **Error tracking** - failures captured with full context
- **State transitions** - every status change logged with timestamps

## Database Schema Overview

### Core Entity Relationships

```
Agent (1) ──→ (N) Task ──→ (N) TaskRun ──→ (N) PipelineStep
   │                │           │              │
   │                │           └──→ (N) RunEvent
   │                └──→ (1) Schedule
   └──→ (N) AgentScope ──→ (N) ToolPermission
```

### Table Categories

**Agent Management:**
- `agent` - AI agents and their authentication
- `agent_scope` - Agent permissions and tool access
- `tool_catalog` - Available tools and their schemas

**Task Scheduling:**
- `task` - Scheduled work definitions
- `schedule` - Timing rules (cron, RRULE, one-time)
- `due_work` - Work items ready for execution (SKIP LOCKED queue)

**Execution Tracking:**
- `task_run` - Individual execution instances
- `pipeline_step` - Step-by-step execution results
- `run_event` - Detailed execution audit log

**System Operations:**
- `migration_version` - Schema version tracking
- `system_config` - Runtime configuration parameters

## Migration Patterns & Best Practices

### Migration File Structure
```
migrations/
├── CLAUDE.md                    # This documentation
├── version_0001_initial.sql     # Initial schema creation
├── version_0002_indexes.sql     # Performance indexes
├── version_0003_partitions.sql  # Table partitioning
└── version_NNNN_feature.sql     # Future schema changes
```

### Version Control Strategy

**Sequential Numbering:**
- Migrations numbered sequentially: `version_0001`, `version_0002`, etc.
- Each migration includes both **UP** and **DOWN** scripts
- Version tracking in `migration_version` table

**Atomic Migrations:**
```sql
-- Every migration wrapped in transaction
BEGIN;

-- Schema changes here
CREATE TABLE new_feature (...);

-- Update version tracking
INSERT INTO migration_version (version, applied_at, description)
VALUES ('0001', NOW(), 'Initial schema with SKIP LOCKED patterns');

COMMIT;
```

**Backward Compatibility:**
- Column additions are safe (existing code continues working)
- Column removals require deprecation period
- Index changes applied without blocking operations
- Data migrations use batched updates to avoid locks

### Safe Schema Evolution

**Adding New Tables:**
```sql
-- Safe: New tables don't break existing code
CREATE TABLE new_feature (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Adding Columns:**
```sql
-- Safe: New nullable columns with defaults
ALTER TABLE task ADD COLUMN priority INTEGER DEFAULT 5;
```

**Removing Columns (Two-Phase):**
```sql
-- Phase 1: Mark as deprecated (deploy code that doesn't use column)
ALTER TABLE task ALTER COLUMN old_column SET DEFAULT NULL;

-- Phase 2: Drop column (after confirming no usage)
ALTER TABLE task DROP COLUMN old_column;
```

**Index Management:**
```sql
-- Safe: Create indexes concurrently to avoid blocking
CREATE INDEX CONCURRENTLY idx_task_run_status 
ON task_run (status, started_at) 
WHERE status IN ('running', 'failed');

-- Safe: Drop unused indexes
DROP INDEX IF EXISTS old_index_name;
```

## SKIP LOCKED Implementation Patterns

### Core Work Queue Pattern

The `due_work` table implements the canonical PostgreSQL work queue:

```sql
-- Worker claims work safely
SELECT id, task_id, payload, priority
FROM due_work 
WHERE run_at <= NOW()
  AND (locked_until IS NULL OR locked_until < NOW())
  AND (agent_scope IS NULL OR agent_scope = $1)
ORDER BY priority DESC, run_at ASC
FOR UPDATE SKIP LOCKED
LIMIT 1;

-- Claim the work item
UPDATE due_work 
SET locked_until = NOW() + INTERVAL '5 minutes',
    locked_by = $worker_id,
    started_at = NOW()
WHERE id = $work_id;
```

### Why SKIP LOCKED Works

**Traditional Locking Problems:**
```sql
-- BAD: This causes deadlocks under load
SELECT * FROM work_queue WHERE status = 'ready' FOR UPDATE;
-- Multiple workers block waiting for same rows
```

**SKIP LOCKED Solution:**
```sql
-- GOOD: Workers never block, get different rows
SELECT * FROM work_queue 
WHERE status = 'ready' 
FOR UPDATE SKIP LOCKED 
LIMIT 1;
-- Each worker gets a different row immediately
```

**Guarantees:**
- **No blocking** - workers never wait for locks
- **No deadlocks** - no circular lock dependencies
- **Fair distribution** - work spread across workers
- **Immediate feedback** - workers know instantly if no work available

### Advanced SKIP LOCKED Patterns

**Priority-Based Work Distribution:**
```sql
-- High priority work processed first
SELECT id, priority, payload
FROM due_work 
WHERE run_at <= NOW()
  AND (locked_until IS NULL OR locked_until < NOW())
ORDER BY priority DESC, run_at ASC  -- Priority first, then FIFO
FOR UPDATE SKIP LOCKED
LIMIT $batch_size;
```

**Agent-Scoped Work Queues:**
```sql
-- Workers only claim work they're authorized for
SELECT dw.id, dw.task_id, dw.payload
FROM due_work dw
JOIN task t ON dw.task_id = t.id  
WHERE dw.run_at <= NOW()
  AND (dw.locked_until IS NULL OR dw.locked_until < NOW())
  AND t.agent_id IN (
    SELECT agent_id FROM agent_scope 
    WHERE scope_name = ANY($worker_scopes)
  )
FOR UPDATE SKIP LOCKED
LIMIT 1;
```

**Batched Work Processing:**
```sql
-- Process multiple items per worker transaction
WITH claimed_work AS (
  SELECT id, task_id, payload
  FROM due_work
  WHERE run_at <= NOW()
    AND (locked_until IS NULL OR locked_until < NOW())
  ORDER BY priority DESC, run_at ASC
  FOR UPDATE SKIP LOCKED
  LIMIT $batch_size
)
UPDATE due_work 
SET locked_until = NOW() + INTERVAL '5 minutes',
    locked_by = $worker_id
FROM claimed_work
WHERE due_work.id = claimed_work.id
RETURNING due_work.id, claimed_work.payload;
```

## Performance Optimization Strategies

### Strategic Indexing

**Time-Based Queries:**
```sql
-- Critical for scheduler queries
CREATE INDEX idx_due_work_ready ON due_work (run_at, priority) 
WHERE locked_until IS NULL OR locked_until < NOW();

-- Task execution history
CREATE INDEX idx_task_run_timeline ON task_run (task_id, started_at DESC);

-- Agent activity tracking  
CREATE INDEX idx_run_event_agent_time ON run_event (agent_id, created_at DESC);
```

**Partial Indexes for Common Filters:**
```sql
-- Only index active tasks (saves space)
CREATE INDEX idx_task_active ON task (next_run_at, priority)
WHERE status = 'active';

-- Only index recent failures (for monitoring)
CREATE INDEX idx_task_run_recent_failures ON task_run (finished_at DESC)
WHERE success = FALSE AND finished_at > NOW() - INTERVAL '7 days';
```

**Compound Indexes for Complex Queries:**
```sql
-- Agent authorization lookup
CREATE INDEX idx_agent_scope_lookup ON agent_scope (agent_id, scope_name, expires_at);

-- Pipeline step analysis
CREATE INDEX idx_pipeline_step_analysis ON pipeline_step 
(run_id, step_index, success, duration_ms);
```

### Table Partitioning Strategy

**Time-Based Partitioning:**
```sql
-- Partition run events by month for better query performance
CREATE TABLE run_event (
    id UUID DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    -- other columns...
) PARTITION BY RANGE (created_at);

-- Create monthly partitions
CREATE TABLE run_event_2025_01 PARTITION OF run_event
FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');

CREATE TABLE run_event_2025_02 PARTITION OF run_event  
FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');
```

**Benefits:**
- **Query performance** - queries only scan relevant partitions
- **Maintenance efficiency** - can drop old partitions instead of DELETE
- **Concurrent operations** - operations on different partitions don't block
- **Storage optimization** - old partitions can use different storage tiers

### Query Optimization Guidelines

**Efficient Work Queue Queries:**
```sql
-- GOOD: Uses index effectively
SELECT id FROM due_work 
WHERE run_at <= NOW() AND locked_until IS NULL
ORDER BY priority DESC, run_at ASC
FOR UPDATE SKIP LOCKED LIMIT 1;

-- BAD: Scans too many rows
SELECT id FROM due_work 
WHERE run_at <= NOW() + INTERVAL '1 hour'  -- Too broad
ORDER BY created_at  -- Wrong sort order
FOR UPDATE SKIP LOCKED LIMIT 1;
```

**Efficient Status Queries:**
```sql
-- GOOD: Uses partial index
SELECT COUNT(*) FROM task WHERE status = 'active';

-- BAD: Scans entire table
SELECT COUNT(*) FROM task WHERE status != 'deleted';
```

## Data Integrity & Constraints

### Foreign Key Relationships
```sql
-- Ensure referential integrity
ALTER TABLE task ADD CONSTRAINT fk_task_agent 
FOREIGN KEY (agent_id) REFERENCES agent(id) ON DELETE CASCADE;

ALTER TABLE task_run ADD CONSTRAINT fk_task_run_task
FOREIGN KEY (task_id) REFERENCES task(id) ON DELETE CASCADE;

ALTER TABLE pipeline_step ADD CONSTRAINT fk_pipeline_step_run
FOREIGN KEY (run_id) REFERENCES task_run(id) ON DELETE CASCADE;
```

### Business Logic Constraints
```sql
-- Ensure valid status transitions
ALTER TABLE task_run ADD CONSTRAINT chk_valid_status
CHECK (status IN ('pending', 'running', 'success', 'failed', 'timeout'));

-- Ensure positive durations
ALTER TABLE pipeline_step ADD CONSTRAINT chk_positive_duration
CHECK (duration_ms >= 0);

-- Ensure valid schedule expressions
ALTER TABLE task ADD CONSTRAINT chk_schedule_kind
CHECK (schedule_kind IN ('cron', 'rrule', 'once', 'event'));
```

### Data Validation Triggers
```sql
-- Validate RRULE expressions before storage
CREATE OR REPLACE FUNCTION validate_rrule_expression()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.schedule_kind = 'rrule' THEN
        -- Validate RRULE syntax (implementation in Python)
        PERFORM validate_rrule_syntax(NEW.schedule_expr);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_validate_schedule
BEFORE INSERT OR UPDATE ON task
FOR EACH ROW EXECUTE FUNCTION validate_rrule_expression();
```

## Monitoring & Observability

### Key Metrics Tables

**Performance Tracking:**
```sql
-- Worker performance metrics
CREATE VIEW worker_performance AS
SELECT 
    locked_by as worker_id,
    COUNT(*) as jobs_processed,
    AVG(EXTRACT(EPOCH FROM (finished_at - started_at))) as avg_duration,
    MAX(EXTRACT(EPOCH FROM (finished_at - started_at))) as max_duration
FROM task_run 
WHERE finished_at > NOW() - INTERVAL '1 hour'
  AND locked_by IS NOT NULL
GROUP BY locked_by;

-- Queue depth monitoring
CREATE VIEW queue_health AS
SELECT 
    COUNT(*) FILTER (WHERE run_at <= NOW()) as ready_count,
    COUNT(*) FILTER (WHERE locked_until > NOW()) as locked_count,
    COUNT(*) FILTER (WHERE run_at > NOW()) as scheduled_count,
    AVG(EXTRACT(EPOCH FROM (NOW() - run_at))) FILTER (WHERE run_at <= NOW()) as avg_age_seconds
FROM due_work;
```

**Error Analysis:**
```sql
-- Task failure rates
CREATE VIEW task_failure_rates AS
SELECT 
    t.title,
    COUNT(*) as total_runs,
    COUNT(*) FILTER (WHERE tr.success = FALSE) as failures,
    ROUND(COUNT(*) FILTER (WHERE tr.success = FALSE) * 100.0 / COUNT(*), 2) as failure_rate
FROM task t
JOIN task_run tr ON t.id = tr.task_id
WHERE tr.finished_at > NOW() - INTERVAL '24 hours'
GROUP BY t.id, t.title
HAVING COUNT(*) > 1
ORDER BY failure_rate DESC;
```

### Audit Trail Implementation

**Immutable Event Log:**
```sql
-- All operations logged immutably
CREATE TABLE run_event (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES task_run(id),
    event_type VARCHAR(50) NOT NULL,
    step_index INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    data JSONB,
    
    -- Immutability constraints
    CONSTRAINT chk_immutable_timestamp CHECK (created_at <= NOW())
);

-- Prevent updates/deletes on audit log
CREATE RULE no_update_run_event AS ON UPDATE TO run_event DO INSTEAD NOTHING;
CREATE RULE no_delete_run_event AS ON DELETE TO run_event DO INSTEAD NOTHING;
```

## Common Anti-Patterns to Avoid

### 1. Polling Instead of SKIP LOCKED
```sql
-- BAD: Wastes resources, prone to race conditions
while True:
    work = SELECT * FROM due_work WHERE status = 'ready' LIMIT 1;
    if work:
        UPDATE due_work SET status = 'processing' WHERE id = work.id;
        process(work);
    time.sleep(1);  -- Wastes CPU

-- GOOD: Efficient, safe, immediate response
work = SELECT * FROM due_work 
       WHERE run_at <= NOW() 
       FOR UPDATE SKIP LOCKED LIMIT 1;
```

### 2. Application-Level Locking
```sql
-- BAD: Race conditions, doesn't survive crashes
app_locks = {}  # In-memory locks
if work_id not in app_locks:
    app_locks[work_id] = True
    process(work_id)

-- GOOD: Database-level atomicity
SELECT * FROM due_work FOR UPDATE SKIP LOCKED;
```

### 3. Unbounded Queries
```sql
-- BAD: Can scan millions of rows
SELECT * FROM task_run ORDER BY started_at DESC;

-- GOOD: Bounded queries with indexes
SELECT * FROM task_run 
WHERE started_at > NOW() - INTERVAL '24 hours'
ORDER BY started_at DESC 
LIMIT 100;
```

### 4. Missing Cleanup Procedures
```sql
-- BAD: Stale locks accumulate over time
-- No cleanup of expired locks

-- GOOD: Regular cleanup procedures
DELETE FROM due_work 
WHERE locked_until < NOW() - INTERVAL '1 hour'
  AND status = 'processing';
```

## Deployment & Operations

### Database Setup
```bash
# Initialize database
createdb orchestrator_prod

# Run migrations in order
psql orchestrator_prod -f migrations/version_0001_initial.sql
psql orchestrator_prod -f migrations/version_0002_indexes.sql
psql orchestrator_prod -f migrations/version_0003_partitions.sql
```

### Backup Strategy
```bash
# Daily schema backup
pg_dump --schema-only orchestrator_prod > schema_backup_$(date +%Y%m%d).sql

# Incremental WAL archiving for point-in-time recovery
archive_command = 'cp %p /backups/wal/%f'
```

### Performance Monitoring
```bash
# Check index usage
SELECT schemaname, tablename, attname, n_distinct, correlation
FROM pg_stats 
WHERE tablename IN ('due_work', 'task_run', 'pipeline_step');

# Monitor query performance
SELECT query, calls, total_time, mean_time 
FROM pg_stat_statements 
ORDER BY total_time DESC LIMIT 10;
```

## Migration Development Workflow

### 1. Design Phase
- Analyze requirements and data access patterns
- Design schema changes with performance implications
- Consider backward compatibility and rollback scenarios
- Document migration rationale and expected impact

### 2. Implementation Phase
```sql
-- Template for new migration
-- migrations/version_NNNN_feature_name.sql

BEGIN;

-- Schema changes
CREATE TABLE new_feature (...);
CREATE INDEX CONCURRENTLY ...;

-- Data migration (if needed)
INSERT INTO new_table SELECT ... FROM old_table;

-- Update version
INSERT INTO migration_version (version, applied_at, description)
VALUES ('NNNN', NOW(), 'Brief description of changes');

COMMIT;
```

### 3. Testing Phase
- Test migration on copy of production data
- Verify performance impact with realistic workload
- Test rollback procedures
- Validate application compatibility

### 4. Deployment Phase
- Schedule migration during low-traffic window
- Monitor system performance during and after migration
- Have rollback plan ready
- Update documentation and runbooks

## Troubleshooting Guide

### Common Issues

**SKIP LOCKED Not Working:**
- Check transaction isolation level (READ COMMITTED required)
- Verify FOR UPDATE SKIP LOCKED syntax
- Ensure proper ordering (priority, then timestamp)
- Check for blocking long-running transactions

**Poor Query Performance:**
- Analyze query plans with EXPLAIN ANALYZE
- Check if indexes are being used
- Look for table scans on large tables
- Consider query rewriting or additional indexes

**Lock Contention:**
- Identify blocking queries with pg_stat_activity
- Check for long-running transactions
- Look for inappropriate lock levels
- Consider breaking large operations into smaller chunks

**Data Inconsistency:**
- Verify foreign key constraints are in place
- Check for application bugs bypassing constraints
- Look for incomplete transactions
- Validate data with consistency checks

### Diagnostic Queries

**Check Work Queue Health:**
```sql
SELECT 
    COUNT(*) as total_items,
    COUNT(*) FILTER (WHERE run_at <= NOW()) as ready_now,
    COUNT(*) FILTER (WHERE locked_until > NOW()) as currently_locked,
    MAX(run_at) as latest_scheduled
FROM due_work;
```

**Identify Blocking Locks:**
```sql
SELECT 
    blocked_locks.pid AS blocked_pid,
    blocked_activity.usename AS blocked_user,
    blocking_locks.pid AS blocking_pid,
    blocking_activity.usename AS blocking_user,
    blocked_activity.query AS blocked_statement,
    blocking_activity.query AS current_statement_in_blocking_process
FROM pg_catalog.pg_locks blocked_locks
JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
JOIN pg_catalog.pg_locks blocking_locks ON blocking_locks.locktype = blocked_locks.locktype
JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
WHERE NOT blocked_locks.granted;
```

**Monitor Index Usage:**
```sql
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY idx_tup_read DESC;
```

This migrations directory provides the foundation for a robust, scalable, and maintainable database backend that supports the Personal Agent Orchestrator's mission of coordinated AI agent management with bulletproof reliability.