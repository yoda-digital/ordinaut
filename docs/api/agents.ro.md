# API-ul de Agenți (Agents)

API-ul de Agenți este utilizat pentru a gestiona agenții care interacționează cu sistemul Ordinaut. Majoritatea acestor puncte finale necesită scopul `admin` pentru acces.

!!! note
    Vă rugăm să consultați ghidul de [Autentificare](./authentication.md) pentru informații critice despre starea actuală a sistemului de autentificare.

---

## `POST /agents`

Creează un agent nou. Necesită scopul `admin`.

---

## `GET /agents`

Afișează toți agenții. Necesită scopul `admin`.

---

## `GET /agents/{agent_id}`

Recuperează un agent specific după UUID-ul său. Necesită scopul `admin`.

---

## Puncte Finale de Autentificare

Aceste puncte finale sunt utilizate pentru a autentifica un agent și a gestiona token-urile sale.

- **`POST /agents/auth/token`**: Autentifică un agent și returnează token-uri JWT.
- **`POST /agents/auth/refresh`**: Reîmprospătează un token de acces folosind un token de reîmprospătare.
- **`POST /agents/auth/revoke`**: Revocă un token.
- **`POST /agents/{agent_id}/credentials`**: Creează sau resetează credențialele de autentificare pentru un agent (necesită `admin`).
