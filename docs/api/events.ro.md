# API-ul de Evenimente (Events)

Ordinaut poate declanșa sarcini pe baza evenimentelor externe. API-ul de Evenimente este punctul de intrare pentru publicarea acestor evenimente în sistem.

---

## `POST /events`

Publică un eveniment în sistem. Orice sarcini configurate cu `schedule_kind` de tip `event` care se potrivesc cu `topic` vor fi declanșate.

**Corpul Cererii:**

| Câmp              | Tip    | Necesar | Descriere                                      |
|:------------------|:-------|:--------|:-------------------------------------------------|
| `topic`           | string | Da      | Numele/topicul evenimentului.                    |
| `payload`         | object | Da      | Sarcina utilă JSON asociată cu evenimentul.      |
| `source_agent_id` | UUID   | Da      | UUID-ul agentului care publică evenimentul.      |

**Răspuns (`202 Accepted`):**

API-ul confirmă primirea evenimentului imediat. Procesarea are loc asincron.

---

## `GET /topics`

Afișează toate subiectele de evenimente active la care este abonată cel puțin o sarcină.

---

## `GET /stream/recent`

Recuperează cele mai recente evenimente din fluxul de evenimente. Util pentru depanare.

---

## `DELETE /stream/cleanup`

Șterge evenimentele vechi din fluxul Redis. Aceasta este o acțiune administrativă.