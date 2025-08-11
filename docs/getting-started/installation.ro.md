# Instalare

Ordinaut este conceput pentru a fi rulat ca un set de servicii containerizate folosind Docker. Această abordare asigură un mediu consistent și reproductibil atât pentru dezvoltare, cât și pentru producție.

## Cerințe Preliminare

Înainte de a începe, asigurați-vă că aveți instalate următoarele instrumente pe sistemul dumneavoastră:

- **Motor Docker:** Versiunea 24.0 sau mai recentă. [Instalați Docker](https://docs.docker.com/engine/install/)
- **Docker Compose:** Inclus cu Docker Desktop sau ca un plugin independent. [Instalați Docker Compose](https://docs.docker.com/compose/install/)
- **Git:** Pentru clonarea repozitoriului. [Instalați Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git)
- **cURL:** Un instrument de linie de comandă pentru efectuarea de cereri API, utilizat pentru verificare.

## 1. Clonați Repozitoriul

Mai întâi, clonați repozitoriul Ordinaut de pe GitHub pe mașina dumneavoastră locală.

```bash
git clone https://github.com/yoda-digital/ordinaut.git
cd ordinaut
```

## 2. Porniți Sistemul

Repozitoriul include un script de conveniență (`start.sh`) și fișiere Docker Compose în directorul `ops/` pentru a gestiona sistemul.

```bash
cd ops/
./start.sh dev --build
```

Această comandă efectuează mai multe acțiuni:
- Citește fișierele `docker-compose.yml` și `docker-compose.dev.yml`.
- Construiește imaginile Docker pentru serviciile API, scheduler și worker.
- Pornește toate containerele necesare în ordinea corectă.
- Montează codul sursă local în containere pentru reîncărcare live în timpul dezvoltării.

### Stiva de Servicii

Când rulați scriptul de pornire, sunt lansate următoarele servicii:

- **`postgres`**: Baza de date PostgreSQL, unde sunt stocate toate datele despre sarcini și stări.
- **`redis`**: Serverul Redis, utilizat pentru fluxuri de evenimente și caching.
- **`api`**: Serverul principal FastAPI care expune API-ul REST pe portul `8080`.
- **`scheduler`**: Procesul APScheduler care calculează când ar trebui să ruleze sarcinile.
- **`worker`**: Un proces de lucru care preia și execută sarcinile scadente.

## 3. Verificați Instalarea

După un minut, toate serviciile ar trebui să funcționeze și să fie sănătoase. Puteți verifica acest lucru verificând starea containerelor și interogând punctul final de sănătate.

### Verificați Sănătatea Containerelor

```bash
docker compose ps
```

Ar trebui să vedeți toate serviciile cu starea `Up (healthy)` sau `Up`.

### Interogați API-ul de Sănătate

Folosiți `curl` pentru a verifica punctul final principal de sănătate:

```bash
curl http://localhost:8080/health
```

Un răspuns de succes indică faptul că API-ul funcționează și se poate conecta la baza de date și la Redis:

```json
{
  "status": "healthy",
  "checks": [
    {"name": "database", "status": "healthy"},
    {"name": "redis", "status": "healthy"},
    {"name": "scheduler", "status": "healthy"},
    {"name": "workers", "status": "healthy"}
  ]
}
```

## Pașii Următori

Instanța dumneavoastră Ordinaut este acum complet operațională într-un mediu de dezvoltare.

- **Explorați API-ul:** Deschideți interfața Swagger UI interactivă la [http://localhost:8080/docs](http://localhost:8080/docs) pentru a vedea toate punctele finale disponibile.
- **Creați prima sarcină:** Urmați [Tutorialul de Pornire Rapidă](quick-start.md) pentru a programa primul dumneavoastră flux de lucru.
