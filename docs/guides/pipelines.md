# Pipelines & Tools

Ordinaut's power comes from its declarative pipeline engine, which executes a series of steps in a predictable and reliable way.

## Pipeline Structure

A pipeline is a JSON array of **steps** defined in the `payload` of a Task. The engine processes these steps in order, passing context between them.

```json
{
  "payload": {
    "params": { "city": "Chisinau" },
    "pipeline": [
      {
        "id": "get_weather",
        "uses": "weather-api.get_forecast",
        "with": {"location": "${params.city}"},
        "save_as": "weather"
      },
      {
        "id": "send_alert",
        "uses": "telegram.send_message",
        "if": "steps.weather.temperature > 25",
        "with": {
          "message": "It's hot today: ${steps.weather.temperature}°C"
        }
      }
    ]
  }
}
```

### Key Step Properties

- `id`: A unique identifier for the step within the pipeline.
- `uses`: The address of the **Tool** to execute (e.g., `weather-api.get_forecast`).
- `with`: An object containing the arguments for the tool. This section supports template variables.
- `save_as`: The key under which the step's output will be saved in the context. This allows subsequent steps to use the result (e.g., `steps.weather`).
- `if`: A conditional [JMESPath](https://jmespath.org/) expression. If it evaluates to a "falsy" value (like `false`, `null`, `[]`, `{}`), the step is skipped.
- `timeout_seconds`: An optional timeout for the tool call (default is 30 seconds).
- `max_retries`: An optional number of times to retry this specific step if it fails.

## Template Variables

You can dynamically insert data into the `with` block using template variables, which are resolved using JMESPath expressions against the current context.

- **`${params.variable_name}`**: Accesses parameters defined in the `payload.params` section of the task.
- **`${steps.step_id.output_field}`**: Accesses the output of a previous step that used `save_as`. You can traverse nested JSON objects (e.g., `${steps.weather.details.humidity}`).
- **`${now}`**: A special variable that provides the current UTC timestamp in ISO 8601 format.

## Tool Catalog

Tools are the building blocks of pipelines. They represent a specific capability, like sending an email or querying a database. Each tool is defined in a central catalog and has a strict contract:

- **Address:** A unique, human-readable identifier (e.g., `google-calendar.list_events`).
- **Input Schema:** A JSON Schema that defines the expected arguments. The pipeline engine validates the `with` block of a step against this schema before execution.
- **Output Schema:** A JSON Schema that defines the expected result. The engine validates the tool's response against this schema after execution.

This schema-driven approach ensures that all interactions are predictable, validated, and type-safe, which is critical for building robust automations.

## Error Handling

If a step fails (e.g., a tool call times out or returns an error), the engine will respect the `max_retries` policy defined on the task or the step itself. If all retries fail, the entire pipeline run is marked as `failed`, and the error details are recorded in the **Run** object.