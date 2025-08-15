# Depanare (Troubleshooting)

Acest ghid oferă soluții la problemele comune pe care le puteți întâmpina în timpul rulării backend-ului API Ordinaut pentru programarea sarcinilor.

## Listă de Verificare pentru Diagnostic

Când apare o problemă, începeți cu acești pași:

1.  **Verificați Sănătatea Sistemului:** Interogați punctul final principal de sănătate.
    ```bash
    curl http://localhost:8080/health | jq
    ```
    Căutați orice componente care nu sunt `healthy`.

2.  **Verificați Starea Containerelor:**
    ```bash
    docker compose ps
    ```
    Asigurați-vă că toate serviciile sunt `Up` și `healthy`.

3.  **Verificați Jurnalele Serviciilor:** Vizualizați jurnalele pentru componenta specifică care pare să aibă probleme.
    ```bash
    # Exemplu: Verificați jurnalele worker-ului
    docker compose logs -f worker
    ```

## Probleme Comune

### Sarcinile nu se execută

- **Simptom:** Creați o sarcină, dar aceasta nu rulează niciodată.
- **Soluție:**
    1.  **Verificați coada `due_work`:** Conectați-vă la baza de date PostgreSQL și rulați `SELECT COUNT(*) FROM due_work WHERE run_at <= now();`. Dacă numărul este mare, workerii dumneavoastră pot fi supraîncărcați sau blocați.
    2.  **Verificați jurnalele planificatorului:** Rulați `docker compose logs scheduler` pentru a vedea dacă calculează și adaugă corect în coadă timpii de rulare.
    3.  **Verificați starea sarcinii:** Asigurați-vă că sarcina este `active` și nu `paused` interogând `GET /tasks/{id}`.

### Un pas din pipeline eșuează

- **Simptom:** O rulare a unei sarcini are starea `success: false`.
- **Soluție:**
    1.  **Obțineți detaliile rulării:** Interogați `GET /runs/{id}` pentru rularea eșuată.
    2.  **Examinați câmpul `error`:** Acesta va conține mesajul de eroare specific, cum ar fi un timeout al instrumentului, o eroare de validare sau o defecțiune a conexiunii.
    3.  **Verificați jurnalele worker-ului:** Jurnalele worker-ului vor conține o urmă detaliată a stivei (stack trace) și context pentru eșec.

### Utilizare Ridicată a CPU-ului sau a Memoriei

- **Simptom:** Sistemul este lent sau nu răspunde.
- **Soluție:**
    1.  **Identificați blocajul:** Folosiți `docker stats` pentru a vedea ce container consumă cele mai multe resurse.
    2.  **Scalați workerii:** Dacă coada `due_work` este constant mare, este posibil să aveți nevoie de mai mulți workeri. Consultați [Ghidul de Implementare](deployment.md).
    3.  **Optimizați pipeline-urile:** Căutați pași ineficienți în pipeline care ar putea efectua calcule grele sau transferuri mari de date.

### Erori de Conexiune la Baza de Date

- **Simptom:** API-ul sau alte servicii raportează că nu se pot conecta la baza de date.
- **Soluție:**
    1.  **Verificați containerul PostgreSQL:** Asigurați-vă că containerul `postgres` funcționează și este sănătos.
    2.  **Verificați pool-ul de conexiuni:** Punctul final `GET /health` oferă detalii despre starea pool-ului de conexiuni la baza de date. Dacă pool-ul este epuizat, poate fi necesar să măriți dimensiunea acestuia în configurație.
    3.  **Verificați rețeaua:** Asigurați-vă că rețeaua Docker funcționează corect.