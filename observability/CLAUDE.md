# Observability Stack - Ordinaut

## Purpose & Mission

The observability stack provides comprehensive monitoring, metrics collection, structured logging, and intelligent alerting for the Ordinaut. This system ensures production reliability, performance visibility, and rapid incident response through a complete observability solution integrated with the extension system.

**Core Objectives:**
- **Real-time Monitoring**: Track system health, performance metrics, and business KPIs
- **Extension Integration**: ✅ **OPERATIONAL** - Observability extension provides `/metrics` endpoint
- **Structured Logging**: Centralized, searchable logs with correlation IDs and context
- **Proactive Alerting**: Intelligent alerts with actionable information and escalation
- **Performance Visibility**: Deep insights into system behavior and optimization opportunities

---

## Architecture Overview

```
Production Traffic → [Metrics Collection] → [Prometheus] → [Grafana Dashboards]
                  → [Structured Logging] → [Log Aggregation] → [Search & Analysis]  
                  → [Health Checks] → [Alert Manager] → [Notification Channels]
                  → [Distributed Tracing] → [Jaeger] → [Request Flow Analysis]
```

### Component Relationships
- **metrics.py** → Core metrics collection and instrumentation (also served by observability extension)
- **logging.py** → Structured logging with correlation IDs and context enrichment
- **health.py** → System health checks and dependency monitoring
- **Extension Integration** → ✅ **OPERATIONAL** - `/ext/observability/metrics` endpoint
- **alerts.py** → Alert definitions, routing rules, and notification management

---

## Core Components

### 1. Metrics Collection (metrics.py)

**Purpose**: Collect, aggregate, and expose system metrics for monitoring and alerting.

**Key Features:**
- Prometheus-compatible metrics exposition
- Custom business logic metrics
- Performance counters and histograms
- Resource utilization tracking
- Pipeline execution metrics

**Implementation Pattern:**
```python
from prometheus_client import Counter, Histogram, Gauge, start_http_server
import time
from functools import wraps
from typing import Dict, Any

# Core metrics definitions
TASK_EXECUTIONS = Counter('orchestrator_task_executions_total', 
                         'Total task executions', ['status', 'task_type'])

PIPELINE_DURATION = Histogram('orchestrator_pipeline_duration_seconds',
                             'Pipeline execution time', ['task_id', 'pipeline_type'])

ACTIVE_WORKERS = Gauge('orchestrator_active_workers', 'Number of active workers')

QUEUE_DEPTH = Gauge('orchestrator_queue_depth', 'Number of queued tasks')

DATABASE_CONNECTIONS = Gauge('orchestrator_database_connections_active', 
                            'Active database connections')

# Decorator for automatic instrumentation
def monitor_execution(metric_name: str = None):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                TASK_EXECUTIONS.labels(status='success', 
                                     task_type=metric_name or func.__name__).inc()
                return result
            except Exception as e:
                TASK_EXECUTIONS.labels(status='error', 
                                     task_type=metric_name or func.__name__).inc()
                raise
            finally:
                duration = time.time() - start_time
                PIPELINE_DURATION.labels(task_id=kwargs.get('task_id', 'unknown'),
                                       pipeline_type=metric_name or func.__name__).observe(duration)
        return wrapper
    return decorator
```

**Business Metrics Tracked:**
- Task execution rates (per minute/hour/day)
- Pipeline success/failure ratios
- Schedule accuracy (drift from expected execution time)
- Tool invocation patterns and latencies
- Agent activity levels and resource consumption

### 2. Structured Logging (logging.py)

**Purpose**: Provide comprehensive, searchable, and contextual logging across all system components.

**Key Features:**
- JSON-structured log entries
- Correlation ID propagation
- Request context enrichment
- Log level management
- Integration with log aggregation systems

