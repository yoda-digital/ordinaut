# Implementare (Deployment)

Acest ghid acoperă implementarea sistemului Ordinaut în medii de producție.

## Configurare pentru Producție

### 1. Configurați Mediul

!!! danger "Acțiune Critică de Securitate Necesară"
    Înainte de implementare, **TREBUIE** să configurați un secret JWT sigur. Sistemul este nesigur fără acesta.

    1.  Navigați în directorul `ops/`.
    2.  Copiați fișierul exemplu de mediu: `cp .env.example .env`
    3.  Deschideți fișierul `.env` și setați o valoare puternică și aleatorie pentru `JWT_SECRET_KEY` și `POSTGRES_PASSWORD`.

### 2. Implementați Sistemul

Utilizați scriptul de pornire pentru a lansa sistemul cu imagini pre-construite de pe GHCR.

```bash
# Din directorul ops/
./start.sh ghcr
```

## Scalare

Puteți scala numărul de servicii `worker` și `api` pentru a gestiona sarcini mai mari folosind flag-ul `--scale`.

```bash
# Scalează la 5 instanțe de worker
docker compose -f docker-compose.ghcr.yml up -d --scale worker=5
```

## Operațiuni de Producție

- **Backup Bază de Date:** Implementați o strategie standard de backup pentru PostgreSQL (de exemplu, `pg_dump`).
- **Monitorizare:** Implementați un stack de monitorizare folosind fișierul `docker-compose.observability.yml`.
- **Actualizări:** Pentru stabilitate, fixați versiunile imaginilor în `docker-compose.ghcr.yml` în loc să folosiți `latest`.
