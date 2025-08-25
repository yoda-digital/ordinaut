# Instalare

Sistemul Ordinaut este conceput pentru a fi rulat ca un set de servicii containerizate folosind Docker. Această abordare asigură un mediu consistent și reproductibil atât pentru dezvoltare, cât și pentru producție.

**🚀 Instalare Rapidă:** Utilizați imaginile noastre Docker pre-construite pentru implementare instantanee sau construiți din sursă pentru dezvoltare și personalizare.

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

Sistemul oferă două abordări de instalare - alegeți cea care se potrivește nevoilor dumneavoastră:

### 🚀 **Opțiunea A: Imagini Pre-construite (RECOMANDAT - Start Instantaneu)**

Utilizați imagini Docker gata de producție, publicate automat cu fiecare lansare:

```bash
cd ops/
./start.sh ghcr --logs
```

**✅ Beneficii:**
- **Pornire în 30 de secunde** vs 5-10 minute la construirea din sursă
- **Imagini testate în producție** cu atestări de securitate
- **Suport multi-arhitectură** pentru Intel/AMD (linux/amd64)
- **Actualizări automate** cu versionare semantică
- **Nu sunt necesare dependențe de compilare** pe sistemul dumneavoastră

**📚 Imagini Disponibile:**
- `ghcr.io/yoda-digital/ordinaut-api:latest` - Serviciul API REST FastAPI
- `ghcr.io/yoda-digital/ordinaut-scheduler:latest` - Serviciul APScheduler
- `ghcr.io/yoda-digital/ordinaut-worker:latest` - Serviciul de execuție a joburilor

### 🛠️ **Opțiunea B: Construire din Sursă (Dezvoltare)**

Pentru dezvoltare, personalizare sau când trebuie să modificați codul sursă:

```bash
cd ops/
./start.sh dev --build --logs
```

### Stiva de Servicii

Când rulați scriptul de pornire, sunt lansate următoarele servicii:

- **`postgres`**: Baza de date PostgreSQL.
- **`redis`**: Serverul Redis.
- **`api`**: Serverul principal FastAPI pe portul `8080`.
- **`scheduler`**: Procesul APScheduler.
- **`worker`**: Un proces de lucru care execută sarcinile.

## 3. Verificați Instalarea

Verificați starea containerelor și interogați punctul final de sănătate.

### Verificați Sănătatea Containerelor

```bash
docker compose ps
```

### Interogați API-ul de Sănătate

```bash
curl http://localhost:8080/health
```

Un răspuns de succes indică faptul că sistemul funcționează corect.

## Pașii Următori

Instanța dumneavoastră Ordinaut este acum complet operațională! 🎉

- **[Tutorial de Pornire Rapidă](quick-start.md)**
- **[Referință API](../api/api_reference.md)**
- **[Ghid de Dezvoltare](../guides/development.md)**
