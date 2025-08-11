# API-ul de Rulări (Runs)

API-ul de Rulări vă permite să monitorizați istoricul de execuție al sarcinilor dumneavoastră.

## `GET /runs`

Afișează rulările de execuție ale sarcinilor cu filtrare opțională.

**Parametri de Interogare:**
- `task_id`: Filtrează rulările pentru un UUID de sarcină specific.
- `success`: Filtrează după rezultatul execuției (`true` sau `false`).
- `limit`: Numărul de rezultate de returnat (implicit: 50).
- `offset`: Decalaj pentru paginare.

**Exemplu de Răspuns:**
```json
{
  "runs": [
    {
      "id": "7f3e4d2c-1a9b-4c8d-9e6f-2b5a8c7d4e9f",
      "task_id": "550e8400-e29b-41d4-a716-446655440000",
      "started_at": "2025-01-11T08:00:00+02:00",
      "finished_at": "2025-01-11T08:00:02+02:00",
      "success": true,
      "attempt": 1,
      "duration_ms": 2150
    }
  ]
}
```

---

## `GET /runs/{id}`

Recuperează rezultatele detaliate ale unei singure rulări de sarcină, inclusiv rezultatul complet al execuției pipeline-ului.

**Exemplu de Răspuns (Succes):**
```json
{
  "id": "7f3e4d2c-1a9b-4c8d-9e6f-2b5a8c7d4e9f",
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "success": true,
  "error": null,
  "output": {
    "steps": {
      "weather": {
        "temperature": 15,
        "summary": "Parțial înnorat, 15°C"
      }
    }
  }
}
```

**Exemplu de Răspuns (Eșec):**
```json
{
  "id": "9b5g6f4e-3c1d-6e0f-1a8b-4d7c0e9f6a1b",
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "success": false,
  "error": "Instrumentul 'weather-api.get_forecast' a expirat după 30 de secunde",
  "output": {
    "failed_step": "get_weather",
    "partial_results": {}
  }
}
```
