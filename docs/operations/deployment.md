# Deployment

This guide covers deploying the Ordinaut system to a production environment using Docker Compose.

## Production Setup

The recommended way to run Ordinaut in production is using the provided Docker Compose files, which manage the multi-container setup.

### Configuration

1.  **Environment Variables:** Before deploying, copy the `.env.example` file in the `ops/` directory to `.env` and customize the values. It is **critical** to set a secure, random `JWT_SECRET_KEY`.

2.  **Docker Compose:** The `docker-compose.prod.yml` file is optimized for production. It uses environment variables for configuration, sets resource limits, and enables multiple worker replicas.

### Starting the System

Use the provided start script to launch the production stack:

```bash
cd ops/

# Ensure your .env file is configured

./start.sh prod --build
```

This will start all services in detached mode with production settings.

## Scaling

### Worker Scaling

The most common scaling requirement is to adjust the number of `worker` replicas to handle your task load. You can do this with the `--scale` flag:

```bash
# Scale to 5 worker instances
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --scale worker=5
```

### API Server Scaling

For high availability, you can also scale the `api` service and place them behind a load balancer.

## Data Persistence & Backups

- **PostgreSQL:** All core data is stored in the PostgreSQL database. The data is persisted in a Docker volume (`pgdata-prod`). You should implement a standard PostgreSQL backup strategy (e.g., `pg_dump`) to protect your data.

- **Redis:** Redis is used for transient data like event streams and caches. While it has persistence enabled, it should not be treated as a primary data store.

Refer to the `BACKUP_PROCEDURES.md` and `DISASTER_RECOVERY.md` documents in the `ops/` directory for detailed operational plans.
