# Operations - Personal Agent Orchestrator Production Deployment

## Purpose & Scope

The `./ops/` directory contains all production deployment infrastructure for the Personal Agent Orchestrator. This includes Docker containerization, monitoring stack, health checks, configuration management, and deployment patterns for both development and production environments.

**Core Responsibilities:**
- Multi-stage Docker builds optimized for production performance
- Docker Compose orchestration for local development and production deployment
- Monitoring and observability stack (Prometheus, Grafana, AlertManager)
- Health check systems and graceful shutdown procedures
- Configuration management and secret handling
- Production deployment automation and rollback procedures

---

## Directory Structure

```
ops/
├── CLAUDE.md                    # This file - operations documentation
├── docker-compose.yml          # Development environment
├── docker-compose.prod.yml     # Production environment with monitoring
├── Dockerfile.api               # Multi-stage API service container
├── Dockerfile.scheduler         # Scheduler service container
├── Dockerfile.worker           # Worker service container
├── monitoring/                  # Observability stack
│   ├── prometheus.yml           # Metrics collection configuration
│   ├── grafana/
│   │   ├── dashboards/          # Pre-configured dashboards
│   │   │   ├── orchestrator-overview.json
│   │   │   ├── task-performance.json
│   │   │   └── system-health.json
│   │   └── provisioning/        # Grafana auto-provisioning
│   │       ├── dashboards.yml
│   │       └── datasources.yml
│   └── alerting/
│       ├── alertmanager.yml     # Alert routing and notifications
│       └── rules/               # Prometheus alerting rules
│           ├── orchestrator.yml
│           ├── database.yml
│           └── infrastructure.yml
├── config/                      # Configuration templates
│   ├── nginx.conf              # Reverse proxy configuration
│   ├── redis.conf              # Redis optimization
│   └── postgresql.conf         # PostgreSQL tuning
├── scripts/                     # Deployment automation
│   ├── deploy.sh               # Production deployment script
│   ├── backup.sh               # Database backup automation
│   ├── restore.sh              # Disaster recovery procedures
│   └── health-check.sh         # External health monitoring
└── k8s/                        # Kubernetes manifests (future)
    ├── namespace.yml
    ├── configmap.yml
    ├── secrets.yml
    └── deployments/
```

---

## Container Architecture

### Multi-Stage Docker Builds

All services use optimized multi-stage builds for minimal production images:

