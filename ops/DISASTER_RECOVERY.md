# Disaster Recovery Procedures
## Enterprise Task Scheduling System

### Recovery Time Objective (RTO): 30 minutes
### Recovery Point Objective (RPO): 5 minutes

---

## 1. IMMEDIATE RESPONSE PROCEDURES

### Complete System Failure Response
```bash
# Step 1: Assess system status
./ops/health-check.sh --full-system
docker ps -a | grep -E "(api|scheduler|worker|postgres|redis)"
docker-compose -f ops/docker-compose.observability.yml ps

# Step 2: Check data integrity
docker exec postgres pg_isready -U orchestrator
docker exec redis redis-cli ping

# Step 3: Verify backup availability
ls -la /backups/postgres/$(date +%Y-%m-%d)*
ls -la /backups/redis/$(date +%Y-%m-%d)*
```

### Critical Service Recovery Order
1. **PostgreSQL Database** (Core data store)
2. **Redis** (Event streams and caching)
3. **API Service** (External interface)
4. **Scheduler Service** (Task scheduling)
5. **Worker Services** (Task execution)
6. **Monitoring Stack** (Observability)

---

## 2. DATABASE RECOVERY PROCEDURES

### PostgreSQL Complete Recovery
```bash
# Stop all services except postgres
docker-compose -f ops/docker-compose.yml stop api scheduler worker

# Create recovery directory
mkdir -p /recovery/postgres/$(date +%Y%m%d_%H%M%S)
cd /recovery/postgres/$(date +%Y%m%d_%H%M%S)

# Stop PostgreSQL service
docker-compose -f ops/docker-compose.yml stop postgres

# Backup current data (if accessible)
docker run --rm -v task_scheduler_pgdata:/source -v $(pwd):/backup \
  busybox tar czf /backup/current_data_backup.tar.gz -C /source .

# Restore from latest backup
LATEST_BACKUP=$(ls -1t /backups/postgres/ | head -1)
echo "Restoring from: $LATEST_BACKUP"

# Remove corrupted data volume
docker volume rm task_scheduler_pgdata
docker volume create task_scheduler_pgdata

# Restore backup data
docker run --rm -v $(pwd)/backups/postgres/$LATEST_BACKUP:/backup \
  -v task_scheduler_pgdata:/target busybox tar xzf /backup -C /target

# Start PostgreSQL
docker-compose -f ops/docker-compose.yml up -d postgres

# Wait for startup and verify
timeout 60s bash -c 'until docker exec postgres pg_isready -U orchestrator; do sleep 2; done'

# Verify data integrity
docker exec postgres psql -U orchestrator -c "
SELECT 
  schemaname, 
  tablename, 
  n_tup_ins as inserts, 
  n_tup_upd as updates,
  n_tup_del as deletes
FROM pg_stat_user_tables 
ORDER BY schemaname, tablename;"

# Check for corruption
docker exec postgres psql -U orchestrator -c "
SELECT datname, pg_size_pretty(pg_database_size(datname)) as size 
FROM pg_database WHERE datname = 'orchestrator';"

# Verify critical tables
docker exec postgres psql -U orchestrator -c "
SELECT 
  COUNT(*) as task_count 
FROM task WHERE status = 'active';

SELECT 
  COUNT(*) as pending_work 
FROM due_work WHERE run_at <= now() 
  AND (locked_until IS NULL OR locked_until < now());
"
```

### Point-in-Time Recovery (PITR)
```bash
# For recovery to specific timestamp
RECOVERY_TARGET="2025-01-10 14:30:00+00"

# Stop all services
docker-compose -f ops/docker-compose.yml down

# Create recovery configuration
cat > /recovery/recovery.conf << EOF
restore_command = 'cp /backups/postgres/wal/%f %p'
recovery_target_time = '$RECOVERY_TARGET'
recovery_target_action = 'promote'
EOF

# Restore base backup and apply WAL logs
docker volume rm task_scheduler_pgdata
docker volume create task_scheduler_pgdata

# Restore base backup (find closest backup before target time)
BASE_BACKUP=$(ls -1 /backups/postgres/base/ | \
  awk -v target="$RECOVERY_TARGET" '$0 <= target' | tail -1)

docker run --rm -v /backups/postgres/base/$BASE_BACKUP:/backup \
  -v task_scheduler_pgdata:/target busybox tar xzf /backup -C /target

# Copy recovery configuration
docker run --rm -v $(pwd)/recovery.conf:/recovery.conf \
  -v task_scheduler_pgdata:/target busybox cp /recovery.conf /target/

# Start PostgreSQL in recovery mode
docker-compose -f ops/docker-compose.yml up -d postgres

# Monitor recovery progress
docker logs postgres -f | grep -E "(redo|recovery)"

# Verify recovery completion
docker exec postgres psql -U orchestrator -c "SELECT pg_is_in_recovery();"
```

---

## 3. REDIS RECOVERY PROCEDURES

