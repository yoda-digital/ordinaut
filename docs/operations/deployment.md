# Deployment

This guide covers deploying the Ordinaut system to production environments using production-ready Docker images.

**🚀 Recommended:** Use pre-built images from GitHub Container Registry (GHCR) for reliable, security-tested production deployments.

## Production Setup

### 🚀 **Option A: Production Images (RECOMMENDED)**

Use battle-tested, automatically published Docker images for reliable production deployment:

```bash
cd ops/

# Configure environment (copy and customize .env.example to .env)
cp .env.example .env
# Set secure JWT_SECRET_KEY and production database credentials

# Deploy with pre-built GHCR images
./start.sh ghcr
```

**✅ Production Benefits:**
- **Security-tested images** with automated vulnerability scanning
- **Build attestations** and Software Bill of Materials (SBOM) included
- **Zero build time** - instant deployment without compilation
- **Semantic versioning** with tagged releases (`v1.7.1`, `latest`)
- **Multi-stage optimized** images (50% smaller than development builds)
- **Automatic updates** via GitHub Actions on every release

**📚 Production Images Available:**
- `ghcr.io/yoda-digital/ordinaut-api:latest` - FastAPI REST API service
- `ghcr.io/yoda-digital/ordinaut-scheduler:latest` - APScheduler service  
- `ghcr.io/yoda-digital/ordinaut-worker:latest` - Job execution service

### 🛠️ **Option B: Custom Build (Advanced)**

For customized deployments or when you need to modify the source:

```bash
cd ops/

# Ensure your .env file is configured
cp .env.example .env
# Customize JWT_SECRET_KEY and other production values

# Build and deploy from source
./start.sh prod --build
```

**⚠️ Note:** Building from source requires additional build time, dependencies, and maintenance.

### 🚀 **Production Configuration**

**Critical Environment Variables:**
```bash
# Security (REQUIRED)
JWT_SECRET_KEY="$(openssl rand -hex 32)"  # Generate secure 256-bit key

# Database (Production values)
DATABASE_URL="postgresql://orchestrator:SECURE_PASSWORD@postgres:5432/orchestrator"
REDIS_URL="redis://redis:6379/0"

# Performance
WORKER_CONCURRENCY=10
API_WORKERS=4
SCHEDULER_INTERVAL=5

# Monitoring
ENABLE_METRICS=true
LOG_LEVEL=INFO
```

## Scaling & High Availability

### 🚀 **Horizontal Scaling with GHCR Images**

Pre-built images scale instantly without build overhead:

```bash
# Scale workers for high task throughput
docker compose -f docker-compose.ghcr.yml up -d --scale worker=10

# Scale API servers for high availability
docker compose -f docker-compose.ghcr.yml up -d --scale api=3

# Check scaling status
docker compose ps
```

### 📊 **Resource-Based Scaling**

**Worker Scaling Guidelines:**
- **Light load:** 2-3 workers (handles ~100 tasks/hour)
- **Medium load:** 5-8 workers (handles ~500 tasks/hour)
- **Heavy load:** 10+ workers (handles 1000+ tasks/hour)

**API Scaling for Load Balancing:**
```bash
# Multi-instance API deployment
docker compose -f docker-compose.ghcr.yml up -d \
  --scale api=3 \
  --scale worker=5

# Add nginx load balancer
docker compose -f docker-compose.ghcr.yml -f docker-compose.lb.yml up -d
```

### 🔍 **Monitoring Scaled Deployments**

```bash
# Check container health across scaled services
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

# Monitor resource usage
docker stats --no-stream

# Check application health
curl http://localhost:8080/health | jq '.checks'
```

## Production Operations

### 🔒 **Data Persistence & Backups**

**PostgreSQL (Primary Data):**
- **Data Volume:** `pgdata-prod` Docker volume for persistent storage
- **Backup Strategy:** Implement automated `pg_dump` for data protection
- **High Availability:** Consider PostgreSQL clustering for mission-critical deployments

**Redis (Transient Data):**
- **Purpose:** Event streams, caches, and temporary coordination data
- **Persistence:** AOF enabled but not treated as primary data store
- **Recovery:** Automatically rebuilds from PostgreSQL on restart

**Automated Backup Script:**
```bash
# Example production backup
#!/bin/bash
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
docker compose exec postgres pg_dump -U orchestrator orchestrator | \
  gzip > "/backups/ordinaut_${TIMESTAMP}.sql.gz"
```

### 📊 **Production Monitoring**

**Health Monitoring:**
```bash
# System health check
curl -f http://localhost:8080/health || alert_escalation

# Database connectivity
docker compose exec postgres pg_isready -U orchestrator

# Redis connectivity
docker compose exec redis redis-cli ping
```

**Performance Monitoring:**
```bash
# Check queue depth
curl -s http://localhost:8080/metrics | grep queue_depth

# Monitor task execution rates
curl -s http://localhost:8080/metrics | grep task_execution_rate

# Container resource usage
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"
```

### 🚀 **Image Update Strategy**

**Automatic Updates (Production):**
```bash
# Pull latest production images
docker compose -f docker-compose.ghcr.yml pull

# Rolling update with zero downtime
docker compose -f docker-compose.ghcr.yml up -d --scale api=6
sleep 30  # Wait for health checks
docker compose -f docker-compose.ghcr.yml up -d --scale api=3
```

**Version Pinning (Recommended):**
```yaml
# docker-compose.ghcr.yml - pin to specific versions
services:
  api:
    image: ghcr.io/yoda-digital/ordinaut-api:v1.7.1
  scheduler:
    image: ghcr.io/yoda-digital/ordinaut-scheduler:v1.7.1
  worker:
    image: ghcr.io/yoda-digital/ordinaut-worker:v1.7.1
```

**Security Updates:**
- Images automatically rebuilt on security patches
- GHCR images include security attestations and SBOMs
- Automated vulnerability scanning in CI/CD pipeline
- Subscribe to [GitHub releases](https://github.com/yoda-digital/ordinaut/releases) for notifications

### 📚 **Operational Documentation**

For detailed operational procedures, refer to:
- **[Production Runbook](../ops/PRODUCTION_RUNBOOK.md)** - Daily operations and maintenance
- **[Backup Procedures](../ops/BACKUP_PROCEDURES.md)** - Data protection strategies  
- **[Disaster Recovery](../ops/DISASTER_RECOVERY.md)** - 30-minute RTO recovery plans
- **[Monitoring Guide](../ops/MONITORING_PLAYBOOK.md)** - Alert response procedures
