# Depanare (Troubleshooting)

Acest ghid oferă soluții la problemele comune pe care le puteți întâmpina în timpul rulării Ordinaut.

## Listă de Verificare pentru Diagnostic

1.  **Verificați Sănătatea Sistemului:** `curl http://localhost:8080/health | jq`
2.  **Verificați Starea Containerelor:** `docker compose ps`
3.  **Verificați Jurnalele Serviciilor:** `docker compose logs -f <service_name>`

## Probleme Comune

### Erori de Autentificare (`401`/`403`)

- **Simptom:** Primiți o eroare `401 Unauthorized` sau `403 Forbidden`.
- **Soluție:**
    1.  **`401 Unauthorized`**: Asigurați-vă că furnizați un token JWT valid în antetul `Authorization: Bearer <token>`.
    2.  **`403 Forbidden`**: Agentul autentificat nu are `scope`-urile necesare pentru acțiune.
    3.  **Consultați Avertismentele de Securitate:** Verificați ghidul de [Autentificare](../api/authentication.md) pentru avertismente critice.

### Sarcinile nu se execută

- **Simptom:** Creați o sarcină, dar aceasta nu rulează niciodată.
- **Soluție:**
    1.  Verificați coada `due_work` în baza de date PostgreSQL.
    2.  Verificați jurnalele `scheduler`.
    3.  Asigurați-vă că starea sarcinii este `active`.

### Un pas din pipeline eșuează

- **Simptom:** O rulare a unei sarcini are starea `success: false`.
- **Soluție:**
    1.  Obțineți detaliile rulării cu `GET /runs/{id}`.
    2.  Examinați câmpul `error`.
    3.  Verificați jurnalele `worker`.

### Serviciul nu pornește

- **Simptom:** Un container (de ex., `api`) se oprește imediat sau intră într-o buclă de repornire.
- **Soluție:**
    1.  **Verificați Secretele Lipsă:** Pentru implementări de producție, asigurați-vă că ați creat un fișier `.env` în directorul `ops/` și ați setat un `JWT_SECRET_KEY` sigur.
    2.  **Verificați Sănătatea Bazei de Date/Redis:** Asigurați-vă că containerele `postgres` și `redis` sunt sănătoase.
