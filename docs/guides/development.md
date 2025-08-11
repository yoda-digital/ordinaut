# Development Guide

This guide provides instructions for setting up a local development environment, running tests, and contributing to the Ordinaut project.

## Local Development Setup

### Prerequisites

- Python 3.12+
- Docker and Docker Compose
- Git

### Environment Setup

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/yoda-digital/ordinaut.git
    cd ordinaut
    ```

2.  **Create a Python virtual environment:**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    pip install -r observability/requirements.txt # For monitoring components
    ```

4.  **Start background services:**
    For local development, you need the PostgreSQL database and Redis server running. You can start them easily with Docker Compose.
    ```bash
    cd ops/
    docker compose up -d postgres redis
    ```

5.  **Run database migrations:**
    Apply the initial database schema.
    ```bash
    psql "$DATABASE_URL" -f ../migrations/version_0001.sql
    ```

### Running Components Individually

With the database and Redis running, you can run the API server, scheduler, and workers as separate processes on your local machine.

- **Run the API Server:**
  ```bash
  uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload
  ```

- **Run the Scheduler:**
  ```bash
  python scheduler/tick.py
  ```

- **Run a Worker:**
  ```bash
  python workers/runner.py
  ```

## Testing Framework

Ordinaut uses `pytest` for testing. The tests are organized into `unit`, `integration`, and `load` categories.

### Running Tests

- **Run all tests:**
  ```bash
  pytest
  ```

- **Run a specific category:**
  ```bash
  pytest tests/unit/
  ```

- **Run with coverage report:**
  ```bash
  pytest --cov=ordinaut --cov-report=html
  ```

## Code Quality & Standards

We use `black` for code formatting and `flake8` for linting to ensure a consistent code style.

- **Format code:**
  ```bash
  black .
  ```

- **Check for linting errors:**
  ```bash
  flake8 .
  ```

## Contributing

1.  Create a feature branch from `main`.
2.  Write your code, including tests for new functionality.
3.  Ensure all tests pass and the linter is clean.
4.  Submit a Pull Request with a clear description of your changes.
