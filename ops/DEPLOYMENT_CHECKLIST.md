# Production Deployment Checklist
## Enterprise Task Scheduling System Go-Live Validation

### Pre-Deployment Requirements
- [ ] All development testing completed with >95% pass rate
- [ ] Security audit completed and vulnerabilities addressed
- [ ] Performance benchmarks meet SLA requirements
- [ ] Disaster recovery procedures tested and verified
- [ ] Monitoring and alerting fully configured
- [ ] Operations team trained on procedures

---

## 1. PRE-PRODUCTION VALIDATION

### Code Quality & Testing Checklist
```bash
# 1. Run comprehensive test suite
echo "=== RUNNING COMPREHENSIVE TEST SUITE ==="

# Unit tests
python -m pytest tests/unit/ -v --cov=api --cov=engine --cov=scheduler --cov=workers \
  --cov-report=html --cov-report=term-missing

# Integration tests  
python -m pytest tests/integration/ -v --maxfail=5

# Load testing
python -m pytest tests/load/ -v

# Chaos testing
python -m pytest tests/chaos/ -v

# API contract testing
python -m pytest tests/test_api.py -v

echo "Test Results Summary:"
echo "- Unit test coverage: $(coverage report --show-missing | tail -1)"
echo "- Integration tests: $(pytest tests/integration/ --tb=no -q | tail -1)"
echo "- Load tests: $(pytest tests/load/ --tb=no -q | tail -1)"
```

### Security Validation Checklist
```bash
# 2. Security hardening verification
echo "=== SECURITY VALIDATION ==="

# Check for hardcoded secrets
echo "Checking for hardcoded secrets..."
grep -r -E "(password|secret|key|token)" --exclude-dir=.git --exclude="*.md" . | \
  grep -v "example\|template\|TODO" || echo "✅ No hardcoded secrets found"

# Verify JWT configuration
echo "JWT Configuration:"
docker-compose -f ops/docker-compose.yml config | grep -A 5 -B 5 JWT

# Check file permissions
echo "Checking file permissions..."
find . -name "*.py" -perm /o+w -exec echo "World-writable: {}" \;
find ops/ -name "*.yml" -perm /o+w -exec echo "World-writable config: {}" \;

# Database security
echo "Database security check:"
docker exec postgres psql -U orchestrator -c "
SELECT rolname, rolsuper, rolcreaterole, rolcreatedb, rolcanlogin 
FROM pg_roles WHERE rolcanlogin = true;
"

# Network security
echo "Network configuration:"
docker network inspect ordinaut-network | jq '.[].IPAM'
```

### Performance Validation Checklist
```bash
# 3. Performance benchmark validation
echo "=== PERFORMANCE VALIDATION ==="

# API response time benchmark
echo "API Response Time Test (100 requests):"
ab -n 100 -c 10 http://localhost:8080/health | grep -A 20 "Time per request"

# Database performance test
echo "Database Performance Test:"
docker exec postgres psql -U orchestrator -c "
EXPLAIN ANALYZE SELECT COUNT(*) FROM task t 
JOIN task_run tr ON t.id = tr.task_id 
WHERE t.created_at > now() - interval '24 hours';
"

# Memory usage baseline
echo "Memory Usage Baseline:"
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}"

# Task processing rate test
echo "Task Processing Rate Test:"
# Create 50 test tasks and measure processing time
start_time=$(date +%s)
for i in {1..50}; do
  curl -s -X POST http://localhost:8080/tasks \
    -H "Content-Type: application/json" \
    -d '{
      "title": "Load Test Task '$i'",
      "description": "Performance validation task",
      "schedule_kind": "once",
      "schedule_expr": "'$(date -d '+10 seconds' -Iseconds)'",
      "payload": {"pipeline": [{"id": "test", "uses": "noop"}]}
    }' > /dev/null
done

echo "Created 50 test tasks, monitoring completion..."
sleep 60

completed_tasks=$(docker exec postgres psql -U orchestrator -t -c "
SELECT COUNT(*) FROM task_run 
WHERE started_at > now() - interval '2 minutes' 
  AND finished_at IS NOT NULL;
")

end_time=$(date +%s)
duration=$((end_time - start_time))
rate=$((completed_tasks * 60 / duration))

echo "Completed tasks: $completed_tasks in ${duration}s (${rate} tasks/minute)"

if [ "$rate" -gt 100 ]; then
  echo "✅ Performance requirement met (>100 tasks/minute)"
else
  echo "❌ Performance requirement NOT met ($rate < 100 tasks/minute)"
fi
```

---

## 2. INFRASTRUCTURE READINESS

