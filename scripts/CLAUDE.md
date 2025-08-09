# Scripts Directory - Personal Agent Orchestrator

## Purpose
The `scripts/` directory contains operational utilities and system management scripts for the Personal Agent Orchestrator. These scripts provide essential functionality for development, testing, validation, and operational maintenance of the system.

## Core Philosophy
Scripts in this directory follow the "operational excellence" principle:
- **Automated validation** - Every critical system component has validation scripts
- **Local development support** - Alternative deployment methods when containers aren't available
- **Integration testing** - End-to-end system validation with real workflows
- **Observability validation** - Comprehensive testing of monitoring and metrics
- **Graceful degradation** - SQLite fallback when PostgreSQL unavailable

---

## Script Inventory

### Development & Startup Scripts

#### `start_local.py` *(Executable)*
**Purpose:** Local development startup script providing Docker Compose alternative
**Use Case:** Development environments without container support

**Key Features:**
- SQLite database fallback with schema adaptation
- Multi-process service coordination (API, Scheduler, Workers)
- Automatic dependency setup and validation
- Graceful shutdown with process cleanup
- Environment variable configuration

**Usage:**
```bash
./scripts/start_local.py
# Starts complete orchestrator system locally with SQLite backend
# Equivalent to docker-compose up but without containers
```

**Environment Setup:**
- Creates SQLite database at `orchestrator.db`
- Configures memory-based Redis alternative
- Sets development environment variables
- Initializes simplified database schema

#### `start_system.py` *(Executable)*
**Purpose:** Simplified system startup with enhanced error handling
**Use Case:** Quick system validation and component testing

**Key Features:**
- Individual component startup with health checks
- SQLite schema initialization
- Process monitoring and status reporting
- Structured logging and error tracking
- Component dependency validation

**Usage:**
```bash
./scripts/start_system.py
# Starts system components with detailed status reporting
# Validates each service before proceeding to next component
```

### Validation & Testing Scripts

#### `final_validation.py` *(Executable)*
**Purpose:** Comprehensive Day-1 integration flow validation
**Use Case:** Complete system validation implementing plan.md scenarios

**Key Features:**
- Complete API endpoint validation
- Morning briefing pipeline testing
- Multi-step workflow validation
- Agent authentication testing
- Tool catalog integration testing

**Usage:**
```bash
./scripts/final_validation.py
# Implements complete Day-1 integration flow
# Creates agent, schedules tasks, validates execution
# Tests morning briefing pipeline from plan.md
```

**Test Scenarios:**
1. Agent registration and authentication
2. Task creation with RRULE scheduling
3. Morning briefing pipeline execution
4. Template variable resolution
5. Tool catalog integration
6. Error handling and recovery

#### `test_system.py` *(Executable)*
**Purpose:** Quick system integration testing
**Use Case:** Rapid API validation and basic functionality testing

**Key Features:**
- API endpoint health checks
- Basic CRUD operations testing
- Service availability validation
- Quick smoke testing
- Background service management

**Usage:**
```bash
./scripts/test_system.py
# Quick system validation - API endpoints and basic functionality
# Faster than final_validation.py for development iterations
```

#### `validate_scheduler.py`
**Purpose:** Scheduler service validation and RRULE testing
**Use Case:** Validate scheduling logic without external dependencies

**Key Features:**
- Import validation for all scheduler components
- RRULE syntax and processing validation
- Schedule calculation testing
- Timezone handling validation
- Edge case testing (DST, leap years)

**Usage:**
```bash
python scripts/validate_scheduler.py
# Validates scheduler service can be imported and initialized
# Tests RRULE processing with various patterns
# No external services required
```

**Test Coverage:**
- Daily, weekly, monthly RRULE patterns
- Timezone conversion and DST handling
- Business day scheduling
- Complex recurring patterns
- Schedule validation and error handling

#### `test_scheduler_logic.py`
**Purpose:** Static analysis and logic validation of scheduler implementation
**Use Case:** Code structure validation and method completeness

**Key Features:**
- AST-based code analysis
- Required method validation
- Implementation completeness checking
- Code structure analysis
- Method signature validation

**Usage:**
```bash
python scripts/test_scheduler_logic.py
# Static analysis of scheduler implementation
# Validates required methods and code structure
# No runtime dependencies
```

### Observability & Monitoring Scripts

#### `test_observability.py` *(Executable)*
**Purpose:** Comprehensive observability stack validation
**Use Case:** Validate metrics, logging, health checks, and Prometheus integration

**Key Features:**
- Prometheus metrics collection testing
- Structured logging validation
- Health check system testing
- Alert rule validation
- Performance metrics testing

**Usage:**
```bash
./scripts/test_observability.py
# Tests complete observability stack
# Validates metrics collection, logging, health checks
# Tests Prometheus integration and alert rules
```

**Test Components:**
- HTTP request metrics recording
- Task execution metrics tracking
- Worker heartbeat monitoring
- External tool call metrics
- System health monitoring
- Log correlation and tracing

---

## Usage Patterns & Workflows

### Development Workflow
```bash
# 1. Start development environment
./scripts/start_local.py

# 2. Run quick system validation
./scripts/test_system.py

# 3. Validate specific components
python scripts/validate_scheduler.py

# 4. Run comprehensive validation
./scripts/final_validation.py

# 5. Test observability stack
./scripts/test_observability.py
```

### CI/CD Integration
```bash
# Validation pipeline for automated testing
python scripts/validate_scheduler.py
python scripts/test_scheduler_logic.py
./scripts/test_system.py
./scripts/final_validation.py
./scripts/test_observability.py
```

