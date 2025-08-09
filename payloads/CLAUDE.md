# Personal Agent Orchestrator - Payloads Directory

## Purpose and Role

The `payloads/` directory contains example payload files and pipeline definitions that demonstrate how to structure complex automation workflows within the Personal Agent Orchestrator. These files serve as templates, examples, and starting points for creating sophisticated agent-driven tasks.

## Directory Contents

### Current Payload Files
- **`morning_briefing.json`** - Comprehensive morning briefing pipeline with calendar, weather, and email integration

### Planned Payload Categories
```
payloads/
├── productivity/
│   ├── morning_briefing.json          # Daily morning briefing
│   ├── weekly_review.json             # Weekly productivity summary
│   ├── task_followup.json             # Automatic task follow-ups
│   └── meeting_preparation.json       # Pre-meeting briefings
├── communication/
│   ├── email_digest.json              # Email summarization
│   ├── slack_updates.json             # Team status updates
│   ├── social_media_monitoring.json   # Social media alerts
│   └── customer_support_triage.json   # Support ticket routing
├── monitoring/
│   ├── system_health.json             # Infrastructure monitoring
│   ├── budget_tracking.json           # Financial monitoring
│   ├── project_status.json            # Project milestone tracking
│   └── compliance_reporting.json      # Automated compliance checks
├── integration/
│   ├── crm_sync.json                  # CRM data synchronization
│   ├── backup_verification.json       # Backup status verification
│   ├── security_scan.json             # Security assessment automation
│   └── inventory_management.json      # Asset tracking updates
└── examples/
    ├── simple_notification.json       # Basic notification example
    ├── multi_step_processing.json     # Complex pipeline example
    ├── conditional_logic.json         # Conditional execution example
    └── error_handling.json            # Error recovery patterns
```

## Payload Structure and Schema

### Complete Task Definition
```json
{
  "title": "Human-readable task name",
  "description": "Detailed description of task purpose and behavior",
  "created_by": "agent-uuid-who-created-this-task",
  "schedule_kind": "cron|rrule|once|event",
  "schedule_expr": "schedule-expression-based-on-kind",
  "timezone": "IANA-timezone-name",
  "payload": {
    "params": {
      // Global parameters available to all pipeline steps
    },
    "pipeline": [
      // Array of pipeline step definitions
    ]
  },
  "priority": 1-10,
  "max_retries": 3,
  "backoff_strategy": "linear|exponential|fixed",
  "tags": ["category", "environment", "owner"],
  "metadata": {
    // Additional task metadata
  }
}
```

### Pipeline Step Schema
```json
{
  "id": "unique_step_identifier",
  "uses": "tool.address.from.catalog",
  "with": {
    // Tool input parameters with template variables
  },
  "save_as": "result_variable_name",
  "if": "optional_jmespath_condition",
  "timeout_seconds": 30,
  "retry_count": 2,
  "on_error": "fail|continue|retry",
  "description": "Human-readable step description"
}
```

## Template Variable System

### Variable Types and Scoping
```json
{
  "pipeline": [
    {
      "id": "fetch_data",
      "uses": "api.get",
      "with": {
        // Global parameters
        "url": "${params.api_base_url}/endpoint",
        "headers": {"Authorization": "Bearer ${params.api_token}"},
        
        // Built-in variables
        "timestamp": "${now}",
        "date_iso": "${now_iso}",
        "user_agent": "${agent.name}/${agent.version}"
      },
      "save_as": "api_response"
    },
    {
      "id": "process_data",
      "uses": "data.transform",
      "with": {
        // Reference previous step results
        "input": "${steps.fetch_data.api_response}",
        "filter": "${steps.fetch_data.meta.total_count}",
        
        // Nested property access
        "user_name": "${steps.fetch_data.data.user.name}",
        "item_list": "${steps.fetch_data.data.items[*].id}"
      },
      "save_as": "processed_data"
    }
  ]
}
```

