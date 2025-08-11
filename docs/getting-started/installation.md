# Installation

Ordinaut is designed to be run as a set of containerized services using Docker. This approach ensures a consistent, reproducible environment for both development and production.

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

The repository includes a convenience script (`start.sh`) and Docker Compose files in the `ops/` directory to manage the system.

```bash
cd ops/
./start.sh dev --build
```

This command performs several actions:
- Reads the `docker-compose.yml` and `docker-compose.dev.yml` files.
- Builds the Docker images for the API, scheduler, and worker services.
- Starts all the required containers in the correct order.
- Mounts local source code into the containers for live-reloading during development.

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
docker compose ps
```

You should see all services with a `Up (healthy)` or `Up` status.

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

Your Ordinaut instance is now fully operational in a development environment. 

- **Explore the API:** Open the interactive Swagger UI at [http://localhost:8080/docs](http://localhost:8080/docs) to see all available endpoints.
- **Create your first task:** Follow the [Quick Start Tutorial](quick-start.md) to schedule your first workflow.