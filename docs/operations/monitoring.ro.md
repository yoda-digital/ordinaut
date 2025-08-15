# Monitorizare

Backend-ul API Ordinaut este conceput pentru medii de producție și expune metrici cheie pentru monitorizarea sistemului de programare a sarcinilor.

## Metrici Prometheus

Sistemul expune un punct final compatibil cu Prometheus la `/metrics`. Metricile cheie includ:

- `orchestrator_tasks_total`: Contor pentru sarcinile create.
- `orchestrator_runs_total`: Contor pentru rulările sarcinilor, etichetate după stare (`succes`, `eșec`).
- `orchestrator_step_duration_seconds`: Histograma timpilor de execuție a pașilor din pipeline.
- `orchestrator_due_work_queue_depth`: Indicator (gauge) care arată numărul de sarcini în așteptare.
- `orchestrator_scheduler_lag_seconds`: Indicator care măsoară întârzierea dintre ora programată și execuția efectivă.

## Panouri de Bord Grafana

Se recomandă configurarea panourilor de bord Grafana pentru a vizualiza aceste metrici. Panourile cheie includ:

- **Sănătatea Sistemului:** O imagine de ansamblu a timpilor de răspuns API, ratelor de eroare și sănătății componentelor.
- **Analiza Sarcinilor și Rulărilor:** Urmărirea sarcinilor create vs. finalizate, ratele de succes/eșec și sarcinile care eșuează cel mai frecvent.
- **Performanța Worker-ilor:** Monitorizarea adâncimii cozii, latenței de procesare și saturației worker-ilor.

## Jurnalizare (Logging)

Toate serviciile produc jurnale structurate (JSON) cu ID-uri de corelare (`task_id`, `run_id`), permițând filtrarea și analiza ușoară într-o platformă centralizată de jurnalizare precum Loki sau stiva ELK.