### Built-in Template Variables
| Variable | Description | Example Value |
|----------|-------------|---------------|
| `${now}` | Current timestamp | `2025-08-08T10:30:00Z` |
| `${now_iso}` | ISO 8601 timestamp | `2025-08-08T10:30:00.000Z` |
| `${now+1h}` | Time offset calculations | `2025-08-08T11:30:00Z` |
| `${now-24h}` | Backwards time offset | `2025-08-07T10:30:00Z` |
| `${agent.id}` | Executing agent ID | `uuid-string` |
| `${agent.name}` | Agent display name | `"ProductivityBot"` |
| `${run.id}` | Current execution run ID | `uuid-string` |
| `${task.id}` | Parent task ID | `uuid-string` |
| `${params.key}` | Global parameters | User-defined values |
| `${steps.step_id.property}` | Step result data | Previous step outputs |

## Example Payload Patterns

### Morning Briefing Pipeline
The `morning_briefing.json` demonstrates a comprehensive multi-service integration:

```json
{
  "title": "Weekday Morning Briefing",
  "schedule_kind": "rrule",
  "schedule_expr": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=30;BYSECOND=0",
  "timezone": "Europe/Chisinau",
  "payload": {
    "params": {
      "date_start_iso": "2025-08-08T00:00:00+03:00",
      "date_end_iso": "2025-08-08T23:59:59+03:00"
    },
    "pipeline": [
      {
        "id": "calendar",
        "uses": "google-calendar-mcp.list_events",
        "with": {
          "start": "${params.date_start_iso}",
          "end": "${params.date_end_iso}"
        },
        "save_as": "events"
      },
      {
        "id": "weather",
        "uses": "weather-mcp.forecast",
        "with": {"city": "Chisinau"},
        "save_as": "weather"
      },
      {
        "id": "emails",
        "uses": "imap-mcp.top_unread",
        "with": {"count": 5},
        "save_as": "inbox"
      },
      {
        "id": "brief",
        "uses": "llm.plan",
        "with": {
          "instruction": "Create morning briefing with today's schedule, weather, and important emails",
          "calendar": "${steps.events}",
          "weather": "${steps.weather}",
          "emails": "${steps.inbox}"
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

### Conditional Logic Pattern
```json
{
  "title": "Smart Notification with Conditions",
  "payload": {
    "pipeline": [
      {
        "id": "check_status",
        "uses": "system.health_check",
        "save_as": "health"
      },
      {
        "id": "urgent_alert",
        "uses": "telegram.send_message",
        "with": {
          "chat_id": 12345,
          "text": "🚨 URGENT: System health critical!"
        },
        "if": "steps.health.status == 'critical'"
      },
      {
        "id": "normal_update",
        "uses": "slack.post_message",
        "with": {
          "channel": "#monitoring",
          "message": "✅ System status: ${steps.health.status}"
        },
        "if": "steps.health.status != 'critical'"
      }
    ]
  }
}
```

### Error Handling Pattern
```json
{
  "title": "Robust Pipeline with Error Recovery",
  "payload": {
    "pipeline": [
      {
        "id": "primary_service",
        "uses": "service.fetch_data",
        "with": {"endpoint": "/api/primary"},
        "save_as": "data",
        "on_error": "continue",
        "retry_count": 2
      },
      {
        "id": "fallback_service",
        "uses": "service.fetch_data",
        "with": {"endpoint": "/api/backup"},
        "save_as": "data",
        "if": "!steps.primary_service || steps.primary_service.error",
        "description": "Fallback if primary service fails"
      },
      {
        "id": "error_notification",
        "uses": "telegram.send_message",
        "with": {
          "chat_id": 12345,
          "text": "⚠️ Primary service failed, using backup data"
        },
        "if": "steps.primary_service.error && steps.fallback_service.success"
      }
    ]
  }
}
```

## Scheduling Patterns and Examples

### Cron-based Scheduling
```json
{
  "schedule_kind": "cron",
  "schedule_expr": "0 9 * * 1-5",  // 9 AM weekdays
  "timezone": "America/New_York"
}
```

### RRULE-based Scheduling
```json
{
  "schedule_kind": "rrule", 
  "schedule_expr": "FREQ=WEEKLY;BYDAY=MO;BYHOUR=10;BYMINUTE=0",  // Monday 10 AM
  "timezone": "Europe/London"
}
```

### One-time Scheduling
```json
{
  "schedule_kind": "once",
  "schedule_expr": "2025-08-15T14:30:00",  // Specific datetime
  "timezone": "UTC"
}
```

### Event-driven Scheduling
```json
{
  "schedule_kind": "event",
  "schedule_expr": "webhook.received",  // Triggered by external events
  "payload": {
    "params": {
      "webhook_data": "${trigger.payload}"
    }
  }
}
```

## Payload Development Workflow

### Creating New Payloads

#### 1. Start with Template
```bash
# Copy base template
cp payloads/examples/simple_notification.json payloads/custom/my_workflow.json

