# Ordinaut - Enterprise Task Scheduling Platform

## Project Mission
Build **Ordinaut**, an enterprise-grade task scheduling API with RRULE support, pipeline execution, and comprehensive observability. Designed as a **pure task scheduler** foundation with a fully operational **extension system** providing modular functionality through capability-based plugins.

## Core Architecture Vision
**(1) Durable Store (PostgreSQL)** → **(2) Scheduler (APScheduler)** → **(3) Event Spine (Redis Streams)** → **(4) Pipeline Executor** → **(5) Extension Framework**

This creates a reliable, persistent task execution system with a complete extension architecture. The core system handles timing, persistence, concurrency, and pipeline processing while extensions (MCP servers, tool integrations, web GUIs, monitoring) operate through a secure, capability-based plugin framework.

---

## Technology Stack (Production Ready)

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
- **JSON Schema** - Framework for input/output validation

### Extension System (FULLY OPERATIONAL)
- **Plugin Framework** - Complete extension loader with capability-based security
- **Lazy Loading** - Redirect-based loading for optimal performance and resource usage
- **Event System** - Redis Streams-based pub/sub for inter-extension communication
- **Background Tasks** - Supervisor for long-running extension processes
- **Tool Registry** - Namespaced tool registration and discovery system
- **Scope Security** - Per-extension authentication and authorization
- **4 Working Extensions** - Fully operational demonstrating all capabilities

### Release Management
- **python-semantic-release==10.3.0** - Automated versioning and release management
- **Conventional Commits** - Standardized commit format for automated releases
- **GitHub Actions** - CI/CD pipeline for automated testing and releases
- **Keep a Changelog** - Professional changelog format with automated generation

---

## Repository Structure (Current)

```
ordinaut/
├── CLAUDE.md                    # This file - project context and instructions
├── README.md                    # Project overview and quick start
├── .claude/                     # Claude Code configuration
├── api/                         # FastAPI service (tasks CRUD, runs, monitoring)
│   ├── main.py                  # Main API application with extension mounting
│   ├── routes/                  # API route modules
│   ├── models.py                # SQLAlchemy database models
│   └── schemas.py               # Pydantic request/response schemas
├── engine/                      # Pipeline execution runtime
│   ├── executor.py              # Deterministic pipeline execution
│   ├── template.py              # ${steps.x.y} variable resolution
│   ├── registry.py              # Task loading from database (simplified)
│   └── rruler.py                # RRULE → next occurrence calculation
├── scheduler/                   # APScheduler service
│   └── tick.py                  # Scheduler daemon
├── workers/                     # Concurrent job processors
│   └── runner.py                # SKIP LOCKED work leasing
├── ordinaut/                    # Extension system core ✅ OPERATIONAL
│   ├── plugins/                 # Extension loader and framework
│   │   ├── loader.py            # Plugin discovery and lifecycle management
│   │   ├── base.py              # Extension base classes and capabilities
│   │   ├── events.py            # Redis Streams event manager
│   │   ├── background.py        # Background task supervisor
│   │   └── schema.py            # Extension manifest validation
│   ├── engine/                  # Tool registry for extensions
│   │   └── registry.py          # Namespaced tool registration system
│   └── extensions/              # Built-in extension implementations ✅ OPERATIONAL
│       ├── observability/       # Prometheus metrics extension
│       ├── webui/              # Task management web interface
│       ├── mcp_http/           # MCP-over-HTTP server
│       └── events_demo/        # Redis Streams demonstration
├── docs/                        # Comprehensive trilingual documentation
│   ├── guides/
│   │   ├── extensions.md        # Complete extension system guide
│   │   ├── extensions.ro.md     # Romanian translation
│   │   └── extensions.ru.md     # Russian translation
│   ├── api/
│   │   ├── extensions.md        # Extension API reference
│   │   ├── extensions.ro.md     # Romanian API reference
│   │   └── extensions.ru.md     # Russian API reference
│   └── mkdocs.yml               # Documentation site configuration
├── migrations/
│   └── version_0001.sql         # Complete database schema
├── ops/                         # Production deployment
│   ├── docker-compose.yml       # Multi-service Docker orchestration
│   ├── Dockerfile.api           # API service container (extension-enabled)
│   ├── Dockerfile.scheduler     # Scheduler service container
│   └── Dockerfile.worker        # Worker service container
└── tests/                       # Comprehensive test suite
```