**Implementation Pattern:**
```python
import logging
import json
import uuid
from datetime import datetime
from contextvars import ContextVar
from typing import Dict, Any, Optional

# Context variables for request tracking
correlation_id: ContextVar[str] = ContextVar('correlation_id', default=None)
task_context: ContextVar[Dict[str, Any]] = ContextVar('task_context', default={})

class StructuredFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add correlation ID if available
        if correlation_id.get():
            log_entry['correlation_id'] = correlation_id.get()
            
        # Add task context if available
        if task_context.get():
            log_entry['task_context'] = task_context.get()
            
        # Add exception information
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
            
        # Add extra fields from record
        if hasattr(record, 'extra'):
            log_entry.update(record.extra)
            
        return json.dumps(log_entry)

# Context manager for request correlation
class RequestContext:
    def __init__(self, task_id: str = None, agent_id: str = None):
        self.correlation_id = str(uuid.uuid4())
        self.context = {
            'task_id': task_id,
            'agent_id': agent_id,
            'request_id': self.correlation_id
        }
    
    def __enter__(self):
        correlation_id.set(self.correlation_id)
        task_context.set(self.context)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        correlation_id.set(None)
        task_context.set({})

# Logger factory with structured output
def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
```

**Log Categories:**
- **System Events**: Service startup, shutdown, configuration changes
- **Request Processing**: API requests, responses, and processing times
- **Task Execution**: Pipeline starts, completions, failures, and step details
- **Integration Events**: External tool calls, MCP interactions, database operations
- **Security Events**: Authentication attempts, authorization failures, rate limiting
- **Error Tracking**: Exception details, stack traces, recovery actions

### 3. Health Monitoring (health.py)

**Purpose**: Continuous monitoring of system health and dependency availability.

**Key Features:**
- Multi-layered health checks
- Dependency monitoring
- Service readiness assessment
- Historical health tracking
- Integration with load balancers and orchestrators

**Implementation Pattern:**
```python
from enum import Enum
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
import asyncio
import aiohttp
import asyncpg

class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"

@dataclass
class HealthCheck:
    name: str
    status: HealthStatus
    message: str
    duration_ms: int
    checked_at: datetime
    details: Optional[Dict] = None

class HealthMonitor:
    def __init__(self):
        self.checks: Dict[str, Callable] = {}
        self.history: Dict[str, List[HealthCheck]] = {}
        
    def register_check(self, name: str, check_func: Callable):
        """Register a health check function"""
        self.checks[name] = check_func
        
    async def run_all_checks(self) -> Dict[str, HealthCheck]:
        """Execute all registered health checks"""
        results = {}
        
        for name, check_func in self.checks.items():
            start_time = datetime.utcnow()
            try:
                result = await asyncio.wait_for(check_func(), timeout=10.0)
                duration = (datetime.utcnow() - start_time).total_seconds() * 1000
                
                health_check = HealthCheck(
                    name=name,
                    status=HealthStatus.HEALTHY,
                    message="Check passed",
                    duration_ms=int(duration),
                    checked_at=start_time,
                    details=result if isinstance(result, dict) else None
                )
            except asyncio.TimeoutError:
                health_check = HealthCheck(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message="Health check timed out",
                    duration_ms=10000,
                    checked_at=start_time
                )
            except Exception as e:
                health_check = HealthCheck(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Health check failed: {str(e)}",
                    duration_ms=int((datetime.utcnow() - start_time).total_seconds() * 1000),
                    checked_at=start_time
                )
                
            results[name] = health_check
            self._record_history(name, health_check)
            
        return results
        
    async def database_check(self) -> Dict:
        """Check database connectivity and performance"""
        try:
            conn = await asyncpg.connect(DATABASE_URL)
            
            # Test basic connectivity
            result = await conn.fetchval("SELECT 1")
            
            # Test scheduler job store
            job_count = await conn.fetchval("SELECT COUNT(*) FROM apscheduler_jobs")
            
            # Test work queue
            queue_depth = await conn.fetchval(
                "SELECT COUNT(*) FROM due_work WHERE run_at <= now()"
            )
            
            await conn.close()
            
            return {
                "connection": "ok",
                "active_jobs": job_count,
                "queue_depth": queue_depth
            }
        except Exception as e:
            raise Exception(f"Database check failed: {e}")
            
    async def redis_check(self) -> Dict:
        """Check Redis connectivity and stream health"""
        import redis.asyncio as redis
        
        client = redis.from_url(REDIS_URL)
        try:
            # Test basic connectivity
            await client.ping()
            
            # Check stream info
            stream_info = await client.xinfo_stream("orchestrator:events")
            
            return {
                "connection": "ok",
                "stream_length": stream_info.get("length", 0),
                "consumer_groups": len(stream_info.get("groups", []))
            }
        finally:
            await client.close()
            
    async def scheduler_check(self) -> Dict:
        """Check APScheduler health and job processing"""
        # Check if scheduler is running
        if not scheduler.running:
            raise Exception("Scheduler is not running")
            
        # Get job statistics
        jobs = scheduler.get_jobs()
        
        return {
            "running": True,
            "total_jobs": len(jobs),
            "next_run": min([job.next_run_time for job in jobs if job.next_run_time], 
                           default=None)
        }

# Initialize health monitor
health_monitor = HealthMonitor()
health_monitor.register_check("database", health_monitor.database_check)
health_monitor.register_check("redis", health_monitor.redis_check)
health_monitor.register_check("scheduler", health_monitor.scheduler_check)
```

