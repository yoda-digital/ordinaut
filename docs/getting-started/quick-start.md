# Quick Start Tutorial

This tutorial will guide you through creating, scheduling, and verifying your first automated workflow with Ordinaut. We will create a task that runs a simple pipeline every minute.

## 1. Define the Task

First, create a JSON file named `my_first_task.json`. This file defines everything about the task: its name, its schedule, and the pipeline to execute.

This task is scheduled to run every minute using a cron expression. The pipeline has two steps:
1.  A step that simulates getting data and saves the result.
2.  A step that uses the output from the first step in its message.

```json
{
  "title": "My First Automated Task",
  "description": "A simple task that runs every minute.",
  "schedule_kind": "cron",
  "schedule_expr": "* * * * *",
  "timezone": "Europe/Chisinau",
  "payload": {
    "params": {
      "user_name": "Ordinaut User"
    },
    "pipeline": [
      {
        "id": "get_data",
        "uses": "debug.echo",
        "with": {
          "message": "Hello, ${params.user_name}!",
          "details": {
            "timestamp": "${now}"
          }
        },
        "save_as": "greeting"
      },
      {
        "id": "process_data",
        "uses": "debug.log",
        "with": {
          "message": "Step 1 said: '${steps.greeting.message}' at ${steps.greeting.details.timestamp}"
        }
      }
    ]
  },
  "created_by": "00000000-0000-0000-0000-000000000001"
}
```

!!! info "Tool Usage"
    The `debug.echo` and `debug.log` tools are built-in utilities for testing. `debug.echo` simply returns the data it receives, while `debug.log` prints the message to the worker's log.

## 2. Create the Task via API

With the Ordinaut services running, use `curl` to send your task definition to the API. This registers the task with the system and the scheduler will immediately pick it up.

```bash
curl -X POST http://localhost:8080/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-agent-token" \
  -d @my_first_task.json
```

The API will respond with the unique ID of your newly created task. **Copy this task ID** for the next step.

```json
{
  "id": "a1b2c3d4-e5f6-7890-1234-567890abcdef"
}
```

## 3. Verify Execution

Since the task is scheduled to run every minute, you can observe its execution history almost immediately.

### Check the Run History

Wait for a minute to pass, then use the `runs` endpoint to see the history. Replace `{task-id}` with the ID you copied.

```bash
curl "http://localhost:8080/runs?task_id={task-id}&limit=5"
```

You will see a JSON response listing the recent runs. Look for `"success": true`.

```json
{
  "runs": [
    {
      "id": "...",
      "task_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
      "started_at": "2025-08-11T12:01:00.123Z",
      "finished_at": "2025-08-11T12:01:00.456Z",
      "success": true,
      "attempt": 1,
      "duration_ms": 333
    }
  ]
}
```

### Check the Worker Logs

You can also see the live execution in the worker's logs. The `debug.log` tool we used in the pipeline will print its output there.

```bash
docker compose logs -f worker
```

You will see log entries like this every minute:

```
INFO:root:Executing step: process_data
INFO:root:Step process_data log: Step 1 said: 'Hello, Ordinaut User!' at 2025-08-11T12:01:00.123Z
INFO:root:Task a1b2c3d4-e5f6-7890-1234-567890abcdef completed successfully
```

---

Congratulations! You have successfully created and verified a recurring automated workflow. You can now adapt this process to build more complex and powerful automations by defining different schedules and pipelines.