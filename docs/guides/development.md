# Development Guide

This guide provides instructions for setting up a local development environment, running tests, and contributing to the Ordinaut project.

## 💻 Local Development Setup

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
    pip install black flake8 pytest # For development and testing
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

With the database and Redis running, you can run the API server, scheduler, and workers as separate processes:

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

!!! warning "Test Suite Status"
    The test suite is currently undergoing significant maintenance. Many tests are known to be broken due to import errors and configuration issues. As detailed in the `test_verification_report.md`, the actual test coverage is approximately 11%.

    Contributors should focus on writing new, passing tests for their features and not be alarmed by the state of the existing suite. Efforts to repair the test suite are ongoing.

### Running Tests

- **Run all tests (expect failures):**
  ```bash
  pytest
  ```

- **Run a specific, working test file:**
  ```bash
  pytest tests/test_rruler.py
  ```

- **Run with coverage report:**
  ```bash
  pytest --cov=ordinaut --cov-report=html
  ```

## Code Quality & Standards

We use `black` for code formatting and `flake8` for linting.

- **Format code:**
  ```bash
  black .
  ```

- **Check for linting errors:**
  ```bash
  flake8 .
  ```

## 🚀 Docker Image Development

Ordinaut uses an automated CI/CD pipeline defined in `.github/workflows/release.yml` for building and publishing Docker images to GitHub Container Registry (GHCR). The pipeline uses a multi-stage build pattern to create optimized, production-ready images.

### Testing Docker Changes Locally

```bash
# Test Dockerfile changes before submitting a PR
docker build -f ops/Dockerfile.api -t test-api .

# Run the locally built image
docker run -p 8080:8080 --env-file ops/.env.example test-api
```

## 🤝 Contributing

1.  **Create a feature branch** from `main`.
2.  **Write code** and include **new, passing tests** for your functionality.
3.  **Test your changes thoroughly.** Given the current state of the test suite, focus on verifying your changes manually and with the new tests you have written.
4.  **Ensure code quality checks pass:**
    ```bash
    black . && flake8 .
    ```
5.  **Submit a Pull Request** with a clear description of your changes.