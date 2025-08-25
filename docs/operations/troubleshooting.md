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
    # Example: Check the API logs
    docker compose logs -f api
    ```

## Common Problems

### Authentication Errors (`401`/`403`)

- **Symptom:** You receive a `401 Unauthorized` or `403 Forbidden` error.
- **Solution:**
    1.  **`401 Unauthorized`**: This means your token is missing, invalid, or expired. Ensure you are providing a valid JWT access token in the `Authorization: Bearer <token>` header.
    2.  **`403 Forbidden`**: This means your token is valid, but the authenticated agent does not have the required `scopes` to perform the requested action.
    3.  **Review Security Warnings:** Check the [Authentication guide](../api/authentication.md) for critical security warnings about the current state of the authentication system, as these may be the source of your issue.

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

### Service Fails to Start

- **Symptom:** A container (e.g., `api`) exits immediately or is in a restart loop.
- **Solution:**
    1.  **Check for Missing Secrets:** For production deployments (`start.sh prod` or `start.sh ghcr`), ensure you have created an `.env` file in the `ops/` directory and set a secure `JWT_SECRET_KEY`. The application will fail to start without it.
    2.  **Check Database/Redis Health:** Ensure the `postgres` and `redis` containers are `Up (healthy)` before the other services start. If they are not, check their logs for errors.