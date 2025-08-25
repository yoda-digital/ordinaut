# Installation

The Ordinaut system is designed to be run as a set of containerized services using Docker. This approach ensures a consistent, reproducible environment for both development and production.

**🚀 Quick Installation:** Use our pre-built Docker images for instant deployment, or build from source for development and customization.

## Prerequisites

Before you begin, ensure you have the following tools installed on your system:

- **Docker Engine:** Version 24.0 or newer. [Install Docker](https://docs.docker.com/engine/install/)
- **Docker Compose:** Included with Docker Desktop, or as a standalone plugin. [Install Docker Compose](https://docs.docker.com/compose/install/)
- **Git:** For cloning the repository. [Install Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git)
- **cURL:** A command-line tool for making API requests, used for verification.

## 1. Clone the Repository

First, clone the Ordinaut repository from GitHub to your local machine.

```bash
git clone https://github.com/yoda-digital/ordinaut.git
cd ordinaut
```

## 2. Start the System

The system provides two installation approaches - choose the one that fits your needs:

### 🚀 **Option A: Pre-built Images (RECOMMENDED - Instant Start)**

Use production-ready Docker images published automatically with every release:

```bash
cd ops/
./start.sh ghcr --logs
```

**✅ Benefits:**
- **30-second startup** vs 5-10 minutes building from source
- **Production-tested** images with security attestations
- **Multi-architecture support** for Intel/AMD (linux/amd64)
- **Automatic updates** with semantic versioning
- **No build dependencies** required on your system

**📚 Available Images:**
- `ghcr.io/yoda-digital/ordinaut-api:latest` - FastAPI REST API service
- `ghcr.io/yoda-digital/ordinaut-scheduler:latest` - APScheduler service  
- `ghcr.io/yoda-digital/ordinaut-worker:latest` - Job execution service

### 🛠️ **Option B: Build from Source (Development)**

For development, customization, or when you need to modify the source code:

```bash
cd ops/
./start.sh dev --build --logs
```

**⚙️ This command:**
- Reads the `docker-compose.yml` and `docker-compose.dev.yml` files
- Builds the Docker images for API, scheduler, and worker services
- Starts all required containers in the correct order
- Mounts local source code for live-reloading during development

**⚠️ Note:** Building from source requires additional time and system resources.

### The Service Stack

When you run the start script, the following services are launched:

- **`postgres`**: The PostgreSQL database, where all task and state data is stored.
- **`redis`**: The Redis server, used for event streams and caching.
- **`api`**: The main FastAPI server that exposes the REST API on port `8080`.
- **`scheduler`**: The APScheduler process that calculates when tasks should run.
- **`worker`**: A worker process that picks up and executes due tasks.

## 3. Verify the Installation

After a minute, all services should be running and healthy. You can verify this by checking the container statuses and querying the health endpoint.

### Check Container Health

```bash
# From the ops/ directory
docker compose ps
```

You should see all services with a `Up (healthy)` or `Up` status:

```
NAME                COMMAND                  SERVICE      STATUS        PORTS
ops-api-1          "uvicorn api.main:ap…"  api          Up (healthy)  0.0.0.0:8080->8080/tcp
ops-postgres-1     "docker-entrypoint.s…"  postgres     Up (healthy)  0.0.0.0:5432->5432/tcp
ops-redis-1        "docker-entrypoint.s…"  redis        Up (healthy)  0.0.0.0:6379->6379/tcp
ops-scheduler-1    "python -m scheduler…"  scheduler    Up (healthy)
ops-worker-1       "python -m workers.r…"  worker       Up (healthy)
```

### Query the Health API

Use `curl` to check the main health endpoint:

```bash
curl http://localhost:8080/health
```

A successful response indicates that the API is running and can connect to the database and Redis:

```json
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

## Next Steps

Your Ordinaut instance is now fully operational! 🎉

**🎓 Learn & Explore:**
- **Interactive API Docs:** [http://localhost:8080/docs](http://localhost:8080/docs) - Complete Swagger UI with live testing
- **System Health:** [http://localhost:8080/health](http://localhost:8080/health) - Real-time system status
- **Quick Start Tutorial:** [quick-start.md](quick-start.md) - Create your first automated workflow

**🚀 Production Deployment:**
- **Deployment Guide:** [../operations/deployment.md](../operations/deployment.md) - Production setup with monitoring
- **Docker Images:** All services available as production-ready images on GHCR
- **Configuration:** Environment-specific settings and optimization

**📚 Next Recommended Reading:**
1. [Quick Start Tutorial](quick-start.md) - Create your first task in 5 minutes
2. [API Reference](../api/api_reference.md) - Complete endpoint documentation
3. [Development Guide](../guides/development.md) - Contributing and extending Ordinaut