### Redis Data Recovery
```bash
# Stop services using Redis
docker-compose -f ops/docker-compose.yml stop api scheduler worker

# Backup current Redis data
docker exec redis redis-cli --rdb /data/current_backup.rdb

# Stop Redis
docker-compose -f ops/docker-compose.yml stop redis

# Restore from backup
LATEST_REDIS_BACKUP=$(ls -1t /backups/redis/ | head -1)
docker volume rm task_scheduler_redisdata
docker volume create task_scheduler_redisdata

docker run --rm -v /backups/redis/$LATEST_REDIS_BACKUP:/backup \
  -v task_scheduler_redisdata:/target busybox cp /backup /target/dump.rdb

# Set proper permissions
docker run --rm -v task_scheduler_redisdata:/target busybox chown 999:999 /target/dump.rdb

# Start Redis
docker-compose -f ops/docker-compose.yml up -d redis

# Verify Redis recovery
timeout 30s bash -c 'until docker exec redis redis-cli ping | grep -q PONG; do sleep 1; done'

# Check data integrity
docker exec redis redis-cli info keyspace
docker exec redis redis-cli info replication
```

---

## 4. APPLICATION SERVICES RECOVERY

### API Service Recovery
```bash
# Verify dependencies first
docker exec postgres pg_isready -U orchestrator || echo "Database not ready"
docker exec redis redis-cli ping || echo "Redis not ready"

# Check configuration
docker-compose -f ops/docker-compose.yml config | grep -A 10 api:

# Start API service
docker-compose -f ops/docker-compose.yml up -d api

# Wait for health check
timeout 120s bash -c 'until curl -f http://localhost:8080/health; do sleep 5; done'

# Verify API functionality
curl -X GET http://localhost:8080/health/ready
curl -X GET http://localhost:8080/tasks?limit=5

# Check service logs for errors
docker logs api --tail 100 | grep -E "(ERROR|CRITICAL|FATAL)"
```

### Scheduler Service Recovery
```bash
# Start scheduler
docker-compose -f ops/docker-compose.yml up -d scheduler

# Monitor scheduler initialization
docker logs scheduler -f | grep -E "(started|initialized|ready)"

# Verify scheduler is processing
docker exec postgres psql -U orchestrator -c "
SELECT COUNT(*) as scheduled_tasks 
FROM task WHERE status = 'active';

SELECT COUNT(*) as due_work 
FROM due_work WHERE run_at <= now() + interval '1 hour';
"

# Check for scheduler errors
docker logs scheduler --tail 50 | grep -E "(ERROR|EXCEPTION)"
```

### Worker Services Recovery
```bash
# Start workers
docker-compose -f ops/docker-compose.yml up -d worker

# Verify workers are claiming work
docker exec postgres psql -U orchestrator -c "
SELECT 
  worker_id, 
  last_seen, 
  processed_count,
  hostname 
FROM worker_heartbeat 
WHERE last_seen > now() - interval '1 minute';"

# Monitor work processing
docker logs worker --tail 20
docker exec postgres psql -U orchestrator -c "
SELECT COUNT(*) as active_runs 
FROM task_run 
WHERE finished_at IS NULL;"
```

---

## 5. DATA CONSISTENCY VERIFICATION

### Database Consistency Checks
```bash
# Run comprehensive consistency verification
docker exec postgres psql -U orchestrator << 'EOF'
-- Check for orphaned records
SELECT 'Orphaned task_runs' as check_name, COUNT(*) as count
FROM task_run tr LEFT JOIN task t ON tr.task_id = t.id WHERE t.id IS NULL;

SELECT 'Orphaned due_work' as check_name, COUNT(*) as count  
FROM due_work dw LEFT JOIN task t ON dw.task_id = t.id WHERE t.id IS NULL;

-- Check for data integrity issues
SELECT 'Tasks without valid agents' as check_name, COUNT(*) as count
FROM task t LEFT JOIN agent a ON t.created_by = a.id WHERE a.id IS NULL;

-- Check for scheduling anomalies
SELECT 'Future runs in past' as check_name, COUNT(*) as count
FROM due_work WHERE run_at < now() - interval '1 day';

SELECT 'Stale worker leases' as check_name, COUNT(*) as count
FROM due_work WHERE locked_until < now() - interval '1 hour';

-- Check for performance issues
SELECT 
  'Large due_work queue' as check_name,
  COUNT(*) as count,
  CASE WHEN COUNT(*) > 10000 THEN 'CRITICAL' ELSE 'OK' END as status
FROM due_work WHERE run_at <= now();
EOF
```

