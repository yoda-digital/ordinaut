# API-ul de Sarcini (Tasks)

API-ul de Sarcini este interfața principală pentru crearea, gestionarea și monitorizarea fluxurilor de lucru automate.

## `POST /tasks`

Creează o nouă sarcină programată.

| Câmp                | Tip     | Necesar  | Descriere                                                                      |
|:----------------------|:--------|:---------|:-------------------------------------------------------------------------------|
| `title`               | string  | Da       | Un titlu lizibil pentru sarcină.                                               |
| `description`         | string  | Da       | O descriere mai detaliată a ceea ce face sarcina.                              |
| `schedule_kind`       | string  | Da       | Tipul de programare: `cron`, `rrule`, `once` sau `event`.                        |
| `schedule_expr`       | string  | Cond.    | Expresia de programare (de ex., șir cron, RRULE). Necesară pentru toate, cu excepția `event`. |
| `timezone`            | string  | Nu       | Fusul orar pentru programare (de ex., `Europe/Chisinau`). Implicit este UTC.     |
| `payload`             | object  | Da       | Definiția pipeline-ului care trebuie executat.                                 |
| `created_by`          | UUID    | Da       | ID-ul agentului care creează sarcina.                                          |
| `priority`            | integer | Nu       | O prioritate de la 1-9 (1 este cea mai mare). Implicit este 5.                   |
| `max_retries`         | integer | Nu       | Numărul de reîncercări pentru o rulare eșuată. Implicit este 3.                |

**Exemplu de Cerere:**

```bash
curl -X POST http://localhost:8080/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-agent-token" \
  -d @/path/to/your/task-definition.json
```

---


## `GET /tasks`

Afișează sarcinile cu filtrare opțională.

**Parametri de Interogare:**
- `status`: Filtrează după `active`, `paused` sau `canceled`.
- `limit`: Numărul de rezultate de returnat (implicit: 50).
- `offset`: Decalaj pentru paginare.

---


## `GET /tasks/{id}`

Recuperează detaliile complete ale unei sarcini specifice după UUID-ul său.

---


## `POST /tasks/{id}/run_now`

Declanșează o execuție imediată, unică, a unei sarcini, ocolind programul său regulat.

---


## `POST /tasks/{id}/pause`

Întrerupe o sarcină, prevenind orice rulări programate viitoare până la reluarea sa.

---


## `POST /tasks/{id}/resume`

Reia o sarcină întreruptă anterior.

---


## `POST /tasks/{id}/cancel`

Anulează permanent o sarcină. Această acțiune nu poate fi anulată.
