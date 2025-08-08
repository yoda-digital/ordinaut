# Ordinaut - Troubleshooting Guide

Comprehensive troubleshooting guide for diagnosing and resolving common issues with the Ordinaut system.

## Diagnostic Checklist

When experiencing issues, work through this systematic checklist:

### 1. System Health Check

**Verify Overall System Status:**
```bash
# Check API health endpoint
curl -s http://localhost:8080/health | jq

# Expected response:
{
  "status": "healthy",
  "checks": [
    {"name": "database", "status": "healthy"},
    {"name": "redis", "status": "healthy"}, 
    {"name": "scheduler", "status": "healthy"},
    {"name": "workers", "status": "healthy"}
  ]
}
```

**Check Service Status:**
```bash
# Docker Compose services
docker compose ps

# Expected: all services "Up" and "healthy"
NAME               IMAGE              STATUS
postgres           postgres:16.4      Up (healthy)
redis              redis:7.2.5        Up (healthy)  
api                yoda-tasker-api    Up (healthy)
scheduler          yoda-tasker-scheduler  Up
worker             yoda-tasker-worker     Up (2 replicas)
```

### 2. Service-Specific Health Checks

**Database Health:**
```bash
# Direct PostgreSQL connection test
docker compose exec postgres pg_isready -U orchestrator -d orchestrator

# Check connection pool from API
curl -s http://localhost:8080/health | jq '.checks[] | select(.name=="database")'
```

**Redis Health:**
```bash
# Direct Redis connection test  
docker compose exec redis redis-cli ping
# Expected: PONG

# Check Redis from API
curl -s http://localhost:8080/health | jq '.checks[] | select(.name=="redis")'
```

**Worker Health:**
```bash
# Check worker activity
docker compose logs worker --tail 50

# Look for heartbeat messages:
# "Worker worker-abc123 heartbeat: processed 45 tasks, queue_depth=2"
```

### 3. Quick System Recovery

**Restart All Services:**
```bash
cd ops/
docker compose restart

# Wait for health checks
sleep 30
curl -s http://localhost:8080/health/ready
```

**Clean Restart (Nuclear Option):**
```bash
# WARNING: Removes all data
docker compose down -v
docker system prune -f
./start.sh dev --clean --build
```

## Common Problems and Solutions

### Task Scheduling Issues

#### Problem: Tasks Created But Not Executing

**Symptom:** Tasks show `status: "active"` but no execution history

**Diagnostic Steps:**

1. **Check Task Status:**
```bash
# Get task details
curl -H "Authorization: Bearer agent-uuid" \
     "http://localhost:8080/tasks/task-id" | jq

# Look for:
# - status: "paused" → Resume with POST /tasks/{id}/resume
# - next_run: null → Schedule expression may be invalid
```

2. **Validate Schedule Expression:**
```bash
# For cron schedules - test with online cron validator
echo "0 8 * * 1-5" | # Should be valid weekdays 8 AM

# Check recent scheduler logs
docker compose logs scheduler --tail 100 | grep -i error
```

3. **Check Due Work Queue:**
```sql
-- Connect to database
docker compose exec postgres psql -U orchestrator orchestrator

-- Check queue depth
SELECT COUNT(*) as pending_work FROM due_work WHERE run_at <= now();

-- Check specific task's work items
SELECT * FROM due_work 
WHERE task_id = 'your-task-id' 
ORDER BY run_at DESC LIMIT 5;
```

**Solutions:**

- **Schedule Issues:** Fix cron expression or RRULE syntax
- **Paused Tasks:** Resume with `POST /tasks/{id}/resume`
- **Worker Issues:** Check worker logs and restart workers
- **Queue Backlog:** Scale workers with `docker compose up -d --scale worker=4`

#### Problem: RRULE Schedule Not Working

**Symptom:** RRULE-based tasks not triggering at expected times

**Diagnostic:**
```bash
# Check RRULE syntax with Python validation
python3 -c "
from dateutil.rrule import rrulestr
from datetime import datetime
import pytz

tz = pytz.timezone('Europe/Chisinau')
rule = rrulestr('FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=30')
next_run = rule.after(datetime.now(tz))
print(f'Next run: {next_run}')
"
```

