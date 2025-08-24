# Qwen Code Context for Ordinaut Project

## Project Overview

Ordinaut is an enterprise-grade task scheduling API with RRULE support, pipeline execution, and comprehensive observability. The system functions as a **pure task scheduler** foundation that provides clean APIs for extension development. MCP integration and external tool support are implemented as separate extensions that communicate with the core scheduler through REST APIs.

The system implements a **clean extension architecture** with a pure task scheduler core:

```
🔄 CURRENT STATE: Pure Task Scheduler
┌─────────────────┐    ┌────────────────┐    ┌─────────────────┐
│   FastAPI       │───▶│   PostgreSQL    │◀───│   APScheduler   │
│  (REST API)     │    │ (Durable Store) │    │  (Time Logic)   │
│                 │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                      ▲                      │
         ▼                      │                      ▼
┌─────────────────┐    ┌────────────────┐    ┌─────────────────┐
│   Workers       │───▶│   Pipeline     │◀───│Redis Streams    │
│(SKIP LOCKED)    │    │  (Simulator)   │    │  (Events)       │
└─────────────────┘    └────────────────┘    └─────────────────┘
                               │
                               ▼
                   ┌────────────────┐
                   │  Observability │
                   │(Prometheus +   │
                   │ Grafana)       │
                   └────────────────┘

🚀 FUTURE EXTENSIONS: (To be implemented separately)
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐
│ AI Assistant│───▶│   MCP Server │───▶│ Ordinaut Core   │
│(Claude/GPT) │    │  Extension   │    │ (REST APIs)     │
└─────────────┘    └──────────────┘    └─────────────────┘
        │                    │                    ▲
        ▼                    ▼                    │
┌─────────────┐    ┌──────────────┐              │
│   Tools     │    │   Web GUI    │              │
│ Extension   │    │  Extension   │              │
└─────────────┘    └──────────────┘──────────────┘
```

## Technology Stack

### Core Infrastructure
- **Python 3.12.x** - Modern async/await patterns and type hints
- **PostgreSQL 16.x** - ACID compliance, SKIP LOCKED for job queues, JSONB for flexible data
- **Redis 7.x** - Streams for ordered events with consumer groups (`XADD`/`XREADGROUP`)
- **APScheduler 3.x** - Battle-tested scheduling with SQLAlchemyJobStore on PostgreSQL
- **FastAPI** - Modern Python API framework with automatic OpenAPI docs

### Specialized Libraries
- **psycopg[binary]==3.1.19** - Modern PostgreSQL driver with binary optimizations
- **python-dateutil** - RFC-5545 RRULE processing for complex recurring schedules
- **JMESPath** - JSON querying for conditional logic and data selection
- **JSON Schema** - Framework for input/output validation (ready for extensions)
- **Extension Architecture** - Clean separation for future MCP and tool integrations

### Release Management
- **python-semantic-release==10.3.0** - Automated versioning and release management
- **Conventional Commits** - Standardized commit format for automated releases
- **GitHub Actions** - CI/CD pipeline for automated testing and releases
- **Keep a Changelog** - Professional changelog format with automated generation

## Core Components

1. **PostgreSQL Database** - ACID-compliant durable storage with `FOR UPDATE SKIP LOCKED` job queues
2. **APScheduler** - Battle-tested scheduling with SQLAlchemy job store for temporal logic  
3. **Redis Streams** - Ordered, durable event logs with consumer groups (`XADD`/`XREADGROUP`)
4. **FastAPI Service** - Modern REST API with automatic OpenAPI documentation
5. **Worker Pool** - Distributed job processors using safe work leasing patterns
6. **Pipeline Engine** - Deterministic pipeline execution with template rendering (tool simulation)
7. **Extension Architecture** - Clean REST APIs ready for MCP and tool integration development

## Key Features

### 🕐 Advanced Scheduling
- **Cron expressions**: Traditional cron-style scheduling (`0 8 * * 1-5`)
- **RRULE support**: Full RFC-5545 recurrence rules with timezone handling
- **One-time tasks**: ISO timestamp-based single execution
- **Event-driven**: Tasks triggered by external events
- **Conditional logic**: Tasks with complex trigger conditions

### ⚡ Reliable Execution
- **>99.9% uptime** with graceful failure handling
- **Zero work loss** - all scheduled work persists across restarts
- **Concurrent processing** via PostgreSQL `SKIP LOCKED` patterns
- **Retry mechanisms** with exponential backoff and jitter
- **Idempotent operations** to prevent duplicate processing

