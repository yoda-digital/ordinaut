# API-ul de Sănătate (Health)

API-ul de Sănătate oferă puncte finale pentru monitorizarea stării sistemului Ordinaut. Acestea sunt esențiale pentru operațiunile de producție, echilibrarea încărcăturii și recuperarea automată.

## `GET /health`

Oferă o verificare de sănătate cuprinzătoare și detaliată a întregului sistem și a componentelor sale (Bază de date, Redis, Planificator, Workeri). Acesta este cel mai bun punct final pentru o imagine de ansamblu a stării sistemului.

**Exemplu de Răspuns:**
```json
{
  "status": "healthy",
  "timestamp": "2025-01-11T10:45:00Z",
  "version": "1.0.0",
  "checks": [
    {
      "name": "database",
      "status": "healthy",
      "message": "Pool-ul de conexiuni PostgreSQL este sănătos"
    },
    {
      "name": "redis",
      "status": "healthy",
      "message": "Conexiunea Redis este activă"
    }
  ]
}
```

---

## `GET /health/ready`

Un punct final ușor, potrivit pentru o **sondă de pregătire (readiness probe)** Kubernetes. Returnează o stare `200 OK` dacă serviciul este gata să accepte trafic (de exemplu, conexiunile la baza de date și cache sunt disponibile). Un echilibrator de încărcătură ar trebui să direcționeze traficul către o instanță numai dacă această verificare trece.

---

## `GET /health/live`

Un punct final minimal, potrivit pentru o **sondă de viață (liveness probe)** Kubernetes. Returnează o stare `200 OK` dacă procesul API este în viață și răspunde. Această verificare nu verifică dependențele din aval. Dacă această sondă eșuează, orchestratorul de containere ar trebui să repornească instanța.