**Solutions:**
- Verify RRULE syntax with [iCalendar validators](https://icalendar.org/validator.html)
- Check timezone is valid: `timedatectl list-timezones | grep Chisinau`
- Ensure scheduler service has correct `TZ` environment variable

#### Problem: Tasks Executing Multiple Times

**Symptom:** Duplicate executions for the same scheduled time

**Diagnostic:**
```sql
-- Check for duplicate due_work entries
SELECT task_id, run_at, COUNT(*) 
FROM due_work 
GROUP BY task_id, run_at 
HAVING COUNT(*) > 1;

-- Check task_run history for duplicates
SELECT task_id, started_at, COUNT(*) 
FROM task_run 
WHERE started_at > now() - INTERVAL '1 hour'
GROUP BY task_id, started_at 
HAVING COUNT(*) > 1;
```

**Solutions:**
- Restart scheduler service to reset state
- Check for multiple scheduler instances (should only be 1)
- Verify unique constraints in database schema

### Pipeline Execution Failures

#### Problem: Pipeline Steps Failing

**Symptom:** Tasks fail with step-specific error messages

**Diagnostic Steps:**

1. **Get Detailed Execution Logs:**
```bash
# Get failed run details
curl -H "Authorization: Bearer agent-uuid" \
     "http://localhost:8080/runs/run-id" | jq '.error'

# Check worker logs for this execution
docker compose logs worker | grep "run-id"
```

2. **Common Pipeline Issues:**

| Error Pattern | Cause | Solution |
|---------------|-------|----------|
| `Tool 'tool-name' not found` | Tool not in registry | Check `catalogs/tools.json` |
| `Template variable '${steps.missing}' undefined` | Typo in step name | Check pipeline step names |
| `JSON Schema validation failed` | Invalid tool input | Check tool documentation |
| `Timeout after 30s` | Slow external service | Increase `timeout_seconds` |
| `Connection refused` | External service down | Check service availability |

3. **Test Individual Steps:**
```bash
# Test template rendering
python3 -c "
from engine.template import render_templates
result = render_templates({'message': 'Weather is \${steps.weather.temp}'}, {
    'steps': {'weather': {'temp': '15°C'}}
})
print(result)
"
```

**Solutions:**

- **Tool Issues:** Update tool catalog or fix tool addresses
- **Template Issues:** Verify variable names and step outputs
- **Timeout Issues:** Increase timeout or optimize tool calls
- **Network Issues:** Check external service connectivity

#### Problem: Template Variable Resolution Errors

**Symptom:** `${steps.x.y}` variables not resolving correctly

**Diagnostic:**
```python
# Test template rendering manually
from engine.template import render_templates
import json

context = {
    "now": "2025-01-11T10:00:00Z",
    "params": {"user_id": 12345},
    "steps": {
        "weather": {"summary": "Sunny", "temp": 20},
        "calendar": {"events": [{"title": "Meeting", "time": "14:00"}]}
    }
}

template = {
    "message": "Weather: ${steps.weather.summary} (${steps.weather.temp}°C)",
    "event_count": "${length(steps.calendar.events)}"
}

result = render_templates(template, context)
print(json.dumps(result, indent=2))
```

**Common Template Issues:**
- **Incorrect Path:** `${steps.wether.temp}` (typo) → `${steps.weather.temp}`
- **Missing Step:** `${steps.missing.field}` → Check if step executed successfully  
- **Wrong Syntax:** `$steps.weather.temp` → `${steps.weather.temp}`
- **Complex Expressions:** Use JMESPath for complex data access

### Worker and Concurrency Issues

#### Problem: Workers Not Processing Jobs

**Symptom:** Queue depth increasing, workers idle

**Diagnostic:**
```bash
# Check worker status
docker compose logs worker --tail 100

# Look for:
# - "Leased work item: {...}" (worker is active)
# - "No work available" (normal when queue empty)
# - Connection errors or exceptions

# Check worker heartbeats
curl -s http://localhost:8080/health | jq '.checks[] | select(.name=="workers")'
```

**Database Query to Check Locks:**
```sql
-- Check for stuck locks
SELECT id, task_id, locked_until, locked_by
FROM due_work 
WHERE locked_until > now() 
ORDER BY locked_until;

-- Check worker heartbeats
SELECT worker_id, last_seen, processed_count 
FROM worker_heartbeat 
WHERE last_seen > now() - INTERVAL '2 minutes'
ORDER BY last_seen DESC;
```

**Solutions:**

- **Stuck Locks:** Clear expired locks manually or restart workers
- **Worker Crashes:** Check logs and restart: `docker compose restart worker`
- **Database Issues:** Check connection pool settings and restart database
- **Scale Workers:** Increase replicas: `docker compose up -d --scale worker=4`

#### Problem: High Queue Depth / Processing Lag

**Symptom:** Many pending jobs, slow processing

**Diagnostic:**
```sql
-- Check queue depth and age
SELECT 
  COUNT(*) as pending_jobs,
  MIN(run_at) as oldest_job,
  MAX(run_at) as newest_job,
  AVG(EXTRACT(EPOCH FROM (now() - run_at))) as avg_lag_seconds
FROM due_work 
WHERE run_at <= now();

-- Check processing rate
SELECT 
  DATE_TRUNC('minute', finished_at) as minute,
  COUNT(*) as completed_tasks
FROM task_run 
WHERE finished_at > now() - INTERVAL '1 hour'
GROUP BY DATE_TRUNC('minute', finished_at)
ORDER BY minute DESC;
```

**Performance Solutions:**

1. **Scale Workers:**
```bash
# Increase worker replicas
docker compose up -d --scale worker=6

# Monitor improvement
watch -n 5 'curl -s http://localhost:8080/health | jq .checks'
```

2. **Optimize Database:**
```sql
-- Check slow queries
SELECT query, mean_time, calls 
FROM pg_stat_statements 
ORDER BY mean_time DESC LIMIT 10;

-- Update table statistics
ANALYZE due_work;
ANALYZE task_run;
```

3. **Resource Allocation:**
```yaml
# In docker-compose.prod.yml - increase resources
worker:
  deploy:
    resources:
      limits:
        cpus: '2.0'
        memory: 2G
    replicas: 4
```

### Database Connection Issues

#### Problem: Database Connection Failures

**Symptom:** API returns 500 errors, "database unhealthy" in health checks

**Diagnostic:**
```bash
# Check PostgreSQL logs
docker compose logs postgres --tail 100

# Test direct connection
docker compose exec postgres psql -U orchestrator orchestrator -c "SELECT 1;"

# Check connection pool status
curl -s http://localhost:8080/health | jq '.checks[] | select(.name=="database").details'
```

**Common Connection Issues:**

1. **Connection Pool Exhaustion:**
```python
# Check pool settings in api/dependencies.py
engine = create_engine(
    DATABASE_URL, 
    pool_size=20,          # Increase if needed
    max_overflow=30,       # Increase if needed  
    pool_pre_ping=True,    # Must be True
    pool_recycle=3600      # Prevent stale connections
)
```

2. **PostgreSQL Configuration:**
```sql
-- Check connection limits
SHOW max_connections;  -- Should be > pool_size * num_services

-- Check active connections
SELECT count(*) FROM pg_stat_activity;
```

**Solutions:**

- **Pool Issues:** Increase pool size in configuration
- **Connection Limits:** Increase PostgreSQL `max_connections`  
- **Network Issues:** Check Docker network connectivity
- **Restart Database:** `docker compose restart postgres`

### Redis and Event Issues

#### Problem: Events Not Processing

**Symptom:** Events published but event-based tasks not triggering

**Diagnostic:**
```bash
# Check Redis connection
docker compose exec redis redis-cli ping

# Check event stream
docker compose exec redis redis-cli XLEN events

# Check for recent events
docker compose exec redis redis-cli XRANGE events - + COUNT 10
```

**Redis Stream Debug:**
```bash
# Check consumer groups
docker compose exec redis redis-cli XINFO GROUPS events

# Check consumer lag
docker compose exec redis redis-cli XPENDING events orchestrator-workers
```

**Solutions:**

- **Redis Down:** Restart Redis: `docker compose restart redis`
- **Stream Issues:** Reset consumer group or recreate stream
- **Event Processing:** Check event-type matching in task definitions

### Performance and Resource Issues

#### Problem: High CPU/Memory Usage

**Diagnostic:**
```bash
# Check resource usage
docker stats

# Check system load
docker compose exec api top

# Check memory usage patterns
docker compose logs api | grep -i "memory\|oom"
```

**Memory Optimization:**
```yaml
# Adjust resource limits
services:
  api:
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 1G
```

**CPU Optimization:**
```python
# Reduce worker threads if CPU-bound
UVICORN_WORKERS=2  # Instead of 4
WORKER_POLL_INTERVAL=1.0  # Instead of 0.5
```

#### Problem: Slow API Responses

**Diagnostic:**
```bash
# Test API response times
time curl -s http://localhost:8080/health

# Check slow queries
docker compose exec postgres psql -U orchestrator orchestrator -c "
SELECT query, mean_time, calls 
FROM pg_stat_statements 
WHERE mean_time > 1000 
ORDER BY mean_time DESC;"
```

**Performance Solutions:**

- **Database Indexes:** Ensure proper indexes for common queries
- **Connection Pooling:** Optimize pool settings
- **Query Optimization:** Analyze and optimize slow queries
- **Caching:** Add Redis caching for frequent operations

## Advanced Diagnostics

### Enable Debug Logging

**Temporary Debug Mode:**
```bash
# Set debug environment variables
export LOG_LEVEL=debug
export DEBUG=true

# Restart services with debug logging
docker compose restart api scheduler worker
```

**Persistent Debug Configuration:**
```yaml
# In docker-compose.dev.yml
environment:
  LOG_LEVEL: debug
  DEBUG: "true"
  SQLALCHEMY_ECHO: "true"  # Log all SQL queries
```

### Database Query Analysis

**Check Critical Indexes:**
```sql
-- Ensure indexes exist for worker queries
\d+ due_work

-- Should include:
-- idx_due_work_ready ON (run_at, locked_until) WHERE locked_until IS NULL
-- idx_due_work_run_at ON (run_at)

-- Check index usage
SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read 
FROM pg_stat_user_indexes 
WHERE tablename = 'due_work';
```

**Monitor Lock Contention:**
```sql
-- Check for blocking locks
SELECT 
  blocked_locks.pid AS blocked_pid,
  blocked_activity.usename AS blocked_user,
  blocking_locks.pid AS blocking_pid,
  blocking_activity.usename AS blocking_user,
  blocked_activity.query AS blocked_statement
FROM pg_catalog.pg_locks blocked_locks
JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
JOIN pg_catalog.pg_locks blocking_locks ON blocking_locks.locktype = blocked_locks.locktype
JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
WHERE NOT blocked_locks.granted;
```

### System Monitoring Commands

**Real-time System Status:**
```bash
# Watch system health
watch -n 5 'curl -s http://localhost:8080/health | jq'

# Monitor queue depth  
watch -n 2 'docker compose exec postgres psql -U orchestrator orchestrator -c "SELECT COUNT(*) FROM due_work;"'

# Monitor worker activity
docker compose logs worker -f | grep -E "(Leased work|Task completed|heartbeat)"
```

**Performance Benchmarking:**
```bash
# API response time test
for i in {1..10}; do
  time curl -s http://localhost:8080/health > /dev/null
done

# Database performance test
docker compose exec postgres pgbench -U orchestrator -T 30 orchestrator
```

## Recovery Procedures

### Partial System Recovery

**API Service Recovery:**
```bash
# Restart API only
docker compose restart api

# Verify health
curl -s http://localhost:8080/health/ready
```

**Worker Recovery:**
```bash
# Clear stuck locks (if needed)
docker compose exec postgres psql -U orchestrator orchestrator -c "
UPDATE due_work 
SET locked_until = NULL, locked_by = NULL 
WHERE locked_until < now() - INTERVAL '5 minutes';"

# Restart workers
docker compose restart worker
```

### Full System Recovery

**Complete System Reset:**
```bash
# Stop all services
docker compose down

# Clean up resources (optional)
docker system prune -f
docker volume prune -f

# Restart system
./start.sh dev --build

# Verify all services healthy
docker compose ps
curl -s http://localhost:8080/health
```

## Getting Help

### Information to Collect for Support

When reporting issues, include:

1. **System Status:**
```bash
# Health check output
curl -s http://localhost:8080/health | jq > health_report.json

# Service status
docker compose ps > service_status.txt

# Recent logs
docker compose logs --tail 200 > system_logs.txt
```

2. **Error Details:**
- Complete error messages and stack traces
- Request/response examples that fail
- Timeline of when issues started
- Steps to reproduce the problem

3. **Environment Information:**
- Operating system and Docker version
- Resource allocation (CPU, RAM, disk)
- Network configuration
- Recent changes or deployments

### Self-Service Resources

- **Health Monitoring:** `http://localhost:8080/health`
- **API Documentation:** `http://localhost:8080/docs`
- **Prometheus Metrics:** `http://localhost:8080/metrics`
- **Database Schema:** `migrations/version_0001.sql`
- **Configuration:** `ops/docker-compose.yml`

### Emergency Contacts

- **System Status Page:** Monitor for known issues
- **Documentation:** Check latest troubleshooting updates
- **Community Forum:** Search for similar issues
- **Support Channel:** Include diagnostic output from above

Remember: Most issues can be resolved by restarting services, checking logs, and verifying configuration. Start with the diagnostic checklist and work through solutions systematically.