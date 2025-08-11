# Troubleshooting

This guide provides solutions to common problems you might encounter while running Ordinaut.

## Diagnostic Checklist

When an issue occurs, start with these steps:

1.  **Check System Health:** Query the main health endpoint.
    ```bash
    curl http://localhost:8080/health | jq
    ```
    Look for any components that are not `healthy`.

2.  **Check Container Status:**
    ```bash
    docker compose ps
    ```
    Ensure all services are `Up` and `healthy`.

3.  **Check Service Logs:** View the logs for the specific component that seems to be failing.
    ```bash
    # Example: Check the worker logs
    docker compose logs -f worker
    ```

## Common Problems

### Tasks are not executing

- **Symptom:** You create a task, but it never runs.
- **Solution:**
    1.  **Check the `due_work` queue:** Connect to the PostgreSQL database and run `SELECT COUNT(*) FROM due_work WHERE run_at <= now();`. If the count is high, your workers may be overloaded or stuck.
    2.  **Check the scheduler logs:** Run `docker compose logs scheduler` to see if it's correctly calculating and enqueuing run times.
    3.  **Check the task status:** Ensure the task is `active` and not `paused` by querying `GET /tasks/{id}`.

### Pipeline step is failing

- **Symptom:** A task run has a `success: false` status.
- **Solution:**
    1.  **Get the run details:** Query `GET /runs/{id}` for the failed run.
    2.  **Examine the `error` field:** This will contain the specific error message, such as a tool timeout, a validation error, or a connection failure.
    3.  **Check worker logs:** The worker logs will contain a detailed stack trace and context for the failure.

### High CPU or Memory Usage

- **Symptom:** The system is slow or unresponsive.
- **Solution:**
    1.  **Identify the bottleneck:** Use `docker stats` to see which container is consuming the most resources.
    2.  **Scale your workers:** If the `due_work` queue is consistently large, you may need more workers. See the [Deployment Guide](deployment.md).
    3.  **Optimize pipelines:** Look for inefficient pipeline steps that may be performing heavy computations or large data transfers.

### Database Connection Errors

- **Symptom:** The API or other services report that they cannot connect to the database.
- **Solution:**
    1.  **Check PostgreSQL container:** Ensure the `postgres` container is running and healthy.
    2.  **Check connection pool:** The `GET /health` endpoint provides details on the database connection pool status. If the pool is exhausted, you may need to increase its size in the configuration.
    3.  **Check network:** Ensure the Docker network is functioning correctly.