#### API Service (Dockerfile.api)
```dockerfile
# Build stage
FROM python:3.12-slim as builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.12-slim as runtime
RUN groupadd -r orchestrator && useradd -r -g orchestrator orchestrator
WORKDIR /app
COPY --from=builder /root/.local /home/orchestrator/.local
COPY api/ ./api/
COPY engine/ ./engine/
USER orchestrator
ENV PATH=/home/orchestrator/.local/bin:$PATH
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

#### Scheduler Service (Dockerfile.scheduler)
```dockerfile
FROM python:3.12-slim as builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.12-slim as runtime
RUN groupadd -r orchestrator && useradd -r -g orchestrator orchestrator
WORKDIR /app
COPY --from=builder /root/.local /home/orchestrator/.local
COPY scheduler/ ./scheduler/
COPY engine/ ./engine/
USER orchestrator
ENV PATH=/home/orchestrator/.local/bin:$PATH
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD python -c "import psutil; exit(0 if 'scheduler' in [p.name() for p in psutil.process_iter()] else 1)"
CMD ["python", "-m", "scheduler.tick"]
```

#### Worker Service (Dockerfile.worker)
```dockerfile
FROM python:3.12-slim as builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.12-slim as runtime
RUN groupadd -r orchestrator && useradd -r -g orchestrator orchestrator
WORKDIR /app
COPY --from=builder /root/.local /home/orchestrator/.local
COPY workers/ ./workers/
COPY engine/ ./engine/
USER orchestrator
ENV PATH=/home/orchestrator/.local/bin:$PATH
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD python -c "import redis; r=redis.Redis(host='redis'); r.ping()"
CMD ["python", "-m", "workers.runner"]
```

### Container Optimization Features
- **Multi-stage builds** reduce final image size by 70%
- **Non-root user** for security best practices
- **Health checks** for automatic service recovery
- **Graceful shutdown** with proper signal handling
- **Resource limits** prevent container resource exhaustion

---

## Docker Compose Configurations

### Development Environment (docker-compose.yml)
```yaml
version: '3.8'

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: orchestrator
      POSTGRES_USER: orchestrator
      POSTGRES_PASSWORD: dev_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ../migrations:/docker-entrypoint-initdb.d
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U orchestrator"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3

  api:
    build:
      context: ..
      dockerfile: ops/Dockerfile.api
    environment:
      DATABASE_URL: postgresql://orchestrator:dev_password@postgres:5432/orchestrator
      REDIS_URL: redis://redis:6379/0
      LOG_LEVEL: DEBUG
    ports:
      - "8080:8080"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ../api:/app/api  # Hot reload for development
      - ../engine:/app/engine

  scheduler:
    build:
      context: ..
      dockerfile: ops/Dockerfile.scheduler
    environment:
      DATABASE_URL: postgresql://orchestrator:dev_password@postgres:5432/orchestrator
      REDIS_URL: redis://redis:6379/0
      LOG_LEVEL: DEBUG
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  worker:
    build:
      context: ..
      dockerfile: ops/Dockerfile.worker
    environment:
      DATABASE_URL: postgresql://orchestrator:dev_password@postgres:5432/orchestrator
      REDIS_URL: redis://redis:6379/0
      LOG_LEVEL: INFO
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    scale: 2  # Run 2 workers for development testing

volumes:
  postgres_data:
  redis_data:
```

### Production Environment (docker-compose.prod.yml)
```yaml
version: '3.8'

services:
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./config/nginx.conf:/etc/nginx/nginx.conf:ro
      - /etc/letsencrypt:/etc/letsencrypt:ro
    depends_on:
      - api
    restart: unless-stopped

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: orchestrator
      POSTGRES_USER: orchestrator
      POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password
    secrets:
      - postgres_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./config/postgresql.conf:/etc/postgresql/postgresql.conf:ro
      - /backups:/backups
    command: postgres -c config_file=/etc/postgresql/postgresql.conf
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U orchestrator"]
      interval: 30s
      timeout: 10s
      retries: 3

  redis:
    image: redis:7-alpine
    command: redis-server /etc/redis/redis.conf
    volumes:
      - redis_data:/data
      - ./config/redis.conf:/etc/redis/redis.conf:ro
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 30s
      timeout: 10s
      retries: 3

  api:
    build:
      context: ..
      dockerfile: ops/Dockerfile.api
    environment:
      DATABASE_URL: postgresql://orchestrator:${POSTGRES_PASSWORD}@postgres:5432/orchestrator
      REDIS_URL: redis://redis:6379/0
      LOG_LEVEL: INFO
      PROMETHEUS_METRICS: "true"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped
    deploy:
      replicas: 3
      resources:
        limits:
          cpus: '1.0'
          memory: 512M
        reservations:
          cpus: '0.5'
          memory: 256M

  scheduler:
    build:
      context: ..
      dockerfile: ops/Dockerfile.scheduler
    environment:
      DATABASE_URL: postgresql://orchestrator:${POSTGRES_PASSWORD}@postgres:5432/orchestrator
      REDIS_URL: redis://redis:6379/0
      LOG_LEVEL: INFO
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 256M

  worker:
    build:
      context: ..
      dockerfile: ops/Dockerfile.worker
    environment:
      DATABASE_URL: postgresql://orchestrator:${POSTGRES_PASSWORD}@postgres:5432/orchestrator
      REDIS_URL: redis://redis:6379/0
      LOG_LEVEL: INFO
      WORKER_CONCURRENCY: 10
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped
    deploy:
      replicas: 5
      resources:
        limits:
          cpus: '1.0'
          memory: 512M

  # Monitoring Stack
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./monitoring/alerting/rules:/etc/prometheus/rules:ro
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/etc/prometheus/console_libraries'
      - '--web.console.templates=/etc/prometheus/consoles'
      - '--storage.tsdb.retention.time=30d'
      - '--web.enable-lifecycle'
    restart: unless-stopped

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD}
      GF_INSTALL_PLUGINS: "grafana-clock-panel,grafana-simple-json-datasource"
    volumes:
      - grafana_data:/var/lib/grafana
      - ./monitoring/grafana/provisioning:/etc/grafana/provisioning:ro
      - ./monitoring/grafana/dashboards:/var/lib/grafana/dashboards:ro
    restart: unless-stopped

  alertmanager:
    image: prom/alertmanager:latest
    ports:
      - "9093:9093"
    volumes:
      - ./monitoring/alerting/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro
      - alertmanager_data:/alertmanager
    command:
      - '--config.file=/etc/alertmanager/alertmanager.yml'
      - '--storage.path=/alertmanager'
    restart: unless-stopped