### Environment Configuration Checklist
```bash
# 4. Production environment validation
echo "=== ENVIRONMENT CONFIGURATION ==="

# Docker configuration
echo "Docker Environment:"
docker --version
docker-compose --version
docker system info | grep -E "(CPUs|Total Memory|Server Version)"

# Storage capacity
echo "Storage Capacity:"
df -h | grep -E "(/var/lib/docker|/backups|/$)"

# Network configuration
echo "Network Configuration:"
docker network ls | grep orchestrator
ss -tlnp | grep -E "(8080|5432|6379|9090|3000)"

# Environment variables validation
echo "Environment Variables Check:"
docker-compose -f ops/docker-compose.yml config --quiet && echo "✅ Docker Compose config valid" || echo "❌ Docker Compose config invalid"

# SSL/TLS certificates (if applicable)
if [ -d "/etc/ssl/orchestrator" ]; then
  echo "SSL Certificates:"
  openssl x509 -in /etc/ssl/orchestrator/cert.pem -text -noout | grep -A2 "Validity"
fi

# Backup storage verification
echo "Backup Storage:"
ls -la /backups/ && echo "✅ Backup directories accessible" || echo "❌ Backup directories missing"
```

### Database Readiness Checklist
```bash
# 5. Database production readiness
echo "=== DATABASE READINESS ==="

# Database version and configuration
echo "PostgreSQL Configuration:"
docker exec postgres psql -U orchestrator -c "SELECT version();"
docker exec postgres psql -U orchestrator -c "SHOW ALL;" | grep -E "(shared_buffers|work_mem|effective_cache_size|checkpoint_completion_target)"

# Database size and statistics
echo "Database Statistics:"
docker exec postgres psql -U orchestrator -c "
SELECT 
  schemaname,
  tablename,
  n_tup_ins as inserts,
  n_tup_upd as updates,
  n_tup_del as deletes,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_stat_user_tables 
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
"

# Index analysis
echo "Index Analysis:"
docker exec postgres psql -U orchestrator -c "
SELECT 
  schemaname, 
  tablename, 
  indexname,
  idx_tup_read,
  idx_tup_fetch
FROM pg_stat_user_indexes 
WHERE idx_tup_read > 0
ORDER BY idx_tup_read DESC;
"

# Connection limits
echo "Connection Configuration:"
docker exec postgres psql -U orchestrator -c "
SELECT 
  setting as max_connections,
  (SELECT count(*) FROM pg_stat_activity) as current_connections
FROM pg_settings WHERE name = 'max_connections';
"

# Backup verification
echo "Backup System Check:"
ls -la /backups/postgres/ | tail -5
test -f /usr/local/bin/daily_backup.sh && echo "✅ Backup script installed" || echo "❌ Backup script missing"
crontab -l | grep backup && echo "✅ Backup cron job configured" || echo "❌ Backup cron job missing"
```

---

## 3. SECURITY HARDENING VERIFICATION

### Security Configuration Checklist
```bash
# 6. Security hardening verification
echo "=== SECURITY HARDENING ==="

# Authentication configuration
echo "Authentication Configuration:"
docker-compose -f ops/docker-compose.yml config | grep -A 10 -B 5 JWT_SECRET_KEY

# Rate limiting verification  
echo "Rate Limiting Configuration:"
docker-compose -f ops/docker-compose.yml config | grep -A 5 -B 5 RATE_LIMIT

# Database security
echo "Database Security:"
docker exec postgres psql -U orchestrator -c "
SELECT datname, datacl FROM pg_database WHERE datname = 'orchestrator';
"

# Container security
echo "Container Security:"
docker inspect postgres | jq '.[].HostConfig.SecurityOpt'
docker inspect api | jq '.[].HostConfig.SecurityOpt'

# Network security
echo "Network Security:"
docker network inspect ordinaut-network | jq '.[].Options'

# File permissions audit
echo "Critical File Permissions:"
ls -la ops/docker-compose*.yml
ls -la migrations/
ls -la /usr/local/bin/*backup* 2>/dev/null || echo "Backup scripts not found"
```

