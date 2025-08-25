# Events API

Ordinaut can trigger tasks based on external events. The Events API is the entry point for publishing these events into the system.

---

## `POST /events`

Publishes an event to the system's event spine (Redis Streams). Any tasks configured with a `schedule_kind` of `event` that match the `topic` will be triggered.

**Request Body:**

| Field             | Type   | Required | Description                                      |
|:------------------|:-------|:---------|:-------------------------------------------------|
| `topic`           | string | Yes      | The name/topic of the event (e.g., `user.email.received`). |
| `payload`         | object | Yes      | The JSON payload associated with the event.      |
| `source_agent_id` | UUID   | Yes      | The UUID of the agent publishing the event.      |

**Example Request:**
```json
{
  "topic": "user.email.received",
  "payload": {
    "from": "colleague@example.com",
    "subject": "Project Update Required",
    "priority": "high"
  },
  "source_agent_id": "00000000-0000-0000-0000-000000000001"
}
```

**Response (`202 Accepted`):**

The API acknowledges receipt of the event immediately. The processing happens asynchronously.

```json
{
  "success": true,
  "message": "Event published successfully to topic 'user.email.received'",
  "details": {
    "event_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
    "stream_id": "1673434800000-0",
    "topic": "user.email.received",
    "triggered_tasks": [
      "f0a1b2c3-d4e5-f678-9012-34567890abcd"
    ],
    "published_at": "2025-01-11T12:00:00Z"
  }
}
```

---

## `GET /topics`

Lists all active event topics that have at least one task subscribed to them.

---

## `GET /stream/recent`

Retrieves the most recent events from the event stream. Useful for debugging.

**Query Parameters:**
- `count`: (Optional) The number of events to retrieve (default: 50).

---

## `DELETE /stream/cleanup`

Cleans up old events from the Redis Stream to prevent it from growing indefinitely. This is an administrative action.

**Query Parameters:**
- `max_age_hours`: (Optional) The maximum age of events to keep, in hours (default: 24).