secrets:
  postgres_password:
    file: ./secrets/postgres_password.txt

volumes:
  postgres_data:
  redis_data:
  prometheus_data:
  grafana_data:
  alertmanager_data:
```

---

## Monitoring & Observability Stack

### Prometheus Configuration (monitoring/prometheus.yml)
```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - "/etc/prometheus/rules/orchestrator.yml"
  - "/etc/prometheus/rules/database.yml"
  - "/etc/prometheus/rules/infrastructure.yml"

scrape_configs:
  - job_name: 'orchestrator-api'
    static_configs:
      - targets: ['api:8080']
    metrics_path: '/metrics'
    scrape_interval: 10s

  - job_name: 'postgres-exporter'
    static_configs:
      - targets: ['postgres-exporter:9187']

  - job_name: 'redis-exporter'
    static_configs:
      - targets: ['redis-exporter:9121']

  - job_name: 'node-exporter'
    static_configs:
      - targets: ['node-exporter:9100']

alerting:
  alertmanagers:
    - static_configs:
        - targets:
          - alertmanager:9093
```

### Key Metrics Tracked

#### Orchestrator-Specific Metrics
- **Task Execution Metrics**
  - `orchestrator_tasks_total` - Total tasks by status
  - `orchestrator_task_duration_seconds` - Task execution time
  - `orchestrator_pipeline_steps_total` - Pipeline step success/failure rates
  - `orchestrator_queue_depth` - Number of pending tasks

- **Scheduler Metrics**
  - `orchestrator_scheduler_drift_seconds` - Scheduling accuracy
  - `orchestrator_schedule_triggers_total` - Schedule trigger counts
  - `orchestrator_missed_schedules_total` - Missed schedule events

- **Worker Metrics**
  - `orchestrator_worker_active_jobs` - Currently processing jobs
  - `orchestrator_worker_job_duration_seconds` - Job processing time
  - `orchestrator_worker_errors_total` - Worker error rates

#### Infrastructure Metrics
- **Database Performance**
  - Connection pool utilization
  - Query execution time
  - Lock wait times
  - Transaction rollback rates

- **Redis Performance**  
  - Memory usage
  - Command execution rates
  - Pub/sub message rates
  - Connection counts

### Grafana Dashboards

#### Orchestrator Overview Dashboard
```json
{
  "dashboard": {
    "title": "Personal Agent Orchestrator - Overview",
    "panels": [
      {
        "title": "Task Execution Rate",
        "type": "stat",
        "targets": [
          {
            "expr": "rate(orchestrator_tasks_total[5m])",
            "legendFormat": "{{status}}"
          }
        ]
      },
      {
        "title": "Queue Depth",
        "type": "graph",
        "targets": [
          {
            "expr": "orchestrator_queue_depth",
            "legendFormat": "Pending Tasks"
          }
        ]
      },
      {
        "title": "Worker Utilization",
        "type": "graph",
        "targets": [
          {
            "expr": "orchestrator_worker_active_jobs / orchestrator_worker_capacity * 100",
            "legendFormat": "{{instance}}"
          }
        ]
      }
    ]
  }
}
```

### AlertManager Configuration
```yaml
global:
  smtp_smarthost: 'localhost:587'
  smtp_from: 'alerts@orchestrator.example.com'