# Edit with your specific requirements
```

#### 2. Define Global Parameters
```json
{
  "payload": {
    "params": {
      "api_key": "your-api-key",
      "notification_channel": "#alerts",
      "timezone": "America/Chicago",
      "owner_email": "admin@company.com"
    }
  }
}
```

#### 3. Build Pipeline Steps
```json
{
  "pipeline": [
    {
      "id": "step1",
      "uses": "tool.address",
      "with": {"param": "${params.api_key}"},
      "save_as": "result1"
    },
    {
      "id": "step2", 
      "uses": "tool.process",
      "with": {"input": "${steps.step1.output}"},
      "save_as": "result2"
    }
  ]
}
```

#### 4. Test and Validate
```bash
# Validate payload syntax
python scripts/validate_payload.py payloads/custom/my_workflow.json

# Test pipeline execution
python scripts/test_pipeline.py payloads/custom/my_workflow.json
```

### Payload Testing Framework
```python
# Example testing script
import json
from engine.executor import PipelineExecutor
from engine.template import TemplateRenderer

def test_payload(payload_path: str):
    """Test payload execution in dry-run mode"""
    with open(payload_path) as f:
        payload = json.load(f)
    
    executor = PipelineExecutor(dry_run=True)
    renderer = TemplateRenderer()
    
    # Validate template variables
    rendered_payload = renderer.render_payload(payload)
    
    # Simulate execution
    result = executor.execute_pipeline(rendered_payload["payload"]["pipeline"])
    
    print(f"Payload validation: {'PASSED' if result.success else 'FAILED'}")
    if result.errors:
        for error in result.errors:
            print(f"Error: {error}")
