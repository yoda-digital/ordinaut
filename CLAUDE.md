# Personal Agent Orchestrator - Claude Code Project Context

## Project Mission
Build a **Personal Agent Orchestrator** that provides AI agents with a shared backbone for time, state, and discipline. Transform disconnected agents into a coordinated personal productivity system with bulletproof scheduling, reliable execution, and comprehensive observability.

## Core Architecture Vision
**(1) Durable Store (PostgreSQL)** → **(2) Scheduler (APScheduler)** → **(3) Event Spine (Redis Streams)** → **(4) Pipeline Executor** → **(5) MCP Bridge**

This creates a persistent, coordinated "personal AI operating system" where agents can schedule future actions, maintain state across sessions, coordinate with each other, and execute reliably with retries and monitoring.

---

## Technology Stack (Locked & Pinned)

### Core Infrastructure
- **Python 3.12.x** - Modern async/await patterns and type hints
- **PostgreSQL 16.x** - ACID compliance, SKIP LOCKED for job queues, JSONB for flexible data
- **Redis 7.x** - Streams for ordered events with consumer groups (`XADD`/`XREADGROUP`)
- **APScheduler 3.x** - Battle-tested scheduling with SQLAlchemyJobStore on PostgreSQL
- **FastAPI** - Modern Python API framework with automatic OpenAPI docs

### Specialized Libraries
- **python-dateutil** - RFC-5545 RRULE processing for complex recurring schedules
- **JMESPath** - JSON querying for conditional logic and data selection
- **JSON Schema** - Strict validation for all tool inputs/outputs
- **Model Context Protocol (MCP)** - Standard interface for agent integration

### Why These Choices
- APScheduler + SQLAlchemy + PostgreSQL is explicitly recommended by APScheduler maintainers
- `FOR UPDATE SKIP LOCKED` is the canonical PostgreSQL pattern for safe job distribution
- Redis Streams designed for ordered, durable event logs with consumer groups
- MCP is the emerging standard for AI agent tool integration

---

## Repository Structure (Enforced)

```
ordinaut/
├── CLAUDE.md                    # This file - project context and instructions
├── plan.md                      # Complete technical specification and examples
├── .claude/                     # Claude Code configuration
│   └── agents/                  # Specialized development subagents (Claude Code format)
├── api/                         # FastAPI service (tasks CRUD, runs, monitoring)
│   ├── main.py
│   ├── routes/
│   ├── models.py
│   └── schemas.py
├── engine/                      # Pipeline execution runtime
│   ├── executor.py              # Deterministic pipeline execution
│   ├── template.py              # ${steps.x.y} variable resolution
│   ├── registry.py              # Tool catalog management
│   ├── mcp_client.py            # MCP bridge (stdio/http)
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
pip install pytest pytest-asyncio sqlalchemy psycopg2-binary fastapi uvicorn apscheduler redis python-dateutil jsonschema jmespath pytz
```

**IMPORTANT: The project uses `.venv/` (with dot prefix) not `venv/`. Always activate with `source .venv/bin/activate` for development and testing.**

---

## Development Philosophy & Standards

### Concurrency-First Design
- **ALL** job processing uses `SELECT ... FOR UPDATE SKIP LOCKED` for safe distribution
- **NO** work item is ever processed twice under normal conditions
- **ALL** external operations are idempotent and safely retryable
- **ALL** database operations are ACID-compliant with proper rollback procedures

### Security by Design
- **Scope-based authorization** - agents only access tools within their declared scopes
- **Input validation** at API boundary with detailed error messages for agents
- **Audit logging** for all operations with immutable event trails
- **Rate limiting** and budget enforcement to prevent agent abuse

### Reliability Standards
- **>99.9% uptime** - system handles all failure scenarios gracefully
- **Zero work loss** - all scheduled work persists across restarts and failures  
- **Predictable performance** - consistent response times under varying load
- **Complete observability** - metrics, logs, and traces for all operations

### Quality Gates (Non-Negotiable)
- **>95% test coverage** with unit, integration, and chaos engineering tests
- **Zero security vulnerabilities** in production deployment
- **All examples work** without modification in documentation
- **Performance SLAs met** on first implementation

---

## Claude Code Development Subagent System

