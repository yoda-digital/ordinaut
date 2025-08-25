# Referință API

API-ul REST Ordinaut este interfața principală pentru toate interacțiunile cu sistemul de programare a sarcinilor. Este construit cu FastAPI, care oferă documentație interactivă automată.

## Documentație Interactivă

Deși această referință oferă o imagine de ansamblu, puteți utiliza și documentația interactivă generată de API-ul însuși:

- **Swagger UI:** [http://localhost:8080/docs](http://localhost:8080/docs)
- **ReDoc:** [http://localhost:8080/redoc](http://localhost:8080/redoc)

## URL de Bază

- **Dezvoltare:** `http://localhost:8080`
- **Producție:** `https://api.your-domain.com/v1`

## Concepte Comune

### Gestionarea Erorilor

API-ul utilizează coduri de stare HTTP standard. Răspunsurile de eroare urmează un format JSON consistent:

```json
{
  "error": "ValidationError",
  "message": "Expresie de programare invalidă",
  "details": {
    "field": "schedule_expr",
    "value": "cron invalid"
  },
  "request_id": "req-123456789",
  "timestamp": "2025-01-10T10:00:00Z"
}
```

### Limitarea Ratei (Rate Limiting)

Pentru a asigura stabilitatea, API-ul impune limite de rată, implicit pe baza adresei IP a clientului. Dacă depășiți limita, veți primi un răspuns `429 Too Many Requests`. Verificați antetul `Retry-After` pentru a ști când puteți trimite o nouă cerere.
