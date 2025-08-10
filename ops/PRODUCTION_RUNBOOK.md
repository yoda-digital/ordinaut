# Production Runbook
## Ordinaut Daily Operations

### System Overview
- **Environment**: Production
- **Architecture**: Distributed microservices with PostgreSQL and Redis
- **Components**: API, Scheduler, Workers, Database, Cache, Monitoring
- **Uptime SLA**: 99.9% (8.76 hours downtime/year)
- **Performance SLA**: <200ms API response time, <30s scheduling latency

---

## 1. DAILY HEALTH CHECK PROCEDURES

### Morning Health Check (Every 8:00 AM)
```bash
#!/bin/bash
# daily_health_check.sh - Comprehensive morning system verification

echo "=== ORCHESTRATOR DAILY HEALTH CHECK - $(date) ==="

# 1. System Status Overview
echo -e "\n### CONTAINER STATUS ###"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.RunningFor}}\t{{.RestartCount}}" | \
  grep -E "(api|postgres|redis|scheduler|worker|prometheus|grafana)"

# 2. Service Endpoints Health
echo -e "\n### SERVICE HEALTH ENDPOINTS ###"
SERVICES=(
  "API:http://localhost:8080/health"
  "API_Ready:http://localhost:8080/health/ready"
  "Prometheus:http://localhost:9090/-/healthy"
  "Grafana:http://localhost:3000/api/health"
  "AlertManager:http://localhost:9093/api/v1/status"
)

for service_url in "${SERVICES[@]}"; do
  service_name="${service_url%%:*}"
  url="${service_url##*:}"
  if curl -sf "$url" > /dev/null 2>&1; then
    echo "✅ $service_name: HEALTHY"
  else
    echo "❌ $service_name: UNHEALTHY ($url)"
  fi
done

# 3. Database Health
echo -e "\n### DATABASE STATUS ###"
if docker exec postgres pg_isready -U orchestrator > /dev/null 2>&1; then
  echo "✅ PostgreSQL: READY"
  
  # Check database size and connections
  docker exec postgres psql -U orchestrator -t -c "
    SELECT 
      'Database size: ' || pg_size_pretty(pg_database_size('orchestrator')) as info
    UNION ALL
    SELECT 
      'Active connections: ' || count(*)::text
    FROM pg_stat_activity WHERE datname = 'orchestrator' AND state = 'active'
    UNION ALL
    SELECT 
      'Active tasks: ' || count(*)::text
    FROM task WHERE status = 'active';
  "
else
  echo "❌ PostgreSQL: NOT READY"
fi

# 4. Redis Health  
echo -e "\n### REDIS STATUS ###"
if docker exec redis redis-cli ping 2>/dev/null | grep -q PONG; then
  echo "✅ Redis: READY"
  docker exec redis redis-cli info keyspace 2>/dev/null | grep -E "^db[0-9]:" || echo "No active keyspaces"
else
  echo "❌ Redis: NOT READY"
fi

# 5. Work Queue Health
echo -e "\n### WORK QUEUE STATUS ###"
docker exec postgres psql -U orchestrator -t -c "
SELECT 
  'Due now: ' || COUNT(*) FILTER (WHERE run_at <= now() AND (locked_until IS NULL OR locked_until < now())) ||
  ', Locked: ' || COUNT(*) FILTER (WHERE locked_until IS NOT NULL AND locked_until >= now()) ||
  ', Future: ' || COUNT(*) FILTER (WHERE run_at > now()) as queue_stats
FROM due_work;
"

# 6. Worker Health
echo -e "\n### WORKER STATUS ###"  
docker exec postgres psql -U orchestrator -t -c "
SELECT 
  worker_id || ' - Last seen: ' || 
  EXTRACT(EPOCH FROM (now() - last_seen))::int || 's ago, Processed: ' || processed_count
FROM worker_heartbeat 
WHERE last_seen > now() - interval '5 minutes'
ORDER BY last_seen DESC;
"

ACTIVE_WORKERS=$(docker exec postgres psql -U orchestrator -t -c "
SELECT COUNT(*) FROM worker_heartbeat 
WHERE last_seen > now() - interval '2 minutes';
" | tr -d ' ')

if [ "$ACTIVE_WORKERS" -gt 0 ]; then
  echo "✅ Active workers: $ACTIVE_WORKERS"
else
  echo "❌ No active workers detected"
fi

# 7. Recent Error Check
echo -e "\n### RECENT ERRORS ###"
ERROR_COUNT=$(docker logs api --since 24h 2>/dev/null | grep -c -E "(ERROR|CRITICAL|FATAL)" || echo 0)
echo "Last 24h API errors: $ERROR_COUNT"

if [ "$ERROR_COUNT" -gt 100 ]; then
  echo "⚠️  High error rate detected - investigation recommended"
fi

# 8. Performance Metrics
echo -e "\n### PERFORMANCE METRICS ###"
# API response time test
for i in {1..3}; do
  response_time=$(curl -s -w "%{time_total}" -o /dev/null http://localhost:8080/health 2>/dev/null || echo "timeout")
  echo "API response time attempt $i: ${response_time}s"
done

# 9. Alert Status
echo -e "\n### ALERT STATUS ###"
FIRING_ALERTS=$(curl -s http://localhost:9093/api/v1/alerts 2>/dev/null | \
  jq -r '.data[] | select(.status.state == "firing") | .labels.alertname' 2>/dev/null | wc -l || echo "0")
echo "Currently firing alerts: $FIRING_ALERTS"

# 10. Disk Usage Check
echo -e "\n### DISK USAGE ###"
df -h | grep -E "(/$|/var)"
docker system df

# Summary
echo -e "\n### HEALTH CHECK SUMMARY ###"
echo "Timestamp: $(date -Iseconds)"
echo "Overall Status: $([ $ERROR_COUNT -lt 50 ] && [ $ACTIVE_WORKERS -gt 0 ] && [ $FIRING_ALERTS -lt 5 ] && echo "✅ HEALTHY" || echo "⚠️  NEEDS ATTENTION")"
```

