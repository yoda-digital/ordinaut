# Monitoring Playbook
## Ordinaut Alert Response Guide

### Alert Classification System
- **Severity 0**: System down, data loss risk
- **Severity 1**: Performance degraded, user impact  
- **Severity 2**: Warning conditions, trending issues
- **Severity 3**: Informational, maintenance reminders

---

## 1. CRITICAL ALERTS (SEVERITY 0) - IMMEDIATE RESPONSE

### OrchestratorAPIDown
**Trigger**: HTTP health check fails for >2 minutes  
**Impact**: Complete service unavailability  
**Response Time**: 5 minutes

#### Immediate Actions
```bash
# 1. Quick status assessment
curl -I http://localhost:8080/health || echo "API completely down"
docker ps | grep api

# 2. Check container status and logs
docker logs api --tail 50 | grep -E "(ERROR|FATAL|CRITICAL)"

# 3. Verify dependencies
docker exec postgres pg_isready -U orchestrator
docker exec redis redis-cli ping

# 4. Check resource constraints
docker stats api --no-stream
df -h
free -h
```

#### Common Causes & Resolutions
| Cause | Diagnostic | Resolution |
|-------|------------|------------|
| Container crashed | `docker ps` shows exited | `docker-compose restart api` |
| Database connection lost | Logs show DB errors | Check PostgreSQL, restart API |
| Out of memory | High memory usage | Scale up or restart container |
| Port conflict | Port binding errors | Check for conflicting processes |
| Configuration error | Startup errors in logs | Review environment variables |

#### Escalation Criteria
- Resolution not achieved within 15 minutes
- Multiple service failures detected
- Data integrity concerns identified

---

### OrchestratorDatabaseDown  
**Trigger**: PostgreSQL connection failures for >1 minute  
**Impact**: Complete system failure, possible data loss  
**Response Time**: 2 minutes

#### Immediate Actions
```bash
# 1. Database connectivity test
docker exec postgres pg_isready -U orchestrator

# 2. Check container status
docker ps | grep postgres
docker logs postgres --tail 30

# 3. Verify data integrity
docker exec postgres psql -U orchestrator -c "SELECT version();"

# 4. Check disk space and resources
df -h /var/lib/docker/volumes/
docker stats postgres --no-stream
```

#### Resolution Steps
```bash
# Step 1: Attempt soft restart
docker-compose -f ops/docker-compose.yml restart postgres

# Step 2: If restart fails, check for corruption  
docker logs postgres | grep -E "(PANIC|FATAL|corruption)"

# Step 3: Emergency backup if data accessible
docker exec postgres pg_dump -U orchestrator orchestrator > emergency_$(date +%Y%m%d_%H%M%S).sql

# Step 4: If corruption detected, initiate disaster recovery
# See ops/DISASTER_RECOVERY.md for complete procedures
```

#### Data Protection Protocol
```bash
# Before any destructive actions:
# 1. Stop all writes
docker-compose -f ops/docker-compose.yml stop api scheduler worker

# 2. Attempt data extraction
docker exec postgres pg_dumpall -U orchestrator > full_backup_$(date +%Y%m%d_%H%M%S).sql

# 3. Verify backup integrity
head -50 full_backup_$(date +%Y%m%d_%H%M%S).sql
tail -50 full_backup_$(date +%Y%m%d_%H%M%S).sql
```

---

### NoActiveWorkers
**Trigger**: No worker heartbeats for >3 minutes  
**Impact**: Task processing completely stopped  
**Response Time**: 5 minutes

#### Diagnostic Commands
```bash
# 1. Check worker container status
docker ps | grep worker
docker logs worker --tail 50

# 2. Verify worker registration in database
docker exec postgres psql -U orchestrator -c "
SELECT worker_id, last_seen, processed_count 
FROM worker_heartbeat 
WHERE last_seen > now() - interval '10 minutes'
ORDER BY last_seen DESC;
"

# 3. Check for work queue backup
docker exec postgres psql -U orchestrator -c "
SELECT COUNT(*) as pending_work FROM due_work 
WHERE run_at <= now() AND (locked_until IS NULL OR locked_until < now());
"

# 4. Resource constraints check
docker stats worker --no-stream
```

