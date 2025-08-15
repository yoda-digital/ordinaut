# Incident Response Procedures
## Enterprise Task Scheduling System

### Incident Response Team Structure
- **Incident Commander**: Technical Lead (Primary on-call)
- **Technical Lead**: System Architect (Secondary on-call)
- **Database Specialist**: Database Administrator
- **Security Officer**: Security Team Lead
- **Communications Lead**: Operations Manager

---

## 1. ALERT ESCALATION MATRIX

### Severity Levels & Response Times

| Severity | Response Time | Resolution SLA | Escalation |
|----------|---------------|----------------|------------|
| **P0 - Critical** | 5 minutes | 30 minutes | Immediate all-hands |
| **P1 - High** | 15 minutes | 2 hours | Technical leads |
| **P2 - Medium** | 30 minutes | 8 hours | Operations team |
| **P3 - Low** | 2 hours | 24 hours | Next business day |

### Critical (P0) Alerts - Immediate Response Required
- `TaskSchedulerAPIDown` - API service unavailable
- `TaskSchedulerDatabaseDown` - PostgreSQL connection failures
- `NoActiveWorkers` - All workers offline
- `SecurityBreach` - Unauthorized access detected
- `DataCorruption` - Database integrity violations
- `HighErrorRate` - >10% API error rate for 5+ minutes

### High Priority (P1) Alerts - 15 Minute Response
- `HighAPILatency` - API response time >2 seconds
- `DatabaseSlowQueries` - Query performance degraded
- `SchedulerOffline` - Task scheduling stopped
- `WorkerHealthDegraded` - <50% workers operational
- `DiskSpaceCritical` - <10% disk space remaining
- `MemoryUsageCritical` - >90% memory utilization

---

## 2. INCIDENT RESPONSE PROCEDURES

### P0 Critical Incident Response
```bash
# IMMEDIATE ACTIONS (Within 5 minutes)

# 1. Acknowledge alert and notify team
slack-notify "#incident-response" "P0 INCIDENT: $(alert_name) - $(incident_commander) responding"

# 2. Quick system assessment
curl -f http://localhost:8080/health || echo "API DOWN"
docker ps | grep -E "(api|postgres|redis|scheduler|worker)" | grep -v "Up"

# 3. Check system status dashboard
curl -s http://localhost:9090/api/v1/query?query=up | jq '.data.result'

# 4. Start incident bridge
# Conference bridge: +1-XXX-XXX-XXXX, PIN: XXXX
echo "Incident bridge active - all responders join immediately"

# 5. Begin incident log
echo "$(date -Iseconds) [IC] P0 incident started: $(alert_name)" >> /var/log/incidents/$(date +%Y%m%d_%H%M%S)_incident.log
```

### Service-Specific Response Procedures

#### API Service Down (`TaskSchedulerAPIDown`)
```bash
# Diagnosis steps
echo "=== API SERVICE INCIDENT RESPONSE ==="

# Check container status
docker ps | grep api
docker logs api --tail 50 | grep -E "(ERROR|FATAL|CRITICAL)"

# Check health endpoint from inside network
docker exec redis redis-cli ping
docker exec postgres pg_isready -U orchestrator

# Verify load balancer/proxy status
curl -I http://localhost:8080/health
curl -I http://localhost:8080/health/ready

# Check resource utilization
docker stats api --no-stream

# Common resolutions:
# 1. Container restart
docker-compose -f ops/docker-compose.yml restart api

# 2. Database connection issues
docker exec api python -c "
import asyncpg
import asyncio
async def test_db():
    try:
        conn = await asyncpg.connect('postgresql://orchestrator:orchestrator_pw@postgres:5432/orchestrator')
        await conn.close()
        print('DB connection OK')
    except Exception as e:
        print(f'DB connection FAILED: {e}')
asyncio.run(test_db())
"

# 3. Rollback deployment if recent
if [ -n "$LAST_DEPLOYMENT_TIME" ] && [ $(($(date +%s) - LAST_DEPLOYMENT_TIME)) -lt 3600 ]; then
    echo "Recent deployment detected - initiating rollback"
    git log --oneline -10
    # Rollback procedure here
fi
```