### Evening Health Check (Every 6:00 PM)
```bash
#!/bin/bash
# evening_health_check.sh - End of day system verification

echo "=== EVENING HEALTH CHECK - $(date) ==="

# 1. Daily Statistics
echo -e "\n### TODAY'S STATISTICS ###"
docker exec postgres psql -U orchestrator -t -c "
SELECT 
  'Tasks completed today: ' || COUNT(*) FILTER (WHERE started_at::date = CURRENT_DATE AND success = true) ||
  ', Failed: ' || COUNT(*) FILTER (WHERE started_at::date = CURRENT_DATE AND success = false) ||
  ', Success rate: ' || ROUND(
    100.0 * COUNT(*) FILTER (WHERE started_at::date = CURRENT_DATE AND success = true) / 
    NULLIF(COUNT(*) FILTER (WHERE started_at::date = CURRENT_DATE), 0), 2
  ) || '%'
FROM task_run;
"

# 2. Performance Summary  
docker exec postgres psql -U orchestrator -t -c "
SELECT 
  'Avg execution time: ' || ROUND(AVG(EXTRACT(EPOCH FROM (finished_at - started_at))), 2) || 's' ||
  ', Max execution time: ' || ROUND(MAX(EXTRACT(EPOCH FROM (finished_at - started_at))), 2) || 's'
FROM task_run 
WHERE started_at::date = CURRENT_DATE AND finished_at IS NOT NULL;
"

# 3. Queue Health for Tomorrow
echo -e "\n### TOMORROW'S SCHEDULE ###"
docker exec postgres psql -U orchestrator -t -c "
SELECT 
  'Tasks scheduled for tomorrow: ' || COUNT(*)
FROM due_work 
WHERE run_at::date = CURRENT_DATE + 1;
"

# 4. Resource Usage Trends
echo -e "\n### RESOURCE USAGE ###"
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}" | head -8

# 5. Data Growth
echo -e "\n### DATA GROWTH ###"
docker exec postgres psql -U orchestrator -t -c "
SELECT 
  schemaname, tablename, 
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
  n_tup_ins as inserts_today
FROM pg_stat_user_tables 
WHERE n_tup_ins > 0
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
"

echo -e "\n### BACKUP STATUS ###"
# Check if backups ran successfully (assuming backup script logs to /var/log/backups/)
if [ -f "/var/log/backups/$(date +%Y-%m-%d).log" ]; then
  echo "✅ Daily backup completed"
  tail -3 "/var/log/backups/$(date +%Y-%m-%d).log"
else
  echo "⚠️  No backup log found for today"
fi
```