### 🔧 Pipeline Engine
- **Declarative pipelines** with step-by-step execution
- **Template variables**: `${steps.weather.summary}`, `${params.user_id}`
- **Conditional steps**: JMESPath expressions for flow control
- **Schema validation**: JSON Schema framework ready for extensions
- **Tool simulation**: All tool calls simulated with proper context structure

### 🛡️ Security & Governance
- **Agent-based authentication** with scope-based authorization
- **Audit logging** for all operations with immutable trails
- **Input validation** at API boundaries with detailed error responses
- **Rate limiting** and budget enforcement for external tool usage

### 📊 Production Observability
- **Prometheus metrics** for all system components
- **Grafana dashboards** for real-time monitoring
- **Structured logging** with correlation IDs
- **Health checks** for Kubernetes readiness/liveness probes
- **Alert rules** for proactive issue detection

## Architecture Details

### Database Schema
The system uses PostgreSQL with a comprehensive schema including:
- **agent**: Stores agent credentials and scope permissions
- **task**: Stores task definitions with scheduling and execution configuration
- **task_run**: Tracks individual execution attempts with timing and results
- **due_work**: Implements SKIP LOCKED pattern for safe concurrent job distribution
- **audit_log**: Comprehensive operation tracking for security and debugging
- **worker_heartbeat**: Tracks worker health and activity for monitoring

### Scheduling System
The scheduler uses APScheduler with SQLAlchemyJobStore to manage task scheduling:
- Supports cron, RRULE, once, event, and condition scheduling
- Creates due_work rows for worker processing
- Handles timezone-aware scheduling with Europe/Chisinau default
- Implements RRULE processing with proper timezone and DST handling

### Worker System
Workers process tasks using the PostgreSQL SKIP LOCKED pattern:
- Lease work items safely using FOR UPDATE SKIP LOCKED
- Execute pipeline tasks with retry logic
- Record execution results and metrics
- Send heartbeats for health monitoring
- Handle graceful shutdown and error recovery

### Pipeline Execution
The pipeline engine processes declarative task definitions:
- Resolves template variables like `${steps.x.y}` and `${params.z}`
- Executes steps conditionally using JMESPath expressions
- Simulates tool execution (real tools implemented as extensions)
- Validates inputs and outputs with JSON Schema
- Handles error cases with proper logging and metrics

### Observability
The system includes comprehensive observability features:
- Prometheus metrics collection for all components
- Structured logging with correlation IDs
- Health checks for all system components
- Alerting and monitoring integrations

## Building and Running

### Quick Start
Get the system running in 5 minutes with Docker:

```bash
# Option 1: Use pre-built images (RECOMMENDED - instant startup)
git clone https://github.com/yoda-digital/task-scheduler.git
cd task-scheduler/ops/
./start.sh ghcr --logs

# Option 2: Build from source (for development)
./start.sh dev --build --logs

# Access the API documentation
open http://localhost:8080/docs
```

### Production-Ready Docker Images
**✅ FULLY AUTOMATED PUBLISHING** - Images are automatically built and published with every release:

**📦 Available Images:**
- `ghcr.io/yoda-digital/task-scheduler-api:latest` - FastAPI REST API service
- `ghcr.io/yoda-digital/task-scheduler-scheduler:latest` - APScheduler service  
- `ghcr.io/yoda-digital/task-scheduler-worker:latest` - Job execution service

**🚀 Instant Deployment:**
```bash
# Pull and run specific version
docker pull ghcr.io/yoda-digital/task-scheduler-api:v1.7.1
docker pull ghcr.io/yoda-digital/task-scheduler-scheduler:latest
docker pull ghcr.io/yoda-digital/task-scheduler-worker:latest

# Or use the automated GHCR setup
./ops/start.sh ghcr
```

## Development Conventions

### Code Structure
```
ordinaut/
├── api/                         # FastAPI service (tasks CRUD, runs, monitoring)
│   ├── main.py
│   ├── routes/
│   ├── models.py
│   └── schemas.py
├── engine/                      # Pipeline execution runtime
│   ├── executor.py              # Deterministic pipeline execution (simulates tools)
│   ├── template.py              # ${steps.x.y} variable resolution
│   ├── registry.py              # Task loading from database
│   └── rruler.py                # RRULE → next occurrence calculation
├── scheduler/                   # APScheduler service
│   └── tick.py                  # Scheduler daemon
├── workers/                     # Concurrent job processors
│   └── runner.py                # SKIP LOCKED work leasing
├── migrations/
│   └── version_0001.sql         # Complete database schema
├── ops/                         # Production deployment
│   ├── docker-compose.yml
│   └── Dockerfile.*
└── tests/                       # Comprehensive test suite
```