#### Database Down (`TaskSchedulerDatabaseDown`)
```bash
# Database incident response
echo "=== DATABASE INCIDENT RESPONSE ==="

# Check PostgreSQL container
docker ps | grep postgres
docker logs postgres --tail 30

# Check disk space
df -h /var/lib/docker/volumes/

# Attempt database connection
docker exec postgres pg_isready -U orchestrator
docker exec postgres psql -U orchestrator -c "SELECT version();"

# Check for corruption
docker exec postgres psql -U orchestrator -c "
SELECT datname, pg_size_pretty(pg_database_size(datname)) 
FROM pg_database WHERE datname = 'orchestrator';
"

# Check active connections
docker exec postgres psql -U orchestrator -c "
SELECT count(*), state FROM pg_stat_activity 
WHERE datname = 'orchestrator' GROUP BY state;
"

# Emergency measures:
# 1. Restart PostgreSQL
docker-compose -f ops/docker-compose.yml restart postgres

# 2. If corruption suspected, immediate backup
docker exec postgres pg_dump -U orchestrator orchestrator > emergency_backup_$(date +%Y%m%d_%H%M%S).sql

# 3. Check WAL logs for issues
docker exec postgres ls -la /var/lib/postgresql/data/log/
```

#### No Active Workers (`NoActiveWorkers`)
```bash
# Worker failure response
echo "=== WORKER INCIDENT RESPONSE ==="

# Check worker container status
docker ps | grep worker
docker logs worker --tail 50

# Check worker heartbeats in database
docker exec postgres psql -U orchestrator -c "
SELECT worker_id, last_seen, processed_count 
FROM worker_heartbeat 
WHERE last_seen > now() - interval '5 minutes'
ORDER BY last_seen DESC;
"

# Check for work queue backup
docker exec postgres psql -U orchestrator -c "
SELECT COUNT(*) as pending_work, 
       MIN(run_at) as oldest_work,
       MAX(run_at) as newest_work
FROM due_work 
WHERE run_at <= now() 
  AND (locked_until IS NULL OR locked_until < now());
"

# Restart workers
docker-compose -f ops/docker-compose.yml restart worker

# Scale up workers temporarily
docker-compose -f ops/docker-compose.yml up -d --scale worker=4

# Check resource constraints
docker stats worker --no-stream
free -h
df -h
```

#### Security Breach (`SecurityBreach`)
```bash
# SECURITY INCIDENT - IMMEDIATE LOCKDOWN
echo "=== SECURITY INCIDENT RESPONSE ==="

# 1. Immediate isolation
iptables -A INPUT -p tcp --dport 8080 -j DROP  # Block external API access
docker-compose -f ops/docker-compose.yml pause api  # Pause API service

# 2. Capture evidence
docker logs api > /security/incident_$(date +%Y%m%d_%H%M%S)_api.log
docker exec postgres pg_dump -U orchestrator orchestrator > /security/incident_$(date +%Y%m%d_%H%M%S)_db.sql

# 3. Check audit logs for breach indicators
docker exec postgres psql -U orchestrator -c "
SELECT * FROM audit_log 
WHERE at > now() - interval '2 hours' 
ORDER BY at DESC LIMIT 100;
"

# 4. Notify security team immediately
echo "SECURITY INCIDENT - $(date) - All hands to security bridge" | \
  mail -s "URGENT: Security Incident" security-team@example.com

# 5. Begin forensic analysis
tcpdump -i any -w /security/incident_$(date +%Y%m%d_%H%M%S)_network.pcap &
TCPDUMP_PID=$!

# 6. Check for indicators of compromise
grep -E "(failed|unauthorized|invalid)" /var/log/auth.log
netstat -tulpn | grep ESTABLISHED
```

---

## 3. COMMUNICATION PROCEDURES

### Incident Communication Templates

#### P0 Critical Incident Notification
```
🚨 P0 CRITICAL INCIDENT - Task Scheduling System

INCIDENT: [Alert name and brief description]
STARTED: [ISO timestamp] 
IMPACT: [User-facing impact description]
STATUS: INVESTIGATING

Incident Commander: [Name]
Bridge: [Conference line/Slack channel]

Actions in progress:
- [Current action 1]
- [Current action 2]

Next update: [Time - typically 15 minutes]
```

#### P1 High Priority Incident Notification
```
⚠️  P1 HIGH PRIORITY - Task Scheduling System

INCIDENT: [Alert name]
STARTED: [ISO timestamp]
IMPACT: [Impact description]
STATUS: [Current status]

Lead Responder: [Name]
ETA Resolution: [Time estimate]

Current actions:
- [Action description]

Next update: [Time - typically 30 minutes]
```

#### Resolution Notification Template
```
✅ RESOLVED - Task Scheduling System Incident

INCIDENT: [Original alert name]
DURATION: [Start time] to [End time] ([Duration])
ROOT CAUSE: [Brief root cause description]

RESOLUTION:
- [Resolution step 1]
- [Resolution step 2]

IMPACT SUMMARY:
- [User impact summary]
- [Data integrity status]
- [Performance impact]

POST-INCIDENT: 
Review scheduled for [Date/Time]
Improvement items logged in [Ticket system]

Incident Commander: [Name]
```

