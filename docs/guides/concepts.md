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
- **Schedule:** Defines *when* the task should run, using `schedule_kind` (`cron`, `rrule`, `once`, `event`) and `schedule_expr`.
- **Pipeline:** The `payload` defines the sequence of steps to execute.
- **Execution Policy:** Defines *how* the task should run, including its `priority`, `max_retries`, `backoff_strategy`, and a `concurrency_key` for controlling parallel execution.
- **Ownership:** The `created_by` field links the task to an Agent.

---

### Task Execution Triggers

Ordinaut provides several trigger mechanisms that determine when tasks execute:

- **Time-Based Triggers (`cron`, `rrule`, `once`):** Handled internally by the APScheduler service, which calculates the next run time and places a job in the `due_work` queue.
- **Event-Based Triggers (`event`):** These tasks are not scheduled directly. Instead, they are triggered when an external system publishes a matching event to the `/events` API endpoint.
- **Conditional Triggers (`condition`):** Similar to event-based triggers, these are meant to be triggered by external systems that monitor specific conditions.
- **Manual Triggers:** Any task can be run immediately via a `POST /tasks/{id}/run_now` API call.

---

### Pipeline

The **Pipeline** is the heart of a task—it's the declarative definition of the work to be done, specified in the `payload` field. It consists of an ordered list of **Steps**.

- **Data Flow:** The output of one step can be used as the input for subsequent steps, allowing you to chain operations together.
- **Parameters:** Pipelines can receive initial data from the `payload.params` object in the task definition.
- **Conditional Logic:** Steps can be executed conditionally based on the output of previous steps using an `if` condition.

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

A **Tool** represents a specific, reusable capability that can be called from a pipeline step (e.g., sending an email, querying a database).

!!! warning "Tool Execution is Simulated"
    It is critical to understand that the core Ordinaut engine **simulates tool execution**. When a step with a `uses` field is processed, the engine acknowledges the step, renders the input templates, and generates a mock output. It **does not** execute any real-world code for the tool.

    The system is designed as a pure task scheduler. The actual implementation of tools (e.g., connecting to the Telegram API) must be built as **separate extension services** that interact with Ordinaut via its REST API.

---

### Run

A **Run** is a record of a single execution of a task's pipeline. Every time a task is triggered, a new Run object is created. This object tracks:

- The start and end time of the execution.
- The final status (`success` or `failure`).
- The number of retry `attempt`s.
- The detailed `output` of the pipeline, including the (simulated) results of each step.
- Any `error` that occurred.

This provides a complete, auditable history of every action the system takes.

---

### `due_work` Queue

This is an internal database table that acts as the job queue. The **Scheduler**'s only job is to calculate the next run time for each task and insert a corresponding row into the `due_work` table. The **Workers** then poll this table, safely lease jobs using the `FOR UPDATE SKIP LOCKED` SQL pattern, and execute them. This decoupling of scheduling from execution is fundamental to Ordinaut's reliability and scalability.