#### Resolution Procedures
```bash
# Option 1: Restart workers
docker-compose -f ops/docker-compose.yml restart worker

# Option 2: Scale up workers if high load
docker-compose -f ops/docker-compose.yml up -d --scale worker=4

# Option 3: Emergency single worker start
docker run -d --name emergency-worker \
  --network ordinaut_ordinaut-network \
  -e DATABASE_URL=postgresql+psycopg://orchestrator:orchestrator_pw@postgres:5432/orchestrator \
  -e REDIS_URL=redis://redis:6379/0 \
  orchestrator-worker

# Verify recovery
sleep 30
docker exec postgres psql -U orchestrator -c "
SELECT COUNT(*) FROM worker_heartbeat 
WHERE last_seen > now() - interval '1 minute';
"
```

---

## 2. HIGH PRIORITY ALERTS (SEVERITY 1) - 15 MINUTE RESPONSE

### HighAPILatency
**Trigger**: 95th percentile response time >2 seconds for 5 minutes  
**Impact**: Poor user experience, potential timeouts  
**Response Time**: 15 minutes

#### Performance Analysis
```bash
# 1. Current response time test
for i in {1..10}; do
  curl -s -w "Response time: %{time_total}s (HTTP %{http_code})\n" -o /dev/null http://localhost:8080/health
done

# 2. Check API resource usage
docker stats api --no-stream

# 3. Database performance check
docker exec postgres psql -U orchestrator -c "
SELECT query, calls, total_time/calls as avg_time_ms
FROM pg_stat_statements 
ORDER BY total_time DESC LIMIT 10;
"

# 4. Check for slow queries
docker logs postgres --since 10m | grep "slow query"
```

#### Optimization Steps
```bash
# Step 1: Check database connections
docker exec postgres psql -U orchestrator -c "
SELECT count(*), state FROM pg_stat_activity 
WHERE datname = 'orchestrator' GROUP BY state;
"

# Step 2: Clear potential locks
docker exec postgres psql -U orchestrator -c "
SELECT pid, query, state, waiting 
FROM pg_stat_activity 
WHERE state = 'active' AND waiting = true;
"

# Step 3: Restart API if necessary (non-disruptive)
# Only if latency is >5 seconds consistently
docker-compose -f ops/docker-compose.yml restart api

# Step 4: Scale API if needed (not currently supported but plan for load balancer)
# Future: docker-compose up -d --scale api=2
```

---

### DatabaseSlowQueries
**Trigger**: Queries taking >10 seconds detected  
**Impact**: Performance degradation, potential blocking  
**Response Time**: 15 minutes

#### Query Analysis
```bash
# 1. Identify current slow queries
docker exec postgres psql -U orchestrator -c "
SELECT pid, now() - pg_stat_activity.query_start as duration, query 
FROM pg_stat_activity 
WHERE (now() - pg_stat_activity.query_start) > interval '5 seconds'
  AND state = 'active';
"

# 2. Check for blocking queries
docker exec postgres psql -U orchestrator -c "
SELECT blocked_locks.pid as blocked_pid, blocking_locks.pid as blocking_pid,
       blocked_activity.query as blocked_statement,
       blocking_activity.query as blocking_statement
FROM pg_catalog.pg_locks blocked_locks
JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
JOIN pg_catalog.pg_locks blocking_locks ON blocking_locks.locktype = blocked_locks.locktype
JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
WHERE NOT blocked_locks.granted;
"

# 3. Analyze query statistics
docker exec postgres psql -U orchestrator -c "
SELECT query, calls, total_time, mean_time, max_time
FROM pg_stat_statements 
WHERE mean_time > 1000  -- queries averaging >1 second
ORDER BY mean_time DESC LIMIT 15;
"
```