### Stakeholder Notification List

#### P0 Critical Incidents
- **Immediate Notification** (within 5 minutes):
  - Technical Leadership Team
  - Operations Team
  - On-call Engineers
- **15 minute update**:
  - Product Management
  - Customer Success
  - Executive Team
- **Resolution notification**:
  - All stakeholders
  - Customer-facing teams

#### Communication Channels Priority
1. **Primary**: Slack #incident-response
2. **Secondary**: Email incident-team@example.com
3. **Escalation**: Phone/SMS for P0 incidents
4. **Public**: Status page for customer impact

---

## 4. DIAGNOSTIC COMMANDS & PROCEDURES

### System Health Quick Assessment
```bash
#!/bin/bash
# health_check.sh - Comprehensive system health assessment

echo "=== TASK SCHEDULING SYSTEM HEALTH CHECK ==="
echo "Timestamp: $(date -Iseconds)"

# Container status
echo -e "\n=== CONTAINER STATUS ==="
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "(api|postgres|redis|scheduler|worker|prometheus)"

# Service health endpoints
echo -e "\n=== SERVICE HEALTH ==="
curl -s -o /dev/null -w "API Health: %{http_code} (%{time_total}s)\n" http://localhost:8080/health
curl -s -o /dev/null -w "Prometheus: %{http_code} (%{time_total}s)\n" http://localhost:9090/-/healthy
curl -s -o /dev/null -w "Grafana: %{http_code} (%{time_total}s)\n" http://localhost:3000/api/health

# Database connectivity
echo -e "\n=== DATABASE STATUS ==="
docker exec postgres pg_isready -U orchestrator
docker exec postgres psql -U orchestrator -c "SELECT COUNT(*) as active_tasks FROM task WHERE status = 'active';" 2>/dev/null || echo "Database query failed"

# Redis connectivity
echo -e "\n=== REDIS STATUS ==="
docker exec redis redis-cli ping 2>/dev/null || echo "Redis connection failed"
docker exec redis redis-cli info keyspace 2>/dev/null | head -5

# Work queue status
echo -e "\n=== WORK QUEUE STATUS ==="
docker exec postgres psql -U orchestrator -c "
SELECT 
  COUNT(*) as due_now,
  COUNT(*) FILTER (WHERE locked_until IS NOT NULL) as locked,
  COUNT(*) FILTER (WHERE run_at > now()) as future
FROM due_work;
" 2>/dev/null || echo "Work queue query failed"

# Worker status
echo -e "\n=== WORKER STATUS ==="
docker exec postgres psql -U orchestrator -c "
SELECT worker_id, last_seen, processed_count 
FROM worker_heartbeat 
WHERE last_seen > now() - interval '2 minutes'
ORDER BY last_seen DESC;
" 2>/dev/null || echo "Worker status query failed"

# Resource utilization
echo -e "\n=== RESOURCE UTILIZATION ==="
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" | head -10

# Recent errors
echo -e "\n=== RECENT ERRORS ==="
docker logs api --since 15m 2>/dev/null | grep -E "(ERROR|FATAL|CRITICAL)" | tail -5 || echo "No recent API errors"
docker logs postgres --since 15m 2>/dev/null | grep -E "(ERROR|FATAL|CRITICAL)" | tail -5 || echo "No recent database errors"
```

### Performance Diagnostics
```bash
#!/bin/bash
# performance_check.sh - System performance diagnostics

echo "=== PERFORMANCE DIAGNOSTICS ==="

# API response time test
echo "API Response Time Test:"
for i in {1..5}; do
    curl -s -w "Attempt $i: %{time_total}s (HTTP %{http_code})\n" -o /dev/null http://localhost:8080/health
done

# Database performance
echo -e "\nDatabase Performance:"
docker exec postgres psql -U orchestrator -c "
SELECT 
  query,
  calls,
  total_time/calls as avg_time_ms,
  rows/calls as avg_rows
FROM pg_stat_statements 
ORDER BY total_time DESC 
LIMIT 5;
" 2>/dev/null || echo "pg_stat_statements not available"

# Task processing rate
echo -e "\nTask Processing Rate (last hour):"
docker exec postgres psql -U orchestrator -c "
SELECT 
  COUNT(*) as completed_tasks,
  AVG(EXTRACT(EPOCH FROM (finished_at - started_at))) as avg_duration_seconds
FROM task_run 
WHERE started_at > now() - interval '1 hour' 
  AND success = true;
"

# Queue depth over time
echo -e "\nWork Queue Depth:"
docker exec postgres psql -U orchestrator -c "
SELECT 
  date_trunc('minute', created_at) as minute,
  COUNT(*) as work_items_created
FROM due_work 
WHERE created_at > now() - interval '30 minutes'
GROUP BY date_trunc('minute', created_at)
ORDER BY minute DESC
LIMIT 10;
"
```