---

## 2. ROUTINE MAINTENANCE SCHEDULES

### Weekly Maintenance (Sunday 2:00 AM)
```bash
#!/bin/bash
# weekly_maintenance.sh - Weekly system maintenance tasks

echo "=== WEEKLY MAINTENANCE - $(date) ==="

# 1. Database Maintenance
echo "### DATABASE MAINTENANCE ###"

# VACUUM and ANALYZE critical tables
docker exec postgres psql -U orchestrator -c "
VACUUM ANALYZE task;
VACUUM ANALYZE task_run;  
VACUUM ANALYZE due_work;
VACUUM ANALYZE audit_log;
VACUUM ANALYZE worker_heartbeat;
"

# Update statistics
docker exec postgres psql -U orchestrator -c "ANALYZE;"

# Check table sizes and growth
docker exec postgres psql -U orchestrator -c "
SELECT 
  schemaname, tablename,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename) - pg_relation_size(schemaname||'.'||tablename)) as index_size
FROM pg_stat_user_tables 
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
"

# 2. Log Rotation and Cleanup
echo -e "\n### LOG CLEANUP ###"

# Rotate Docker logs (keep last 7 days)
find /var/lib/docker/containers -name "*-json.log" -mtime +7 -delete

# Clean old audit logs (keep last 90 days)
docker exec postgres psql -U orchestrator -c "
DELETE FROM audit_log WHERE at < now() - interval '90 days';
"

# Clean old task runs (keep last 30 days)
docker exec postgres psql -U orchestrator -c "
DELETE FROM task_run WHERE created_at < now() - interval '30 days';
"

# Clean completed due_work (keep last 7 days)
docker exec postgres psql -U orchestrator -c "
DELETE FROM due_work 
WHERE created_at < now() - interval '7 days'
  AND id NOT IN (SELECT DISTINCT task_id FROM task WHERE status = 'active');
"

# 3. Docker System Cleanup
echo -e "\n### DOCKER CLEANUP ###"
docker system prune -f
docker volume prune -f

# 4. Index Maintenance
echo -e "\n### INDEX MAINTENANCE ###"
docker exec postgres psql -U orchestrator -c "REINDEX DATABASE orchestrator;"

# 5. Performance Statistics Reset
docker exec postgres psql -U orchestrator -c "SELECT pg_stat_reset();"

echo "Weekly maintenance completed at $(date)"
```

### Monthly Maintenance (First Sunday 1:00 AM)
```bash
#!/bin/bash
# monthly_maintenance.sh - Monthly system maintenance

echo "=== MONTHLY MAINTENANCE - $(date) ==="

# 1. Full Database Backup
echo "### FULL DATABASE BACKUP ###"
backup_file="/backups/postgres/monthly_backup_$(date +%Y%m%d).sql"
docker exec postgres pg_dump -U orchestrator orchestrator > "$backup_file"
gzip "$backup_file"
echo "Full backup completed: ${backup_file}.gz"

# 2. Configuration Backup
echo -e "\n### CONFIGURATION BACKUP ###" 
tar czf "/backups/config/orchestrator_config_$(date +%Y%m%d).tar.gz" \
  ops/docker-compose*.yml \
  ops/prometheus/ \
  ops/grafana/ \
  ops/alertmanager/ \
  migrations/

# 3. Performance Analysis
echo -e "\n### MONTHLY PERFORMANCE ANALYSIS ###"
docker exec postgres psql -U orchestrator -c "
SELECT 
  'Total tasks processed: ' || COUNT(*),
  'Success rate: ' || ROUND(100.0 * COUNT(*) FILTER (WHERE success = true) / COUNT(*), 2) || '%',
  'Avg execution time: ' || ROUND(AVG(EXTRACT(EPOCH FROM (finished_at - started_at))), 2) || 's'
FROM task_run 
WHERE started_at > date_trunc('month', CURRENT_DATE - interval '1 month')
  AND started_at < date_trunc('month', CURRENT_DATE);
"

# 4. Capacity Planning Data
echo -e "\n### CAPACITY METRICS ###"
docker exec postgres psql -U orchestrator -c "
SELECT 
  date_trunc('day', created_at)::date as day,
  COUNT(*) as tasks_created
FROM task 
WHERE created_at > CURRENT_DATE - interval '30 days'
GROUP BY date_trunc('day', created_at)
ORDER BY day DESC
LIMIT 7;
"

# 5. Security Audit
echo -e "\n### SECURITY AUDIT ###"
docker exec postgres psql -U orchestrator -c "
SELECT 
  action, 
  COUNT(*) as count,
  COUNT(DISTINCT actor_agent_id) as unique_actors
FROM audit_log 
WHERE at > CURRENT_DATE - interval '30 days'
GROUP BY action 
ORDER BY count DESC;
"

# 6. Cleanup Old Backups (keep 6 months)
find /backups/ -name "*.gz" -mtime +180 -delete
find /backups/ -name "*.sql" -mtime +180 -delete

echo "Monthly maintenance completed at $(date)"
```