```

## Advanced Payload Patterns

### Multi-Environment Payloads
```json
{
  "title": "Environment-Aware Deployment Check",
  "payload": {
    "params": {
      "environment": "${env.DEPLOYMENT_ENV}",
      "prod_endpoints": ["api1.prod.com", "api2.prod.com"],
      "staging_endpoints": ["api1.staging.com", "api2.staging.com"]
    },
    "pipeline": [
      {
        "id": "select_endpoints",
        "uses": "data.select",
        "with": {
          "condition": "${params.environment}",
          "prod": "${params.prod_endpoints}",
          "staging": "${params.staging_endpoints}"
        },
        "save_as": "endpoints"
      }
    ]
  }
}
```

### Parallel Execution Pattern
```json
{
  "title": "Parallel Data Collection",
  "payload": {
    "pipeline": [
      {
        "id": "fetch_weather",
        "uses": "weather.forecast",
        "with": {"location": "New York"},
        "save_as": "weather",
        "parallel_group": "data_collection"
      },
      {
        "id": "fetch_news",
        "uses": "news.headlines", 
        "with": {"category": "business"},
        "save_as": "news",
        "parallel_group": "data_collection"
      },
      {
        "id": "fetch_stocks",
        "uses": "finance.quotes",
        "with": {"symbols": ["AAPL", "GOOGL"]},
        "save_as": "stocks",
        "parallel_group": "data_collection"
      },
      {
        "id": "combine_data",
        "uses": "llm.synthesize",
        "with": {
          "weather": "${steps.fetch_weather.weather}",
          "news": "${steps.fetch_news.articles}",
          "stocks": "${steps.fetch_stocks.quotes}"
        },
        "depends_on": ["fetch_weather", "fetch_news", "fetch_stocks"]
      }
    ]
  }
}
```

### Data Pipeline Pattern
```json
{
  "title": "ETL Data Pipeline",
  "payload": {
    "pipeline": [
      {
        "id": "extract",
        "uses": "database.query",
        "with": {
          "sql": "SELECT * FROM orders WHERE created_at >= ${now-24h}",
          "connection": "warehouse"
        },
        "save_as": "raw_data"
      },
      {
        "id": "transform", 
        "uses": "data.transform",
        "with": {
          "input": "${steps.extract.rows}",
          "operations": [
            {"type": "filter", "condition": "amount > 0"},
            {"type": "aggregate", "group_by": "customer_id", "sum": "amount"}
          ]
        },
        "save_as": "transformed_data"
      },
      {
        "id": "load",
        "uses": "database.bulk_insert",
        "with": {
          "table": "daily_customer_totals",
          "data": "${steps.transform.result}",
          "connection": "analytics"
        }
      },
      {
        "id": "notify_completion",
        "uses": "slack.post_message",
        "with": {
          "channel": "#data-team",
          "message": "Daily ETL completed: ${steps.transform.result.length} customers processed"
        }
      }
    ]
  }
}
```

## Best Practices and Guidelines

### Payload Design Principles
- **Single Responsibility**: Each payload should have one clear purpose
- **Idempotent Operations**: Design pipelines to be safely re-runnable
- **Error Resilience**: Include fallbacks and error handling
- **Resource Efficiency**: Minimize API calls and processing time
- **Maintainable Structure**: Use clear naming and documentation

### Template Variable Guidelines
- **Descriptive Names**: Use clear, semantic variable names
- **Minimal Scope**: Only pass necessary data between steps
- **Type Safety**: Ensure template variables match expected types
- **Default Values**: Provide defaults for optional parameters

### Security Considerations
- **Sensitive Data**: Never include credentials in payload files
- **Parameter Validation**: Validate all external inputs
- **Access Control**: Use appropriate scopes for tool access
- **Audit Logging**: Include tracking for sensitive operations

## Troubleshooting and Debugging

### Common Issues
- **Template Resolution Errors**: Check variable names and step dependencies
- **Tool Not Found**: Verify tool addresses exist in catalog
- **Schema Validation**: Ensure tool inputs match expected schemas
- **Timeout Errors**: Adjust timeout values for slow operations

### Debugging Tools
```bash
# Validate payload structure
python scripts/validate_payload.py payloads/my_pipeline.json

# Test template rendering
python scripts/render_templates.py payloads/my_pipeline.json --dry-run

# Simulate pipeline execution
python scripts/simulate_pipeline.py payloads/my_pipeline.json --verbose
```

### Payload Linting
```python
def lint_payload(payload_path: str):
    """Check payload for common issues"""
    with open(payload_path) as f:
        payload = json.load(f)
    
    issues = []
    
    # Check for circular dependencies
    step_deps = build_dependency_graph(payload["payload"]["pipeline"])
    if has_cycles(step_deps):
        issues.append("Circular dependency detected in pipeline steps")
    
    # Check for unreferenced steps
    referenced_steps = find_referenced_steps(payload)
    all_steps = {step["id"] for step in payload["payload"]["pipeline"]}
    unreferenced = all_steps - referenced_steps
    if unreferenced:
        issues.append(f"Unreferenced steps: {unreferenced}")
    
    return issues
```

## Future Enhancements

### Planned Features
- **Visual Pipeline Editor**: Drag-and-drop pipeline creation
- **Pipeline Templates**: Library of pre-built workflow templates
- **Dynamic Parameters**: Runtime parameter injection
- **Pipeline Composition**: Combine multiple payloads into workflows

### Advanced Capabilities
- **Machine Learning Integration**: ML model inference in pipelines
- **Real-time Streaming**: Support for continuous data processing
- **Multi-Agent Coordination**: Cross-agent workflow orchestration
- **Workflow Optimization**: Automatic pipeline performance optimization

---

*The payloads directory provides the blueprint for sophisticated automation workflows, enabling agents to coordinate complex multi-service operations with reliability, flexibility, and maintainability.*