**Health Check Categories:**
- **Core Infrastructure**: Database, Redis, message queues
- **Application Services**: API server, scheduler, worker processes  
- **External Dependencies**: MCP servers, external APIs, authentication services
- **Business Logic**: Task processing rates, success ratios, queue depths
- **Resource Utilization**: Memory, CPU, disk space, network connectivity

### 4. Alert Management (alerts.py)

**Purpose**: Intelligent alerting system with escalation, routing, and notification management.

**Key Features:**
- Rule-based alert definitions
- Multi-channel notifications (email, Slack, PagerDuty)
- Alert aggregation and deduplication
- Escalation policies
- Maintenance mode and alert suppression

**Implementation Pattern:**
```python
from enum import Enum
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
import asyncio
import aiohttp

class AlertSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

class AlertStatus(Enum):
    FIRING = "firing"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"

@dataclass
class Alert:
    name: str
    severity: AlertSeverity
    status: AlertStatus
    message: str
    fired_at: datetime
    resolved_at: Optional[datetime] = None
    context: Dict[str, Any] = None
    fingerprint: str = None

class AlertRule:
    def __init__(self, name: str, condition: Callable, severity: AlertSeverity,
                 message_template: str, cooldown_minutes: int = 15):
        self.name = name
        self.condition = condition
        self.severity = severity
        self.message_template = message_template
        self.cooldown_minutes = cooldown_minutes
        self.last_fired: Optional[datetime] = None
        
    def should_fire(self, context: Dict) -> bool:
        """Check if alert should fire given current context"""
        # Check cooldown period
        if (self.last_fired and 
            datetime.utcnow() - self.last_fired < timedelta(minutes=self.cooldown_minutes)):
            return False
            
        # Evaluate condition
        return self.condition(context)
        
    def create_alert(self, context: Dict) -> Alert:
        """Create alert instance from rule and context"""
        message = self.message_template.format(**context)
        fingerprint = f"{self.name}:{hash(str(sorted(context.items())))}"
        
        return Alert(
            name=self.name,
            severity=self.severity,
            status=AlertStatus.FIRING,
            message=message,
            fired_at=datetime.utcnow(),
            context=context,
            fingerprint=fingerprint
        )

class AlertManager:
    def __init__(self):
        self.rules: List[AlertRule] = []
        self.active_alerts: Dict[str, Alert] = {}
        self.notification_channels: Dict[str, Callable] = {}
        self.routing_rules: Dict[AlertSeverity, List[str]] = {
            AlertSeverity.INFO: ['log'],
            AlertSeverity.WARNING: ['log', 'slack'],
            AlertSeverity.CRITICAL: ['log', 'slack', 'pagerduty']
        }
        
    def add_rule(self, rule: AlertRule):
        """Add alert rule to manager"""
        self.rules.append(rule)
        
    def add_notification_channel(self, name: str, handler: Callable):
        """Register notification channel handler"""
        self.notification_channels[name] = handler
        
    async def evaluate_rules(self, context: Dict):
        """Evaluate all rules and fire/resolve alerts"""
        for rule in self.rules:
            try:
                if rule.should_fire(context):
                    alert = rule.create_alert(context)
                    await self._fire_alert(alert)
                    rule.last_fired = datetime.utcnow()
                else:
                    # Check if existing alert should be resolved
                    existing = self.active_alerts.get(rule.name)
                    if existing and existing.status == AlertStatus.FIRING:
                        await self._resolve_alert(existing)
            except Exception as e:
                logger.error(f"Error evaluating alert rule {rule.name}: {e}")
                
    async def _fire_alert(self, alert: Alert):
        """Fire alert and send notifications"""
        self.active_alerts[alert.fingerprint] = alert
        
        # Send notifications based on routing rules
        channels = self.routing_rules.get(alert.severity, ['log'])
        
        for channel_name in channels:
            channel_handler = self.notification_channels.get(channel_name)
            if channel_handler:
                try:
                    await channel_handler(alert)
                except Exception as e:
                    logger.error(f"Failed to send alert via {channel_name}: {e}")
                    
    async def _resolve_alert(self, alert: Alert):
        """Resolve active alert"""
        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.utcnow()
        
        # Send resolution notifications
        for channel_name in self.routing_rules.get(alert.severity, ['log']):
            channel_handler = self.notification_channels.get(channel_name)
            if channel_handler:
                try:
                    await channel_handler(alert)
                except Exception as e:
                    logger.error(f"Failed to send resolution via {channel_name}: {e}")

# Notification channel implementations
async def slack_notification(alert: Alert):
    """Send alert to Slack channel"""
    webhook_url = os.getenv('SLACK_WEBHOOK_URL')
    if not webhook_url:
        return
        
    color = {
        AlertSeverity.INFO: 'good',
        AlertSeverity.WARNING: 'warning', 
        AlertSeverity.CRITICAL: 'danger'
    }[alert.severity]
    
    payload = {
        'attachments': [{
            'color': color,
            'title': f"{alert.severity.value.upper()}: {alert.name}",
            'text': alert.message,
            'fields': [
                {'title': 'Status', 'value': alert.status.value, 'short': True},
                {'title': 'Time', 'value': alert.fired_at.isoformat(), 'short': True}
            ]
        }]
    }
    
    async with aiohttp.ClientSession() as session:
        await session.post(webhook_url, json=payload)

# Common alert rules
def high_queue_depth_rule():
    return AlertRule(
        name="high_queue_depth",
        condition=lambda ctx: ctx.get('queue_depth', 0) > 100,
        severity=AlertSeverity.WARNING,
        message_template="High queue depth detected: {queue_depth} tasks pending",
        cooldown_minutes=10
    )

def database_connectivity_rule():
    return AlertRule(
        name="database_down", 
        condition=lambda ctx: ctx.get('database_status') != 'healthy',
        severity=AlertSeverity.CRITICAL,
        message_template="Database connectivity issue: {database_error}",
        cooldown_minutes=5
    )

def task_failure_rate_rule():
    return AlertRule(
        name="high_task_failure_rate",
        condition=lambda ctx: ctx.get('task_failure_rate', 0) > 0.1,  # 10%
        severity=AlertSeverity.WARNING, 
        message_template="High task failure rate: {task_failure_rate:.2%} over last hour",
        cooldown_minutes=30
    )
```

