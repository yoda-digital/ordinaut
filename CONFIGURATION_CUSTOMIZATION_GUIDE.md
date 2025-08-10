# Configuration & Customization Guide for Ordinaut
## Comprehensive System Configuration for Moldovan Software Company CTOs

*Transform your business operations with intelligent AI agent orchestration*

---

## Table of Contents

1. [Quick Start Configuration Wizard](#quick-start-configuration-wizard)
2. [Task Creation & Management](#task-creation--management)
3. [Advanced Scheduling Patterns](#advanced-scheduling-patterns)  
4. [Pipeline Template System](#pipeline-template-system)
5. [Security & Access Control](#security--access-control)
6. [Customization Framework](#customization-framework)
7. [Moldova Business Context](#moldova-business-context)
8. [Configuration Templates](#configuration-templates)
9. [Performance Tuning](#performance-tuning)
10. [Troubleshooting & Support](#troubleshooting--support)

---

## Quick Start Configuration Wizard

### Environment Setup for Moldova Operations

```bash
# Production environment configuration
export DATABASE_URL="postgresql://user:pass@localhost:5432/ordinaut"
export REDIS_URL="redis://localhost:6379/0"
export TZ="Europe/Chisinau"  # Moldova timezone
export JWT_SECRET_KEY="$(openssl rand -hex 32)"

# Business hours configuration
export BUSINESS_HOURS_START="09:00"
export BUSINESS_HOURS_END="18:00"
export BUSINESS_TIMEZONE="Europe/Chisinau"

# Notification channels
export TELEGRAM_BOT_TOKEN="your-bot-token"
export SLACK_WEBHOOK_URL="your-slack-webhook"
export EMAIL_SMTP_HOST="mail.company.md"
```

### Initial System Configuration

```bash
# 1. Start the system
cd ops/
docker-compose up -d

# 2. Create system admin agent
curl -X POST http://localhost:8080/agents/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer system-admin-token" \
  -d '{
    "name": "system-admin",
    "scopes": ["admin", "task.create", "task.manage", "agent.manage"]
  }'

# 3. Verify system health
curl http://localhost:8080/health
```

---

## Task Creation & Management

### REST API Usage Patterns

#### 1. Basic Task Creation

```bash
# Create a simple daily reminder task
curl -X POST http://localhost:8080/tasks/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-agent-token" \
  -d '{
    "title": "Daily Standup Reminder",
    "description": "Remind team about daily standup meeting",
    "schedule_kind": "cron",
    "schedule_expr": "55 8 * * 1-5",
    "timezone": "Europe/Chisinau",
    "payload": {
      "pipeline": [
        {
          "id": "send_reminder",
          "uses": "telegram-mcp.send_message",
          "with": {
            "chat_id": "${params.team_chat_id}",
            "text": "🕘 Daily standup starts in 5 minutes! Join the meeting room."
          }
        }
      ],
      "params": {
        "team_chat_id": 123456789
      }
    },
    "priority": 3,
    "created_by": "550e8400-e29b-41d4-a716-446655440000"
  }'
```

#### 2. Complex Multi-Step Pipeline

```bash
# Create comprehensive morning briefing for executives
curl -X POST http://localhost:8080/tasks/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-agent-token" \
  -d '{
    "title": "Executive Morning Briefing",
    "description": "Comprehensive morning report with KPIs, calendar, and priorities",
    "schedule_kind": "rrule",
    "schedule_expr": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=7;BYMINUTE=30",
    "timezone": "Europe/Chisinau",
    "payload": {
      "pipeline": [
        {
          "id": "fetch_kpis",
          "uses": "analytics-api.daily_metrics",
          "with": {
            "date": "${now | date(\"%Y-%m-%d\")}",
            "metrics": ["revenue", "active_users", "support_tickets"]
          },
          "save_as": "kpis"
        },
        {
          "id": "get_calendar",
          "uses": "google-calendar-mcp.list_events",
          "with": {
            "start": "${now}",
            "end": "${now + 86400}",
            "calendar_id": "${params.executive_calendar}"
          },
          "save_as": "calendar"
        },
        {
          "id": "check_critical_alerts",
          "uses": "monitoring.get_alerts",
          "with": {
            "severity": "critical",
            "since": "${now - 86400}"
          },
          "save_as": "alerts"
        },
        {
          "id": "generate_summary",
          "uses": "llm.executive_summary",
          "with": {
            "instruction": "Create executive briefing in Romanian and English",
            "kpis": "${steps.kpis.data}",
            "calendar": "${steps.calendar.items}",
            "alerts": "${steps.alerts.items}",
            "format": "structured_report"
          },
          "save_as": "briefing"
        },
        {
          "id": "send_briefing",
          "uses": "email.send_html",
          "with": {
            "to": "${params.executive_email}",
            "subject": "📊 Briefing Executiv ${now | date(\"%d.%m.%Y\")}",
            "html_body": "${steps.briefing.html}",
            "priority": "high"
          }
        }
      ],
      "params": {
        "executive_calendar": "ceo@company.md",
        "executive_email": "ceo@company.md"
      }
    },
    "priority": 1,
    "max_retries": 2,
    "created_by": "550e8400-e29b-41d4-a716-446655440000"
  }'
```

#### 3. Task Management Operations

```bash
# List all active tasks
curl "http://localhost:8080/tasks/?status=active&limit=20" \
  -H "Authorization: Bearer your-agent-token"

# Get specific task details
curl "http://localhost:8080/tasks/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer your-agent-token"

# Update task schedule
curl -X PUT "http://localhost:8080/tasks/550e8400-e29b-41d4-a716-446655440000" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-agent-token" \
  -d '{
    "schedule_expr": "0 9 * * 1-5",
    "priority": 2
  }'

# Pause task temporarily
curl -X POST "http://localhost:8080/tasks/550e8400-e29b-41d4-a716-446655440000/pause" \
  -H "Authorization: Bearer your-agent-token"

# Resume paused task
curl -X POST "http://localhost:8080/tasks/550e8400-e29b-41d4-a716-446655440000/resume" \
  -H "Authorization: Bearer your-agent-token"

# Trigger immediate execution
curl -X POST "http://localhost:8080/tasks/550e8400-e29b-41d4-a716-446655440000/run_now" \
  -H "Authorization: Bearer your-agent-token"

# Snooze task for 2 hours
curl -X POST "http://localhost:8080/tasks/550e8400-e29b-41d4-a716-446655440000/snooze" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-agent-token" \
  -d '{
    "delay_seconds": 7200,
    "reason": "Emergency meeting scheduled"
  }'
```

### Pipeline Templates Library

#### Customer Onboarding Workflow
```json
{
  "title": "Customer Onboarding Process",
  "description": "Automated workflow for new customer setup",
  "schedule_kind": "event",
  "schedule_expr": "customer.registered",
  "payload": {
    "pipeline": [
      {
        "id": "create_accounts",
        "uses": "crm.create_customer",
        "with": {
          "customer_data": "${event.payload.customer}",
          "plan": "${event.payload.plan}"
        },
        "save_as": "customer"
      },
      {
        "id": "setup_billing",
        "uses": "billing.setup_subscription",
        "with": {
          "customer_id": "${steps.customer.id}",
          "plan_id": "${event.payload.plan}",
          "billing_email": "${event.payload.customer.email}"
        },
        "save_as": "subscription"
      },
      {
        "id": "send_welcome_email",
        "uses": "email.send_template",
        "with": {
          "to": "${event.payload.customer.email}",
          "template": "welcome_series",
          "language": "${event.payload.customer.language || 'ro'}",
          "variables": {
            "customer_name": "${steps.customer.name}",
            "login_url": "${steps.customer.login_url}",
            "support_email": "support@company.md"
          }
        }
      },
      {
        "id": "notify_sales",
        "uses": "slack.post_message",
        "with": {
          "channel": "#sales",
          "text": "🎉 New customer: ${steps.customer.name} (${steps.customer.plan})"
        }
      },
      {
        "id": "schedule_followup",
        "uses": "orchestrator.create_task",
        "with": {
          "title": "Customer Follow-up: ${steps.customer.name}",
          "schedule_kind": "once",
          "schedule_expr": "${now + 3 * 24 * 3600 | iso}",
          "payload": {
            "pipeline": [
              {
                "id": "check_activation",
                "uses": "crm.get_customer_status",
                "with": {"customer_id": "${steps.customer.id}"}
              }
            ]
          }
        }
      }
    ]
  }
}
```

#### Incident Response Automation
```json
{
  "title": "Critical Alert Response",
  "description": "Automated incident response for critical system alerts",
  "schedule_kind": "event", 
  "schedule_expr": "monitoring.alert.critical",
  "payload": {
    "pipeline": [
      {
        "id": "assess_severity",
        "uses": "monitoring.analyze_impact",
        "with": {
          "alert": "${event.payload.alert}",
          "context_window": "30m"
        },
        "save_as": "assessment"
      },
      {
        "id": "create_incident",
        "uses": "pagerduty.create_incident",
        "with": {
          "title": "${event.payload.alert.title}",
          "description": "${steps.assessment.summary}",
          "urgency": "${steps.assessment.urgency}",
          "service": "${event.payload.alert.service}"
        },
        "save_as": "incident",
        "if": "${steps.assessment.requires_incident == true}"
      },
      {
        "id": "notify_oncall",
        "uses": "telegram-mcp.send_message",
        "with": {
          "chat_id": "${params.oncall_chat}",
          "text": "🚨 INCIDENT: ${steps.incident.title}\\n\\nSeverity: ${steps.assessment.severity}\\nLink: ${steps.incident.web_url}"
        },
        "if": "${steps.incident != null}"
      },
      {
        "id": "start_war_room",
        "uses": "slack.create_channel",
        "with": {
          "name": "incident-${steps.incident.number}",
          "topic": "${steps.incident.title}",
          "invite_users": "${params.incident_response_team}"
        },
        "if": "${steps.assessment.severity == 'critical'}"
      },
      {
        "id": "auto_remediation",
        "uses": "infrastructure.auto_heal",
        "with": {
          "alert": "${event.payload.alert}",
          "safe_mode": true
        },
        "if": "${steps.assessment.auto_fixable == true}",
        "timeout_seconds": 120
      }
    ],
    "params": {
      "oncall_chat": -123456789,
      "incident_response_team": ["user1", "user2", "user3"]
    }
  }
}
```

---

## Advanced Scheduling Patterns

### RRULE Examples for Business Operations

#### 1. Complex Business Schedules

```python
# Monthly board meetings - first Monday of each month at 14:00
"FREQ=MONTHLY;BYDAY=1MO;BYHOUR=14;BYMINUTE=0"

# Quarterly business reviews - last Friday of March, June, September, December
"FREQ=YEARLY;BYMONTH=3,6,9,12;BYDAY=-1FR;BYHOUR=10;BYMINUTE=0"

# Bi-weekly sprint planning - every other Wednesday at 10:00
"FREQ=WEEKLY;INTERVAL=2;BYDAY=WE;BYHOUR=10;BYMINUTE=0"

# End-of-month financial reports - last working day of month
"FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1;BYHOUR=17;BYMINUTE=0"

# Holiday-aware notifications (skips specified dates)
"FREQ=DAILY;BYHOUR=9;BYMINUTE=0;UNTIL=20241231T235959Z"
```

#### 2. Timezone Handling for Distributed Teams

```bash
# Create task with explicit timezone handling
curl -X POST http://localhost:8080/tasks/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-agent-token" \
  -d '{
    "title": "Multi-Timezone Team Sync",
    "description": "Daily standup accommodating US, Moldova, and Singapore offices",
    "schedule_kind": "rrule",
    "schedule_expr": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=13;BYMINUTE=0",
    "timezone": "Europe/Chisinau",
    "payload": {
      "pipeline": [
        {
          "id": "calculate_timezones",
          "uses": "timezone.convert_time",
          "with": {
            "base_time": "${now}",
            "timezones": ["Europe/Chisinau", "America/New_York", "Asia/Singapore"]
          },
          "save_as": "meeting_times"
        },
        {
          "id": "send_invites",
          "uses": "calendar.send_invite",
          "with": {
            "title": "Daily Team Sync",
            "attendees": "${params.global_team}",
            "start_times": "${steps.meeting_times.converted}"
          }
        }
      ]
    }
  }'
```

#### 3. Holiday Calendar Integration

```json
{
  "title": "Moldova Holiday-Aware Notifications",
  "description": "Skip notifications on Moldovan national holidays",
  "schedule_kind": "rrule",
  "schedule_expr": "FREQ=DAILY;BYHOUR=9;BYMINUTE=0",
  "timezone": "Europe/Chisinau",
  "payload": {
    "pipeline": [
      {
        "id": "check_holiday",
        "uses": "calendar.is_holiday",
        "with": {
          "date": "${now | date('%Y-%m-%d')}",
          "country": "MD",
          "include_custom": true
        },
        "save_as": "holiday_check"
      },
      {
        "id": "send_notification",
        "uses": "telegram-mcp.send_message",
        "with": {
          "chat_id": "${params.team_chat}",
          "text": "Good morning team! Here's your daily update."
        },
        "if": "${steps.holiday_check.is_holiday == false}"
      },
      {
        "id": "send_holiday_greeting",
        "uses": "telegram-mcp.send_message", 
        "with": {
          "chat_id": "${params.team_chat}",
          "text": "🎉 Happy ${steps.holiday_check.holiday_name}! Enjoy your day off."
        },
        "if": "${steps.holiday_check.is_holiday == true}"
      }
    ],
    "params": {
      "team_chat": 123456789
    }
  }
}
```

### Business Calendar Patterns

```python
# Common Moldova business patterns
BUSINESS_PATTERNS = {
    "workdays_9am": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=9;BYMINUTE=0",
    "end_of_workday": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=18;BYMINUTE=0", 
    "lunch_reminder": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=12;BYMINUTE=30",
    "weekly_reports": "FREQ=WEEKLY;BYDAY=FR;BYHOUR=17;BYMINUTE=0",
    "monthly_closing": "FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1;BYHOUR=16;BYMINUTE=0",
    "quarterly_review": "FREQ=MONTHLY;INTERVAL=3;BYMONTHDAY=1;BYHOUR=10;BYMINUTE=0"
}
```

---

## Pipeline Template System

### Variable Resolution with ${steps.x.y} Syntax

#### 1. Basic Variable Usage

```json
{
  "pipeline": [
    {
      "id": "fetch_data",
      "uses": "api.get_user",
      "with": {
        "user_id": "${params.user_id}"
      },
      "save_as": "user"
    },
    {
      "id": "send_welcome",
      "uses": "email.send",
      "with": {
        "to": "${steps.user.email}",
        "subject": "Welcome ${steps.user.name}!",
        "body": "Hello ${steps.user.name}, your account ID is ${steps.user.id}"
      }
    }
  ],
  "params": {
    "user_id": 12345
  }
}
```

#### 2. Advanced JMESPath Expressions

```json
{
  "pipeline": [
    {
      "id": "get_orders",
      "uses": "ecommerce.get_orders",
      "with": {
        "status": "pending",
        "limit": 100
      },
      "save_as": "orders"
    },
    {
      "id": "process_high_value",
      "uses": "payment.process_batch",
      "with": {
        "orders": "${steps.orders.items[?amount > `1000`]}",
        "priority": "high"
      },
      "save_as": "processed_orders"
    },
    {
      "id": "notify_finance",
      "uses": "slack.post_message",
      "with": {
        "channel": "#finance",
        "text": "Processed ${length(steps.processed_orders.successful)} high-value orders totaling $${sum(steps.processed_orders.successful[].amount)}"
      }
    }
  ]
}
```

#### 3. Conditional Logic Patterns

```json
{
  "pipeline": [
    {
      "id": "check_business_hours",
      "uses": "time.is_business_hours",
      "with": {
        "timezone": "Europe/Chisinau",
        "start_hour": 9,
        "end_hour": 18,
        "workdays": [1, 2, 3, 4, 5]
      },
      "save_as": "business_hours"
    },
    {
      "id": "immediate_response",
      "uses": "support.auto_respond",
      "with": {
        "ticket_id": "${event.payload.ticket_id}",
        "response": "We'll respond within 4 hours during business hours."
      },
      "if": "${steps.business_hours.is_business_hours == true}"
    },
    {
      "id": "after_hours_response", 
      "uses": "support.auto_respond",
      "with": {
        "ticket_id": "${event.payload.ticket_id}",
        "response": "Thank you for contacting us. We'll respond first thing tomorrow."
      },
      "if": "${steps.business_hours.is_business_hours == false}"
    },
    {
      "id": "escalate_urgent",
      "uses": "pagerduty.create_incident",
      "with": {
        "title": "Urgent after-hours ticket: ${event.payload.subject}",
        "priority": "high"
      },
      "if": "${steps.business_hours.is_business_hours == false && event.payload.priority == 'urgent'}"
    }
  ]
}
```

### Error Handling and Retry Strategies

```json
{
  "pipeline": [
    {
      "id": "api_call_with_retry",
      "uses": "external-api.get_data",
      "with": {
        "endpoint": "https://api.partner.com/data",
        "api_key": "${params.partner_api_key}"
      },
      "save_as": "api_data",
      "timeout_seconds": 30,
      "retry_count": 3,
      "retry_delay": [1, 2, 4],
      "on_error": {
        "strategy": "continue",
        "fallback_value": {"data": [], "status": "fallback_used"}
      }
    },
    {
      "id": "process_data",
      "uses": "data.transform",
      "with": {
        "input": "${steps.api_data.data || []}",
        "format": "normalized"
      },
      "save_as": "processed",
      "if": "${length(steps.api_data.data) > 0}"
    },
    {
      "id": "error_notification",
      "uses": "alert.send",
      "with": {
        "severity": "warning",
        "message": "Partner API unavailable, using cached data",
        "details": "${steps.api_data}"
      },
      "if": "${steps.api_data.status == 'fallback_used'}"
    }
  ]
}
```

---

## Security & Access Control

### Agent Management and Scopes

#### 1. Creating Role-Based Agents

```bash
# Finance team agent with limited scopes
curl -X POST http://localhost:8080/agents/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer admin-token" \
  -d '{
    "name": "finance-agent",
    "scopes": [
      "analytics.read",
      "billing.read", 
      "reporting.generate",
      "email.send",
      "slack.post"
    ]
  }'

# DevOps agent with infrastructure access
curl -X POST http://localhost:8080/agents/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer admin-token" \
  -d '{
    "name": "devops-agent",
    "scopes": [
      "monitoring.read",
      "monitoring.write",
      "infrastructure.manage",
      "alerts.manage",
      "pagerduty.incident"
    ]
  }'

# Executive assistant with broad read access
curl -X POST http://localhost:8080/agents/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer admin-token" \
  -d '{
    "name": "executive-assistant",
    "scopes": [
      "calendar.read",
      "analytics.read",
      "crm.read",
      "email.send",
      "reports.generate"
    ]
  }'
```

#### 2. Agent Authentication Setup

```bash
# Create agent credentials
curl -X POST "http://localhost:8080/agents/550e8400-e29b-41d4-a716-446655440000/credentials" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer admin-token" \
  -d '{"password": "secure-agent-password"}'

# Authenticate and get JWT tokens
curl -X POST http://localhost:8080/agents/auth/token \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "550e8400-e29b-41d4-a716-446655440000",
    "agent_secret": "secure-agent-password"
  }'

# Response includes access and refresh tokens
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

### Audit Logging and Compliance

#### 1. Audit Trail Configuration

```python
# All operations are automatically logged to audit_log table
# Query audit logs for compliance
SELECT 
    al.created_at,
    a.name as actor_name,
    al.action,
    al.subject_id,
    al.details
FROM audit_log al
JOIN agent a ON al.actor_agent_id = a.id
WHERE al.created_at >= '2024-01-01'
  AND al.action LIKE 'task.%'
ORDER BY al.created_at DESC;

# Export audit logs for compliance reporting
curl "http://localhost:8080/admin/audit-logs?start_date=2024-01-01&end_date=2024-01-31" \
  -H "Authorization: Bearer admin-token" \
  -H "Accept: text/csv"
```

#### 2. Role-Based Access Control

```json
{
  "role_definitions": {
    "finance_manager": {
      "scopes": ["analytics.read", "billing.read", "reports.generate"],
      "can_create_tasks": true,
      "can_manage_agents": false
    },
    "devops_engineer": {
      "scopes": ["monitoring.*", "infrastructure.*", "alerts.*"],
      "can_create_tasks": true,
      "can_manage_agents": false
    },
    "system_admin": {
      "scopes": ["*"],
      "can_create_tasks": true,
      "can_manage_agents": true
    }
  }
}
```

---

## Customization Framework

### Custom Tool Integration

#### 1. Creating Custom Tool Catalog

```json
{
  "tools": [
    {
      "address": "company-erp.get_sales_data",
      "transport": "http",
      "endpoint": "http://erp.company.md/api/sales",
      "input_schema": {
        "type": "object",
        "required": ["start_date", "end_date"],
        "properties": {
          "start_date": {"type": "string", "format": "date"},
          "end_date": {"type": "string", "format": "date"},
          "department": {"type": "string", "enum": ["sales", "marketing", "all"]}
        }
      },
      "output_schema": {
        "type": "object",
        "required": ["total_revenue", "orders_count"],
        "properties": {
          "total_revenue": {"type": "number"},
          "orders_count": {"type": "integer"},
          "breakdown": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "product": {"type": "string"},
                "revenue": {"type": "number"},
                "quantity": {"type": "integer"}
              }
            }
          }
        }
      },
      "timeout_seconds": 30,
      "scopes": ["erp.sales.read"],
      "cost_tier": "medium",
      "description": "Fetch sales data from company ERP system"
    },
    {
      "address": "company-slack.post_announcement",
      "transport": "http", 
      "endpoint": "http://slack-bridge.company.md/post",
      "input_schema": {
        "type": "object",
        "required": ["channel", "message"],
        "properties": {
          "channel": {"type": "string", "pattern": "^#[a-z0-9-_]+$"},
          "message": {"type": "string", "maxLength": 3000},
          "priority": {"type": "string", "enum": ["low", "normal", "high"]},
          "mention_groups": {
            "type": "array",
            "items": {"type": "string"}
          }
        }
      },
      "output_schema": {
        "type": "object",
        "properties": {
          "message_id": {"type": "string"},
          "timestamp": {"type": "string", "format": "date-time"},
          "channel": {"type": "string"}
        }
      },
      "scopes": ["slack.post"],
      "description": "Post announcements to company Slack channels"
    }
  ]
}
```

#### 2. Custom Business Logic Integration

```python
# Custom validation webhook for business rules
@app.route('/webhooks/validate-expense', methods=['POST'])
def validate_expense():
    """Custom business logic for expense validation."""
    data = request.json
    expense = data.get('expense', {})
    
    # Moldova-specific business rules
    rules = {
        'max_amount_mdl': 50000,  # 50,000 MDL limit
        'requires_receipt': expense.get('amount_mdl', 0) > 1000,
        'working_hours_only': True,
        'approved_categories': ['travel', 'meals', 'supplies', 'software']
    }
    
    validation_result = {
        'valid': True,
        'errors': [],
        'warnings': [],
        'requires_approval': False
    }
    
    # Apply business rules
    if expense.get('amount_mdl', 0) > rules['max_amount_mdl']:
        validation_result['errors'].append(f"Amount exceeds limit of {rules['max_amount_mdl']} MDL")
        validation_result['valid'] = False
    
    if expense.get('category') not in rules['approved_categories']:
        validation_result['errors'].append(f"Category must be one of: {rules['approved_categories']}")
        validation_result['valid'] = False
    
    if expense.get('amount_mdl', 0) > 10000:
        validation_result['requires_approval'] = True
        validation_result['warnings'].append("Requires manager approval")
    
    return jsonify(validation_result)
```

### Workflow Templates for Common Business Processes

#### 1. Employee Onboarding Workflow

```json
{
  "title": "Employee Onboarding - Moldova Office",
  "description": "Complete onboarding process for new employees",
  "schedule_kind": "event",
  "schedule_expr": "hr.employee.hired",
  "payload": {
    "pipeline": [
      {
        "id": "create_accounts",
        "uses": "ad.create_user",
        "with": {
          "username": "${event.payload.employee.email | split('@') | [0]}",
          "full_name": "${event.payload.employee.full_name}",
          "department": "${event.payload.employee.department}",
          "manager": "${event.payload.employee.manager_email}"
        },
        "save_as": "user_account"
      },
      {
        "id": "setup_equipment",
        "uses": "inventory.assign_equipment",
        "with": {
          "employee_id": "${event.payload.employee.id}",
          "role": "${event.payload.employee.role}",
          "location": "Chisinau"
        },
        "save_as": "equipment"
      },
      {
        "id": "create_calendar",
        "uses": "google-workspace.create_calendar",
        "with": {
          "email": "${event.payload.employee.email}",
          "name": "${event.payload.employee.full_name}",
          "department": "${event.payload.employee.department}"
        }
      },
      {
        "id": "send_welcome_email",
        "uses": "email.send_template",
        "with": {
          "to": "${event.payload.employee.email}",
          "template": "welcome_onboarding_ro",
          "language": "ro",
          "variables": {
            "employee_name": "${event.payload.employee.full_name}",
            "start_date": "${event.payload.employee.start_date}",
            "manager_name": "${event.payload.employee.manager_name}",
            "login_credentials": "${steps.user_account.credentials}",
            "equipment_list": "${steps.equipment.assigned_items}"
          }
        }
      },
      {
        "id": "notify_it_department",
        "uses": "slack.post_message",
        "with": {
          "channel": "#it-support",
          "text": "🆕 New employee setup complete:\\n**Name:** ${event.payload.employee.full_name}\\n**Department:** ${event.payload.employee.department}\\n**Start Date:** ${event.payload.employee.start_date}\\n**Equipment:** ${join(', ', steps.equipment.assigned_items)}"
        }
      },
      {
        "id": "schedule_check_ins",
        "uses": "orchestrator.create_task",
        "with": {
          "title": "Onboarding Check-in: ${event.payload.employee.full_name}",
          "schedule_kind": "once",
          "schedule_expr": "${event.payload.employee.start_date | add_days(7) | iso}",
          "payload": {
            "pipeline": [
              {
                "id": "send_checkin",
                "uses": "email.send_template",
                "with": {
                  "to": "${event.payload.employee.manager_email}",
                  "template": "manager_checkin_ro",
                  "variables": {
                    "employee_name": "${event.payload.employee.full_name}",
                    "week_number": 1
                  }
                }
              }
            ]
          }
        }
      }
    ]
  }
}
```

#### 2. Invoice Processing Automation

```json
{
  "title": "Invoice Processing - Moldova Compliance",
  "description": "Automated invoice processing with Moldova tax compliance",
  "schedule_kind": "event",
  "schedule_expr": "finance.invoice.received",
  "payload": {
    "pipeline": [
      {
        "id": "extract_invoice_data",
        "uses": "ocr.extract_invoice",
        "with": {
          "document": "${event.payload.document}",
          "language": "ro",
          "currency": "MDL"
        },
        "save_as": "invoice_data"
      },
      {
        "id": "validate_fiscal_data",
        "uses": "moldova-tax.validate_invoice",
        "with": {
          "fiscal_code": "${steps.invoice_data.supplier_fiscal_code}",
          "vat_number": "${steps.invoice_data.vat_number}",
          "amount": "${steps.invoice_data.total_amount}"
        },
        "save_as": "validation"
      },
      {
        "id": "check_budget_approval",
        "uses": "erp.check_budget",
        "with": {
          "department": "${steps.invoice_data.department}",
          "amount": "${steps.invoice_data.total_amount}",
          "category": "${steps.invoice_data.expense_category}"
        },
        "save_as": "budget_check"
      },
      {
        "id": "auto_approve_small_amounts",
        "uses": "erp.approve_invoice",
        "with": {
          "invoice_id": "${event.payload.invoice_id}",
          "approval_type": "automatic",
          "approver": "system"
        },
        "if": "${steps.validation.valid == true && steps.budget_check.approved == true && steps.invoice_data.total_amount <= 5000}",
        "save_as": "approval"
      },
      {
        "id": "request_manual_approval",
        "uses": "approval.request",
        "with": {
          "type": "invoice_approval",
          "approvers": "${steps.budget_check.required_approvers}",
          "data": {
            "invoice": "${steps.invoice_data}",
            "validation": "${steps.validation}",
            "budget": "${steps.budget_check}"
          },
          "deadline": "${now + 3 * 24 * 3600 | iso}"
        },
        "if": "${steps.approval == null}",
        "save_as": "manual_approval"
      },
      {
        "id": "notify_finance",
        "uses": "email.send",
        "with": {
          "to": "finance@company.md",
          "subject": "Invoice ${if(steps.approval, 'Approved', 'Requires Approval')}: ${steps.invoice_data.supplier_name}",
          "body": "Invoice from ${steps.invoice_data.supplier_name} for ${steps.invoice_data.total_amount} MDL has been ${if(steps.approval, 'automatically approved', 'sent for manual approval')}."
        }
      }
    ]
  }
}
```

---

## Moldova Business Context

### Local Compliance and Regulations

#### 1. Moldova Tax System Integration

```json
{
  "tools": [
    {
      "address": "moldova-tax.validate_company",
      "transport": "http",
      "endpoint": "https://api.fisc.md/company/validate",
      "input_schema": {
        "type": "object",
        "required": ["fiscal_code"],
        "properties": {
          "fiscal_code": {"type": "string", "pattern": "^[0-9]{7,13}$"},
          "vat_number": {"type": "string", "pattern": "^MD[0-9]{8}$"}
        }
      },
      "output_schema": {
        "type": "object",
        "properties": {
          "valid": {"type": "boolean"},
          "company_name": {"type": "string"},
          "status": {"type": "string"},
          "vat_registered": {"type": "boolean"}
        }
      },
      "scopes": ["tax.validate"],
      "description": "Validate company data with Moldova fiscal service"
    }
  ]
}
```

#### 2. Moldova Holiday Calendar

```python
MOLDOVA_HOLIDAYS = {
    "2024": [
        {"date": "2024-01-01", "name": "New Year", "name_ro": "Anul Nou"},
        {"date": "2024-01-07", "name": "Orthodox Christmas", "name_ro": "Crăciunul pe stil vechi"},
        {"date": "2024-01-08", "name": "Orthodox Christmas (2nd day)", "name_ro": "Crăciunul pe stil vechi (ziua a 2-a)"},
        {"date": "2024-03-08", "name": "Women's Day", "name_ro": "Ziua Femeii"},
        {"date": "2024-05-01", "name": "Labor Day", "name_ro": "Ziua Muncii"},
        {"date": "2024-05-05", "name": "Orthodox Easter", "name_ro": "Paștele ortodox"},
        {"date": "2024-05-06", "name": "Orthodox Easter Monday", "name_ro": "Lunea Paștilor"},
        {"date": "2024-05-09", "name": "Victory Day", "name_ro": "Ziua Victoriei"},
        {"date": "2024-08-27", "name": "Independence Day", "name_ro": "Ziua Independenței"},
        {"date": "2024-08-31", "name": "Language Day", "name_ro": "Ziua Limbii"},
        {"date": "2024-12-25", "name": "Christmas Day", "name_ro": "Crăciunul"}
    ]
}

# Holiday-aware scheduling template
{
  "id": "check_moldova_holiday",
  "uses": "calendar.is_holiday",
  "with": {
    "date": "${now | date('%Y-%m-%d')}",
    "country": "MD",
    "holidays": "${params.moldova_holidays}"
  },
  "save_as": "holiday_status"
}
```

#### 3. Working Hours Configuration for Moldova

```json
{
  "moldova_business_config": {
    "standard_hours": {
      "monday": {"start": "09:00", "end": "18:00"},
      "tuesday": {"start": "09:00", "end": "18:00"},
      "wednesday": {"start": "09:00", "end": "18:00"},
      "thursday": {"start": "09:00", "end": "18:00"},
      "friday": {"start": "09:00", "end": "18:00"},
      "saturday": "off",
      "sunday": "off"
    },
    "lunch_break": {
      "start": "12:00",
      "end": "13:00"
    },
    "timezone": "Europe/Chisinau",
    "summer_schedule": {
      "enabled": true,
      "period": "2024-06-01 to 2024-08-31",
      "friday_end": "17:00"
    }
  }
}
```

### Multi-Language Support

#### 1. Romanian/English Templates

```json
{
  "email_templates": {
    "meeting_reminder_ro": {
      "subject": "Reamintire: Întâlnire ${meeting_title}",
      "body": "Bună ziua,\n\nVă reamintim despre întâlnirea '${meeting_title}' programată pentru ${meeting_time}.\n\nLocalitate: ${location}\nAgenda: ${agenda}\n\nCu stimă,\nEchipa de management"
    },
    "meeting_reminder_en": {
      "subject": "Reminder: Meeting ${meeting_title}",
      "body": "Hello,\n\nThis is a reminder about the meeting '${meeting_title}' scheduled for ${meeting_time}.\n\nLocation: ${location}\nAgenda: ${agenda}\n\nBest regards,\nManagement Team"
    },
    "invoice_approval_ro": {
      "subject": "Aprobare necesară: Factură ${supplier_name}",
      "body": "Stimați colegi,\n\nO nouă factură necesită aprobarea dumneavoastră:\n\nFurnizor: ${supplier_name}\nSuma: ${amount} MDL\nCategorie: ${category}\n\nVă rugăm să accesați sistemul pentru aprobare.\n\nMultumesc!"
    }
  }
}
```

#### 2. Dynamic Language Selection

```json
{
  "id": "send_localized_notification",
  "uses": "email.send_template",
  "with": {
    "to": "${params.recipient_email}",
    "template": "meeting_reminder_${params.user_language || 'ro'}",
    "variables": {
      "meeting_title": "${steps.meeting.title}",
      "meeting_time": "${steps.meeting.start_time | format_datetime(params.user_language || 'ro')}",
      "location": "${steps.meeting.location}",
      "agenda": "${steps.meeting.agenda}"
    }
  }
}
```

---

## Configuration Templates

### Development Team Automation

```json
{
  "title": "Development Team Daily Workflows",
  "templates": [
    {
      "name": "Sprint Planning Reminder",
      "schedule": "FREQ=WEEKLY;BYDAY=MO;BYHOUR=9;BYMINUTE=0",
      "pipeline": [
        {
          "id": "get_sprint_info",
          "uses": "jira.get_sprint",
          "with": {"project": "${params.project_key}"}
        },
        {
          "id": "notify_team",
          "uses": "slack.post_message",
          "with": {
            "channel": "#dev-team",
            "text": "🏃‍♂️ Sprint Planning starts in 30 minutes!\\n**Current Sprint:** ${steps.sprint_info.name}\\n**Stories:** ${length(steps.sprint_info.stories)} planned"
          }
        }
      ]
    },
    {
      "name": "Code Review Reminder",
      "schedule": "FREQ=DAILY;BYHOUR=15;BYMINUTE=0;BYDAY=MO,TU,WE,TH,FR",
      "pipeline": [
        {
          "id": "check_pending_prs",
          "uses": "github.get_pending_reviews",
          "with": {"org": "${params.github_org}"}
        },
        {
          "id": "remind_reviewers",
          "uses": "slack.post_message",
          "with": {
            "channel": "#dev-team",
            "text": "⏰ Daily code review reminder:\\n${length(steps.pending_prs.items)} PRs need review"
          },
          "if": "${length(steps.pending_prs.items) > 0}"
        }
      ]
    }
  ]
}
```

### Sales Team Automation

```json
{
  "title": "Sales Team Performance Tracking",
  "templates": [
    {
      "name": "Daily Sales Report",
      "schedule": "FREQ=DAILY;BYHOUR=18;BYMINUTE=30;BYDAY=MO,TU,WE,TH,FR",
      "pipeline": [
        {
          "id": "get_daily_metrics",
          "uses": "crm.get_daily_sales",
          "with": {"date": "${now | date('%Y-%m-%d')}"}
        },
        {
          "id": "calculate_targets",
          "uses": "analytics.compare_targets",
          "with": {
            "actual": "${steps.daily_metrics.revenue}",
            "target": "${params.daily_target}",
            "period": "daily"
          }
        },
        {
          "id": "send_report",
          "uses": "email.send_template",
          "with": {
            "to": "${params.sales_team_email}",
            "template": "daily_sales_report_ro",
            "variables": {
              "revenue": "${steps.daily_metrics.revenue}",
              "target_progress": "${steps.calculate_targets.percentage}",
              "deals_closed": "${steps.daily_metrics.deals_count}",
              "top_performer": "${steps.daily_metrics.top_performer}"
            }
          }
        }
      ]
    }
  ]
}
```

### Executive Dashboard Automation

```json
{
  "title": "Executive KPI Dashboard",
  "templates": [
    {
      "name": "Weekly Executive Summary",
      "schedule": "FREQ=WEEKLY;BYDAY=MO;BYHOUR=8;BYMINUTE=0",
      "pipeline": [
        {
          "id": "collect_kpis",
          "uses": "analytics.get_weekly_kpis",
          "with": {
            "metrics": ["revenue", "customers", "churn", "support_tickets"],
            "period": "last_week"
          }
        },
        {
          "id": "generate_insights",
          "uses": "llm.executive_insights",
          "with": {
            "data": "${steps.collect_kpis}",
            "language": "ro",
            "focus_areas": ["growth", "customer_satisfaction", "operational_efficiency"]
          }
        },
        {
          "id": "create_presentation",
          "uses": "powerpoint.generate_slides",
          "with": {
            "template": "executive_weekly_ro",
            "data": "${steps.collect_kpis}",
            "insights": "${steps.generate_insights.key_points}"
          }
        },
        {
          "id": "send_to_executives",
          "uses": "email.send",
          "with": {
            "to": "${params.executive_team}",
            "subject": "📊 Raport Executiv - Săptămâna ${now | week_number}",
            "body": "${steps.generate_insights.summary}",
            "attachments": ["${steps.create_presentation.file_path}"]
          }
        }
      ]
    }
  ]
}
```

---

## Performance Tuning

### Database Optimization

```sql
-- Create indexes for common query patterns
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_task_status_priority 
ON task (status, priority) WHERE status = 'active';

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_due_work_run_at_unlocked
ON due_work (run_at) WHERE locked_until IS NULL OR locked_until < now();

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_task_run_task_created 
ON task_run (task_id, created_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_log_created_action
ON audit_log (created_at DESC, action);

-- Optimize configuration
ALTER SYSTEM SET shared_preload_libraries = 'pg_stat_statements';
ALTER SYSTEM SET work_mem = '256MB';
ALTER SYSTEM SET effective_cache_size = '2GB';
ALTER SYSTEM SET random_page_cost = 1.1;  -- For SSD storage
```

### Worker Scaling Configuration

```yaml
# docker-compose.override.yml for production scaling
version: '3.8'
services:
  worker:
    deploy:
      replicas: 5
    environment:
      - WORKER_BATCH_SIZE=10
      - WORKER_POLL_INTERVAL=1
      - WORKER_MAX_CONCURRENCY=20
    resources:
      limits:
        memory: 512M
        cpus: '0.5'
      reservations:
        memory: 256M
        cpus: '0.25'

  scheduler:
    environment:
      - SCHEDULER_TICK_INTERVAL=30
      - MAX_CONCURRENT_JOBS=100
    resources:
      limits:
        memory: 256M
        cpus: '0.25'
```

### Redis Configuration for High Throughput

```redis
# redis.conf optimization for high throughput
maxmemory 2gb
maxmemory-policy allkeys-lru
save 900 1
save 300 10
save 60 10000

# For event streams
stream-node-max-bytes 4096
stream-node-max-entries 100

# Connection settings
tcp-keepalive 300
timeout 0
tcp-backlog 511
```

### Monitoring and Alerting Setup

```yaml
# Prometheus configuration
version: '3.8'
services:
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/etc/prometheus/console_libraries'
      - '--web.console.templates=/etc/prometheus/consoles'
      - '--web.enable-lifecycle'
      - '--storage.tsdb.retention.time=30d'

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin123
    volumes:
      - grafana-data:/var/lib/grafana
```

---

## Troubleshooting & Support

### Common Configuration Issues

#### 1. Database Connection Problems

```bash
# Check database connectivity
docker exec -it postgres psql -U orchestrator -d orchestrator -c "SELECT version();"

# Verify table creation
docker exec -it postgres psql -U orchestrator -d orchestrator -c "\dt"

# Check for active connections
docker exec -it postgres psql -U orchestrator -d orchestrator -c "
SELECT count(*) as active_connections, 
       state, 
       client_addr 
FROM pg_stat_activity 
WHERE datname = 'orchestrator' 
GROUP BY state, client_addr;
"
```

#### 2. Task Scheduling Issues

```bash
# Check APScheduler job store
curl "http://localhost:8080/admin/jobs" -H "Authorization: Bearer admin-token"

# Verify RRULE parsing
curl -X POST "http://localhost:8080/admin/validate-rrule" \
  -H "Content-Type: application/json" \
  -d '{"rrule": "FREQ=DAILY;BYHOUR=9;BYMINUTE=0", "timezone": "Europe/Chisinau"}'

# Check due work queue depth
docker exec -it postgres psql -U orchestrator -d orchestrator -c "
SELECT 
    COUNT(*) as pending_work,
    MIN(run_at) as oldest_work,
    MAX(run_at) as newest_work
FROM due_work 
WHERE run_at <= now() 
  AND (locked_until IS NULL OR locked_until < now());
"
```

#### 3. Performance Monitoring

```bash
# Check system metrics
curl "http://localhost:8080/metrics" | grep -E "(task_|worker_|scheduler_)"

# Database performance analysis
docker exec -it postgres psql -U orchestrator -d orchestrator -c "
SELECT 
    query,
    calls,
    total_time,
    mean_time,
    max_time
FROM pg_stat_statements 
WHERE query LIKE '%task%' OR query LIKE '%due_work%'
ORDER BY total_time DESC
LIMIT 10;
"

# Redis performance check
docker exec -it redis redis-cli info stats | grep -E "(instantaneous_ops|total_commands)"
```

### Support Escalation Matrix

| Issue Severity | Response Time | Escalation Path |
|---------------|---------------|-----------------|
| Critical (System Down) | 15 minutes | → DevOps Team → CTO |
| High (Major Feature) | 2 hours | → Tech Lead → CTO |
| Medium (Minor Issues) | 8 hours | → Support Team |
| Low (Enhancement) | 3 days | → Product Team |

### Configuration Validation Checklist

```bash
#!/bin/bash
# Pre-production validation script

echo "🔍 Validating Ordinaut Configuration..."

# 1. Environment variables
required_vars=("DATABASE_URL" "REDIS_URL" "JWT_SECRET_KEY")
for var in "${required_vars[@]}"; do
    if [[ -z "${!var}" ]]; then
        echo "❌ Missing environment variable: $var"
        exit 1
    fi
done

# 2. Database connectivity
echo "📊 Testing database connection..."
if ! docker exec postgres psql -U orchestrator -d orchestrator -c "SELECT 1;" >/dev/null 2>&1; then
    echo "❌ Database connection failed"
    exit 1
fi

# 3. Redis connectivity
echo "📦 Testing Redis connection..."
if ! docker exec redis redis-cli ping >/dev/null 2>&1; then
    echo "❌ Redis connection failed"
    exit 1
fi

# 4. API health check
echo "🌐 Testing API health..."
if ! curl -f http://localhost:8080/health >/dev/null 2>&1; then
    echo "❌ API health check failed"
    exit 1
fi

# 5. Tool catalog validation
echo "🔧 Validating tool catalog..."
if ! curl -f "http://localhost:8080/admin/tools" -H "Authorization: Bearer system-token" >/dev/null 2>&1; then
    echo "❌ Tool catalog validation failed"
    exit 1
fi

echo "✅ All configuration checks passed!"
echo "🚀 System ready for production deployment"
```

---

## Quick Reference

### Essential API Endpoints

```bash
# Authentication
POST /agents/auth/token          # Get JWT tokens
POST /agents/auth/refresh        # Refresh access token

# Task Management
POST /tasks/                     # Create task
GET /tasks/                      # List tasks
GET /tasks/{id}                  # Get task details
PUT /tasks/{id}                  # Update task
POST /tasks/{id}/run_now         # Trigger immediate execution
POST /tasks/{id}/pause           # Pause task
POST /tasks/{id}/resume          # Resume task
POST /tasks/{id}/snooze          # Snooze task

# Agent Management
POST /agents/                    # Create agent
GET /agents/                     # List agents
POST /agents/{id}/credentials    # Create agent credentials

# System Operations
GET /health                      # System health check
GET /metrics                     # Prometheus metrics
GET /admin/jobs                  # APScheduler jobs
```

### Common RRULE Patterns

```python
# Business schedules for Moldova companies
COMMON_SCHEDULES = {
    "workdays_9am": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=9;BYMINUTE=0",
    "end_of_workday": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=18;BYMINUTE=0",
    "daily_standup": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=10;BYMINUTE=0", 
    "weekly_reports": "FREQ=WEEKLY;BYDAY=FR;BYHOUR=17;BYMINUTE=0",
    "monthly_review": "FREQ=MONTHLY;BYDAY=1MO;BYHOUR=14;BYMINUTE=0",
    "quarterly_board": "FREQ=MONTHLY;INTERVAL=3;BYMONTHDAY=1;BYHOUR=10;BYMINUTE=0",
    "lunch_reminder": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=12;BYMINUTE=30"
}
```

---

*This comprehensive configuration guide empowers Moldovan software company CTOs to fully customize and optimize Ordinaut for their specific business needs. The system provides enterprise-grade reliability with the flexibility to adapt to unique operational requirements.*

**For additional support:**
- 📧 Technical Support: support@ordinaut.md
- 📖 Documentation: https://docs.ordinaut.com
- 💬 Community Forum: https://forum.ordinaut.com
- 🏢 Enterprise Consulting: enterprise@ordinaut.md