#### Performance Resolution
```bash
# Step 1: Kill long-running queries if necessary (CAUTION)
# Only kill if query is clearly problematic and not critical
PROBLEM_PID=$(docker exec postgres psql -U orchestrator -t -c "
SELECT pid FROM pg_stat_activity 
WHERE state = 'active' 
  AND (now() - query_start) > interval '300 seconds'
  AND query NOT ILIKE '%backup%' 
  AND query NOT ILIKE '%vacuum%'
LIMIT 1;")

if [ -n "$PROBLEM_PID" ] && [ "$PROBLEM_PID" != "" ]; then
  echo "Terminating long-running query PID: $PROBLEM_PID"
  docker exec postgres psql -U orchestrator -c "SELECT pg_terminate_backend($PROBLEM_PID);"
fi

# Step 2: Analyze and optimize problematic queries
# Look for missing indexes
docker exec postgres psql -U orchestrator -c "
SELECT schemaname, tablename, attname, n_distinct, correlation 
FROM pg_stats 
WHERE tablename IN ('task', 'task_run', 'due_work')
ORDER BY n_distinct DESC;
"

# Step 3: Consider emergency VACUUM if needed
# Only during low-traffic periods
docker exec postgres psql -U orchestrator -c "VACUUM ANALYZE;"
```

---

### SchedulerOffline
**Trigger**: No task scheduling activity for >5 minutes  
**Impact**: Future tasks not being queued  
**Response Time**: 15 minutes

#### Scheduler Diagnostics
```bash
# 1. Check scheduler container status
docker ps | grep scheduler
docker logs scheduler --tail 100

# 2. Verify scheduling is working
docker exec postgres psql -U orchestrator -c "
SELECT COUNT(*) as recent_schedules 
FROM due_work 
WHERE created_at > now() - interval '10 minutes';
"

# 3. Check for scheduler errors
docker logs scheduler --since 15m | grep -E "(ERROR|EXCEPTION|FATAL)"

# 4. Verify database connectivity from scheduler
docker exec scheduler python -c "
import asyncpg, asyncio
async def test(): 
    try:
        conn = await asyncpg.connect('postgresql://orchestrator:orchestrator_pw@postgres:5432/orchestrator')
        print('Scheduler DB connection: OK')
        await conn.close()
    except Exception as e: 
        print(f'Scheduler DB connection: FAILED - {e}')
asyncio.run(test())
" 2>/dev/null || echo "Scheduler container unreachable"
```

#### Scheduler Recovery
```bash
# Step 1: Restart scheduler service
docker-compose -f ops/docker-compose.yml restart scheduler

# Step 2: Verify scheduler startup
sleep 10
docker logs scheduler --tail 20

# Step 3: Test scheduling functionality
# Create test task for 1 minute from now
TEST_TIME=$(date -d '+1 minute' -Iseconds)
curl -X POST http://localhost:8080/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Scheduler Test", 
    "description": "Test scheduling recovery",
    "schedule_kind": "once",
    "schedule_expr": "'$TEST_TIME'",
    "payload": {"pipeline": [{"id": "test", "uses": "noop"}]}
  }'

# Step 4: Verify scheduling resumed
sleep 70
docker exec postgres psql -U orchestrator -c "
SELECT COUNT(*) FROM due_work 
WHERE created_at > now() - interval '2 minutes';
"
```

---

## 3. WARNING ALERTS (SEVERITY 2) - 30 MINUTE RESPONSE

### HighQueueDepth
**Trigger**: >1000 pending work items for >10 minutes  
**Impact**: Increasing task latency  
**Response Time**: 30 minutes

#### Queue Analysis
```bash
# 1. Analyze queue composition
docker exec postgres psql -U orchestrator -c "
SELECT 
  COUNT(*) as total_pending,
  COUNT(*) FILTER (WHERE run_at <= now()) as due_now,
  COUNT(*) FILTER (WHERE locked_until IS NOT NULL) as locked,
  MIN(run_at) as oldest_task,
  MAX(run_at) as newest_task
FROM due_work;
"

# 2. Check processing rate
docker exec postgres psql -U orchestrator -c "
SELECT 
  COUNT(*) as completed_last_hour,
  AVG(EXTRACT(EPOCH FROM (finished_at - started_at))) as avg_execution_time
FROM task_run 
WHERE finished_at > now() - interval '1 hour';
"

# 3. Worker efficiency analysis
docker exec postgres psql -U orchestrator -c "
SELECT 
  worker_id, 
  processed_count,
  last_seen,
  EXTRACT(EPOCH FROM (now() - last_seen)) as seconds_since_heartbeat
FROM worker_heartbeat 
ORDER BY processed_count DESC;
"
```

