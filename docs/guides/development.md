# Development Guide

This guide provides instructions for setting up a local development environment, running tests, and contributing to the Ordinaut project.

**📚 Multiple Development Approaches:** Choose between native Python development, containerized development with our published images, or hybrid approaches.

## Development Environment Options

### 🚀 **Option A: Quick Start with Published Images**

Use production-ready images for development - fastest setup with production parity:

```bash
# Clone repository
git clone https://github.com/yoda-digital/ordinaut.git
cd ordinaut/ops/

# Start with published images + development overrides
./start.sh ghcr --logs

# Access API for testing
curl http://localhost:8080/health
```

**✅ Benefits:**
- **30-second setup** - no build time or dependencies
- **Production parity** - test against exact production images
- **Multi-architecture** - works on Intel and ARM development machines
- **Always updated** - latest images with every release

**📚 Available Development Images:**
- `ghcr.io/yoda-digital/ordinaut-api:latest`
- `ghcr.io/yoda-digital/ordinaut-scheduler:latest` 
- `ghcr.io/yoda-digital/ordinaut-worker:latest`

### 🛠️ **Option B: Hybrid Development (Source + Containers)**

Combine published images with local source for selective development:

```bash
# Start infrastructure with published images
docker compose -f docker-compose.ghcr.yml up -d postgres redis scheduler worker

# Run API locally for development
source .venv/bin/activate
uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload
```

**⚙️ Use Cases:**
- API development while using stable scheduler/worker
- Testing new pipeline features against production worker
- Database schema development with production services

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

### 📊 Development with Production Images

Test your changes against production-identical environments:

```bash
# Test API changes against production scheduler/worker
docker compose -f docker-compose.ghcr.yml up -d postgres redis scheduler worker
uvicorn api.main:app --reload  # Local API development

# Test worker changes against production API/scheduler
docker compose -f docker-compose.ghcr.yml up -d postgres redis api scheduler
python workers/runner.py  # Local worker development

# Full production simulation for integration testing
docker compose -f docker-compose.ghcr.yml up -d
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

## 🚀 Docker Image Development

### Understanding the Build Pipeline

Ordinaut uses **automated Docker publishing** with every release:

```yaml
# .github/workflows/release.yml (simplified)
jobs:
  release:
    # Semantic release creates version tags
  
  docker-publish:
    # Builds and publishes images to GHCR
    strategy:
      matrix:
        service: [api, scheduler, worker]
    steps:
      - Multi-stage builds (builder + runtime)
      - Multi-architecture support (linux/amd64)
      - Security attestations and SBOM generation
      - Automatic public visibility
```

### 📝 Testing Docker Changes Locally

```bash
# Test Dockerfile changes before submitting PR
docker build -f ops/Dockerfile.api -t test-api .
docker build -f ops/Dockerfile.scheduler -t test-scheduler .
docker build -f ops/Dockerfile.worker -t test-worker .

# Test with local images
docker compose -f docker-compose.yml up -d
```

### 📊 Image Optimization Guidelines

**Multi-stage Build Pattern:**
```dockerfile
# Build stage - includes compilation dependencies
FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Runtime stage - minimal production image
FROM python:3.12-slim AS runtime
RUN groupadd -r appuser && useradd -r -g appuser appuser
COPY --from=builder /root/.local /home/appuser/.local
# ... application code
USER appuser
```

**Security Best Practices:**
- Non-root user execution
- Minimal base images (python:3.12-slim)
- No secrets in image layers
- Health check implementations
- Resource limits and constraints

## 🤝 Contributing

### Standard Contribution Process

1.  **Create feature branch** from `main`
2.  **Write code** including tests for new functionality
3.  **Test thoroughly:**
    ```bash
    # Unit and integration tests
    pytest --cov=ordinaut
    
    # Test with published images
    ./ops/start.sh ghcr
    
    # Code quality checks
    black . && flake8 .
    ```
4.  **Submit Pull Request** with clear description

### 🚀 Docker-Specific Contributions

When contributing Docker/deployment improvements:

1.  **Test multi-architecture builds:**
    ```bash
    docker buildx build --platform linux/amd64 -f ops/Dockerfile.api .
    ```

2.  **Verify security practices:**
    ```bash
    # Check for vulnerabilities
    docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
      aquasec/trivy image your-test-image
    ```

3.  **Test production deployment:**
    ```bash
    # Simulate production deployment
    ./ops/start.sh ghcr --scale worker=3 --scale api=2
    ```

### 📊 Release Process Understanding

**Automated Release Triggers:**
- `feat:` commits → Minor release (1.0.0 → 1.1.0)
- `fix:` commits → Patch release (1.0.0 → 1.0.1)
- `feat!:` commits → Major release (1.0.0 → 2.0.0)

**Docker Publishing:**
- Triggered automatically on every release
- Images tagged with semantic version + `latest`
- Multi-service matrix build (api, scheduler, worker)
- Security attestations and provenance included
- Automatic public visibility on GHCR

**Contributing to Release Quality:**
```bash
# Test your changes against production images
git checkout main
git pull origin main
./ops/start.sh ghcr  # Test with latest published images

# Then test your feature branch changes
git checkout your-feature-branch
./ops/start.sh dev --build  # Test your changes
```