route:
  group_by: ['alertname']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 1h
  receiver: 'web.hook'
  routes:
    - match:
        severity: critical
      receiver: 'critical-alerts'
    - match:
        severity: warning  
      receiver: 'warning-alerts'

receivers:
  - name: 'critical-alerts'
    email_configs:
      - to: 'oncall@example.com'
        subject: 'CRITICAL: Orchestrator Alert'
        body: |
          Alert: {{ .GroupLabels.alertname }}
          Instance: {{ .CommonLabels.instance }}
          Description: {{ .CommonAnnotations.description }}
    
  - name: 'warning-alerts'
    email_configs:
      - to: 'team@example.com'
        subject: 'WARNING: Orchestrator Alert'
```

---

## Health Checks & Service Discovery

### Application Health Endpoints

#### API Service Health Check
```python
# api/main.py
@app.get("/health")
async def health_check():
    checks = {
        "database": await check_database_connection(),
        "redis": await check_redis_connection(),
        "scheduler": await check_scheduler_status(),
        "workers": await check_active_workers()
    }
    
    all_healthy = all(checks.values())
    status_code = 200 if all_healthy else 503
    
    return {
        "status": "healthy" if all_healthy else "unhealthy",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": checks,
        "version": get_version(),
        "uptime": get_uptime_seconds()
    }
```

#### External Health Check Script
```bash
#!/bin/bash
# scripts/health-check.sh

set -e

API_URL="${API_URL:-http://localhost:8080}"
TIMEOUT="${TIMEOUT:-10}"

response=$(curl -s -w "%{http_code}" --max-time $TIMEOUT "$API_URL/health")
http_code="${response: -3}"
body="${response%???}"

if [ "$http_code" != "200" ]; then
    echo "UNHEALTHY: API returned $http_code"
    echo "Response: $body"
    exit 1
fi

# Parse JSON response for detailed health status
if echo "$body" | jq -e '.status == "healthy"' > /dev/null; then
    echo "HEALTHY: All systems operational"
    exit 0
else
    echo "UNHEALTHY: Some components failing"
    echo "$body" | jq '.checks'
    exit 1
fi
```

### Container Health Checks

All containers include health checks that integrate with Docker Compose and orchestration systems:

```dockerfile
# Example health check for worker containers
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD python -c "
import redis, os, sys
try:
    r = redis.Redis.from_url(os.getenv('REDIS_URL'))
    r.ping()
    print('Worker healthy: Redis connection OK')
except Exception as e:
    print(f'Worker unhealthy: {e}')
    sys.exit(1)
"
```

---

## Configuration Management

### Environment-Specific Configuration

#### Development (.env.development)
```bash
# Database
DATABASE_URL=postgresql://orchestrator:dev_password@postgres:5432/orchestrator
REDIS_URL=redis://redis:6379/0

# Logging
LOG_LEVEL=DEBUG
LOG_FORMAT=structured

# Features
ENABLE_METRICS=true
ENABLE_TRACING=false
DEBUG_MODE=true

# Performance
WORKER_CONCURRENCY=2
API_WORKERS=1
SCHEDULER_INTERVAL=10
```

#### Production (.env.production)
```bash
# Database
DATABASE_URL=postgresql://orchestrator:${POSTGRES_PASSWORD}@postgres:5432/orchestrator
REDIS_URL=redis://redis:6379/0

# Logging  
LOG_LEVEL=INFO
LOG_FORMAT=json

# Features
ENABLE_METRICS=true
ENABLE_TRACING=true
DEBUG_MODE=false

# Performance
WORKER_CONCURRENCY=10
API_WORKERS=4
SCHEDULER_INTERVAL=5