---

## Integration Points

### Prometheus Integration

**Metrics Exposition:**
```python
# Start Prometheus metrics server
from prometheus_client import start_http_server, generate_latest

# In main application
start_http_server(8000)  # Expose metrics on :8000/metrics

# Custom metrics endpoint for FastAPI
@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type="text/plain")
```

**Prometheus Configuration (prometheus.yml):**
```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'orchestrator'
    static_configs:
      - targets: ['localhost:8080']
    scrape_interval: 10s
    metrics_path: /metrics
    
rule_files:
  - "orchestrator_alerts.yml"

alerting:
  alertmanagers:
    - static_configs:
        - targets: ['localhost:9093']
```

### Grafana Dashboard Configuration

**Key Dashboard Panels:**
- System overview with key metrics
- Task execution rates and success ratios
- Queue depth and processing latencies
- Resource utilization (CPU, memory, connections)
- Error rates and failure analysis
- Schedule accuracy and drift monitoring

**Sample Dashboard JSON:**
```json
{
  "dashboard": {
    "title": "Ordinaut",
    "panels": [
      {
        "title": "Task Execution Rate",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(orchestrator_task_executions_total[5m])",
            "legendFormat": "{{status}} - {{task_type}}"
          }
        ]
      },
      {
        "title": "Queue Depth", 
        "type": "stat",
        "targets": [
          {
            "expr": "orchestrator_queue_depth",
            "legendFormat": "Pending Tasks"
          }
        ]
      }
    ]
  }
}
```

