# Autentificare

!!! danger "Avertisment Critic de Securitate"
    Sistemul de autentificare **NU ESTE SIGUR** pentru utilizare în producție. Un audit de securitate a identificat două vulnerabilități critice:

    1.  **Ocolirea Autentificării:** Sistemul autentifică în prezent agenții doar pe baza ID-ului lor, fără a valida vreo parolă. Oricine cunoaște ID-ul unui agent îl poate impersona.
    2.  **Cheie Secretă JWT Implicită:** Sistemul utilizează o cheie secretă JWT implicită, hardcodată, dacă nu este furnizată una sigură prin variabila de mediu `JWT_SECRET_KEY`.

    **Nu implementați acest sistem într-un mediu de producție până când aceste probleme nu sunt rezolvate.**

Toate punctele finale ale API-ului (cu excepția verificărilor publice de sănătate) necesită autentificare bazată pe Agent folosind un **Token Bearer**.

## Autentificare cu Token Bearer

Trebuie să includeți un antet `Authorization` cu token-ul agentului dumneavoastră în fiecare cerere. Token-ul ar trebui să fie prefixat cu `Bearer `.

```bash
curl -H "Authorization: Bearer <your-jwt-access-token>" \
     https://api.ordinaut.example.com/v1/tasks
```

## Scopurile și Permisiunile Agentului

Autentificarea este legată de un **Agent** specific, care are un set de **scopuri (scopes)** ce îi acordă permisiunea de a efectua anumite acțiuni. Dacă un agent încearcă o acțiune în afara scopurilor sale permise, API-ul va returna o eroare `403 Forbidden`.

## Răspunsuri de Eroare

- `401 Unauthorized`: Returnat dacă token-ul este invalid sau lipsește.
- `403 Forbidden`: Returnat dacă token-ul este valid, dar agentul nu are scopurile necesare.