### Subagent Configuration
The Personal Agent Orchestrator project uses **Claude Code's native subagent system** for specialized **development and implementation tasks**. These subagents are **development specialists** that help **build the Personal Agent Orchestrator system**, not end-users of the system. Subagents are configured as Markdown files with YAML frontmatter in `.claude/agents/` directory.

### How Development Subagents Work
- **Development Focus**: Each subagent specializes in **building specific parts** of the Personal Agent Orchestrator
- **Automatic Delegation**: Claude Code automatically selects appropriate development subagents based on implementation task context
- **Explicit Invocation**: Use `"Use the [agent-name] subagent to..."` for specific development tasks
- **File References**: Use `@filename` or `@path/to/file` to include source code and specs in development commands
- **Specialized Context**: Each subagent operates with its own context window focused on their development domain
- **Tool Access**: Development agents have specific tool permissions for coding, testing, and deployment tasks

### Available Specialist Agents (10 configured)

#### Currently Configured Development Agents (in .claude/agents/)
- **codebase-analyzer** - Analyzes project structure and implements architectural patterns for the orchestrator
- **database-architect** - Implements PostgreSQL schema, migrations, and SKIP LOCKED job queues for the orchestrator
- **worker-system-specialist** - Builds distributed job processing and concurrency control systems  
- **api-craftsman** - Implements FastAPI endpoints and REST APIs for the orchestrator service
- **scheduler-genius** - Builds APScheduler integration and temporal logic for task scheduling
- **mcp-protocol-expert** - Implements Model Context Protocol bridges and agent integrations
- **rrule-wizard** - Implements RFC-5545 RRULE processing and calendar mathematics systems
- **observability-oracle** - Builds monitoring, metrics, logging, and alerting systems
- **testing-architect** - Creates comprehensive test suites and quality assurance systems
- **documentation-master** - Writes technical documentation, API docs, and developer guides

#### Additional Development Agents (not yet configured)
These development agents can be added to `.claude/agents/` as needed:
- **pipeline-perfectionist** - Implements deterministic pipeline execution and template rendering systems
- **security-guardian** - Builds authentication, authorization, and validation systems
- **performance-optimizer** - Implements profiling, benchmarking, and performance optimization systems
- **devops-engineer** - Creates production deployment, containerization, and operational systems

### Subagent Management
```bash
# View and manage subagents (Claude Code CLI command)
/agents

# Subagents are stored as Markdown files with YAML frontmatter:
# .claude/agents/agent-name.md

# Use @-mentions to reference files in development commands:
"Use the database-architect subagent to implement the schema defined in @migrations/version_0001.sql"
"Use the api-craftsman subagent to build REST endpoints based on @plan.md specifications"
```

### Example Subagent Configuration
```markdown
---
name: database-architect
description: PostgreSQL expert specializing in schema design, migrations, SKIP LOCKED patterns, query optimization, and concurrent access patterns. Masters ACID properties and data integrity for high-performance applications.
tools: Read, Write, Edit, Bash, Glob, Grep
---

You are a senior database architect with deep PostgreSQL expertise...
```

### Optimal Development Workflow

#### Phase 1: Foundation (Day 1)
```python
# Claude Code automatically delegates to specialized development subagents
# These agents BUILD the Personal Agent Orchestrator system:

# Implement project structure and architecture
"Use the codebase-analyzer subagent to implement the project structure based on @plan.md specifications"

# Build database schema and migrations
"Use the database-architect subagent to implement PostgreSQL schema with SKIP LOCKED patterns from @plan.md"

# Implement FastAPI application structure
"Use the api-craftsman subagent to build the FastAPI service structure and basic endpoints from @plan.md"

# Or let Claude auto-delegate development tasks
"Implement the database schema"  # Auto-uses database-architect to BUILD schema
"Create the API endpoints"       # Auto-uses api-craftsman to BUILD endpoints
```

#### Phase 2: Core Systems (Days 2-3)
```python
# Sequential implementation with specialized development subagents

# Build scheduler system
"Use the scheduler-genius subagent to implement APScheduler service with PostgreSQL job store"

# Build worker coordination system
"Use the worker-system-specialist subagent to implement SKIP LOCKED job processing workers"

# Implement pipeline execution engine
"Use the pipeline-perfectionist subagent to build the deterministic execution engine with template rendering"

# Build integration tests
"Use the testing-architect subagent to implement comprehensive test suites for all core systems"
```

