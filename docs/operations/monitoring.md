# Monitoring

Ordinaut is designed for production environments and exposes key metrics for monitoring and alerting. A full observability stack can be launched using the `docker-compose.observability.yml` file in the `ops/` directory.

## Prometheus Metrics

The system exposes a Prometheus-compatible endpoint at `/metrics`. Key metrics include:

### Core Metrics
- `orchestrator_tasks_created_total`: Counter for created tasks, labeled by `schedule_kind` and `agent_id`.
- `orchestrator_runs_total`: Counter for task runs, labeled by `status`, `task_id`, and `agent_id`.
- `orchestrator_task_duration_seconds`: Histogram of complete task execution times.
- `orchestrator_step_duration_seconds`: Histogram of individual pipeline step execution times.

### System & Worker Health
- `orchestrator_due_work_queue_depth`: Gauge showing the number of pending jobs.
- `orchestrator_scheduler_lag_seconds`: Gauge measuring the delay between scheduled time and actual execution.
- `orchestrator_active_workers`: Gauge showing the number of active workers and their state.
- `orchestrator_worker_heartbeat_total`: Counter for worker heartbeats.

### API & Security
- `orchestrator_http_request_duration_seconds`: Histogram of API request latency.
- `orchestrator_security_events_total`: Counter for security events, labeled by `event_type` and `severity`.
- `orchestrator_authentication_attempts_total`: Counter for authentication attempts, labeled by `result`.

## Grafana Dashboards

The `ops/` directory contains provisioning files for Grafana, which can be used to visualize the Prometheus metrics. It is recommended to set up dashboards to monitor:

- **System Health:** An overview of API response times, error rates, and component health.
- **Task & Run Analysis:** Tracking of created vs. completed tasks, success/failure rates, and top failing tasks.
- **Worker Performance:** Monitoring queue depth, processing latency, and worker saturation.

## Logging

All services produce structured (JSON) logs with correlation IDs (`task_id`, `run_id`), allowing for easy filtering and analysis. The provided observability stack includes **Loki** for centralized log aggregation, which can be queried from Grafana.