---

## 3. CAPACITY MONITORING & PLANNING

### Daily Capacity Check
```bash
#!/bin/bash
# capacity_check.sh - Daily capacity monitoring

echo "=== CAPACITY MONITORING - $(date) ==="

# 1. Database Growth Rate
echo "### DATABASE GROWTH ###"
docker exec postgres psql -U orchestrator -c "
SELECT 
  'Current DB size: ' || pg_size_pretty(pg_database_size('orchestrator')),
  'Estimated monthly growth: ' || pg_size_pretty(
    (pg_database_size('orchestrator') / EXTRACT(DAY FROM CURRENT_DATE - date_trunc('month', CURRENT_DATE))) * 30
  )
"

# 2. Queue Depth Trends  
echo -e "\n### QUEUE DEPTH ANALYSIS ###"
docker exec postgres psql -U orchestrator -c "
SELECT 
  date_trunc('hour', created_at) as hour,
  COUNT(*) as work_items_created,
  AVG(EXTRACT(EPOCH FROM (COALESCE(locked_until, now()) - created_at))) as avg_wait_seconds
FROM due_work 
WHERE created_at > now() - interval '24 hours'
GROUP BY date_trunc('hour', created_at)
ORDER BY hour DESC
LIMIT 12;
"

# 3. Worker Utilization
echo -e "\n### WORKER UTILIZATION ###" 
docker exec postgres psql -U orchestrator -c "
SELECT 
  worker_id,
  processed_count,
  EXTRACT(EPOCH FROM (now() - created_at))/3600 as hours_active,
  ROUND(processed_count / (EXTRACT(EPOCH FROM (now() - created_at))/3600), 2) as tasks_per_hour
FROM worker_heartbeat 
WHERE last_seen > now() - interval '1 hour'
ORDER BY tasks_per_hour DESC;
"

# 4. API Load Analysis
echo -e "\n### API PERFORMANCE ###"
# Check recent response times from Prometheus
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,rate(http_request_duration_seconds_bucket[5m]))" | \
  jq -r '.data.result[0].value[1] // "No data"' | \
  awk '{print "95th percentile response time: " $1 "s"}'

# 5. Resource Utilization Alerts
echo -e "\n### RESOURCE ALERTS ###"

# Check disk usage
DISK_USAGE=$(df / | awk 'NR==2 {print $5}' | tr -d '%')
if [ "$DISK_USAGE" -gt 85 ]; then
  echo "⚠️  DISK USAGE: ${DISK_USAGE}% - Consider cleanup or expansion"
else
  echo "✅ Disk usage: ${DISK_USAGE}% - Normal"
fi

# Check memory usage
MEMORY_USAGE=$(free | awk 'NR==2{printf "%.0f", $3*100/$2}')
if [ "$MEMORY_USAGE" -gt 90 ]; then
  echo "⚠️  MEMORY USAGE: ${MEMORY_USAGE}% - Consider scaling"
else
  echo "✅ Memory usage: ${MEMORY_USAGE}% - Normal"  
fi

# 6. Scaling Recommendations
echo -e "\n### SCALING RECOMMENDATIONS ###"

PENDING_WORK=$(docker exec postgres psql -U orchestrator -t -c "
SELECT COUNT(*) FROM due_work 
WHERE run_at <= now() AND (locked_until IS NULL OR locked_until < now());
" | tr -d ' ')

ACTIVE_WORKERS=$(docker exec postgres psql -U orchestrator -t -c "
SELECT COUNT(*) FROM worker_heartbeat 
WHERE last_seen > now() - interval '2 minutes';
" | tr -d ' ')

if [ "$PENDING_WORK" -gt 1000 ] && [ "$ACTIVE_WORKERS" -lt 5 ]; then
  echo "📈 RECOMMENDATION: Scale up workers (current: $ACTIVE_WORKERS, queue: $PENDING_WORK)"
elif [ "$PENDING_WORK" -lt 10 ] && [ "$ACTIVE_WORKERS" -gt 2 ]; then
  echo "📉 RECOMMENDATION: Consider scaling down workers (current: $ACTIVE_WORKERS, queue: $PENDING_WORK)"
else
  echo "✅ Current scaling appropriate (workers: $ACTIVE_WORKERS, queue: $PENDING_WORK)"
fi
```