### Log Aggregation Integration

**Fluentd Configuration:**
```xml
<source>
  @type tail
  path /var/log/orchestrator/*.log
  pos_file /var/log/fluentd/orchestrator.log.pos
  tag orchestrator.*
  format json
  time_key timestamp
  time_format %Y-%m-%dT%H:%M:%S.%LZ
</source>

<filter orchestrator.**>
  @type record_transformer
  <record>
    service orchestrator
    environment ${ENV}
  </record>
</filter>

<match orchestrator.**>
  @type elasticsearch
  host elasticsearch.example.com
  port 9200
  index_name orchestrator-logs
</match>
```

**ELK Stack Integration:**
- **Elasticsearch**: Store and index structured logs
- **Logstash**: Process and enrich log entries
- **Kibana**: Search, analyze, and visualize logs

---

## Monitoring Dashboards

### Executive Dashboard
**Key Metrics:**
- System uptime and availability
- Daily/weekly task execution volumes
- Success rates and SLA compliance
- User adoption and engagement metrics

### Operational Dashboard  
**Key Metrics:**
- Real-time queue depth and processing rates
- Worker health and utilization
- Database and Redis performance
- API response times and error rates

### Development Dashboard
**Key Metrics:**
- Code deployment frequency and success rates
- Test coverage and quality metrics
- Feature usage analytics
- Performance regression tracking

---

## Performance Monitoring

### Application Performance Monitoring (APM)

**Key Performance Indicators:**
- **Latency**: API response times, pipeline execution duration
- **Throughput**: Tasks per second, API requests per minute
- **Error Rate**: Failed tasks, API errors, exception rates
- **Saturation**: Queue depth, worker utilization, resource usage

**Distributed Tracing:**
```python
from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

# Initialize tracing
tracer = trace.get_tracer(__name__)

# Instrument FastAPI automatically
FastAPIInstrumentor.instrument_app(app)

# Manual instrumentation for pipeline execution
@tracer.start_as_current_span("execute_pipeline")
async def execute_pipeline(pipeline_data: dict):
    with tracer.start_as_current_span("validate_pipeline") as span:
        span.set_attribute("pipeline.steps", len(pipeline_data.get("pipeline", [])))
        # ... validation logic
        
    for step in pipeline_data["pipeline"]:
        with tracer.start_as_current_span(f"execute_step_{step['id']}") as span:
            span.set_attribute("step.tool", step["uses"])
            # ... step execution
```

### Database Monitoring

**Key Database Metrics:**
- Connection pool utilization
- Query execution times
- Lock contention and blocking queries
- Index usage and performance
- Transaction rates and rollback ratios

