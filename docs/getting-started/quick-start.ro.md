# Ghid de Pornire Rapidă

Acest tutorial vă va ghida prin crearea, programarea și verificarea primului dumneavoastră flux de lucru automatizat cu Ordinaut. Vom crea o sarcină care rulează un pipeline simplu în fiecare minut.

## Prerechizite: Porniți Sistemul

Înainte de a crea prima sarcină, aveți nevoie de un sistem Ordinaut funcțional. Urmați [Ghidul de Instalare](installation.md) pentru a începe.

---

## 1. Definiți Sarcina

Mai întâi, creați un fișier JSON numit `my_first_task.json`. Acest fișier definește totul despre sarcină: numele său, programul său și pipeline-ul de executat.

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

## 2. Creați Sarcina prin API

Cu serviciile Ordinaut în funcțiune, folosiți `curl` pentru a trimite definiția sarcinii dumneavoastră la API.

```bash
curl -X POST http://localhost:8080/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-agent-token" \
  -d @my_first_task.json
```

API-ul va răspunde cu ID-ul unic al sarcinii nou create. **Copiați acest ID de sarcină**.

## 3. Verificați Execuția

Deoarece sarcina este programată să ruleze în fiecare minut, puteți observa istoricul execuției aproape imediat.

### Verificați Istoricul Rulărilor

Așteptați să treacă un minut, apoi folosiți punctul final `runs`. Înlocuiți `{task-id}` cu ID-ul pe care l-ați copiat.

```bash
curl "http://localhost:8080/runs?task_id={task-id}&limit=5"
```

### Verificați Jurnalele Worker-ului

Puteți vedea, de asemenea, execuția live în jurnalele worker-ului.

```bash
docker compose logs -f worker
```

---

Felicitări! Ați creat și verificat cu succes un flux de lucru automatizat recurent.