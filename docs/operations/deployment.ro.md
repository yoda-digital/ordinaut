# Implementare (Deployment)

Acest ghid acoperă implementarea sistemului Ordinaut într-un mediu de producție folosind Docker Compose.

## Configurare pentru Producție

Modul recomandat de a rula Ordinaut în producție este folosind fișierele Docker Compose furnizate, care gestionează configurarea multi-container.

### Configurare

1.  **Variabile de Mediu:** Înainte de implementare, copiați fișierul `.env.example` din directorul `ops/` în `.env` și personalizați valorile. Este **critic** să setați o cheie `JWT_SECRET_KEY` sigură și aleatorie.

2.  **Docker Compose:** Fișierul `docker-compose.prod.yml` este optimizat pentru producție. Utilizează variabile de mediu pentru configurare, setează limite de resurse și activează multiple replici ale worker-ilor.

### Pornirea Sistemului

Utilizați scriptul de pornire furnizat pentru a lansa stiva de producție:

```bash
cd ops/

# Asigurați-vă că fișierul .env este configurat

./start.sh prod --build
```

Acest lucru va porni toate serviciile în mod detașat cu setările de producție.

## Scalare

### Scalarea Worker-ilor

Cea mai frecventă cerință de scalare este ajustarea numărului de replici `worker` pentru a gestiona încărcătura de sarcini. Puteți face acest lucru cu flag-ul `--scale`:

```bash
# Scalează la 5 instanțe de worker
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --scale worker=5
```

### Scalarea Serverului API

Pentru disponibilitate ridicată, puteți, de asemenea, să scalați serviciul `api` și să le plasați în spatele unui load balancer.

## Persistența Datelor și Backup-uri

- **PostgreSQL:** Toate datele de bază sunt stocate în baza de date PostgreSQL. Datele sunt persistate într-un volum Docker (`pgdata-prod`). Ar trebui să implementați o strategie standard de backup pentru PostgreSQL (de exemplu, `pg_dump`) pentru a vă proteja datele.

- **Redis:** Redis este utilizat pentru date tranzitorii, cum ar fi fluxurile de evenimente și cache-urile. Deși are persistența activată, nu ar trebui tratat ca un magazin de date primar.

Consultați documentele `BACKUP_PROCEDURES.md` și `DISASTER_RECOVERY.md` din directorul `ops/` pentru planuri operaționale detaliate.