**Query Performance Monitoring:**
```python
import asyncpg
import time
from typing import Any

class InstrumentedConnection:
    def __init__(self, connection):
        self._connection = connection
        
    async def execute(self, query: str, *args) -> Any:
        start_time = time.time()
        try:
            result = await self._connection.execute(query, *args)
            duration = time.time() - start_time
            
            # Record query metrics
            DATABASE_QUERY_DURATION.labels(
                operation='execute',
                table=self._extract_table(query)
            ).observe(duration)
            
            return result
        except Exception as e:
            DATABASE_QUERY_ERRORS.labels(
                operation='execute',
                error_type=type(e).__name__
            ).inc()
            raise
            
    def _extract_table(self, query: str) -> str:
        # Simple table extraction from query
        query_upper = query.upper().strip()
        if query_upper.startswith('SELECT'):
            from_idx = query_upper.find('FROM')
            if from_idx != -1:
                table_part = query_upper[from_idx + 4:].split()[0]
                return table_part.strip()
        return 'unknown'
```

---

## Debugging and Troubleshooting

### Log Analysis Queries

**Common Elasticsearch Queries:**
```json
// Find all errors in last hour
{
  "query": {
    "bool": {
      "must": [
        {"term": {"level": "ERROR"}},
        {"range": {"timestamp": {"gte": "now-1h"}}}
      ]
    }
  }
}

// Track request flow by correlation ID
{
  "query": {
    "term": {"correlation_id": "123e4567-e89b-12d3-a456-426614174000"}
  },
  "sort": [{"timestamp": {"order": "asc"}}]
}

// Find slow pipeline executions
{
  "query": {
    "bool": {
      "must": [
        {"exists": {"field": "task_context.task_id"}},
        {"range": {"duration_ms": {"gte": 30000}}}
      ]
    }
  }
}
```

### Performance Debugging Tools

**Profiling Integration:**
```python
import cProfile
import pstats
from functools import wraps

def profile_execution(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        if os.getenv('ENABLE_PROFILING') == 'true':
            profiler = cProfile.Profile()
            profiler.enable()
            
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                profiler.disable()
                stats = pstats.Stats(profiler)
                stats.sort_stats('cumulative')
                stats.dump_stats(f'/tmp/profile_{func.__name__}_{time.time()}.prof')
        else:
            return await func(*args, **kwargs)
    return wrapper
```

**Memory Usage Tracking:**
```python
import psutil
import tracemalloc
from typing import Dict

class MemoryTracker:
    def __init__(self):
        tracemalloc.start()
        self.snapshots: Dict[str, tracemalloc.Snapshot] = {}
        
    def take_snapshot(self, name: str):
        """Take memory snapshot at checkpoint"""
        self.snapshots[name] = tracemalloc.take_snapshot()
        
        # Record current memory usage
        process = psutil.Process()
        memory_info = process.memory_info()
        
        MEMORY_USAGE.labels(
            process='orchestrator',
            type='rss'
        ).set(memory_info.rss / 1024 / 1024)  # MB
        
    def compare_snapshots(self, before: str, after: str) -> List[str]:
        """Compare two memory snapshots"""
        if before not in self.snapshots or after not in self.snapshots:
            return []
            
        snapshot_before = self.snapshots[before]
        snapshot_after = self.snapshots[after]
        
        top_stats = snapshot_after.compare_to(snapshot_before, 'lineno')
        
        return [
            f"{stat.traceback.format()[-1]}: {stat.size_diff / 1024:.1f} KB"
            for stat in top_stats[:10]
            if stat.size_diff > 0
        ]

# Usage in pipeline execution
memory_tracker = MemoryTracker()

async def execute_pipeline_with_tracking(pipeline_data: dict):
    memory_tracker.take_snapshot('pipeline_start')
    
    try:
        result = await execute_pipeline(pipeline_data)
        return result
    finally:
        memory_tracker.take_snapshot('pipeline_end')
        memory_diffs = memory_tracker.compare_snapshots('pipeline_start', 'pipeline_end')
        
        if memory_diffs:
            logger.info("Memory usage changes during pipeline execution",
                       extra={'memory_diffs': memory_diffs})
```

