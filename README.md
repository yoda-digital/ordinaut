<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/ordinaut_logo.png">
    <source media="(prefers-color-scheme: light)" srcset="docs/assets/ordinaut_logo.png">
    <img alt="Task Scheduling System Logo" src="docs/assets/task_scheduler_logo.png" width="200" height="auto">
  </picture>
  
  <p>
    <strong>Enterprise-grade pure task scheduling API with RRULE support, pipeline execution, and comprehensive observability. Designed as a clean foundation for extension development with MCP and tool integrations implemented as separate services.</strong>
  </p>
  
  <p>
    ⚡ <strong>PURE TASK SCHEDULER</strong> - Clean foundation ready for extension development. MCP integration and tool execution will be implemented as separate extension services that communicate via REST APIs.
  </p>
  
  <p>
    <a href="https://github.com/yoda-digital/task-scheduler">
      <img src="https://img.shields.io/github/stars/yoda-digital/task-scheduler?style=social" alt="GitHub stars">
    </a>
    <a href="https://github.com/yoda-digital/task-scheduler/issues">
      <img src="https://img.shields.io/github/issues/yoda-digital/task-scheduler" alt="GitHub issues">
    </a>
    <a href="https://github.com/yoda-digital/task-scheduler/blob/main/LICENSE">
      <img src="https://img.shields.io/github/license/yoda-digital/task-scheduler" alt="License">
    </a>
  </p>
</div>

---

## Quick Start

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

**That's it!** Your task scheduling system is now running with:
- 📡 **REST API** at `http://localhost:8080`
- 📊 **Health Dashboard** at `http://localhost:8080/health`
- 📚 **Interactive Docs** at `http://localhost:8080/docs`

### 🐳 **Production-Ready Docker Images**

**✅ FULLY AUTOMATED PUBLISHING** - Images are automatically built and published with every release:

**📦 Available Images:**
- `ghcr.io/yoda-digital/task-scheduler-api:latest` - FastAPI REST API service
- `ghcr.io/yoda-digital/task-scheduler-scheduler:latest` - APScheduler service  
- `ghcr.io/yoda-digital/task-scheduler-worker:latest` - Job execution service

**🏗️ Build Pipeline:**
- **Triggered**: Automatically on every semantic-release (conventional commits)
- **Platform**: `linux/amd64` (Intel/AMD - universal compatibility)
- **Registry**: GitHub Container Registry (GHCR) - publicly accessible
- **Versioning**: Semantic version tags (`v1.7.1`) + `latest` tag
- **Security**: Build attestations, SBOM, and provenance signatures included

**🚀 Instant Deployment:**
```bash
# Pull and run specific version
docker pull ghcr.io/yoda-digital/task-scheduler-api:v1.7.1
docker pull ghcr.io/yoda-digital/task-scheduler-scheduler:latest
docker pull ghcr.io/yoda-digital/task-scheduler-worker:latest

# Or use the automated GHCR setup
./ops/start.sh ghcr
```

**🔒 Production Features:**
- **Multi-stage builds** - Optimized runtime images (50% smaller)
- **Non-root execution** - Security best practices enforced
- **Health checks** - Built-in container health monitoring  
- **Retry mechanisms** - Network resilience for publishing pipeline
- **Automatic public visibility** - No manual registry configuration needed

## Architecture Overview

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

### Core Components

1. **PostgreSQL Database** - ACID-compliant durable storage with `FOR UPDATE SKIP LOCKED` job queues
2. **APScheduler** - Battle-tested scheduling with SQLAlchemy job store for temporal logic  
3. **Redis Streams** - Ordered, durable event logs with consumer groups (`XADD`/`XREADGROUP`)
4. **FastAPI Service** - Modern REST API with automatic OpenAPI documentation
5. **Worker Pool** - Distributed job processors using safe work leasing patterns
6. **Pipeline Engine** - Deterministic pipeline execution with template rendering (tool simulation)
7. **Extension Architecture** - Clean REST APIs ready for MCP and tool integration development

## Key Features

### 🕐 **Advanced Scheduling**
- **Cron expressions**: Traditional cron-style scheduling (`0 8 * * 1-5`)
- **RRULE support**: Full RFC-5545 recurrence rules with timezone handling
- **One-time tasks**: ISO timestamp-based single execution
- **Event-driven**: Tasks triggered by external events
- **Conditional logic**: Tasks with complex trigger conditions

### ⚡ **Reliable Execution**
- **>99.9% uptime** with graceful failure handling
- **Zero work loss** - all scheduled work persists across restarts
- **Concurrent processing** via PostgreSQL `SKIP LOCKED` patterns
- **Retry mechanisms** with exponential backoff and jitter
- **Idempotent operations** to prevent duplicate processing

