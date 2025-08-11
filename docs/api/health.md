# Health API

The Health API provides endpoints for monitoring the status of the Ordinaut system. These are essential for production operations, load balancing, and automated recovery.

## `GET /health`

Provides a comprehensive, detailed health check of the entire system and its components (Database, Redis, Scheduler, Workers). This is the best endpoint for a general overview of system status.

**Example Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-01-11T10:45:00Z",
  "version": "1.0.0",
  "checks": [
    {
      "name": "database",
      "status": "healthy",
      "message": "PostgreSQL connection pool healthy"
    },
    {
      "name": "redis",
      "status": "healthy",
      "message": "Redis connection active"
    }
  ]
}
```

---

## `GET /health/ready`

A lightweight endpoint suitable for a Kubernetes **readiness probe**. It returns a `200 OK` status if the service is ready to accept traffic (e.g., database and cache connections are available). A load balancer should route traffic to an instance only if this check passes.

---

## `GET /health/live`

A minimal endpoint suitable for a Kubernetes **liveness probe**. It returns a `200 OK` status if the API process is alive and responding. This check does not verify downstream dependencies. If this probe fails, the container orchestrator should restart the instance.