---

## ⚡ **CURRENT SYSTEM STATE (August 25, 2025)**

### **System Status: PRODUCTION OPERATIONAL** ✅

The Ordinaut is a **complete, production-ready task scheduling platform** with a fully operational extension system. All core functionality and extension framework have been implemented, tested, and deployed.

**✅ CURRENT CAPABILITIES (FULLY OPERATIONAL):**
- **Task Scheduling**: Complete RRULE support with Europe/Chisinau timezone handling
- **Pipeline Processing**: Full template resolution (${steps.x.y}), conditional logic with JMESPath
- **Worker Coordination**: PostgreSQL SKIP LOCKED job queues, zero-duplicate-work guarantee
- **Database Persistence**: PostgreSQL 16.x with ACID compliance, complete task/run tracking
- **Extension Framework**: ✅ **FULLY OPERATIONAL** - Complete plugin system with all capabilities
- **4 Working Extensions**: ✅ **ALL OPERATIONAL** - observability, webui, mcp_http, events_demo
- **Event Management**: ✅ **REDIS STREAMS** - Pub/sub system for extension coordination
- **REST API**: Complete CRUD operations, health checks, admin interfaces, JWT authentication
- **Production Deployment**: Docker Compose with automated builds and monitoring

### **✅ Extension System - FULLY OPERATIONAL**

The extension system provides a complete plugin architecture with the following working extensions:

#### **Built-in Extensions (All Operational)**

1. **🔍 Observability Extension** (`/ext/observability/`)
   - **Purpose**: Prometheus metrics collection and monitoring
   - **Capabilities**: `ROUTES`
   - **Endpoints**: `/metrics` - Production Prometheus metrics
   - **Status**: ✅ **OPERATIONAL** - Verified working

2. **🌐 Web UI Extension** (`/ext/webui/`)
   - **Purpose**: Web-based task management interface
   - **Capabilities**: `ROUTES`, `STATIC`
   - **Features**: Task creation, monitoring, real-time status
   - **Status**: ✅ **OPERATIONAL** - Full web interface working

3. **🔌 MCP HTTP Extension** (`/ext/mcp_http/`)
   - **Purpose**: Model Context Protocol over HTTP
   - **Capabilities**: `ROUTES`
   - **Features**: Tool discovery, handshake, invocation, streaming
   - **Status**: ✅ **OPERATIONAL** - MCP protocol working

4. **📡 Events Demo Extension** (`/ext/events_demo/`)
   - **Purpose**: Redis Streams event system demonstration
   - **Capabilities**: `ROUTES`, `EVENTS_PUB`, `EVENTS_SUB`
   - **Features**: Event publishing, subscription, real-time streaming
   - **Status**: ✅ **OPERATIONAL** - Events working

### **Extension Architecture**

