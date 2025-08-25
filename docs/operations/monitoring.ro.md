# Monitorizare

Ordinaut este conceput pentru medii de producție și expune metrici cheie pentru monitorizare și alertare. Un stack complet de observabilitate poate fi lansat folosind fișierul `docker-compose.observability.yml`.

## Metrici Prometheus

Sistemul expune un punct final compatibil cu Prometheus la `/metrics`. Metricile cheie includ:

- `orchestrator_tasks_created_total`: Contor pentru sarcinile create.
- `orchestrator_runs_total`: Contor pentru rulările sarcinilor, etichetate după stare.
- `orchestrator_task_duration_seconds`: Histograma timpilor de execuție a sarcinilor.
- `orchestrator_due_work_queue_depth`: Indicator care arată numărul de sarcini în așteptare.
- `orchestrator_http_request_duration_seconds`: Histograma latenței cererilor API.

## Panouri de Bord Grafana

Se recomandă configurarea panourilor de bord Grafana pentru a vizualiza aceste metrici. Stack-ul de observabilitate include o instanță Grafana pre-configurată.

## Jurnalizare (Logging)

Toate serviciile produc jurnale structurate (JSON) cu ID-uri de corelare (`task_id`, `run_id`). Stack-ul de observabilitate include **Loki** pentru agregarea centralizată a jurnalelor.