#### Queue Management
```bash
# Option 1: Scale up workers temporarily
current_workers=$(docker ps | grep worker | wc -l)
target_workers=$((current_workers + 2))
docker-compose -f ops/docker-compose.yml up -d --scale worker=$target_workers

# Option 2: Analyze for stuck work items
docker exec postgres psql -U orchestrator -c "
SELECT task_id, run_at, locked_until, locked_by 
FROM due_work 
WHERE locked_until < now() - interval '10 minutes'
LIMIT 10;
"

# Option 3: Clear potentially stuck locks (CAUTION)
# Only if locks are clearly stale (>1 hour old)
docker exec postgres psql -U orchestrator -c "
UPDATE due_work 
SET locked_until = NULL, locked_by = NULL 
WHERE locked_until < now() - interval '1 hour';
"
```

---

### DiskSpaceCritical  
**Trigger**: <15% disk space remaining  
**Impact**: Risk of system failure  
**Response Time**: 30 minutes

#### Disk Analysis
```bash
# 1. Overall disk usage
df -h

# 2. Docker space usage
docker system df -v

# 3. Large file identification
du -sh /var/lib/docker/volumes/* | sort -hr | head -20
du -sh /var/log/* | sort -hr | head -10

# 4. Database growth analysis
docker exec postgres psql -U orchestrator -c "
SELECT 
  schemaname, 
  tablename,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_stat_user_tables 
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
"
```

#### Disk Cleanup Procedures
```bash
# Step 1: Clean Docker system (safe)
docker system prune -f
docker volume prune -f

# Step 2: Clean old log files
find /var/log -name "*.log" -mtime +7 -delete
docker logs api > /dev/null  # Truncate container logs

# Step 3: Database cleanup (CAUTION - verify before running)
# Clean old audit logs (>30 days)
docker exec postgres psql -U orchestrator -c "
DELETE FROM audit_log WHERE at < now() - interval '30 days';
"

# Clean old task runs (>14 days)  
docker exec postgres psql -U orchestrator -c "
DELETE FROM task_run WHERE created_at < now() - interval '14 days';
"

# Step 4: Emergency measures if still critical
# Compress log files
find /var/log -name "*.log" -exec gzip {} \;

# Archive old database dumps
find /backups -name "*.sql" -mtime +30 -exec gzip {} \;
```

---

### MemoryUsageCritical
**Trigger**: >90% system memory usage for >5 minutes  
**Impact**: Performance degradation, OOM risk  
**Response Time**: 30 minutes

#### Memory Analysis
```bash
# 1. System memory overview
free -h
ps aux --sort=-%mem | head -20

# 2. Container memory usage
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}"

# 3. Database memory analysis
docker exec postgres psql -U orchestrator -c "
SELECT 
  setting as shared_buffers,
  unit 
FROM pg_settings 
WHERE name = 'shared_buffers';
"

# 4. Check for memory leaks
# Look for continuously growing processes
docker stats --format "table {{.Name}}\t{{.MemUsage}}" | head -10
```

#### Memory Optimization
```bash
# Step 1: Restart memory-intensive services
# Identify highest memory consumer
highest_mem_container=$(docker stats --no-stream --format "{{.Name}}\t{{.MemPerc}}" | \
  sort -k2 -nr | head -1 | cut -f1)

echo "Highest memory consumer: $highest_mem_container"

# Restart if it's not the database (requires special handling)
if [ "$highest_mem_container" != "postgres" ]; then
  docker-compose -f ops/docker-compose.yml restart "$highest_mem_container"
fi

# Step 2: Clear caches if possible
# Clear Redis cache (non-persistent data only)
docker exec redis redis-cli FLUSHDB

# Step 3: Scale down non-essential services temporarily
docker-compose -f ops/docker-compose.observability.yml stop grafana

# Step 4: Emergency measures
# If critical, restart services in order of importance
# API -> Workers -> Scheduler (database last resort)
```

---

## 4. INFORMATIONAL ALERTS (SEVERITY 3) - 2 HOUR RESPONSE

### BackupFailed
**Trigger**: Daily backup script reports failure  
**Impact**: Loss of backup protection  
**Response Time**: 2 hours

