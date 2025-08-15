# Instalare

Ordinaut este un API backend de nivel enterprise pentru programarea sarcinilor, conceput pentru a fi rulat ca un set de servicii containerizate folosind Docker. Această abordare asigură un mediu consistent și reproductibil atât pentru dezvoltare, cât și pentru producție.

**🚀 ACTUALIZAT:** Sunt disponibile imagini Docker pre-construite pentru implementare instantanee! Pentru cele mai recente instrucțiuni de instalare cu imagini GHCR, consultați [versiunea în engleză](installation.md) a acestui ghid.

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

### 🚀 **Opțiunea A: Imagini Pre-construite (RECOMANDAT - Start Instantaneu)**

```bash
cd ops/
./start.sh ghcr --logs
```

**✅ Pornire în 30 de secunde** cu imagini testate în producție de la GitHub Container Registry!

### 🛠️ **Opțiunea B: Construire din Sursă (Dezvoltare)**

Pentru dezvoltare sau personalizare:

```bash
cd ops/
./start.sh dev --build --logs
```

Repozitoriul include un script de conveniență (`start.sh`) și fișiere Docker Compose în directorul `ops/` pentru a gestiona sistemul.

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

Instanța dumneavoastră Ordinaut este acum complet operațională! 🎉

**📚 Explorare & Învățare:**
- **Documentație API Interactivă:** [http://localhost:8080/docs](http://localhost:8080/docs) - Swagger UI complet cu testare live
- **Starea Sistemului:** [http://localhost:8080/health](http://localhost:8080/health) - Status în timp real
- **Tutorial de Pornire Rapidă:** [quick-start.md](quick-start.md) - Creați primul flux de lucru automatizat

**🚀 Pentru informații complete despre implementarea în producție cu imagini GHCR, consultați [versiunea în engleză](installation.md) pentru instrucțiunile cele mai recente.**