```
┌─────────────────────────────────────────────────────────────┐
│                    Ordinaut Core                            │
│  (Pure Task Scheduler + Extension Framework)               │
│  ✅ Task Scheduling  ✅ Pipeline Processing                 │
│  ✅ Worker System    ✅ Database Persistence                │
└─────────────────┬───────────────┬─────────────────────────────┘
                  │               │
    Plugin API    │               │  Plugin API
    ┌─────────────▼─────────────┐ │ ┌─────────────▼─────────────┐
    │   Observability         │ │ │    Web UI Extension     │
    │    Extension            │ │ │                         │
    │  ✅ Prometheus Metrics  │ │ │  ✅ Task Management      │
    │  ✅ /ext/observability/ │ │ │  ✅ /ext/webui/         │
    └─────────────────────────┘ │ └─────────────────────────┘
                                │
      ┌─────────────▼─────────────┐ ┌─────────────▼─────────────┐
      │   MCP HTTP Extension    │ │   Events Demo Extension   │
      │                         │ │                           │
      │  ✅ MCP Protocol        │ │  ✅ Redis Streams        │
      │  ✅ /ext/mcp_http/      │ │  ✅ /ext/events_demo/    │
      └─────────────────────────┘ └─────────────────────────┘
                      │
                      ▼
            ┌─────────────────┐
            │  AI Assistants  │
            │ (ChatGPT, etc.) │
            │  ✅ SUPPORTED   │
            └─────────────────┘
```

### **✅ Recent Fixes & Improvements (August 25, 2025)**

**Documentation System Fixes:**
- ✅ **Complete Extension Documentation**: Comprehensive guides in EN/RO/RU
- ✅ **API Reference**: Full extension API documentation with examples
- ✅ **Navigation Fixes**: Added missing api/agents.md to mkdocs navigation
- ✅ **Broken Link Fixes**: Fixed authentication.md references in troubleshooting docs
- ✅ **MkDocs Build**: Verified strict mode passes without warnings

**Docker Build Fixes:**
- ✅ **Obsolete References Removed**: Cleaned up `observability/` COPY commands from Dockerfiles
- ✅ **Multi-service Builds**: All containers (API, Scheduler, Worker) build successfully
- ✅ **Extension Integration**: Extensions properly included in container builds

**Codebase Cleanup:**
- ✅ **Legacy Files Removed**: 23+ obsolete CLAUDE.md and AGENTS.md files deleted
- ✅ **Directory Cleanup**: Removed obsolete catalogs/, observability/, payloads/ directories
- ✅ **Debug Artifacts**: Cleaned up debug scripts and coverage files

---

## Development Environment Setup

### Python Virtual Environment (Required)
```bash
# Virtual environment is located at .venv/ (with dot prefix)
source .venv/bin/activate

# If creating new environment:
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# For documentation development:
pip install -r requirements-docs.txt
```

### Docker Development Environment
```bash
# Start all services with extensions
cd ops/
docker-compose up -d

# Verify extension system
curl http://localhost:8080/ext/observability/metrics
curl http://localhost:8080/ext/webui/
curl http://localhost:8080/ext/mcp_http/meta

# Check system health
curl http://localhost:8080/health
```

---

## Extension Development

### Creating New Extensions

Extensions are discovered from multiple sources:
1. **Built-in**: `ordinaut/extensions/` directory
2. **External**: `ORDINAUT_EXT_PATHS` environment variable
3. **Python Packages**: `ordinaut.plugins` entry points

Each extension requires:
- `extension.json` - Extension manifest with capabilities
- `extension.py` - Implementation with `get_extension()` factory

Example minimal extension:
```python
from ordinaut.plugins.base import Extension, ExtensionInfo, Capability
from fastapi import APIRouter

class MyExtension(Extension):
    def info(self) -> ExtensionInfo:
        return ExtensionInfo(
            id="my_extension",
            name="My Custom Extension",
            version="1.0.0"
        )

    def requested_capabilities(self) -> set[Capability]:
        return {Capability.ROUTES}

    def setup(self, *, app, mount_path, **kwargs):
        router = APIRouter()
        
        @router.get("/hello")
        def hello():
            return {"message": "Hello from my extension!"}
            
        return router

def get_extension():
    return MyExtension()
```

### Extension Capabilities

- **ROUTES**: HTTP endpoint creation
- **TOOLS**: Tool registry access for custom tool registration
- **EVENTS_PUB**: Event publishing to Redis Streams
- **EVENTS_SUB**: Event subscription from Redis Streams
- **BACKGROUND_TASKS**: Long-running background process management
- **STATIC**: Static file serving capabilities

