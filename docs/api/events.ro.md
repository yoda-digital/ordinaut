# API-ul de Evenimente (Events)

Backend-ul API Ordinaut poate declanșa sarcini pe baza evenimentelor externe, permițând asistenților AI să creeze workflow-uri reactive prin MCP. API-ul de Evenimente este punctul de intrare pentru publicarea acestor evenimente în sistem.

## `POST /events`

Publică un eveniment în coloana vertebrală de evenimente a sistemului (Redis Streams). Orice sarcini configurate cu un `schedule_kind` de tip `event` care se potrivesc cu `event_type` vor fi declanșate.

**Corpul Cererii:**

| Câmp         | Tip    | Necesar | Descriere                                                    |
|:-------------|:-------|:--------|:-------------------------------------------------------------|
| `event_type` | string | Da      | Numele evenimentului (de ex., `user.email.received`).        |
| `data`       | object | Da      | Sarcina utilă JSON asociată cu evenimentul.                  |
| `source`     | string | Nu      | Un identificator pentru sistemul care a trimis evenimentul.  |

**Exemplu de Cerere:**
```json
{
  "event_type": "user.email.received",
  "data": {
    "from": "colleague@example.com",
    "subject": "Actualizare Proiect Necesară",
    "priority": "high"
  },
  "source": "email-monitor-agent"
}
```

**Răspuns (`202 Accepted`):**

API-ul confirmă primirea evenimentului imediat. Procesarea are loc asincron.

```json
{
  "success": true,
  "message": "Eveniment publicat cu succes",
  "event_id": "evt_abc123def456",
  "matched_tasks": 2
}
```
