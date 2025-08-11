# Core Concepts

Understanding these core concepts is key to using Ordinaut effectively. They form the building blocks of any automation you create.

---

### Agent

An **Agent** is an actor in the system, identified by a unique ID (UUID) and an authentication token. Agents are the owners of tasks and the initiators of actions. You can create different agents for different roles (e.g., a `reporting-agent`, a `data-processing-agent`) and grant them specific permissions (scopes) to control what they are allowed to do.

---

### Task

The **Task** is the fundamental unit of work in Ordinaut. It is a persistent object that brings together the *what*, *when*, and *how* of an automation.

A Task object contains:
- **Metadata:** A `title` and `description` for human readability.
- **Schedule:** Defines *when* the task should run.
- **Pipeline:** Defines the sequence of steps to execute.
- **Execution Policy:** Defines *how* the task should run, including its `priority`, `max_retries`, and `concurrency_key`.
- **Ownership:** The `created_by` field links the task to an Agent.

---

### Schedule

The **Schedule** determines when a task is triggered. Ordinaut provides a highly flexible scheduling system that supports multiple types of triggers.

| `schedule_kind` | Description                                                                                             | Example `schedule_expr`                                     |
|:----------------|:--------------------------------------------------------------------------------------------------------|:------------------------------------------------------------|
| `cron`          | Uses standard 5-field cron syntax for recurring schedules.                                              | `"0 9 * * 1-5"` (Every weekday at 9:00 AM)                |
| `rrule`         | Uses RFC-5545 Recurrence Rules for complex calendar-based logic.                                          | `"FREQ=MONTHLY;BYDAY=-1FR"` (The last Friday of every month) |
| `once`          | Executes the task a single time at a specific ISO 8601 timestamp.                                       | `"2025-12-31T23:59:59Z"`                                  |
| `event`         | Triggers the task when a matching event is published to the system.                                     | `"user.email.received"`                                   |

!!! tip "Timezones are Important"
    All schedules are timezone-aware. You should always specify a `timezone` (e.g., `Europe/Chisinau`) in your task definition to ensure schedules trigger at the correct local time, especially across Daylight Saving Time changes.

---

### Pipeline

The **Pipeline** is the heart of a task—it's the declarative definition of the work to be done. It consists of an ordered list of **Steps**.

- **Data Flow:** The output of one step can be used as the input for subsequent steps, allowing you to chain operations together.
- **Parameters:** Pipelines can receive initial data from the `payload.params` object in the task definition.
- **Conditional Logic:** Steps can be executed conditionally based on the output of previous steps.

---

### Step

A **Step** is a single, atomic action within a pipeline. Each step has several key properties:

- `id`: A unique name for the step within the pipeline.
- `uses`: The address of the **Tool** to be executed (e.g., `telegram.send_message`).
- `with`: An object containing the arguments to pass to the tool. This is where you can use template variables.
- `save_as`: A name to store the step's output under. This makes the result available to later steps via the `steps` context.
- `if`: A conditional expression that determines whether the step should run.

---

### Tool

A **Tool** is a registered, reusable capability that can be called from a pipeline step. Each tool has a strictly defined **input schema** and **output schema**, which ensures that data flowing through the pipeline is predictable and valid. Ordinaut can be extended with tools that connect to any external API or service.

---

### Run

A **Run** is a record of a single execution of a task's pipeline. Every time a task is triggered by its schedule or an event, a new Run object is created. This object tracks:

- The start and end time of the execution.
- The final status (`success` or `failure`).
- The number of retry `attempt`s.
- The detailed `output` of the pipeline, including the results of each step.
- Any `error` that occurred.

This provides a complete, auditable history of every action the system takes.

---

### `due_work` Queue

This is an internal database table that acts as the job queue. The **Scheduler**'s only job is to calculate the next run time for each task and insert a corresponding row into the `due_work` table. The **Workers** then poll this table, safely lease jobs using `FOR UPDATE SKIP LOCKED`, and execute them. This decoupling of scheduling from execution is fundamental to Ordinaut's reliability and scalability.