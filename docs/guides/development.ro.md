# Ghid de Dezvoltare

Acest ghid oferă instrucțiuni pentru configurarea unui mediu de dezvoltare local, rularea testelor și contribuirea la backend-ul API Ordinaut pentru programarea sarcinilor.

## Configurare Mediu de Dezvoltare Local

### Cerințe Preliminare

- Python 3.12+
- Docker și Docker Compose
- Git

### Configurare Mediu

1.  **Clonați repozitoriul:**
    ```bash
    git clone https://github.com/yoda-digital/ordinaut.git
    cd ordinaut
    ```

2.  **Creați un mediu virtual Python:**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3.  **Instalați dependențele:**
    ```bash
    pip install -r requirements.txt
    pip install -r observability/requirements.txt # Pentru componentele de monitorizare
    ```

4.  **Porniți serviciile de fundal:**
    Pentru dezvoltare locală, aveți nevoie de baza de date PostgreSQL și serverul Redis în funcțiune. Le puteți porni ușor cu Docker Compose.
    ```bash
    cd ops/
    docker compose up -d postgres redis
    ```

5.  **Rulați migrațiile bazei de date:**
    Aplicați schema inițială a bazei de date.
    ```bash
    psql "$DATABASE_URL" -f ../migrations/version_0001.sql
    ```

### Rularea Componentelor Individual

Cu baza de date și Redis în funcțiune, puteți rula serverul API, planificatorul și workerii ca procese separate pe mașina locală.

- **Rulați Serverul API:**
  ```bash
  uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload
  ```

- **Rulați Serviciul de Planificare:**
  ```bash
  python scheduler/tick.py
  ```

- **Rulați un Worker:**
  ```bash
  python workers/runner.py
  ```

## Cadru de Testare

Ordinaut folosește `pytest` pentru testare. Testele sunt organizate în categoriile `unit`, `integration` și `load`.

### Rularea Testelor

- **Rulați toate testele:**
  ```bash
  pytest
  ```

- **Rulați o categorie specifică:**
  ```bash
  pytest tests/unit/
  ```

- **Rulați cu raport de acoperire:**
  ```bash
  pytest --cov=ordinaut --cov-report=html
  ```

## Calitatea și Standardele Codului

Folosim `black` pentru formatarea codului și `flake8` pentru linting pentru a asigura un stil de cod consistent.

- **Formatați codul:**
  ```bash
  black .
  ```

- **Verificați erorile de linting:**
  ```bash
  flake8 .
  ```

## Contribuire

1.  Creați un branch de caracteristică (feature branch) din `main`.
2.  Scrieți codul, inclusiv teste pentru funcționalități noi.
3.  Asigurați-vă că toate testele trec și că linter-ul este curat.
4.  Trimiteți un Pull Request cu o descriere clară a modificărilor dumneavoastră.