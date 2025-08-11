# Monitoring

Ordinaut is designed for production environments and exposes key metrics for monitoring and alerting.

## Prometheus Metrics

The system exposes a Prometheus-compatible endpoint at `/metrics`. Key metrics include:

- `orchestrator_tasks_total`: Counter for created tasks.
- `orchestrator_runs_total`: Counter for task runs, labeled by status (`success`, `failure`).
- `orchestrator_step_duration_seconds`: Histogram of pipeline step execution times.
- `orchestrator_due_work_queue_depth`: Gauge showing the number of pending jobs.
- `orchestrator_scheduler_lag_seconds`: Gauge measuring the delay between scheduled time and actual execution.

## Grafana Dashboards

It is recommended to set up Grafana dashboards to visualize these metrics. Key dashboards include:

- **System Health:** An overview of API response times, error rates, and component health.
- **Task & Run Analysis:** Tracking of created vs. completed tasks, success/failure rates, and top failing tasks.
- **Worker Performance:** Monitoring queue depth, processing latency, and worker saturation.

## Logging

All services produce structured (JSON) logs with correlation IDs (`task_id`, `run_id`), allowing for easy filtering and analysis in a centralized logging platform like Loki or the ELK stack.