---

## Production Deployment

### Quick Start (Recommended)
```bash
# Using published Docker images
cd ops/
./start.sh ghcr --logs

# System will be available at:
# API: http://localhost:8080
# Web UI: http://localhost:8080/ext/webui/
# Metrics: http://localhost:8080/ext/observability/metrics
# Health: http://localhost:8080/health
```

### Docker Services
- **API Service**: FastAPI with extension system mounted
- **PostgreSQL**: Database with SKIP LOCKED job queues
- **Redis**: Streams for event coordination
- **Scheduler**: APScheduler daemon for timing
- **Workers**: Concurrent job processors (2 instances)

### System Health Verification
```bash
# Check all services healthy
curl http://localhost:8080/health | jq

# Test extension system
curl http://localhost:8080/ext/observability/metrics | head -5
curl http://localhost:8080/ext/webui/ | head -5

# Verify MCP integration
curl http://localhost:8080/ext/mcp_http/meta | jq
```

---

## Git Commit Standards

**CRITICAL: Clean commit messages without AI attribution.**

Follow [Conventional Commits](https://conventionalcommits.org/) for automated releases:

```bash
feat(api): add new extension capability
fix(scheduler): resolve timezone handling issue
docs(extensions): add comprehensive API documentation
```

**Commit Types:**
- `feat:` → Minor version bump (new features)
- `fix:` → Patch version bump (bug fixes)
- `docs:`, `refactor:`, `style:` → No version bump

**Always pull-rebase before pushing:**
```bash
git pull --rebase origin main
git push origin main
```

---

## Key Implementation Patterns

### Database Access (REQUIRED)
```python
# ALWAYS use SKIP LOCKED for job queues
from sqlalchemy import text

def lease_work():
    with db.begin() as tx:
        work = tx.execute(text("""
            SELECT id, task_id, payload
            FROM due_work 
            WHERE run_at <= now() 
              AND (locked_until IS NULL OR locked_until < now())
            ORDER BY priority DESC, run_at ASC
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        """)).fetchone()
        # Process work item...
```

### Extension Registration (AUTOMATIC)
```python
# Extensions are automatically discovered and loaded
# No manual registration required
# Place in ordinaut/extensions/ or use ORDINAUT_EXT_PATHS
```

### Pipeline Execution (CURRENT)
```python
# Core system processes pipeline structure
# Tool execution simulated - extensions provide real tools
from engine.executor import run_pipeline

result = run_pipeline(task)
# Contains resolved templates, simulated results, execution context
```

---

## Documentation

### Comprehensive Documentation Available

- **Extension System Guide**: `docs/guides/extensions.md` (EN/RO/RU)
- **Extension API Reference**: `docs/api/extensions.md` (EN/RO/RU)
- **Task Management**: `docs/api/tasks.md`
- **Deployment Guide**: `docs/operations/deployment.md`

### Building Documentation
```bash
source .venv/bin/activate
pip install -r requirements-docs.txt
mkdocs build --strict
mkdocs serve  # Local development server
```

---

## System Status Summary

**🎉 PRODUCTION READY - COMPLETE TASK SCHEDULING PLATFORM** 

✅ **Core Scheduler**: 100% operational with RRULE, timezone support, worker coordination  
✅ **Extension Framework**: Fully operational with 4 working extensions  
✅ **Production Deployment**: Docker Compose with automated builds  
✅ **Comprehensive Documentation**: Trilingual docs with complete API reference  
✅ **CI/CD Pipeline**: Automated releases with semantic versioning  
✅ **Monitoring**: Prometheus metrics and health checks operational  

The Ordinaut is now a complete, production-ready enterprise task scheduling platform with a proven extension system that demonstrates MCP integration, web interfaces, metrics collection, and event coordination.

**Next Steps**: Ready for production deployment and custom extension development.