---

## 5. ESCALATION PROCEDURES

### When to Escalate

#### Immediate Escalation (P0)
- Service down for >15 minutes
- Data corruption or loss detected
- Security breach confirmed
- Multiple cascading failures
- Unable to identify root cause within 15 minutes

#### 30-Minute Escalation (P1)
- Performance degradation affecting >50% of operations
- Intermittent failures with unknown cause
- Resource exhaustion trending toward critical

#### 2-Hour Escalation (P2)
- Persistent but non-critical issues
- Performance optimization needed
- Capacity planning concerns

### Escalation Contacts

#### Technical Escalation Path
1. **On-call Engineer** → 2. **Technical Lead** → 3. **Engineering Manager** → 4. **CTO**

#### Business Escalation Path  
1. **Operations Manager** → 2. **Product Manager** → 3. **VP Engineering** → 4. **CEO**

#### External Support Contacts
- **Database Support**: vendor-support@postgresql.org
- **Cloud Provider**: [AWS/GCP/Azure] support case
- **Security Vendor**: security-soc@vendor.com

---

## 6. POST-INCIDENT PROCEDURES

### Immediate Post-Resolution Actions
```bash
# 1. Verify system stability
./ops/health_check.sh --full-system

# 2. Check for related issues
curl -s http://localhost:9093/api/v1/alerts | \
  jq '.data[] | select(.status.state == "firing") | .labels.alertname'

# 3. Document resolution in incident log
echo "$(date -Iseconds) [RESOLVED] Root cause: $ROOT_CAUSE, Resolution: $RESOLUTION" >> \
  /var/log/incidents/$(date +%Y%m%d_%H%M%S)_incident.log

# 4. Update monitoring (silence false alarms if needed)
# Silence alerts for 30 minutes to prevent noise
curl -X POST http://localhost:9093/api/v1/silences -d '{
  "matchers": [{"name": "alertname", "value": "'$ALERT_NAME'"}],
  "startsAt": "'$(date -Iseconds)'",
  "endsAt": "'$(date -d '+30 minutes' -Iseconds)'",
  "comment": "Post-incident silence for '$INCIDENT_ID'"
}'
```

### Post-Incident Review Process

#### Within 24 Hours
1. **Incident Timeline Creation**
   - Detailed chronology of events
   - Decision points and rationale
   - Communication effectiveness assessment

2. **Root Cause Analysis**
   - Technical root cause identification
   - Contributing factors analysis  
   - Prevention opportunity assessment

3. **Action Item Generation**
   - Immediate fixes required
   - Process improvements needed
   - Documentation updates required
   - Training or knowledge gaps identified

#### Post-Incident Review Template
```markdown
# Post-Incident Review: [Incident ID]

## Incident Summary
- **Date/Time**: [Start] to [End] 
- **Duration**: [Total duration]
- **Severity**: P[0-3]
- **Services Affected**: [List]
- **Customer Impact**: [Description]

## Timeline
| Time | Event | Action Taken | Owner |
|------|-------|-------------|-------|
| HH:MM | Alert triggered | Acknowledged | [Name] |
| HH:MM | Investigation began | [Action] | [Name] |
| HH:MM | Root cause identified | [Action] | [Name] |
| HH:MM | Resolution implemented | [Action] | [Name] |
| HH:MM | Service restored | Verified | [Name] |

## Root Cause Analysis
**Technical Root Cause**: [Detailed explanation]
**Contributing Factors**: 
- [Factor 1]
- [Factor 2]

## What Went Well
- [Positive observation 1]
- [Positive observation 2]

## What Could Be Improved
- [Improvement opportunity 1]
- [Improvement opportunity 2]

## Action Items
| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| [Action 1] | [Name] | [Date] | Open |
| [Action 2] | [Name] | [Date] | Open |

## Lessons Learned
- [Key lesson 1]
- [Key lesson 2]
```

### Monthly Incident Review
- Trend analysis of incident frequency and types
- Effectiveness of response procedures
- Training needs assessment
- Documentation and runbook updates
- Process optimization opportunities

**Last Updated**: 2025-01-10  
**Next Review**: 2025-04-10  
**Owner**: Operations Team  
**Approver**: Technical Lead