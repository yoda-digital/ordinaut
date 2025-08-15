# Autentificare

Toate punctele finale ale API-ului (cu excepția verificărilor publice de sănătate) necesită autentificare bazată pe Agent folosind un **Token Bearer**. Asistenții AI se conectează prin MCP folosind aceste token-uri.

## Autentificare cu Token Bearer

Trebuie să includeți un antet `Authorization` cu token-ul agentului dumneavoastră în fiecare cerere. Token-ul ar trebui să fie prefixat cu `Bearer `.

```bash
curl -H "Authorization: Bearer 00000000-0000-0000-0000-000000000001" \
     https://api.ordinaut.example.com/v1/tasks
```

## Scopurile și Permisiunile Agentului

Autentificarea este legată de un **Agent** specific, care are un set de **scopuri (scopes)** ce îi acordă permisiunea de a efectua anumite acțiuni. De exemplu, un agent ar putea avea scopul `tasks:create`, dar nu și `tasks:cancel`.

Dacă un agent încearcă o acțiune în afara scopurilor sale permise, API-ul va returna o eroare `403 Forbidden`.

### Scopuri Comune

- `tasks:create`, `tasks:read`, `tasks:update`, `tasks:delete`
- `runs:read`
- `events:publish`
- `admin` (acordă acces la toate operațiunile)

## Răspunsuri de Eroare

- `401 Unauthorized`: Returnat dacă antetul `Authorization` lipsește sau token-ul este invalid, malformat sau expirat.
- `403 Forbidden`: Returnat dacă token-ul agentului este valid, dar acesta nu are scopurile necesare pentru operațiunea solicitată.

```