### Audit Logging Verification
```bash
# 7. Audit logging verification
echo "=== AUDIT LOGGING VERIFICATION ==="

# Test audit log creation
echo "Testing audit log functionality..."
TEST_AGENT_ID=$(docker exec postgres psql -U orchestrator -t -c "
SELECT id FROM agent LIMIT 1;" | tr -d ' ')

if [ -n "$TEST_AGENT_ID" ]; then
  # Create test audit entry
  docker exec postgres psql -U orchestrator -c "
  INSERT INTO audit_log (actor_agent_id, action, subject_id, details) 
  VALUES ('$TEST_AGENT_ID', 'test_action', null, '{\"test\": true}');
  "
  
  # Verify audit entry creation
  AUDIT_COUNT=$(docker exec postgres psql -U orchestrator -t -c "
  SELECT COUNT(*) FROM audit_log 
  WHERE action = 'test_action' AND at > now() - interval '1 minute';
  " | tr -d ' ')
  
  if [ "$AUDIT_COUNT" -gt 0 ]; then
    echo "✅ Audit logging functional"
  else
    echo "❌ Audit logging NOT functional"
  fi
else
  echo "❌ Cannot test audit logging - no agents found"
fi

# Check audit log retention
echo "Audit Log Statistics:"
docker exec postgres psql -U orchestrator -c "
SELECT 
  action,
  COUNT(*) as count,
  MIN(at) as oldest,
  MAX(at) as newest
FROM audit_log 
GROUP BY action 
ORDER BY count DESC;
"
```

---

## 4. MONITORING & OBSERVABILITY

### Monitoring Stack Verification
```bash
# 8. Monitoring and alerting verification
echo "=== MONITORING STACK VERIFICATION ==="

# Prometheus health
echo "Prometheus Status:"
curl -f http://localhost:9090/-/healthy && echo "✅ Prometheus healthy" || echo "❌ Prometheus unhealthy"
curl -f http://localhost:9090/-/ready && echo "✅ Prometheus ready" || echo "❌ Prometheus not ready"

# Check Prometheus targets
echo "Prometheus Targets:"
curl -s http://localhost:9090/api/v1/targets | \
  jq -r '.data.activeTargets[] | "\(.labels.job): \(.health)"'

# Grafana health
echo "Grafana Status:"
curl -f http://localhost:3000/api/health && echo "✅ Grafana healthy" || echo "❌ Grafana unhealthy"

# AlertManager health
echo "AlertManager Status:"
curl -f http://localhost:9093/api/v1/status && echo "✅ AlertManager healthy" || echo "❌ AlertManager unhealthy"

# Test alert firing
echo "Testing Alert System:"
curl -X POST http://localhost:9093/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '[{
    "labels": {"alertname": "DeploymentTest", "severity": "info"},
    "annotations": {"summary": "Deployment validation test alert"},
    "startsAt": "'$(date -Iseconds)'",
    "endsAt": "'$(date -d '+5 minutes' -Iseconds)'"
  }]'

sleep 10
FIRING_ALERTS=$(curl -s http://localhost:9093/api/v1/alerts | \
  jq '.data[] | select(.labels.alertname == "DeploymentTest") | length')

if [ "$FIRING_ALERTS" -gt 0 ]; then
  echo "✅ Alert system functional"
else
  echo "❌ Alert system NOT functional"
fi
```

### Metrics Collection Verification
```bash
# 9. Metrics collection verification
echo "=== METRICS COLLECTION VERIFICATION ==="

# Verify key metrics are being collected
METRICS_TO_CHECK=(
  "up"
  "http_requests_total"
  "database_connections"
  "task_processing_rate"
  "worker_active_count"
)

echo "Checking key metrics availability:"
for metric in "${METRICS_TO_CHECK[@]}"; do
  result=$(curl -s "http://localhost:9090/api/v1/query?query=$metric" | \
    jq '.data.result | length')
  
  if [ "$result" -gt 0 ]; then
    echo "✅ $metric: Available"
  else
    echo "⚠️  $metric: No data (may be normal for new deployment)"
  fi
done

# Check metric collection rate
echo "Metric Collection Rate:"
curl -s "http://localhost:9090/api/v1/query?query=prometheus_tsdb_samples_appended_total" | \
  jq -r '.data.result[0].value[1] + " samples/second"'
```

---

## 5. OPERATIONAL READINESS