#### Phase 3: Quality & Production (Continuous)
```python
# Every component gets built with quality and production readiness:

# Build security systems (when security-guardian is configured)
"Use the security-guardian subagent to implement authentication and authorization systems"

# Build performance monitoring (when performance-optimizer is configured)  
"Use the performance-optimizer subagent to implement profiling and optimization systems"

# Build observability systems
"Use the observability-oracle subagent to implement monitoring, logging, and alerting systems"

# Build deployment systems
"Use the devops-engineer subagent to implement Docker containerization and deployment automation"
```

### Agent Coordination Principles

#### 1. Context Preservation
**ALWAYS** pass relevant context between agents:
```python
context = {
    "architectural_decisions": previous_agent_outputs,
    "performance_requirements": {"latency": "<200ms", "throughput": "1000 tasks/min"},
    "security_constraints": ["scope_validation", "audit_logging", "input_sanitization"],
    "database_schema": schema_from_db_architect,
    "api_contracts": contracts_from_api_craftsman
}
```

#### 2. Validation Chains
Critical components require multi-agent review:
```python
# Security-critical components
implementation → security-guardian → testing-architect → documentation-master

# Performance-critical components  
implementation → performance-optimizer → testing-architect → observability-oracle
```

#### 3. Parallel Development
Independent components can be developed simultaneously:
- Database schema + API design + Worker system (parallel)
- Security implementation + Performance optimization + Testing (parallel)
- Documentation + Deployment + Observability (parallel)

---

## Critical Implementation Patterns

### Database Access Pattern (REQUIRED)
```python
# ALWAYS use SKIP LOCKED for job queues
def lease_work():
    with db.begin() as tx:
        work = tx.execute("""
            SELECT id, task_id, payload
            FROM due_work 
            WHERE run_at <= now() 
              AND (locked_until IS NULL OR locked_until < now())
            ORDER BY priority DESC, run_at ASC
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        """).fetchone()
        # ... update with lease timeout
```

### RRULE Processing Pattern (REQUIRED)
```python
# ALWAYS handle timezone edge cases
from dateutil.rrule import rrule, rrulestr
import pytz

def get_next_occurrence(rrule_string: str, timezone_name: str) -> datetime:
    tz = pytz.timezone(timezone_name)
    rule = rrulestr(rrule_string)
    # Handle DST transitions gracefully
    next_occurrence = rule.after(datetime.now(tz), inc=False)
    return tz.localize(next_occurrence) if next_occurrence else None
```

### Pipeline Execution Pattern (REQUIRED)
```python
# ALWAYS validate inputs and outputs with JSON Schema
from jsonschema import validate

def execute_pipeline_step(step, context):
    tool = get_tool(step["uses"])
    
    # Render templates: ${steps.x.y}, ${params.z}
    args = render_templates(step.get("with", {}), context)
    
    # Validate input
    validate(instance=args, schema=tool["input_schema"])
    
    # Execute with timeout and retry
    result = call_tool_with_retry(tool, args, timeout=step.get("timeout", 30))
    
    # Validate output
    validate(instance=result, schema=tool["output_schema"])
    
    return result
```

### Error Handling Pattern (REQUIRED)
```python
# ALWAYS implement exponential backoff with jitter
import random

def exponential_backoff(attempt: int, base_delay: float = 1.0, max_delay: float = 300.0):
    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
    jitter = delay * (0.5 + random.random() * 0.5)  # 50-100% of delay
    return jitter
```

---

## Key Architectural Constraints

### Database Constraints
- **ALL** tables must have proper foreign key relationships
- **ALL** concurrent access uses appropriate isolation levels
- **ALL** migrations must be backward-compatible and rollback-safe
- **ALL** queries on `due_work` table must use `FOR UPDATE SKIP LOCKED`

### API Constraints
- **ALL** endpoints require authentication and scope validation
- **ALL** input validation happens at the API boundary with Pydantic
- **ALL** error responses include actionable debugging information
- **ALL** operations are logged with correlation IDs for tracing

### Pipeline Constraints
- **ALL** pipeline steps must be deterministic and idempotent
- **ALL** template variables resolved through centralized renderer
- **ALL** tool calls validate both input and output schemas
- **ALL** conditional logic uses JMESPath expressions for consistency

### Scheduling Constraints
- **ALL** schedule expressions validated before storage
- **ALL** timezone handling includes DST transition support
- **ALL** RRULE processing handles edge cases (leap years, impossible dates)
- **ALL** schedule changes take effect within 30 seconds