---

## Production Deployment

### Container Health Checks

**Dockerfile Health Check:**
```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1
```

**Kubernetes Liveness/Readiness Probes:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orchestrator
spec:
  template:
    spec:
      containers:
      - name: orchestrator
        image: orchestrator:latest
        livenessProbe:
          httpGet:
            path: /health/live
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
```

### Monitoring Infrastructure

**Docker Compose Monitoring Stack:**
```yaml
version: '3.8'

services:
  orchestrator:
    build: .
    ports:
      - "8080:8080"
    environment:
      - ENABLE_METRICS=true
      - LOG_LEVEL=INFO
    
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      
  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    volumes:
      - ./monitoring/grafana/dashboards:/var/lib/grafana/dashboards
      
  alertmanager:
    image: prom/alertmanager:latest
    ports:
      - "9093:9093"
    volumes:
      - ./monitoring/alertmanager.yml:/etc/alertmanager/alertmanager.yml
```

---

## Security and Compliance

### Audit Logging

**Security Event Tracking:**
```python
SECURITY_EVENTS = Counter('orchestrator_security_events_total',
                         'Security-related events', ['event_type', 'result'])

async def log_security_event(event_type: str, result: str, 
                           context: Dict[str, Any]):
    """Log security event with full context"""
    logger.warning(f"Security event: {event_type}",
                  extra={
                      'event_type': event_type,
                      'result': result,
                      'context': context,
                      'security_event': True
                  })
    
    SECURITY_EVENTS.labels(event_type=event_type, result=result).inc()

# Usage examples
await log_security_event('authentication_failure', 'blocked', {
    'agent_id': 'unknown',
    'ip_address': request.client.host,
    'user_agent': request.headers.get('user-agent')
})

await log_security_event('rate_limit_exceeded', 'throttled', {
    'agent_id': agent_id,
    'endpoint': request.url.path,
    'request_count': current_count
})
```

### Data Privacy

**PII Handling in Logs:**
```python
import re
from typing import Any, Dict