### Operations Team Readiness Checklist
```bash
# 10. Operations team readiness verification
echo "=== OPERATIONS READINESS ==="

# Documentation verification
echo "Documentation Check:"
REQUIRED_DOCS=(
  "ops/DISASTER_RECOVERY.md"
  "ops/INCIDENT_RESPONSE.md"
  "ops/PRODUCTION_RUNBOOK.md"
  "ops/MONITORING_PLAYBOOK.md"
  "ops/BACKUP_PROCEDURES.md"
)

for doc in "${REQUIRED_DOCS[@]}"; do
  if [ -f "$doc" ]; then
    echo "✅ $doc: Present"
  else
    echo "❌ $doc: Missing"
  fi
done

# Operational scripts verification
echo "Operational Scripts Check:"
REQUIRED_SCRIPTS=(
  "/usr/local/bin/daily_backup.sh"
  "/usr/local/bin/health_check.sh"
  "/usr/local/bin/service_restart.sh"
)

for script in "${REQUIRED_SCRIPTS[@]}"; do
  if [ -f "$script" ] && [ -x "$script" ]; then
    echo "✅ $(basename $script): Installed and executable"
  else
    echo "❌ $(basename $script): Missing or not executable"
  fi
done

# Cron jobs verification
echo "Scheduled Jobs Check:"
crontab -l | grep -E "(backup|health)" || echo "⚠️  No scheduled jobs found"

# Contact information verification
echo "Emergency Contact Information:"
echo "- Technical Lead: [FILL IN]"
echo "- Database Admin: [FILL IN]" 
echo "- Security Officer: [FILL IN]"
echo "- Operations Manager: [FILL IN]"
```

### Capacity Planning Verification
```bash
# 11. Capacity planning verification
echo "=== CAPACITY PLANNING VERIFICATION ==="

# Resource utilization baseline
echo "Resource Utilization Baseline:"
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"

# Database capacity analysis
echo "Database Capacity Analysis:"
docker exec postgres psql -U orchestrator -c "
SELECT 
  'Current database size: ' || pg_size_pretty(pg_database_size('orchestrator')),
  'Estimated daily growth: ' || pg_size_pretty(
    (SELECT SUM(pg_total_relation_size(schemaname||'.'||tablename)) 
     FROM pg_stat_user_tables WHERE n_tup_ins > 100) / 30
  ) as daily_growth_estimate;
"

# Work queue capacity analysis  
echo "Work Queue Capacity Analysis:"
docker exec postgres psql -U orchestrator -c "
WITH queue_stats AS (
  SELECT 
    COUNT(*) as current_queue_size,
    AVG(EXTRACT(EPOCH FROM (COALESCE(locked_until, now()) - created_at))) as avg_wait_time
  FROM due_work 
  WHERE created_at > now() - interval '1 hour'
)
SELECT 
  current_queue_size,
  ROUND(avg_wait_time, 2) as avg_wait_seconds,
  CASE 
    WHEN current_queue_size > 1000 THEN 'Scale up workers recommended'
    WHEN current_queue_size < 10 THEN 'Current capacity sufficient'
    ELSE 'Monitor closely'
  END as recommendation
FROM queue_stats;
"

# Storage growth projection
echo "Storage Growth Projection:"
CURRENT_SIZE=$(du -sh /var/lib/docker | cut -f1)
BACKUP_SIZE=$(du -sh /backups 2>/dev/null | cut -f1 || echo "N/A")
echo "Current Docker storage: $CURRENT_SIZE"
echo "Current backup storage: $BACKUP_SIZE"

# Network capacity
echo "Network Configuration:"
ss -i | grep -E "(ESTAB.*:8080|ESTAB.*:5432)" | wc -l | xargs echo "Active connections:"
```

---

## 6. GO-LIVE DECISION FRAMEWORK

### Pre-Go-Live Approval Checklist
- [ ] **Technical Validation** (All tests pass, performance meets SLA)
- [ ] **Security Clearance** (Security audit complete, vulnerabilities resolved)
- [ ] **Infrastructure Ready** (Environment configured, resources allocated)
- [ ] **Monitoring Active** (Full observability stack operational)
- [ ] **Backup Systems** (Backup and recovery procedures tested)
- [ ] **Operations Ready** (Team trained, procedures documented)
- [ ] **Rollback Plan** (Rollback procedures tested and ready)

