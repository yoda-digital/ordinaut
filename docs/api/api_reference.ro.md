# Referință API

API-ul REST Ordinaut este interfața principală pentru agenți și sisteme externe pentru a interacționa cu orchestratorul. API-ul este construit cu FastAPI și oferă documentație interactivă automată.

## Documentație Interactivă

Deși această referință oferă o imagine de ansamblu cuprinzătoare, puteți utiliza și documentația interactivă generată de API-ul însuși:

- **Swagger UI:** [http://localhost:8080/docs](http://localhost:8080/docs)
- **ReDoc:** [http://localhost:8080/redoc](http://localhost:8080/redoc)

Aceste interfețe vă permit să explorați și să testați fiecare punct final direct din browser.

## URL de Bază

- **Dezvoltare:** `http://localhost:8080`
- **Producție:** `https://api.your-domain.com/v1`

## Concepte Comune

### Gestionarea Erorilor

API-ul utilizează coduri de stare HTTP standard pentru a indica succesul sau eșecul unei cereri. Răspunsurile de eroare urmează un format JSON consistent:

```json
{
  "error": "ValidationError",
  "message": "Expresie de programare invalidă",
  "details": {
    "field": "schedule_expr",
    "value": "cron invalid",
    "expected": "Expresie cron validă (de ex., '0 9 * * 1-5')"
  }
}
```

### Limitarea Ratei (Rate Limiting)

Pentru a asigura stabilitatea sistemului, API-ul impune limite de rată pe bază de agent. Dacă depășiți limita de rată, veți primi un răspuns `429 Too Many Requests`. Verificați antetele `X-RateLimit-Remaining` și `X-RateLimit-Reset` pentru a vă gestiona frecvența cererilor.