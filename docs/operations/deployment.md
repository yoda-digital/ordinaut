# Deployment

This guide covers deploying the Ordinaut system to production environments using production-ready Docker images.

**🚀 Recommended:** Use pre-built images from GitHub Container Registry (GHCR) for reliable, security-tested production deployments.

## Production Setup

### 1. Configure Your Environment

!!! danger "Critical Security Action Required"
    Before deploying to production, you **MUST** configure a secure JWT secret. The system is insecure without it.

    1.  Navigate to the `ops/` directory.
    2.  Copy the example environment file:
        ```bash
        cp .env.example .env
        ```
    3.  Open the `.env` file and set a strong, random value for `JWT_SECRET_KEY`. You can generate one with:
        ```bash
        openssl rand -hex 32
        ```
    4.  Update the `POSTGRES_PASSWORD` to a secure password.

### 2. Deploy the System

Use the provided startup script to launch the system with production-ready, pre-built images from GHCR.

```bash
# From the ops/ directory
./start.sh ghcr
```

This command reads the `docker-compose.ghcr.yml` file and starts all services in the correct order.

### 3. Verify the Deployment

Check that all services are running and healthy.

```bash
# From the ops/ directory
docker compose -f docker-compose.ghcr.yml ps

# Query the health endpoint
curl http://localhost:8080/health
```

## Scaling & High Availability

### Horizontal Scaling

You can scale the number of `worker` and `api` services to handle higher loads. Use the `--scale` flag with the appropriate compose file.

```bash
# From the ops/ directory

# Scale workers to handle more concurrent tasks
docker compose -f docker-compose.ghcr.yml up -d --scale worker=5

# Scale the API for high availability behind a load balancer
docker compose -f docker-compose.ghcr.yml up -d --scale api=3
```

## Production Operations

### Data Persistence & Backups

- **PostgreSQL:** All core data is stored in the PostgreSQL database. The data is persisted in a Docker volume named `postgres_data`. You must implement a standard database backup strategy (e.g., a cron job running `pg_dump`) to protect your data.
- **Redis:** Redis is used for transient data like event streams and caches. While basic persistence is enabled, it should not be treated as a primary data store.

### Monitoring

The system is designed for observability. You can deploy a full monitoring stack (Prometheus, Grafana, etc.) using the provided compose file:

```bash
# From the ops/ directory
docker compose -f docker-compose.ghcr.yml -f docker-compose.observability.yml up -d
```

### Image Update Strategy

For production stability, it is recommended to pin your deployment to a specific version tag instead of using `latest`.

Edit your `ops/docker-compose.ghcr.yml` file:

```yaml
services:
  api:
    image: ghcr.io/yoda-digital/ordinaut-api:v1.7.1 # Pinned version
  scheduler:
    image: ghcr.io/yoda-digital/ordinaut-scheduler:v1.7.1 # Pinned version
  worker:
    image: ghcr.io/yoda-digital/ordinaut-worker:v1.7.1 # Pinned version
```

To update, you can pull the latest images and restart the services:

```bash
# Pull the latest tagged images
docker compose -f docker-compose.ghcr.yml pull

# Restart the services to apply the update
docker compose -f docker-compose.ghcr.yml up -d
```