### Resource Scaling Procedures
```bash
#!/bin/bash
# scaling_operations.sh - Dynamic resource scaling

OPERATION=$1
SCALE_COUNT=${2:-2}

case $OPERATION in
  "scale-up-workers")
    echo "Scaling up workers to $SCALE_COUNT instances"
    docker-compose -f ops/docker-compose.yml up -d --scale worker=$SCALE_COUNT
    sleep 10
    docker ps | grep worker
    ;;
    
  "scale-down-workers") 
    echo "Scaling down workers to $SCALE_COUNT instances"
    docker-compose -f ops/docker-compose.yml up -d --scale worker=$SCALE_COUNT
    sleep 10
    docker ps | grep worker
    ;;
    
  "emergency-scale")
    echo "Emergency scaling - adding maximum workers"
    docker-compose -f ops/docker-compose.yml up -d --scale worker=8
    echo "Emergency scaling completed - monitor performance"
    ;;
    
  "check-scaling")
    echo "Current scaling status:"
    echo "Workers: $(docker ps | grep worker | wc -l)"
    echo "API instances: $(docker ps | grep api | wc -l)"
    docker exec postgres psql -U orchestrator -c "
    SELECT COUNT(*) as active_workers FROM worker_heartbeat 
    WHERE last_seen > now() - interval '1 minute';"
    ;;
    
  *)
    echo "Usage: $0 {scale-up-workers|scale-down-workers|emergency-scale|check-scaling} [count]"
    exit 1
    ;;
esac
```

---

## 4. PERFORMANCE BASELINE VERIFICATION