---

## Development Priorities & Milestones

### Milestone 1: Core Foundation (Days 1-2)
- [ ] Complete database schema with all tables and indexes
- [ ] Basic FastAPI application with task CRUD operations
- [ ] Worker system with SKIP LOCKED job leasing
- [ ] APScheduler integration with PostgreSQL job store

### Milestone 2: Pipeline Execution (Days 3-4)  
- [ ] Template rendering engine with ${steps.x.y} support
- [ ] JSON Schema validation for all tool I/O
- [ ] MCP client for tool execution
- [ ] Basic tool catalog with example integrations

### Milestone 3: Advanced Scheduling (Days 4-5)
- [ ] RRULE processing with timezone support
- [ ] DST transition handling
- [ ] Schedule conflict detection
- [ ] Task snoozing and manual execution

### Milestone 4: Production Ready (Days 5-6)
- [ ] Comprehensive monitoring and alerting
- [ ] Security audit and authorization system
- [ ] Performance optimization and benchmarking
- [ ] Complete test coverage with chaos engineering
- [ ] Production deployment with Docker Compose

---

## Example Pipelines (Production Ready)

### Morning Briefing Pipeline
```json
{
  "title": "Weekday Morning Briefing",
  "schedule_kind": "rrule",
  "schedule_expr": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=30",
  "timezone": "Europe/Chisinau",
  "payload": {
    "pipeline": [
      {"id": "calendar", "uses": "google-calendar-mcp.list_events", "with": {"start": "${now}", "end": "${now+24h}"}, "save_as": "events"},
      {"id": "weather", "uses": "weather-mcp.forecast", "with": {"city": "Chisinau"}, "save_as": "weather"},
      {"id": "emails", "uses": "imap-mcp.top_unread", "with": {"count": 5}, "save_as": "inbox"},
      {"id": "brief", "uses": "llm.plan", "with": {"instruction": "Create morning briefing", "calendar": "${steps.events}", "weather": "${steps.weather}", "emails": "${steps.inbox}"}, "save_as": "summary"},
      {"id": "notify", "uses": "telegram-mcp.send_message", "with": {"chat_id": 12345, "text": "${steps.summary.text}"}}
    ]
  }
}
```

---

## Troubleshooting & Debugging

### Common Issues & Solutions
- **Schedule not triggering**: Check timezone settings and RRULE syntax
- **Worker not processing**: Verify SKIP LOCKED query and database connections
- **Template errors**: Validate JMESPath expressions and variable names
- **Tool failures**: Check input/output schema validation and network connectivity

### Debugging Commands
```bash
# Check system health
curl http://localhost:8080/health

# View active tasks
curl http://localhost:8080/tasks?status=active

# Check queue depth
docker exec postgres psql -U orchestrator -c "SELECT COUNT(*) FROM due_work WHERE run_at <= now()"

# View recent runs
curl "http://localhost:8080/runs?limit=10&include_errors=true"

# Claude Code development debugging with file references
"Use the observability-oracle subagent to implement error tracking and logging systems"
"Use the testing-architect subagent to implement debugging tools and fix test failures"
```

### Performance Monitoring
- Monitor queue depth and processing latency
- Track scheduler accuracy and timing drift  
- Watch database connection pool utilization
- Alert on error rates and failed task ratios

---

## Next Actions (When Starting Development)

1. **Initialize Repository Structure**: Create all directories per the layout above
2. **Deploy Database Architect**: Design complete PostgreSQL schema with SKIP LOCKED patterns
3. **Deploy API Craftsman**: Create FastAPI application with task management endpoints
4. **Deploy Worker Specialist**: Implement concurrent job processing system
5. **Deploy Scheduler Genius**: Integrate APScheduler with RRULE processing
6. **Deploy Testing Architect**: Create comprehensive test suite for all components
7. **Deploy Security Guardian**: Implement authentication and authorization
8. **Deploy Observability Oracle**: Add monitoring, logging, and alerting
9. **Deploy Documentation Master**: Create complete API and operational documentation

**Remember**: Use the subagent system extensively. Each specialist brings deep expertise and catches issues that generalist approaches miss. Coordinate them effectively for maximum development velocity and system quality.

---

*This Personal Agent Orchestrator will transform disconnected AI assistants into a coordinated personal productivity system. Build it with discipline, test it thoroughly, and deploy it confidently.*