### 🔧 **Pipeline Engine**
- **Declarative pipelines** with step-by-step execution
- **Template variables**: `${steps.weather.summary}`, `${params.user_id}`
- **Conditional steps**: JMESPath expressions for flow control
- **Schema validation**: JSON Schema framework ready for extensions
- **Tool simulation**: All tool calls simulated with proper context structure

### 🛡️ **Security & Governance**
- **Agent-based authentication** with scope-based authorization
- **Audit logging** for all operations with immutable trails
- **Input validation** at API boundaries with detailed error responses
- **Rate limiting** and budget enforcement for external tool usage

### 📊 **Production Observability**
- **Prometheus metrics** for all system components
- **Grafana dashboards** for real-time monitoring
- **Structured logging** with correlation IDs
- **Health checks** for Kubernetes readiness/liveness probes
- **Alert rules** for proactive issue detection

## Example Use Cases

**⚡ IMPORTANT**: The examples below show pipeline *structure* processing. All tool calls (google-calendar-mcp, weather-mcp, etc.) are currently **SIMULATED** by the core system. Real tool execution will be implemented as extensions that communicate with the scheduler via REST APIs.

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

### Email Follow-up Automation (Template Structure)
```json
{
  "title": "Email Follow-up Manager",
  "description": "Check for emails without replies and send polite follow-ups",
  "schedule_kind": "cron",
  "schedule_expr": "0 10 * * *",
  "payload": {
    "pipeline": [
      {
        "id": "scan_outbox",
        "uses": "imap-mcp.find_outbound_without_reply",
        "with": {"lookback_days": 7, "min_age_hours": 72},
        "save_as": "pending_emails"
      },
      {
        "id": "generate_followups",
        "uses": "llm.generate_followups",
        "with": {
          "emails": "${steps.pending_emails.threads}",
          "tone": "professional_friendly"
        },
        "save_as": "drafts"
      },
      {
        "id": "request_approval",
        "uses": "orchestrator.request_approval",
        "with": {
          "message": "Review ${steps.drafts.count} follow-up emails",
          "data": "${steps.drafts.messages}"
        },
        "save_as": "approval"
      },
      {
        "id": "send_approved",
        "uses": "gmail-mcp.send_followups",
        "with": {"drafts": "${steps.approval.approved_items}"},
        "if": "${steps.approval.status == 'approved'}"
      }
    ]
  }
}
```

**Note**: This pipeline demonstrates complex conditional logic (`if` expressions), approval workflows, and multi-step processing. All tool calls (imap-mcp, llm.generate_followups, gmail-mcp) are simulated. Extensions will implement real email processing, LLM integration, and approval systems.

## Technology Stack

### Core Infrastructure
- **Python 3.12** - Modern async/await patterns and type hints
- **PostgreSQL 16** - ACID compliance, SKIP LOCKED for job queues
- **Redis 7** - Streams for ordered events with consumer groups
- **APScheduler 3** - Battle-tested scheduling with SQLAlchemy job store
- **FastAPI** - Modern Python API framework with automatic OpenAPI docs

### Specialized Libraries
- **python-dateutil** - RFC-5545 RRULE processing for complex recurring schedules
- **JMESPath** - JSON querying for conditional logic and data selection
- **JSON Schema** - Validation framework (ready for extension development)
- **Extension Framework** - Clean architecture for MCP and tool integration

### Why These Choices
- APScheduler + SQLAlchemy + PostgreSQL is explicitly recommended by APScheduler maintainers
- `FOR UPDATE SKIP LOCKED` is the canonical PostgreSQL pattern for safe job distribution
- Redis Streams designed for ordered, durable event logs with consumer groups
- Clean extension architecture enables modular development of MCP and tool integrations

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

See [API Reference](https://yoda-digital.github.io/ordinaut/api/api_reference/) for complete endpoint documentation with examples.

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

## Next Steps

1. **[Quick Start](docs/getting-started/quick-start.md)** - Get the system running in 5 minutes
2. **[API Reference](docs/api/api_reference.md)** - Complete REST API documentation
3. **[Development Setup](docs/guides/development.md)** - Contribute and extend the system
4. **[Troubleshooting](docs/operations/troubleshooting.md)** - Common issues and solutions
5. **[Production Deployment](docs/operations/deployment.md)** - Scale and monitor in production

## Community and Support

- **Documentation**: Complete guides and API reference
- **Health Monitoring**: Built-in observability and alerting
- **Testing**: Comprehensive test suite with >95% coverage
- **Security**: Production-ready security patterns and audit trails

## License

See [LICENSE](LICENSE) for details.

---

**\ud83d\ude80 Pure Task Scheduler Foundation - Ready for Extension Development**

The Ordinaut core provides bulletproof scheduling, pipeline processing, and observability. Start with the [Quick Start](#quick-start) guide and have your pure scheduler running in 5 minutes. MCP integration and tool execution will be added as separate extension services.