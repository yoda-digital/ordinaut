# Tasks API

The Tasks API is the primary interface for creating, managing, and monitoring automated workflows.

## `POST /tasks`

Creates a new scheduled task.

| Field                 | Type    | Required | Description                                                              |
|:----------------------|:--------|:---------|:-------------------------------------------------------------------------|
| `title`               | string  | Yes      | A human-readable title for the task.                                     |
| `description`         | string  | Yes      | A more detailed description of what the task does.                       |
| `schedule_kind`       | string  | Yes      | The type of schedule: `cron`, `rrule`, `once`, or `event`.                 |
| `schedule_expr`       | string  | Cond.    | The schedule expression (e.g., cron string, RRULE). Required for all but `event`. |
| `timezone`            | string  | No       | The timezone for the schedule (e.g., `Europe/Chisinau`). Defaults to UTC. |
| `payload`             | object  | Yes      | The pipeline definition to be executed.                                  |
| `created_by`          | UUID    | Yes      | The ID of the agent creating the task.                                   |
| `priority`            | integer | No       | A priority from 1-9 (1 is highest). Default is 5.                        |
| `max_retries`         | integer | No       | The number of times to retry a failed run. Default is 3.                 |

**Example Request:**

```bash
curl -X POST http://localhost:8080/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-agent-token" \
  -d @/path/to/your/task-definition.json
```

---

## `GET /tasks`

Lists tasks with optional filtering.

**Query Parameters:**
- `status`: Filter by `active`, `paused`, or `canceled`.
- `limit`: Number of results to return (default: 50).
- `offset`: Pagination offset.

---

## `GET /tasks/{id}`

Retrieves the full details of a specific task by its UUID.

---

## `POST /tasks/{id}/run_now`

Triggers an immediate, one-time execution of a task, bypassing its regular schedule.

---

## `POST /tasks/{id}/pause`

Pauses a task, preventing any future scheduled runs until it is resumed.

---

## `POST /tasks/{id}/resume`

Resumes a previously paused task.

---

## `POST /tasks/{id}/cancel`

Permanently cancels a task. This action cannot be undone.