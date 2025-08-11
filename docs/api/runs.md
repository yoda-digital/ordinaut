# Runs API

The Runs API allows you to monitor the execution history of your tasks.

## `GET /runs`

Lists task execution runs with optional filtering.

**Query Parameters:**
- `task_id`: Filter runs for a specific task UUID.
- `success`: Filter by execution result (`true` or `false`).
- `limit`: Number of results to return (default: 50).
- `offset`: Pagination offset.

**Example Response:**
```json
{
  "runs": [
    {
      "id": "7f3e4d2c-1a9b-4c8d-9e6f-2b5a8c7d4e9f",
      "task_id": "550e8400-e29b-41d4-a716-446655440000",
      "started_at": "2025-01-11T08:00:00+02:00",
      "finished_at": "2025-01-11T08:00:02+02:00",
      "success": true,
      "attempt": 1,
      "duration_ms": 2150
    }
  ]
}
```

---

## `GET /runs/{id}`

Retrieves the detailed results of a single task run, including the full output from the pipeline execution.

**Example Response (Success):**
```json
{
  "id": "7f3e4d2c-1a9b-4c8d-9e6f-2b5a8c7d4e9f",
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "success": true,
  "error": null,
  "output": {
    "steps": {
      "weather": {
        "temperature": 15,
        "summary": "Partly cloudy, 15°C"
      }
    }
  }
}
```

**Example Response (Failure):**
```json
{
  "id": "9b5g6f4e-3c1d-6e0f-1a8b-4d7c0e9f6a1b",
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "success": false,
  "error": "Tool 'weather-api.get_forecast' timeout after 30 seconds",
  "output": {
    "failed_step": "get_weather",
    "partial_results": {}
  }
}
```