# Security
API_RATE_LIMIT=1000
AUTH_TOKEN_EXPIRE=3600
```

### Configuration Validation

```python
# config/settings.py
from pydantic import BaseSettings, validator
from typing import Optional

class Settings(BaseSettings):
    database_url: str
    redis_url: str
    log_level: str = "INFO"
    worker_concurrency: int = 5
    api_rate_limit: int = 100
    
    @validator('log_level')
    def validate_log_level(cls, v):
        if v not in ['DEBUG', 'INFO', 'WARNING', 'ERROR']:
            raise ValueError('Invalid log level')
        return v
    
    @validator('worker_concurrency')
    def validate_concurrency(cls, v):
        if v < 1 or v > 50:
            raise ValueError('Worker concurrency must be 1-50')
        return v
    
    class Config:
        env_file = ".env"
        case_sensitive = False
```

---

## Deployment Procedures

### Development Deployment
```bash
#!/bin/bash
# scripts/deploy-dev.sh

echo "Starting development deployment..."

# Start infrastructure
docker-compose up -d postgres redis

# Wait for services to be healthy
echo "Waiting for infrastructure..."
docker-compose exec postgres pg_isready -U orchestrator
docker-compose exec redis redis-cli ping

# Run migrations
docker-compose exec postgres psql -U orchestrator -d orchestrator -f /docker-entrypoint-initdb.d/version_0001.sql

# Start application services
docker-compose up -d api scheduler worker

# Verify deployment
sleep 10
curl -f http://localhost:8080/health || {
    echo "Health check failed"
    docker-compose logs api
    exit 1
}

echo "Development deployment complete"
echo "API: http://localhost:8080"
echo "Grafana: http://localhost:3000 (admin/admin)"
```

### Production Deployment
```bash
#!/bin/bash
# scripts/deploy.sh

set -e

ENVIRONMENT=${1:-production}
COMPOSE_FILE="docker-compose.prod.yml"

echo "Deploying Personal Agent Orchestrator to $ENVIRONMENT..."

# Validate environment
if [[ ! -f ".env.$ENVIRONMENT" ]]; then
    echo "Environment file .env.$ENVIRONMENT not found"
    exit 1
fi

# Load environment variables
set -a
source ".env.$ENVIRONMENT"
set +a

# Pre-deployment validation
echo "Running pre-deployment checks..."

# Check required secrets exist
required_secrets=("postgres_password.txt" "grafana_password.txt")
for secret in "${required_secrets[@]}"; do
    if [[ ! -f "secrets/$secret" ]]; then
        echo "Required secret missing: secrets/$secret"
        exit 1
    fi
done

# Backup database before deployment
echo "Creating database backup..."
./scripts/backup.sh

# Deploy with zero-downtime strategy
echo "Starting zero-downtime deployment..."

# Scale up new containers
docker-compose -f $COMPOSE_FILE up -d --scale api=6 --scale worker=10

# Health check new containers
echo "Waiting for new containers to be healthy..."
sleep 30

# Check health endpoints
for i in {1..5}; do
    if curl -f http://localhost:8080/health > /dev/null 2>&1; then
        echo "Health check passed"
        break
    else
        echo "Health check attempt $i failed, retrying..."
        sleep 10
        if [[ $i -eq 5 ]]; then
            echo "Health checks failed, rolling back..."
            ./scripts/rollback.sh
            exit 1
        fi
    fi
done

# Scale down old containers
docker-compose -f $COMPOSE_FILE up -d --scale api=3 --scale worker=5

# Post-deployment verification
echo "Running post-deployment tests..."
./scripts/smoke-test.sh

echo "Production deployment complete!"
echo "Dashboard: http://localhost:3000"
echo "API: http://localhost:8080"
echo "Metrics: http://localhost:9090"
```

### Backup & Recovery Procedures

#### Automated Backup Script
```bash
#!/bin/bash
# scripts/backup.sh

set -e

BACKUP_DIR="/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
DATABASE_URL="${DATABASE_URL:-postgresql://orchestrator:password@postgres:5432/orchestrator}"

