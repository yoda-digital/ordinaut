# Ordinaut - Deployment Guide

## Overview

Ordinaut consists of 5 containerized services:
- **postgres**: PostgreSQL 16.4 database with orchestrator schema
- **redis**: Redis 7.2.5 for event streaming and caching  
- **api**: FastAPI service exposing REST endpoints
- **scheduler**: APScheduler service for temporal logic
- **worker**: SKIP LOCKED job processing workers (2+ replicas)

## Quick Start

### 1. Prerequisites

- Docker 24.0+ and Docker Compose plugin
- At least 4GB RAM and 2GB disk space
- Ports 5432, 6379, and 8080 available

### 2. Development Mode

```bash
# Start all services in development mode
cd ops/
./start.sh dev

# With rebuild and logs
./start.sh dev --build --logs

# Clean start (removes all data)
./start.sh dev --clean --build
```

### 3. Production Mode

```bash
# Copy and configure environment
cp .env.example .env
# Edit .env with your production values

# Start in production mode
./start.sh prod

# Production with resource limits and multiple replicas
./start.sh prod --build
```

## Service Configuration

### Environment Variables

All services support these common environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | Required | PostgreSQL connection string |
| `REDIS_URL` | Required | Redis connection string |
| `TZ` | Europe/Chisinau | Container timezone |
| `LOG_LEVEL` | info | Logging level (debug, info, warn, error) |

### API Service

| Variable | Default | Description |
|----------|---------|-------------|
| `UVICORN_HOST` | 0.0.0.0 | API bind address |
| `UVICORN_PORT` | 8080 | API port |
| `UVICORN_WORKERS` | 1 (4 in prod) | Number of worker processes |

### Scheduler Service

| Variable | Default | Description |
|----------|---------|-------------|
| `SCHEDULER_MISFIRE_GRACE_TIME` | 30 | Seconds to allow late job execution |
| `SCHEDULER_MAX_WORKERS` | 10 | Max concurrent job threads |

### Worker Service

| Variable | Default | Description |
|----------|---------|-------------|
| `WORKER_LEASE_SECONDS` | 60 | Job lease duration |
| `WORKER_POLL_INTERVAL` | 0.5 | Seconds between queue polls |
| `WORKER_MAX_RETRIES` | 3 | Max retry attempts |
| `WORKER_BACKOFF_MAX_DELAY` | 60 | Max backoff delay in seconds |

## Docker Compose Files

### Core Configuration (`docker-compose.yml`)

Base configuration with all services, suitable for local development.

### Development Overrides (`docker-compose.dev.yml`)

- Development database credentials
- Volume mounts for hot reloading
- Debug logging enabled
- Single worker replica
- All ports exposed

Usage:
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

### Production Overrides (`docker-compose.prod.yml`)

- Environment-based configuration
- Resource limits and reservations
- Multiple API and worker replicas
- Production logging configuration
- Security hardening

Usage:
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up
```

## Data Persistence

### PostgreSQL Data

- **Development**: `pgdata-dev` volume
- **Production**: `pgdata-prod` volume
- **Schema**: Applied automatically from `migrations/version_0001.sql`

### Redis Data

- **Development**: `redisdata-dev` volume
- **Production**: `redisdata-prod` volume  
- **Persistence**: AOF (Append Only File) enabled

## Networking

All services run in a custom bridge network `yoda-tasker-network`.

**Internal Communication:**
- API ↔ PostgreSQL: `postgres:5432`
- API ↔ Redis: `redis:6379`
- Scheduler ↔ PostgreSQL: `postgres:5432`
- Workers ↔ PostgreSQL: `postgres:5432`
- Workers ↔ Redis: `redis:6379`

**External Access:**
- API: `localhost:8080`
- PostgreSQL: `localhost:5432` (dev only)
- Redis: `localhost:6379` (dev only)

## Health Checks

All services include comprehensive health checks:

- **PostgreSQL**: `pg_isready` command
- **Redis**: `redis-cli ping` command  
- **API**: HTTP health endpoint at `/health`
- **Scheduler**: Process health via APScheduler
- **Workers**: Queue connectivity check

## Monitoring and Logs

### Log Management

All services use structured JSON logging with rotation:
- **Max Size**: 100MB (API/Scheduler/Worker), 50MB (Redis)
- **Max Files**: 3 rotated files
- **Driver**: Docker json-file

### Log Viewing

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f api
docker compose logs -f scheduler
docker compose logs -f worker

# Follow with timestamps
docker compose logs -f -t
```

### Health Status

```bash
# Check service health
docker compose ps

# Detailed service status
docker compose top

# Resource usage
docker stats
```

## Scaling

### Horizontal Scaling

Workers can be scaled horizontally for increased throughput:

```bash
# Scale to 4 worker instances
docker compose up -d --scale worker=4

# Scale API for high availability
docker compose up -d --scale api=2
```

### Resource Allocation

Production resource limits per service:

| Service | CPU Limit | Memory Limit | Replicas |
|---------|-----------|--------------|----------|
| PostgreSQL | 1.0 | 1GB | 1 |
| Redis | 0.5 | 512MB | 1 |
| API | 1.0 | 1GB | 2 |
| Scheduler | 0.5 | 512MB | 1 |
| Worker | 1.0 | 1GB | 4 |

## Troubleshooting

### Common Issues

**Services won't start:**
1. Check port availability: `netstat -tlnp | grep -E '(5432|6379|8080)'`
2. Verify Docker daemon: `docker system info`
3. Check disk space: `df -h`

**Database connection errors:**
1. Wait for PostgreSQL health check: `docker compose logs postgres`
2. Verify DATABASE_URL format
3. Check network connectivity: `docker network ls`

**Worker not processing jobs:**
1. Check queue depth: Connect to PostgreSQL and run `SELECT COUNT(*) FROM due_work;`
2. Verify worker logs: `docker compose logs worker`
3. Check database locks: `SELECT * FROM pg_locks WHERE granted = false;`

**High resource usage:**
1. Monitor with: `docker stats`
2. Check log file sizes: `docker system df`
3. Scale services as needed

### Debug Mode

Enable debug logging for detailed troubleshooting:

```bash
# Edit environment
export LOG_LEVEL=debug

# Restart services
docker compose restart
```

### Database Access

Connect directly to PostgreSQL for debugging:

```bash
# Development
docker compose exec postgres psql -U orchestrator -d orchestrator_dev

# Production
docker compose exec postgres psql -U orchestrator -d orchestrator
```

### Redis Access

Connect to Redis for cache inspection:

```bash
docker compose exec redis redis-cli
# Redis commands:
# KEYS *
# XINFO STREAM events
# MONITOR
```

## Security Considerations

### Production Security

1. **Change default passwords** in `.env` file
2. **Limit network exposure** - only expose necessary ports
3. **Use secrets management** for sensitive configuration
4. **Enable firewall** rules for Docker daemon
5. **Regular security updates** for base images

### Container Security

- All containers run as non-root user `appuser`
- Minimal base images (python:3.12-slim)
- No unnecessary packages installed
- Read-only filesystem where possible

### Network Security

- Custom bridge network isolates services
- No direct external access to databases
- API uses standard HTTP security headers

## Backup and Recovery

### Database Backup

```bash
# Create backup
docker compose exec postgres pg_dump -U orchestrator orchestrator > backup.sql

# Restore backup
docker compose exec -i postgres psql -U orchestrator orchestrator < backup.sql
```

### Redis Backup

```bash
# Redis persistence via AOF files
docker compose exec redis redis-cli BGREWRITEAOF

# Copy AOF file
docker cp $(docker compose ps -q redis):/data/appendonly.aof ./redis-backup.aof
```

### Volume Backup

```bash
# Backup PostgreSQL volume
docker run --rm -v yoda-tasker_pgdata:/source -v $(pwd):/backup alpine tar czf /backup/pgdata.tar.gz -C /source .

# Backup Redis volume  
docker run --rm -v yoda-tasker_redisdata:/source -v $(pwd):/backup alpine tar czf /backup/redisdata.tar.gz -C /source .
```

## Updates and Maintenance

### Rolling Updates

1. **Pull latest images**: `docker compose pull`
2. **Update services**: `docker compose up -d`
3. **Verify health**: `docker compose ps`

### Database Migrations

Future schema updates:

```bash
# Apply new migration
docker compose exec postgres psql -U orchestrator orchestrator -f /path/to/new_migration.sql

# Or mount migration and restart
docker compose down
# Add migration to migrations/ directory
docker compose up -d
```

## Performance Tuning

### PostgreSQL Tuning

Add to `docker-compose.prod.yml`:

```yaml
postgres:
  command: [
    "postgres",
    "-c", "shared_preload_libraries=pg_stat_statements",
    "-c", "max_connections=200",
    "-c", "shared_buffers=256MB",
    "-c", "work_mem=4MB"
  ]
```

### Redis Tuning

Already configured with:
- AOF persistence
- Memory policy: allkeys-lru
- Max memory: 256MB (adjustable)

### Application Tuning

- **API**: Scale workers based on CPU cores
- **Workers**: Scale replicas based on job throughput
- **Scheduler**: Monitor job scheduling lag

## Support

For issues or questions:
1. Check logs: `docker compose logs -f`
2. Verify configuration: `docker compose config`
3. Test connectivity: `docker compose exec api curl http://localhost:8080/health`
4. Review resource usage: `docker stats`