### Application State Verification
```bash
# Verify all services are healthy
curl -f http://localhost:8080/health/detailed | jq '.'

# Check system metrics
curl -s http://localhost:9090/api/v1/query?query=up | \
  jq -r '.data.result[] | "\(.metric.job): \(.value[1])"'

# Verify task processing pipeline
TEST_TASK_ID=$(curl -X POST http://localhost:8080/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Recovery Test Task",
    "description": "Verify system recovery",
    "schedule_kind": "once", 
    "schedule_expr": "'$(date -d '+30 seconds' -Iseconds)'",
    "payload": {"pipeline": [{"id": "test", "uses": "noop"}]}
  }' | jq -r '.id')

# Monitor test task execution  
sleep 45
curl http://localhost:8080/tasks/$TEST_TASK_ID/runs | \
  jq '.[] | {started_at, finished_at, success}'
```

---

## 6. POST-RECOVERY PROCEDURES

### System Validation Checklist
- [ ] All Docker containers running and healthy
- [ ] Database connectivity and data integrity verified
- [ ] Redis streams and caching operational
- [ ] API endpoints responding correctly
- [ ] Scheduler processing tasks on schedule
- [ ] Workers claiming and executing work
- [ ] Monitoring and alerting functional
- [ ] No critical errors in application logs
- [ ] Test task execution successful
- [ ] Performance metrics within normal ranges

### Monitoring Restoration
```bash
# Restart full observability stack
docker-compose -f ops/docker-compose.observability.yml up -d

# Verify monitoring services
curl -f http://localhost:9090/api/v1/query?query=up
curl -f http://localhost:3000/api/health
curl -f http://localhost:9093/api/v1/status

# Check alert status (should be minimal after recovery)
curl -s http://localhost:9093/api/v1/alerts | \
  jq '.data[] | select(.status.state == "firing") | .labels.alertname'
```

### Performance Baseline Recovery
```bash
# Load baseline performance test
docker run --rm --network task_scheduler_network \
  -v $(pwd)/tests/load:/tests \
  python:3.12-slim python /tests/recovery_validation.py

# Expected results:
# - API response time: < 200ms (95th percentile)
# - Task scheduling latency: < 30 seconds
# - Worker processing rate: > 100 tasks/minute
# - Database connection pool: < 50% utilization
```

---

## 7. DISASTER SCENARIOS & PROCEDURES

### Scenario 1: Complete Hardware Failure
**Detection**: All services down, no response from host
**Recovery Time**: 30-45 minutes

1. Provision new hardware/cloud instance
2. Install Docker and restore application code
3. Restore data volumes from backups
4. Start services in dependency order
5. Verify full system functionality

### Scenario 2: Database Corruption
**Detection**: PostgreSQL startup failures, data inconsistency
**Recovery Time**: 15-30 minutes

1. Stop all application services
2. Assess corruption extent with pg_dump
3. Restore from most recent clean backup
4. Apply WAL logs if available
5. Restart services and validate

### Scenario 3: Network Partition
**Detection**: Service communication failures
**Recovery Time**: 5-15 minutes

1. Identify network connectivity issues
2. Restart affected containers/networking
3. Verify inter-service communication
4. Monitor for split-brain scenarios
5. Validate data consistency

### Scenario 4: Data Center Outage
**Detection**: Complete site unavailability
**Recovery Time**: 45-90 minutes

1. Activate disaster recovery site
2. Restore data from off-site backups
3. Update DNS/load balancer configuration
4. Verify cross-region replication
5. Monitor performance and capacity

---

## 8. COMMUNICATION PROCEDURES

### Incident Communication Template
```
INCIDENT: Task Scheduling System Service Disruption
SEVERITY: [Critical/High/Medium/Low]
START TIME: [ISO timestamp]
IMPACT: [Description of user impact]

CURRENT STATUS: [Brief status update]
ESTIMATED RESOLUTION: [Time estimate]

ACTIONS TAKEN:
- [Action 1 with timestamp]
- [Action 2 with timestamp]

NEXT UPDATE: [Time for next communication]
```

### Stakeholder Notification Matrix
| Severity | Notification Time | Recipients | Channels |
|----------|------------------|------------|----------|
| Critical | Immediate | All stakeholders | Phone + Email + Slack |
| High | 15 minutes | Technical teams | Email + Slack |
| Medium | 30 minutes | Operations team | Slack |
| Low | 1 hour | Monitoring team | Email |

### Recovery Success Criteria
- [ ] RTO met (system restored within 30 minutes)
- [ ] RPO met (data loss < 5 minutes) 
- [ ] All critical services operational
- [ ] Performance within acceptable ranges
- [ ] Monitoring and alerting restored
- [ ] Stakeholders notified of resolution
- [ ] Post-incident review scheduled

---

## 9. RECOVERY TESTING SCHEDULE

### Monthly Recovery Drills
- **First Tuesday**: Database backup/restore test
- **Second Tuesday**: Redis failover test
- **Third Tuesday**: Complete system recovery test
- **Fourth Tuesday**: Cross-region disaster recovery test

### Annual Recovery Validation
- Full disaster recovery exercise with external validation
- Performance benchmark comparison
- Documentation and procedure updates
- Staff training and certification renewal

**Last Updated**: 2025-01-10  
**Next Review**: 2025-04-10  
**Owner**: Operations Team  
**Approver**: Technical Lead