### Concurrency-First Design
- **ALL** job processing uses `SELECT ... FOR UPDATE SKIP LOCKED` for safe distribution
- **NO** work item is ever processed twice under normal conditions
- **ALL** external operations are idempotent and safely retryable
- **ALL** database operations are ACID-compliant with proper rollback procedures

### Security by Design
- **API-based authorization** - extensions authenticate via JWT tokens
- **Input validation** at API boundary with detailed error messages
- **Audit logging** for all operations with immutable event trails
- **Rate limiting** and extension access control

### Git Commit Standards & Semantic Release

The project uses Python Semantic Release for automated versioning and releases. All commits must follow [Conventional Commits](https://conventionalcommits.org/) format:

**Commit Types & Version Impact:**
- `feat:` → **Minor release** (1.0.0 → 1.1.0) - New features
- `fix:` → **Patch release** (1.0.0 → 1.0.1) - Bug fixes  
- `perf:` → **Patch release** (1.0.0 → 1.0.1) - Performance improvements
- `feat!:` → **Major release** (1.0.0 → 2.0.0) - Breaking changes
- `docs:`, `chore:`, `ci:`, `refactor:`, `style:`, `test:` → **No release**

**Examples:**
```bash
feat(api): add task snoozing functionality
fix(scheduler): resolve DST transition handling  
perf(worker): optimize SKIP LOCKED query performance
feat!: remove support for legacy API endpoints

BREAKING CHANGE: Legacy v1 endpoints removed. Migrate to v2 API.
```

**Scopes:** Use module names (`api`, `engine`, `scheduler`, `workers`, `docs`, `ci`)

**Release Process:**
1. Push conventional commits to `main` branch
2. GitHub Actions automatically analyzes commits
3. Semantic-release calculates next version
4. Creates git tag, GitHub release, and updates changelog
5. All module versions synchronized automatically

### Proactive Synchronization Protocol

To prevent push rejections and merge conflicts caused by a stale local state, the following workflow is **mandatory** before pushing changes:

1.  **Stash Local Changes (If Necessary):** If the working directory is dirty, stash any uncommitted changes (`git stash`).
2.  **Pull with Rebase:** Always execute `git pull --rebase origin main` to fetch and apply remote changes *before* attempting a push. This ensures the local branch is perfectly synchronized with the remote.
3.  **Pop Stash (If Necessary):** Re-apply stashed changes (`git stash pop`).
4.  **Push Changes:** Proceed with the `git push origin main` command.

This "pull-before-push" discipline is non-negotiable and guarantees a clean, conflict-free contribution history.

### Development Environment Setup

**Python Virtual Environment (Required)**
```bash
# Virtual environment is located at .venv/ (with dot prefix)
source .venv/bin/activate

# If creating new environment:
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies (using requirements.txt)
pip install -r requirements.txt
```

**IMPORTANT: The project uses `.venv/` (with dot prefix) not `venv/`. Always activate with `source .venv/bin/activate` for development and testing.

## API Overview

### Task Management
- `POST /tasks` - Create new scheduled tasks
- `GET /tasks` - List tasks with filtering
- `POST /tasks/{id}/run_now` - Trigger immediate execution
- `POST /tasks/{id}/snooze` - Delay next execution
- `POST /tasks/{id}/pause` - Pause task execution
- `POST /tasks/{id}/resume` - Resume paused tasks

### Execution Monitoring
- `GET /runs` - Task execution history
- `GET /runs/{id}` - Execution details and logs

### Event Publishing
- `POST /events` - Publish external events

### System Health
- `GET /health` - Comprehensive system health
- `GET /health/ready` - Kubernetes readiness probe
- `GET /health/live` - Kubernetes liveness probe

## Example Use Cases

### Morning Briefing Pipeline (Template Structure)
```json
{
  "title": "Weekday Morning Briefing",
  "description": "Daily agenda, weather, and priority summary",
  "schedule_kind": "rrule",
  "schedule_expr": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=30",
  "timezone": "Europe/Chisinau",
  "payload": {
    "pipeline": [
      {
        "id": "calendar",
        "uses": "google-calendar-mcp.list_events",
        "with": {"start": "${now}", "end": "${now+24h}"},
        "save_as": "events"
      },
      {
        "id": "weather", 
        "uses": "weather-mcp.forecast",
        "with": {"city": "Chisinau"},
        "save_as": "weather"
      },
      {
        "id": "summarize",
        "uses": "llm.plan",
        "with": {
          "instruction": "Create morning briefing",
          "calendar": "${steps.events}",
          "weather": "${steps.weather}"
        },
        "save_as": "summary"
      },
      {
        "id": "notify",
        "uses": "telegram-mcp.send_message", 
        "with": {
          "chat_id": 12345,
          "text": "${steps.summary.text}"
        }
      }
    ]
  }
}
```

**Note**: When executed, this pipeline processes the structure, resolves templates (`${steps.events}`, `${steps.weather}`), evaluates conditions, and simulates all tool calls with proper logging. Extensions will implement the actual integrations (google-calendar-mcp, weather-mcp, llm.plan, telegram-mcp.send_message).

## System Requirements

### Minimum Requirements
- **CPU**: 2 cores
- **RAM**: 4GB
- **Disk**: 2GB free space
- **Network**: Internet access for external tool calls
- **Ports**: 5432 (PostgreSQL), 6379 (Redis), 8080 (API)

### Production Requirements
- **CPU**: 4+ cores
- **RAM**: 8GB+
- **Disk**: 20GB+ SSD
- **Network**: Stable internet with low latency
- **Load Balancer**: For high availability deployments

## Current Status

As of August 18, 2025, the system has been successfully transformed into a **PURE TASK SCHEDULER** with complete MCP and tool functionality removal from the core system. This architectural cleanup creates a bulletproof foundation for extension development while maintaining 100% core scheduler functionality.

### Current Capabilities (Fully Operational)
- **Task Scheduling**: Complete RRULE support with Europe/Chisinau timezone handling, APScheduler + PostgreSQL integration
- **Pipeline Processing**: Full template resolution (${steps.x.y}), conditional logic with JMESPath, JSON structure validation
- **Worker Coordination**: PostgreSQL SKIP LOCKED job queues, concurrent processing, zero-duplicate-work guarantee
- **Database Persistence**: PostgreSQL 16.x with ACID compliance, complete task/run/work tracking
- **Observability**: Production-ready monitoring, structured logging, comprehensive metrics collection
- **REST API**: Complete CRUD operations, health checks, admin interfaces, JWT authentication
- **Production Deployment**: Fully operational with Docker Compose, automated releases, security hardening

### Architectural Cleanup Completed
- **MCP Client Integration**: ✅ COMPLETELY REMOVED (`engine/mcp_client.py` deleted)
- **Tool Catalog System**: ✅ COMPLETELY REMOVED (`catalogs/tools.json` deleted, `engine/registry.py` reduced from 358→26 lines)
- **External Tool Execution**: ✅ REPLACED with intelligent simulation in pipeline executor
- **Test Infrastructure**: ✅ 184 test references properly marked as REMOVED with pytest.skip() for future re-enablement

### Pipeline Execution Behavior (Current)
- Pipeline structure is **FULLY PROCESSED** (template resolution, conditions, step flow, error handling)
- Tool calls are **INTELLIGENTLY SIMULATED** with proper logging, metrics, and context structure preservation
- Results maintain **IDENTICAL FORMAT** for complete worker/API compatibility
- Core scheduler provides **REST API BOUNDARY** for future extension integration
- Extensions will implement **REAL TOOL EXECUTION** via REST API calls back to scheduler

### Extension Development Ready - Architecture Complete
The system has been successfully architected for clean extension development with complete separation of concerns:

1. **✅ Core Scheduler (COMPLETE)**: Handles timing, persistence, pipeline processing, worker coordination
2. **✅ Extension Boundary (COMPLETE)**: Clean REST APIs with JWT authentication, input validation, comprehensive observability  
3. **🔄 MCP Extensions (READY)**: Will be implemented as separate services calling core scheduler REST APIs
4. **🔄 Tool Extensions (READY)**: Will register with MCP extensions and be called via standard MCP protocol
5. **🔄 Web GUI Extensions (READY)**: Can be built against the complete REST API surface

### Development Status - Phase 1 Complete
- **Core System**: ✅ **PRODUCTION COMPLETE** - End-to-end validated, 100% functional pure scheduler
- **Extension Framework**: ✅ **ARCHITECTURE COMPLETE** - REST APIs implemented with authentication
- **Database Schema**: ✅ **COMPLETE** - All tables, indexes, SKIP LOCKED patterns operational
- **CI/CD Pipeline**: ✅ **COMPLETE** - Automated releases, Docker publishing, semantic versioning
- **Production Deployment**: ✅ **OPERATIONAL** - Fully deployed with monitoring and security
- **Test Infrastructure**: ✅ **PRESERVED** - 184 test references properly marked for future extension re-enablement
- **Documentation**: ✅ **COMPLETE** - Production runbooks, CTO guides, integration examples

The system is now **production-ready for immediate deployment** as a pure scheduler, while providing the **perfect foundation** for implementing MCP servers, tool integrations, and web interfaces as separate extensions that communicate via the established REST API boundary.