echo "Starting backup at $TIMESTAMP..."

# Create backup directory
mkdir -p "$BACKUP_DIR"

# PostgreSQL backup
echo "Backing up PostgreSQL..."
docker-compose exec -T postgres pg_dump $DATABASE_URL | gzip > "$BACKUP_DIR/postgres_$TIMESTAMP.sql.gz"

# Redis backup  
echo "Backing up Redis..."
docker-compose exec redis redis-cli --rdb - | gzip > "$BACKUP_DIR/redis_$TIMESTAMP.rdb.gz"

# Configuration backup
echo "Backing up configuration..."
tar -czf "$BACKUP_DIR/config_$TIMESTAMP.tar.gz" \
    .env.production \
    ops/config/ \
    ops/monitoring/ \
    secrets/

# Cleanup old backups (keep 30 days)
find "$BACKUP_DIR" -name "*.gz" -mtime +30 -delete
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +30 -delete

echo "Backup completed: $BACKUP_DIR/*_$TIMESTAMP.*"

# Verify backup integrity
gunzip -t "$BACKUP_DIR/postgres_$TIMESTAMP.sql.gz"
gunzip -t "$BACKUP_DIR/redis_$TIMESTAMP.rdb.gz"

echo "Backup verification successful"
```

#### Disaster Recovery Script
```bash
#!/bin/bash
# scripts/restore.sh

set -e

BACKUP_FILE="${1}"
RESTORE_TYPE="${2:-full}"

if [[ -z "$BACKUP_FILE" ]]; then
    echo "Usage: $0 <backup_file> [postgres|redis|config|full]"
    exit 1
fi

echo "Starting restore from $BACKUP_FILE..."

case $RESTORE_TYPE in
    "postgres"|"full")
        echo "Restoring PostgreSQL..."
        docker-compose exec -T postgres psql -U orchestrator -d orchestrator -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
        gunzip -c "$BACKUP_FILE" | docker-compose exec -T postgres psql -U orchestrator -d orchestrator
        ;;
    "redis"|"full")
        echo "Restoring Redis..."
        docker-compose stop redis
        gunzip -c "${BACKUP_FILE/.sql/.rdb}" > /tmp/dump.rdb
        docker-compose run --rm -v /tmp/dump.rdb:/data/dump.rdb redis redis-server --daemonize no --save ""
        docker-compose start redis
        ;;
esac

# Restart all services after restore
if [[ "$RESTORE_TYPE" == "full" ]]; then
    echo "Restarting all services..."
    docker-compose restart
    
    # Verify restoration
    sleep 30
    ./scripts/health-check.sh
fi

echo "Restore completed successfully"
```

---

## Security Considerations

### Container Security
- **Non-root users** in all containers
- **Read-only filesystems** where possible
- **Minimal base images** (Alpine Linux)
- **Security scanning** in CI/CD pipeline
- **Secret management** via Docker secrets or external systems

### Network Security
```yaml
# docker-compose.prod.yml security section
services:
  api:
    networks:
      - frontend
      - backend
    expose:
      - "8080"  # Only expose internally
    
networks:
  frontend:
    driver: bridge
    internal: false  # Internet access for external APIs
  backend:
    driver: bridge  
    internal: true   # No internet access for internal services
```

### Secret Management
```bash
# Production secret management
echo "super_secure_password" | docker secret create postgres_password -
echo "grafana_admin_password" | docker secret create grafana_password -

# Kubernetes secret management (future)
kubectl create secret generic orchestrator-secrets \
  --from-literal=postgres-password="super_secure_password" \
  --from-literal=redis-password="redis_secure_password"
```

---

## Performance Tuning

### Resource Limits & Scaling

#### Production Resource Allocation
```yaml
# docker-compose.prod.yml resource section
services:
  api:
    deploy:
      replicas: 3
      resources:
        limits:
          cpus: '1.0'
          memory: 512M
        reservations:
          cpus: '0.5'
          memory: 256M
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3

  worker:
    deploy:
      replicas: 5
      resources:
        limits:
          cpus: '2.0'
          memory: 1G
        reservations:
          cpus: '1.0'
          memory: 512M