### Go-Live Execution Checklist
```bash
# 12. Final go-live validation
echo "=== FINAL GO-LIVE VALIDATION ==="

# Full system health check
./ops/health_check.sh --full-system

# Load test execution
echo "Executing final load test..."
python -m pytest tests/load/test_comprehensive_performance.py -v

# Security scan
echo "Final security validation..."
# Run security scanning tools if available
# docker run --rm -v $(pwd):/app security-scanner:latest /app

# Data integrity verification
echo "Data integrity verification..."
docker exec postgres psql -U orchestrator -c "
SELECT 
  'System agent exists: ' || CASE WHEN COUNT(*) > 0 THEN 'YES' ELSE 'NO' END
FROM agent WHERE name = 'system';

SELECT 
  'Database constraints valid: ' || 
  CASE WHEN COUNT(*) = 0 THEN 'YES' ELSE 'NO - ' || COUNT(*) || ' violations' END
FROM (
  SELECT 1 FROM task WHERE created_by NOT IN (SELECT id FROM agent)
  UNION ALL
  SELECT 1 FROM task_run WHERE task_id NOT IN (SELECT id FROM task)
  UNION ALL  
  SELECT 1 FROM due_work WHERE task_id NOT IN (SELECT id FROM task)
) violations;
"

# Performance baseline establishment
echo "Establishing performance baseline..."
./ops/performance_baseline.sh > /var/log/production_baseline_$(date +%Y%m%d_%H%M%S).log

echo "=== GO-LIVE READINESS ASSESSMENT ==="
echo "Timestamp: $(date -Iseconds)"
echo "System Status: $(curl -sf http://localhost:8080/health && echo 'HEALTHY' || echo 'UNHEALTHY')"
echo "Database Status: $(docker exec postgres pg_isready -U orchestrator && echo 'READY' || echo 'NOT READY')"
echo "Monitoring Status: $(curl -sf http://localhost:9090/-/healthy && echo 'ACTIVE' || echo 'INACTIVE')"

echo ""
echo "🚀 PRODUCTION DEPLOYMENT CHECKLIST COMPLETED"
echo "Review all validation results before proceeding with go-live decision."
```

### Post-Go-Live Monitoring (First 24 Hours)
```bash
# 13. Post-deployment monitoring checklist
cat > /usr/local/bin/post_golive_monitoring.sh << 'EOF'
#!/bin/bash
# post_golive_monitoring.sh - Intensive monitoring for first 24 hours

echo "=== POST-GO-LIVE MONITORING - $(date) ==="

# Continuous health monitoring
for i in {1..24}; do
  echo "Hour $i monitoring..."
  
  # API health
  api_status=$(curl -sf http://localhost:8080/health && echo "OK" || echo "FAIL")
  echo "$(date): API Status: $api_status"
  
  # Database performance  
  db_connections=$(docker exec postgres psql -U orchestrator -t -c "
  SELECT count(*) FROM pg_stat_activity WHERE datname = 'orchestrator';" | tr -d ' ')
  echo "$(date): DB Connections: $db_connections"
  
  # Task processing rate
  tasks_processed=$(docker exec postgres psql -U orchestrator -t -c "
  SELECT COUNT(*) FROM task_run 
  WHERE started_at > now() - interval '1 hour' AND finished_at IS NOT NULL;" | tr -d ' ')
  echo "$(date): Tasks Processed (last hour): $tasks_processed"
  
  # Error rate check
  error_count=$(docker logs api --since 1h 2>&1 | grep -c ERROR)
  echo "$(date): Error Count (last hour): $error_count"
  
  # Alert status
  firing_alerts=$(curl -s http://localhost:9093/api/v1/alerts | \
    jq '.data[] | select(.status.state == "firing") | length' 2>/dev/null || echo "0")
  echo "$(date): Firing Alerts: $firing_alerts"
  
  if [ "$api_status" != "OK" ] || [ "$error_count" -gt 50 ] || [ "$firing_alerts" -gt 5 ]; then
    echo "⚠️  ATTENTION REQUIRED - Hour $i"
    # Send alert to operations team
    echo "Production system requires attention at $(date)" | \
      mail -s "URGENT: Production System Alert" ops-team@example.com 2>/dev/null || true
  fi
  
  sleep 3600  # Wait 1 hour
done

echo "=== 24-HOUR POST-GO-LIVE MONITORING COMPLETED ==="
EOF

chmod +x /usr/local/bin/post_golive_monitoring.sh

# Schedule intensive monitoring (run in background)
nohup /usr/local/bin/post_golive_monitoring.sh > /var/log/post_golive_monitoring.log 2>&1 &
```

### Rollback Criteria & Procedures
**Immediate Rollback Triggers:**
- API unavailable for >10 minutes
- Database corruption detected
- Security breach confirmed
- Error rate >20% for >15 minutes
- Performance degradation >50% from baseline

**Rollback Procedure:**
1. Stop all services: `docker-compose -f ops/docker-compose.yml down`
2. Restore previous version from git: `git checkout [previous-release-tag]`
3. Restore database from backup if needed (see DISASTER_RECOVERY.md)
4. Start previous version: `docker-compose -f ops/docker-compose.yml up -d`
5. Verify system health and notify stakeholders

**Success Criteria (No Rollback):**
- [ ] System stable for 24 hours
- [ ] Performance within 10% of baseline  
- [ ] Error rate <1%
- [ ] No critical alerts fired
- [ ] User/agent feedback positive

**Last Updated**: 2025-01-10  
**Next Review**: 2025-04-10  
**Owner**: Operations Team  
**Approver**: Technical Lead