### Performance Baseline Tests
```bash
#!/bin/bash
# performance_baseline.sh - Verify system performance against SLAs

echo "=== PERFORMANCE BASELINE VERIFICATION - $(date) ==="

# SLA Targets:
# - API response time: <200ms (95th percentile)
# - Task scheduling latency: <30 seconds  
# - Worker processing rate: >100 tasks/minute
# - Database query time: <100ms (95th percentile)

# 1. API Response Time Test
echo "### API PERFORMANCE TEST ###"
echo "Running 50 requests to measure response time..."

response_times=()
for i in {1..50}; do
  time=$(curl -s -w "%{time_total}" -o /dev/null http://localhost:8080/health 2>/dev/null || echo "999")
  response_times+=($time)
done

# Calculate 95th percentile (simple approximation)
IFS=$'\n' sorted=($(sort -n <<<"${response_times[*]}"))
p95_index=$((${#sorted[@]} * 95 / 100))
p95_time=${sorted[$p95_index]}

echo "95th percentile response time: ${p95_time}s"
if (( $(echo "$p95_time < 0.2" | bc -l) )); then
  echo "✅ API performance: MEETS SLA (<200ms)"
else
  echo "❌ API performance: BELOW SLA (${p95_time}s > 200ms)"
fi

# 2. Task Scheduling Latency Test
echo -e "\n### TASK SCHEDULING LATENCY TEST ###"

# Create test task scheduled for 30 seconds from now
TEST_TASK_TIME=$(date -d '+30 seconds' -Iseconds)
TEST_TASK_ID=$(curl -s -X POST http://localhost:8080/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Performance Test Task",
    "description": "Scheduling latency verification",
    "schedule_kind": "once",
    "schedule_expr": "'$TEST_TASK_TIME'",
    "payload": {"pipeline": [{"id": "test", "uses": "noop", "with": {}}]}
  }' | jq -r '.id' 2>/dev/null || echo "FAILED")

if [ "$TEST_TASK_ID" != "FAILED" ] && [ "$TEST_TASK_ID" != "null" ]; then
  echo "Test task created: $TEST_TASK_ID"
  echo "Scheduled for: $TEST_TASK_TIME"
  
  # Wait for execution and measure latency
  sleep 35
  
  execution_time=$(docker exec postgres psql -U orchestrator -t -c "
  SELECT started_at FROM task_run 
  WHERE task_id = '$TEST_TASK_ID' 
  ORDER BY started_at DESC LIMIT 1;
  " | tr -d ' ')
  
  if [ -n "$execution_time" ] && [ "$execution_time" != "" ]; then
    # Calculate latency (simplified)
    echo "✅ Task scheduling: WORKING"
    echo "Execution started at: $execution_time"
  else
    echo "❌ Task scheduling: FAILED - No execution recorded"
  fi
  
  # Cleanup test task
  curl -s -X DELETE "http://localhost:8080/tasks/$TEST_TASK_ID" > /dev/null
else
  echo "❌ Task scheduling: FAILED - Could not create test task"
fi

# 3. Database Performance Test
echo -e "\n### DATABASE PERFORMANCE TEST ###"

query_times=()
for i in {1..10}; do
  start_time=$(date +%s%N)
  docker exec postgres psql -U orchestrator -c "
  SELECT COUNT(*) FROM task t 
  JOIN task_run tr ON t.id = tr.task_id 
  WHERE t.created_at > now() - interval '24 hours';
  " > /dev/null 2>&1
  end_time=$(date +%s%N)
  
  query_time_ms=$(( (end_time - start_time) / 1000000 ))
  query_times+=($query_time_ms)
done

# Calculate average query time
avg_query_time=0
for time in "${query_times[@]}"; do
  avg_query_time=$((avg_query_time + time))
done
avg_query_time=$((avg_query_time / ${#query_times[@]}))

echo "Average database query time: ${avg_query_time}ms"
if [ "$avg_query_time" -lt 100 ]; then
  echo "✅ Database performance: MEETS SLA (<100ms)"
else
  echo "❌ Database performance: BELOW SLA (${avg_query_time}ms > 100ms)"
fi

# 4. Worker Processing Rate Test  
echo -e "\n### WORKER PROCESSING RATE TEST ###"

# Check processing rate over last hour
processing_rate=$(docker exec postgres psql -U orchestrator -t -c "
SELECT 
  COALESCE(COUNT(*) / GREATEST(EXTRACT(EPOCH FROM (now() - MIN(started_at)))/60, 1), 0) as tasks_per_minute
FROM task_run 
WHERE started_at > now() - interval '1 hour' 
  AND finished_at IS NOT NULL;
" | tr -d ' ' | cut -d'.' -f1)

echo "Current processing rate: ${processing_rate} tasks/minute"
if [ "$processing_rate" -gt 100 ]; then
  echo "✅ Worker processing rate: MEETS SLA (>100 tasks/min)"
else
  echo "⚠️  Worker processing rate: BELOW SLA (${processing_rate} < 100 tasks/min)"
fi

# 5. Overall System Health Score
echo -e "\n### OVERALL PERFORMANCE SUMMARY ###"
echo "Timestamp: $(date -Iseconds)"
echo "API Response Time: $([ $(echo "$p95_time < 0.2" | bc -l) = 1 ] && echo "PASS" || echo "FAIL")"
echo "Database Performance: $([ "$avg_query_time" -lt 100 ] && echo "PASS" || echo "FAIL")"  
echo "Worker Processing Rate: $([ "$processing_rate" -gt 100 ] && echo "PASS" || echo "CAUTION")"
echo "Overall Status: $([ $(echo "$p95_time < 0.2" | bc -l) = 1 ] && [ "$avg_query_time" -lt 100 ] && echo "✅ HEALTHY" || echo "⚠️  NEEDS ATTENTION")"
```

---

## 5. OPERATIONAL PROCEDURES

