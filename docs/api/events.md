# Events API

Ordinaut can trigger tasks based on external events. The Events API is the entry point for publishing these events into the system.

## `POST /events`

Publishes an event to the system's event spine (Redis Streams). Any tasks configured with a `schedule_kind` of `event` that match the `event_type` will be triggered.

**Request Body:**

| Field        | Type   | Required | Description                                      |
|:-------------|:-------|:---------|:-------------------------------------------------|
| `event_type` | string | Yes      | The name of the event (e.g., `user.email.received`). |
| `data`       | object | Yes      | The JSON payload associated with the event.      |
| `source`     | string | No       | An identifier for the system that sent the event.|

**Example Request:**
```json
{
  "event_type": "user.email.received",
  "data": {
    "from": "colleague@example.com",
    "subject": "Project Update Required",
    "priority": "high"
  },
  "source": "email-monitor-agent"
}
```

**Response (`202 Accepted`):**

The API acknowledges receipt of the event immediately. The processing happens asynchronously.

```json
{
  "success": true,
  "message": "Event published successfully",
  "event_id": "evt_abc123def456",
  "matched_tasks": 2
}
```