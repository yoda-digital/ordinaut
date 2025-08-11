# Ghid de Pornire Rapidă

Acest tutorial vă va ghida prin crearea, programarea și verificarea primului dumneavoastră flux de lucru automatizat cu Ordinaut. Vom crea o sarcină care rulează un pipeline simplu în fiecare minut.

## 1. Definiți Sarcina

Mai întâi, creați un fișier JSON numit `my_first_task.json`. Acest fișier definește totul despre sarcină: numele său, programul său și pipeline-ul de executat.

Această sarcină este programată să ruleze în fiecare minut folosind o expresie cron. Pipeline-ul are doi pași:
1.  Un pas care simulează obținerea de date și salvează rezultatul.
2.  Un pas care folosește rezultatul primului pas în mesajul său.

```json
{
  "title": "Prima Mea Sarcină Automată",
  "description": "O sarcină simplă care rulează în fiecare minut.",
  "schedule_kind": "cron",
  "schedule_expr": "* * * * *",
  "timezone": "Europe/Chisinau",
  "payload": {
    "params": {
      "user_name": "Utilizator Ordinaut"
    },
    "pipeline": [
      {
        "id": "get_data",
        "uses": "debug.echo",
        "with": {
          "message": "Salut, ${params.user_name}!",
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
          "message": "Pasul 1 a spus: '${steps.greeting.message}' la ${steps.greeting.details.timestamp}"
        }
      }
    ]
  },
  "created_by": "00000000-0000-0000-0000-000000000001"
}
```

!!! info "Utilizarea Instrumentelor"
    Instrumentele `debug.echo` și `debug.log` sunt utilitare încorporate pentru testare. `debug.echo` returnează pur și simplu datele pe care le primește, în timp ce `debug.log` tipărește mesajul în jurnalul worker-ului.

## 2. Creați Sarcina prin API

Cu serviciile Ordinaut în funcțiune, folosiți `curl` pentru a trimite definiția sarcinii dumneavoastră la API. Acest lucru înregistrează sarcina în sistem, iar planificatorul o va prelua imediat.

```bash
curl -X POST http://localhost:8080/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-agent-token" \
  -d @my_first_task.json
```

API-ul va răspunde cu ID-ul unic al sarcinii nou create. **Copiați acest ID de sarcină** pentru pasul următor.

```json
{
  "id": "a1b2c3d4-e5f6-7890-1234-567890abcdef"
}
```

## 3. Verificați Execuția

Deoarece sarcina este programată să ruleze în fiecare minut, puteți observa istoricul execuției aproape imediat.

### Verificați Istoricul Rulărilor

Așteptați să treacă un minut, apoi folosiți punctul final `runs` pentru a vedea istoricul. Înlocuiți `{task-id}` cu ID-ul pe care l-ați copiat.

```bash
curl "http://localhost:8080/runs?task_id={task-id}&limit=5"
```

Veți vedea un răspuns JSON care listează rulările recente. Căutați `"success": true`.

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

### Verificați Jurnalele Worker-ului

Puteți vedea, de asemenea, execuția live în jurnalele worker-ului. Instrumentul `debug.log` pe care l-am folosit în pipeline își va tipări rezultatul acolo.

```bash
docker compose logs -f worker
```

Veți vedea înregistrări în jurnal ca acestea în fiecare minut:

```
INFO:root:Executing step: process_data
INFO:root:Step process_data log: Step 1 said: 'Hello, Ordinaut User!' at 2025-08-11T12:01:00.123Z
INFO:root:Task a1b2c3d4-e5f6-7890-1234-567890abcdef completed successfully
```

---

Felicitări! Ați creat și verificat cu succes un flux de lucru automatizat recurent. Acum puteți adapta acest proces pentru a construi automatizări mai complexe și mai puternice, definind diferite programe și pipeline-uri.