class LogSanitizer:
    SENSITIVE_PATTERNS = {
        'email': re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
        'phone': re.compile(r'\b\d{3}-\d{3}-\d{4}\b'),
        'ssn': re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
        'credit_card': re.compile(r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b')
    }
    
    @classmethod
    def sanitize_data(cls, data: Any) -> Any:
        """Remove or mask sensitive data from log entries"""
        if isinstance(data, str):
            result = data
            for pattern_name, pattern in cls.SENSITIVE_PATTERNS.items():
                result = pattern.sub(f'[REDACTED_{pattern_name.upper()}]', result)
            return result
        elif isinstance(data, dict):
            return {k: cls.sanitize_data(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [cls.sanitize_data(item) for item in data]
        else:
            return data
```

---

## Testing and Validation

### Monitoring System Tests

**Health Check Testing:**
```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_database_health_check():
    """Test database connectivity health check"""
    health_monitor = HealthMonitor()
    
    # Test successful connection
    with patch('asyncpg.connect') as mock_connect:
        mock_conn = AsyncMock()
        mock_conn.fetchval.return_value = 1
        mock_connect.return_value = mock_conn
        
        result = await health_monitor.database_check()
        
        assert result['connection'] == 'ok'
        assert 'active_jobs' in result
        assert 'queue_depth' in result

@pytest.mark.asyncio        
async def test_alert_rule_evaluation():
    """Test alert rule condition evaluation"""
    rule = AlertRule(
        name="test_alert",
        condition=lambda ctx: ctx.get('error_rate', 0) > 0.1,
        severity=AlertSeverity.WARNING,
        message_template="Error rate too high: {error_rate}"
    )
    
    # Should not fire with low error rate
    assert not rule.should_fire({'error_rate': 0.05})
    
    # Should fire with high error rate  
    assert rule.should_fire({'error_rate': 0.15})
    
    # Should respect cooldown period
    rule.last_fired = datetime.utcnow() - timedelta(minutes=5)
    assert not rule.should_fire({'error_rate': 0.15})
```

**Metrics Validation:**
```python
from prometheus_client import CollectorRegistry, generate_latest

def test_metrics_collection():
    """Test that metrics are properly collected and exposed"""
    # Create isolated registry for testing
    registry = CollectorRegistry()
    
    # Register test metrics
    test_counter = Counter('test_counter', 'Test counter', registry=registry)
    test_counter.inc(5)
    
    # Generate metrics output
    output = generate_latest(registry)
    
    # Validate output format
    assert b'test_counter_total 5.0' in output
    assert b'# HELP test_counter Test counter' in output
    assert b'# TYPE test_counter counter' in output
```

---

## Operational Procedures

### Incident Response

**Alert Escalation Matrix:**
```
INFO → Log + Dashboard Update
WARNING → Log + Slack Channel + Email (Business Hours)
CRITICAL → Log + Slack Channel + Email + PagerDuty (24/7)
```

**Runbook Examples:**

**High Queue Depth Response:**
1. Check worker health and scaling
2. Identify stuck or slow tasks
3. Review recent deployments or configuration changes
4. Scale workers if needed
5. Investigate root cause of task delays

**Database Connectivity Loss:**
1. Verify database server status
2. Check connection pool configuration
3. Review recent schema changes
4. Restart application if connection pool corrupted
5. Escalate to database team if server issues

### Maintenance Procedures

**Scheduled Maintenance:**
```python
class MaintenanceMode:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.maintenance_key = "orchestrator:maintenance"
        
    async def enable(self, duration_minutes: int = 60, reason: str = ""):
        """Enable maintenance mode"""
        await self.redis.setex(
            self.maintenance_key, 
            duration_minutes * 60,
            json.dumps({
                'enabled_at': datetime.utcnow().isoformat(),
                'duration_minutes': duration_minutes,
                'reason': reason
            })
        )
        
        logger.warning("Maintenance mode enabled",
                      extra={'duration_minutes': duration_minutes, 'reason': reason})
        
    async def is_enabled(self) -> bool:
        """Check if maintenance mode is active"""
        return await self.redis.exists(self.maintenance_key)
```

### Performance Tuning

**Database Optimization:**
```sql
-- Query performance analysis
SELECT query, mean_exec_time, calls, total_exec_time
FROM pg_stat_statements
WHERE mean_exec_time > 1000  -- Queries taking > 1 second
ORDER BY mean_exec_time DESC
LIMIT 10;

-- Connection monitoring
SELECT count(*), state
FROM pg_stat_activity 
GROUP BY state;

-- Lock monitoring
SELECT blocked_locks.pid AS blocked_pid,
       blocking_locks.pid AS blocking_pid,
       blocked_activity.query AS blocked_query,
       blocking_activity.query AS blocking_query
FROM pg_catalog.pg_locks blocked_locks
JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
JOIN pg_catalog.pg_locks blocking_locks ON blocking_locks.locktype = blocked_locks.locktype
JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
WHERE NOT blocked_locks.granted;
```

---

## Summary

The observability stack provides comprehensive monitoring, alerting, and debugging capabilities for the Ordinaut. Key components work together to ensure:

**Production Reliability:**
- Real-time system health monitoring
- Proactive alerting with intelligent routing
- Comprehensive error tracking and analysis
- Performance monitoring and optimization

**Developer Experience:**
- Structured logging with correlation tracking
- Detailed performance profiling tools
- Comprehensive metrics and dashboards
- Easy debugging and troubleshooting workflows

**Operational Excellence:**
- Automated incident response procedures
- Maintenance mode and operational controls
- Security event tracking and compliance
- Scalable monitoring infrastructure

This observability foundation enables confident production deployment and efficient operation of the Ordinaut system.