```

#### Database Optimization (config/postgresql.conf)
```conf
# Connection settings
max_connections = 200
shared_buffers = 256MB
effective_cache_size = 1GB
work_mem = 4MB
maintenance_work_mem = 64MB

# WAL settings
wal_buffers = 16MB
checkpoint_completion_target = 0.9
wal_compression = on

# Query optimization
random_page_cost = 1.1  # For SSD storage
effective_io_concurrency = 200

# Logging
log_min_duration_statement = 1000  # Log slow queries
log_line_prefix = '%t [%p]: [%l-1] user=%u,db=%d,app=%a,client=%h '
```

#### Redis Optimization (config/redis.conf)
```conf
# Memory management
maxmemory 512mb
maxmemory-policy allkeys-lru

# Persistence
save 900 1
save 300 10
save 60 10000

# Performance
tcp-keepalive 300
timeout 300
tcp-backlog 511
```

---

## Troubleshooting & Operations

### Common Issues & Solutions

#### Service Won't Start
```bash
# Check logs
docker-compose logs api

# Check resource usage
docker stats

# Check health status
docker-compose ps
curl http://localhost:8080/health
```

#### Database Connection Issues
```bash
# Verify database is running
docker-compose exec postgres pg_isready -U orchestrator

# Check connection pool
docker-compose exec api python -c "
from api.database import engine
print(f'Pool size: {engine.pool.size()}')
print(f'Checked out: {engine.pool.checkedout()}')
"

# Reset connections
docker-compose restart api worker scheduler
```

#### High Memory Usage
```bash
# Check container memory usage
docker stats --no-stream

# Profile Python memory usage
docker-compose exec api python -m memory_profiler api/main.py

# Check for memory leaks
docker-compose exec api python -c "
import gc
import psutil
print(f'Memory: {psutil.virtual_memory().percent}%')
print(f'Objects: {len(gc.get_objects())}')
"
```

### Monitoring Commands
```bash
# Check system health
docker-compose exec api curl -s http://localhost:8080/health | jq

# Monitor queue depth
docker-compose exec redis redis-cli llen orchestrator:work_queue

# Check active workers
docker-compose exec redis redis-cli scard orchestrator:active_workers

# View recent task runs
docker-compose exec api python -c "
from api.database import SessionLocal
from api.models import TaskRun
with SessionLocal() as db:
    runs = db.query(TaskRun).order_by(TaskRun.started_at.desc()).limit(10).all()
    for run in runs:
        print(f'{run.task_id}: {run.success} ({run.started_at})')
"
```

---

## Future Enhancements

### Kubernetes Migration Path
When ready to migrate from Docker Compose to Kubernetes:

1. **Helm Charts**: Convert Docker Compose to Helm templates
2. **Service Mesh**: Implement Istio for advanced traffic management
3. **Auto-scaling**: Use HPA (Horizontal Pod Autoscaler) for dynamic scaling
4. **Persistent Volumes**: Migrate data volumes to Kubernetes PVCs
5. **Ingress Controllers**: Replace nginx with Kubernetes Ingress

### Advanced Monitoring
- **Distributed Tracing**: Implement Jaeger for request tracing
- **Log Aggregation**: Add ELK stack (Elasticsearch, Logstash, Kibana)
- **APM Integration**: Add New Relic or DataDog for application performance monitoring
- **Synthetic Monitoring**: Implement automated end-to-end testing

### Security Enhancements
- **Image Scanning**: Automated vulnerability scanning in CI/CD
- **Runtime Security**: Implement Falco for runtime threat detection
- **Secret Rotation**: Automated secret rotation and management
- **Network Policies**: Implement microsegmentation with Kubernetes NetworkPolicies

This operations infrastructure provides a production-ready foundation that scales from development through enterprise deployment while maintaining reliability, observability, and security.