### Service Restart Procedures
```bash
#!/bin/bash  
# service_restart.sh - Safe service restart procedures

SERVICE=$1

case $SERVICE in
  "api")
    echo "Restarting API service..."
    docker-compose -f ops/docker-compose.yml restart api
    sleep 10
    curl -f http://localhost:8080/health || echo "API health check failed"
    ;;
    
  "scheduler") 
    echo "Restarting Scheduler service..."
    docker-compose -f ops/docker-compose.yml restart scheduler
    sleep 5
    docker logs scheduler --tail 10
    ;;
    
  "workers")
    echo "Rolling restart of worker services..."
    docker-compose -f ops/docker-compose.yml restart worker
    sleep 10
    docker exec postgres psql -U orchestrator -c "
    SELECT COUNT(*) as active_workers FROM worker_heartbeat 
    WHERE last_seen > now() - interval '1 minute';"
    ;;
    
  "database")
    echo "⚠️  Database restart requires maintenance window"
    echo "1. Stop all dependent services"
    docker-compose -f ops/docker-compose.yml stop api scheduler worker
    echo "2. Restart PostgreSQL"
    docker-compose -f ops/docker-compose.yml restart postgres
    sleep 15
    echo "3. Verify database is ready"
    timeout 60s bash -c 'until docker exec postgres pg_isready -U orchestrator; do sleep 2; done'
    echo "4. Restart dependent services"
    docker-compose -f ops/docker-compose.yml start api scheduler worker
    ;;
    
  "redis")
    echo "Restarting Redis service..."
    echo "⚠️  This will clear cache and may impact performance briefly"
    docker-compose -f ops/docker-compose.yml restart redis
    sleep 5
    docker exec redis redis-cli ping
    ;;
    
  "all")
    echo "Full system restart..."
    docker-compose -f ops/docker-compose.yml restart
    sleep 30
    ./ops/health_check.sh --full-system
    ;;
    
  *)
    echo "Usage: $0 {api|scheduler|workers|database|redis|all}"
    echo "Available services:"
    docker-compose -f ops/docker-compose.yml config --services
    exit 1
    ;;
esac

echo "Service restart completed for: $SERVICE"
```

### Log Analysis Procedures  
```bash
#!/bin/bash
# log_analysis.sh - Centralized log analysis and investigation

TIMEFRAME=${1:-"1h"}  # Default to last hour
SERVICE=${2:-"all"}   # Default to all services

echo "=== LOG ANALYSIS - Last $TIMEFRAME for $SERVICE ==="

# 1. Error Pattern Analysis
echo "### ERROR PATTERNS ###"
case $SERVICE in
  "api"|"all")
    echo "API Errors (last $TIMEFRAME):"
    docker logs api --since $TIMEFRAME 2>&1 | \
      grep -E "(ERROR|CRITICAL|FATAL)" | \
      awk '{print $3, $4}' | sort | uniq -c | sort -nr
    ;;
esac

case $SERVICE in  
  "database"|"all")
    echo -e "\nDatabase Errors (last $TIMEFRAME):"
    docker logs postgres --since $TIMEFRAME 2>&1 | \
      grep -E "(ERROR|FATAL|PANIC)" | \
      head -20
    ;;
esac

case $SERVICE in
  "workers"|"all")
    echo -e "\nWorker Errors (last $TIMEFRAME):"
    docker logs worker --since $TIMEFRAME 2>&1 | \
      grep -E "(ERROR|CRITICAL|FATAL)" | \
      head -20
    ;;
esac

# 2. Performance Issues
echo -e "\n### PERFORMANCE INDICATORS ###"
docker logs api --since $TIMEFRAME 2>&1 | \
  grep -E "slow|timeout|high.*latency" | \
  head -10

# 3. Security Events  
echo -e "\n### SECURITY EVENTS ###"
docker exec postgres psql -U orchestrator -c "
SELECT at, action, details 
FROM audit_log 
WHERE at > now() - interval '$TIMEFRAME'
  AND action IN ('login_failed', 'unauthorized_access', 'permission_denied')
ORDER BY at DESC LIMIT 10;
"

# 4. Database Performance Issues
echo -e "\n### DATABASE PERFORMANCE ###"
docker logs postgres --since $TIMEFRAME 2>&1 | \
  grep -E "(slow query|deadlock|lock timeout)" | \
  head -10

# 5. Resource Exhaustion Events
echo -e "\n### RESOURCE WARNINGS ###"
docker logs api --since $TIMEFRAME 2>&1 | \
  grep -iE "(memory|disk|connection.*pool)" | \
  head -10

echo -e "\nLog analysis completed for timeframe: $TIMEFRAME"
```

**Last Updated**: 2025-01-10  
**Next Review**: 2025-04-10  
**Owner**: Operations Team  
**Approver**: Technical Lead