#### Backup Verification
```bash
# 1. Check backup directory and recent files
ls -la /backups/postgres/ | head -10
ls -la /backups/redis/ | head -10

# 2. Verify backup script logs
tail -50 /var/log/backups/$(date +%Y-%m-%d).log

# 3. Test manual backup
docker exec postgres pg_dump -U orchestrator orchestrator > test_backup_$(date +%Y%m%d_%H%M%S).sql
echo "Manual backup test size: $(wc -l < test_backup_$(date +%Y%m%d_%H%M%S).sql) lines"

# 4. Verify backup integrity
head -10 test_backup_$(date +%Y%m%d_%H%M%S).sql
tail -10 test_backup_$(date +%Y%m%d_%H%M%S).sql
```

---

### LowTaskThroughput  
**Trigger**: <50 tasks/hour processed for >2 hours  
**Impact**: Potential efficiency issues  
**Response Time**: 2 hours

#### Throughput Analysis
```bash
# 1. Recent processing statistics
docker exec postgres psql -U orchestrator -c "
SELECT 
  date_trunc('hour', started_at) as hour,
  COUNT(*) as tasks_processed,
  AVG(EXTRACT(EPOCH FROM (finished_at - started_at))) as avg_duration
FROM task_run 
WHERE started_at > now() - interval '24 hours'
GROUP BY date_trunc('hour', started_at)
ORDER BY hour DESC;
"

# 2. Task complexity analysis
docker exec postgres psql -U orchestrator -c "
SELECT 
  jsonb_array_length(payload->'pipeline') as pipeline_length,
  COUNT(*) as task_count,
  AVG(EXTRACT(EPOCH FROM (finished_at - started_at))) as avg_duration
FROM task t
JOIN task_run tr ON t.id = tr.task_id
WHERE tr.started_at > now() - interval '24 hours'
GROUP BY jsonb_array_length(payload->'pipeline')
ORDER BY pipeline_length;
"
```

---

## 5. MONITORING DASHBOARD PROCEDURES

### Grafana Dashboard Verification
```bash
# 1. Verify Grafana accessibility
curl -f http://localhost:3000/api/health

# 2. Check data source connectivity
curl -f http://localhost:3000/api/datasources/proxy/1/api/v1/query?query=up

# 3. Verify key metrics are updating
curl -s "http://localhost:9090/api/v1/query?query=up{job='orchestrator-api'}" | \
  jq '.data.result[0].value[1]'
```

### Prometheus Health Check
```bash
# 1. Prometheus status
curl -f http://localhost:9090/-/healthy
curl -f http://localhost:9090/-/ready

# 2. Check target health
curl -s http://localhost:9090/api/v1/targets | \
  jq -r '.data.activeTargets[] | "\(.labels.job): \(.health)"'

# 3. Verify metrics collection
curl -s "http://localhost:9090/api/v1/query?query=orchestrator_tasks_total" | \
  jq '.data.result | length'
```

---

## 6. ALERT CONFIGURATION

### Alert Rule Validation
```bash
# 1. Check Prometheus rules
curl -s http://localhost:9090/api/v1/rules | \
  jq '.data.groups[] | {name: .name, rules: (.rules | length)}'

# 2. Validate AlertManager configuration
curl -f http://localhost:9093/api/v1/status

# 3. Test alert routing
curl -X POST http://localhost:9093/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '[{
    "labels": {"alertname": "TestAlert", "severity": "warning"},
    "annotations": {"summary": "Test alert for configuration validation"}
  }]'
```

### Silence Management
```bash
# 1. List active silences
curl -s http://localhost:9093/api/v1/silences | \
  jq -r '.data[] | "\(.id): \(.comment) (expires: \(.endsAt))"'

# 2. Create maintenance silence (4 hour window)
curl -X POST http://localhost:9093/api/v1/silences \
  -H "Content-Type: application/json" \
  -d '{
    "matchers": [{"name": "service", "value": "orchestrator"}],
    "startsAt": "'$(date -Iseconds)'",
    "endsAt": "'$(date -d '+4 hours' -Iseconds)'",
    "comment": "Scheduled maintenance window"
  }'
```

**Last Updated**: 2025-01-10  
**Next Review**: 2025-04-10  
**Owner**: Operations Team  
**Approver**: Technical Lead