### Troubleshooting Workflow
```bash
# 1. Basic system health
./scripts/test_system.py

# 2. Component-specific validation
python scripts/validate_scheduler.py  # For scheduling issues
./scripts/test_observability.py       # For monitoring issues

# 3. Full integration testing
./scripts/final_validation.py
```

---

## Integration with Development Workflows

### Local Development Support
Scripts provide complete local development environment:
- **Database:** SQLite fallback with schema adaptation
- **Redis:** Memory-based implementation for development
- **Services:** Multi-process coordination without containers
- **Validation:** Comprehensive testing without external dependencies

### Production Readiness Validation
Scripts ensure production deployment readiness:
- **Integration Testing:** End-to-end workflow validation
- **Observability:** Comprehensive monitoring validation
- **Performance:** Metrics collection and analysis
- **Error Handling:** Failure scenario testing

### Quality Assurance Integration
Scripts support comprehensive quality gates:
- **Static Analysis:** Code structure and completeness validation
- **Dynamic Testing:** Runtime behavior and integration testing
- **Performance Testing:** System performance and scaling validation
- **Security Testing:** Authentication and authorization validation

---

## Automation & Maintenance Tasks

### Automated System Validation
```bash
# Daily system health check
./scripts/test_system.py

# Weekly comprehensive validation
./scripts/final_validation.py

# Continuous observability validation
./scripts/test_observability.py
```

### Development Environment Setup
```bash
# New developer onboarding
./scripts/start_local.py
# Complete development environment in single command
# No external dependencies or complex setup required
```

### System Debugging & Diagnostics
```bash
# Component-specific diagnostics
python scripts/validate_scheduler.py      # Scheduler issues
python scripts/test_scheduler_logic.py    # Logic validation
./scripts/test_observability.py           # Monitoring issues
```

### Performance & Load Testing
```bash
# System performance validation
./scripts/final_validation.py
# Includes performance metrics and load testing scenarios
# Validates system behavior under various conditions
```

---

## Script Dependencies & Requirements

### Common Dependencies
All scripts share common requirements:
- **Python 3.12+** - Modern async/await support
- **Project Dependencies** - SQLAlchemy, FastAPI, APScheduler
- **Development Tools** - pytest, uvicorn for local testing
- **System Integration** - requests library for API testing

### Database Support
Scripts support multiple database backends:
- **Primary:** PostgreSQL with full feature support
- **Development:** SQLite with schema adaptation
- **Testing:** In-memory databases for validation

### External Service Integration
Scripts handle external service dependencies gracefully:
- **Redis:** Falls back to memory implementation
- **Tool Catalog:** Uses local mock implementations
- **External APIs:** Handles service unavailability

---

## Error Handling & Recovery

### Graceful Degradation
Scripts implement comprehensive error handling:
- **Service Unavailability:** Continue with available components
- **Database Issues:** Fall back to SQLite or in-memory storage
- **Network Problems:** Retry with exponential backoff
- **Resource Constraints:** Adjust resource usage dynamically

### Diagnostic Information
Scripts provide detailed diagnostic output:
- **Service Status:** Clear indication of component health
- **Error Details:** Specific error messages with resolution hints
- **Performance Metrics:** Timing and resource usage information
- **Validation Results:** Comprehensive test result reporting

### Recovery Procedures
Scripts include automated recovery mechanisms:
- **Process Restart:** Automatic restart of failed components
- **Database Recovery:** Schema recreation and data migration
- **Service Health:** Automatic health check and recovery
- **Resource Cleanup:** Proper cleanup on shutdown and failure

---

## Best Practices for Script Usage

### Development Environment
- Always activate virtual environment: `source .venv/bin/activate`
- Use `start_local.py` for development without containers
- Run `test_system.py` before code changes
- Validate with `final_validation.py` before commits

### Production Deployment
- Use scripts for deployment validation
- Run observability tests before production deployment
- Implement continuous validation in CI/CD pipelines
- Monitor script execution for system health

### Troubleshooting Guidelines
1. **Start Simple:** Use `test_system.py` for basic validation
2. **Component Specific:** Use targeted validation scripts
3. **Comprehensive:** Run `final_validation.py` for complete testing
4. **Observability:** Always validate monitoring systems

### Performance Optimization
- Scripts include performance benchmarking
- Monitor execution times for performance regression
- Use scripts to validate performance improvements
- Implement load testing with validation scripts

---

## Future Enhancements

### Planned Script Additions
- **Performance Benchmarking:** Dedicated performance testing scripts
- **Security Validation:** Security-focused testing and validation
- **Data Migration:** Database migration and upgrade scripts
- **Backup & Recovery:** System backup and recovery automation

### Integration Improvements
- **CI/CD Templates:** Pre-built pipeline templates using scripts
- **Docker Integration:** Enhanced container deployment scripts
- **Monitoring Integration:** Advanced observability and alerting scripts
- **Documentation Generation:** Automated documentation from script validation

### Operational Enhancements
- **Health Dashboard:** Script-driven system health dashboard
- **Automated Remediation:** Self-healing system capabilities
- **Capacity Planning:** Resource usage analysis and planning scripts
- **Compliance Validation:** Regulatory compliance testing scripts

---

*These operational scripts ensure the Personal Agent Orchestrator maintains high reliability, performance, and operational excellence throughout its lifecycle. They provide comprehensive validation, testing, and maintenance capabilities essential for production deployment and ongoing operations.*