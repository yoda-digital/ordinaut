# Ghid de Dezvoltare

Acest ghid oferă instrucțiuni pentru configurarea unui mediu de dezvoltare local, rularea testelor și contribuirea la proiectul Ordinaut.

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
    pip install -r observability/requirements.txt
    pip install black flake8 pytest
    ```

4.  **Porniți serviciile de fundal (PostgreSQL, Redis):**
    ```bash
    cd ops/
    docker compose up -d postgres redis
    ```

### Rularea Componentelor Individual

- **Server API:**
  ```bash
  uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload
  ```

- **Scheduler:**
  ```bash
  python scheduler/tick.py
  ```

- **Worker:**
  ```bash
  python workers/runner.py
  ```

## Cadru de Testare

Ordinaut folosește `pytest` pentru testare.

!!! warning "Starea Suitei de Teste"
    Suita de teste este în prezent în curs de mentenanță semnificativă. Multe teste sunt cunoscute ca fiind nefuncționale. După cum este detaliat în `test_verification_report.md`, acoperirea reală a testelor este de aproximativ 11%.

    Contribuitorii ar trebui să se concentreze pe scrierea de teste noi, funcționale, pentru caracteristicile lor.

### Rularea Testelor

```bash
# Rulează toate testele (așteptați-vă la eșecuri)
pytest

# Rulează un fișier de test specific, funcțional
pytest tests/test_rruler.py
```

## Calitatea și Standardele Codului

Folosim `black` pentru formatarea codului și `flake8` pentru linting.

- **Formatați codul:** `black .`
- **Verificați erorile:** `flake8 .`

## Contribuire

1.  Creați un feature branch din `main`.
2.  Scrieți cod și includeți **teste noi, funcționale**.
3.  Asigurați-vă că verificările de calitate a codului trec.
4.  Trimiteți un Pull Request.
