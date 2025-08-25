# Runs API

The Runs API allows you to monitor the execution history of your tasks.

---

## `GET /runs`

Lists task execution runs with optional filtering and pagination.

**Query Parameters:**

- `task_id`: (Optional) Filter runs for a specific task UUID.
- `success`: (Optional) Filter by execution result (`true` or `false`).
- `start_time`: (Optional) Filter for runs that started after this ISO 8601 timestamp.
- `end_time`: (Optional) Filter for runs that started before this ISO 8601 timestamp.
- `include_errors`: (Optional) If `true`, includes full error messages in the response. Defaults to `false`.
- `limit`: (Optional) Number of results to return (default: 50, max: 200).
- `offset`: (Optional) Pagination offset.

**Example Response:**

```json
{
  "items": [
    {
      "id": "7f3e4d2c-1a9b-4c8d-9e6f-2b5a8c7d4e9f",
      "task_id": "550e8400-e29b-41d4-a716-446655440000",
      "lease_owner": "worker-xyz",
      "leased_until": "2025-01-11T08:00:32+02:00",
      "started_at": "2025-01-11T08:00:00+02:00",
      "finished_at": "2025-01-11T08:00:02+02:00",
      "success": true,
      "error": null,
      "attempt": 1,
      "output": {},
      "created_at": "2025-01-11T07:59:58+02:00"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0,
  "has_more": false
}
```

---

## `GET /runs/{run_id}`

Retrieves the detailed results of a single task run, including the full output from the pipeline execution.

---

## `GET /task/{task_id}/latest`

Retrieves the most recent run for a specific task. Returns a single run object or `null` if the task has never been executed.

---

## `GET /task/{task_id}/stats`

Retrieves execution statistics for a specific task over a given period.

**Query Parameters:**

- `days`: (Optional) The number of past days to include in the analysis (default: 30).

---

## `GET /stats/summary`

Retrieves system-wide execution statistics across all tasks.

**Query Parameters:**

- `days`: (Optional) The number of past days to include in the analysis (default: 7).
