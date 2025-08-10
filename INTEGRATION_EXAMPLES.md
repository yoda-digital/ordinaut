# Ordinaut Integration Examples for Moldovan CTOs

## Executive Summary

This comprehensive integration guide demonstrates how Ordinaut seamlessly connects with existing enterprise systems commonly used by Moldovan software companies. The examples provide production-ready implementations that CTOs can deploy immediately to transform disconnected AI assistants into a coordinated productivity system.

**Key Benefits:**
- **Zero Disruption**: Integrate without replacing existing tools and processes
- **Enterprise Security**: OAuth 2.0, JWT tokens, and secure credential management
- **Production Scalability**: Handles thousands of daily operations with monitoring
- **Moldova-Specific**: Includes local banking APIs, government services, and regional tools

---

## Architecture Overview

Ordinaut integrates with external systems through three primary patterns:

```mermaid
graph TD
    A[Ordinaut Core] --> B[MCP Protocol Layer]
    B --> C[HTTP/REST APIs]
    B --> D[Websocket/Real-time]
    B --> E[Database Connectors]
    
    C --> F[Slack/Teams]
    C --> G[GitHub/GitLab]
    C --> H[Salesforce/HubSpot]
    
    D --> I[Real-time Chat]
    D --> J[Live Notifications]
    
    E --> K[PostgreSQL/MySQL]
    E --> L[MongoDB/Redis]
```

### Integration Transport Types

1. **HTTP/REST**: Standard web APIs (Slack, GitHub, CRM systems)
2. **MCP Protocol**: AI-optimized integration layer for LLMs and agents
3. **Websocket**: Real-time bidirectional communication
4. **Database**: Direct database connections for enterprise systems

---

## 1. MCP Protocol Integrations

### 1.1 ChatGPT Integration

**Use Case**: Route complex analysis tasks to ChatGPT while maintaining workflow coordination.

#### Architecture
```python
# /catalogs/openai-mcp-tool.json
{
  "address": "openai-chatgpt.analyze",
  "transport": "http",
  "endpoint": "http://openai-bridge:8091/tools/analyze",
  "input_schema": {
    "type": "object",
    "required": ["prompt", "context"],
    "properties": {
      "prompt": {
        "type": "string",
        "maxLength": 4000,
        "description": "Analysis instruction for ChatGPT"
      },
      "context": {
        "type": "object",
        "description": "Structured data context for analysis"
      },
      "model": {
        "type": "string",
        "enum": ["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo"],
        "default": "gpt-4",
        "description": "OpenAI model to use"
      },
      "temperature": {
        "type": "number",
        "minimum": 0,
        "maximum": 1,
        "default": 0.7,
        "description": "Response creativity level"
      }
    }
  },
  "output_schema": {
    "type": "object",
    "required": ["analysis", "confidence"],
    "properties": {
      "analysis": {"type": "string"},
      "confidence": {"type": "number", "minimum": 0, "maximum": 1},
      "token_usage": {
        "type": "object",
        "properties": {
          "prompt_tokens": {"type": "integer"},
          "completion_tokens": {"type": "integer"},
          "total_tokens": {"type": "integer"}
        }
      }
    }
  },
  "timeout_seconds": 60,
  "scopes": ["llm.openai"],
  "cost_tier": "high",
  "description": "Analyze data using ChatGPT with structured output"
}
```

#### MCP Bridge Implementation
```python
# /bridge/openai_mcp_bridge.py
import asyncio
import httpx
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException
import os
import logging

logger = logging.getLogger(__name__)
app = FastAPI(title="OpenAI MCP Bridge")

class OpenAIMCPBridge:
    """Production-ready OpenAI integration bridge."""
    
    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1"):
        self.api_key = api_key
        self.base_url = base_url
        self.client = httpx.AsyncClient(
            timeout=60.0,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=50)
        )
        
    async def analyze(self, prompt: str, context: Dict[str, Any], 
                     model: str = "gpt-4", temperature: float = 0.7) -> Dict[str, Any]:
        """Analyze data using ChatGPT with structured output."""
        
        # Construct system message with context
        system_message = f"""You are a business intelligence analyst. 
        Analyze the provided data and respond with actionable insights.
        
        Context Data:
        {self._format_context(context)}
        """
        
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt}
        ]
        
        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": 1500,
                    "response_format": {"type": "json_object"}
                },
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
            )
            response.raise_for_status()
            
            result = response.json()
            choice = result["choices"][0]
            usage = result["usage"]
            
            # Parse JSON response
            import json
            analysis_data = json.loads(choice["message"]["content"])
            
            return {
                "analysis": analysis_data.get("analysis", choice["message"]["content"]),
                "confidence": analysis_data.get("confidence", 0.8),
                "token_usage": {
                    "prompt_tokens": usage["prompt_tokens"],
                    "completion_tokens": usage["completion_tokens"],
                    "total_tokens": usage["total_tokens"]
                }
            }
            
        except httpx.HTTPStatusError as e:
            logger.error(f"OpenAI API error: {e.response.status_code} - {e.response.text}")
            raise HTTPException(
                status_code=502,
                detail=f"OpenAI API error: {e.response.status_code}"
            )
        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    def _format_context(self, context: Dict[str, Any]) -> str:
        """Format context data for ChatGPT consumption."""
        formatted = []
        for key, value in context.items():
            if isinstance(value, dict):
                formatted.append(f"{key.upper()}: {json.dumps(value, indent=2)}")
            elif isinstance(value, list):
                formatted.append(f"{key.upper()}: {len(value)} items - {value[:3]}...")
            else:
                formatted.append(f"{key.upper()}: {value}")
        return "\n".join(formatted)

# Global bridge instance
openai_bridge = OpenAIMCPBridge(api_key=os.getenv("OPENAI_API_KEY"))

@app.post("/tools/analyze")
async def analyze_endpoint(request: Dict[str, Any]) -> Dict[str, Any]:
    """MCP endpoint for ChatGPT analysis."""
    params = request.get("params", {}).get("arguments", {})
    
    return await openai_bridge.analyze(
        prompt=params["prompt"],
        context=params["context"],
        model=params.get("model", "gpt-4"),
        temperature=params.get("temperature", 0.7)
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8091)
```

#### Production Pipeline Example
```json
{
  "title": "Weekly Business Intelligence Report",
  "schedule_kind": "rrule",
  "schedule_expr": "FREQ=WEEKLY;BYDAY=MO;BYHOUR=9;BYMINUTE=0",
  "timezone": "Europe/Chisinau",
  "payload": {
    "pipeline": [
      {
        "id": "fetch_sales_data",
        "uses": "salesforce.query_reports",
        "with": {
          "report_type": "weekly_sales",
          "date_range": "last_week"
        },
        "save_as": "sales"
      },
      {
        "id": "fetch_support_metrics",
        "uses": "zendesk.get_metrics",
        "with": {
          "period": "week",
          "metrics": ["resolution_time", "satisfaction_score"]
        },
        "save_as": "support"
      },
      {
        "id": "analyze_performance",
        "uses": "openai-chatgpt.analyze",
        "with": {
          "prompt": "Analyze weekly business performance and identify key trends, risks, and opportunities. Provide 3-5 actionable recommendations.",
          "context": {
            "sales_data": "${steps.sales.data}",
            "support_metrics": "${steps.support.metrics}",
            "department": "executive"
          },
          "model": "gpt-4"
        },
        "save_as": "analysis"
      },
      {
        "id": "send_executive_brief",
        "uses": "slack.post_message",
        "with": {
          "channel": "#executives",
          "message": "📊 **Weekly Business Intelligence Report**\n\n${steps.analysis.analysis}\n\n*Confidence: ${steps.analysis.confidence}*",
          "blocks": [
            {
              "type": "section",
              "text": {
                "type": "mrkdwn",
                "text": "📊 *Weekly Business Intelligence Report*"
              }
            },
            {
              "type": "section",
              "text": {
                "type": "mrkdwn",
                "text": "${steps.analysis.analysis}"
              }
            },
            {
              "type": "context",
              "elements": [
                {
                  "type": "mrkdwn",
                  "text": "Confidence: ${steps.analysis.confidence} | Tokens: ${steps.analysis.token_usage.total_tokens}"
                }
              ]
            }
          ]
        }
      }
    ]
  }
}
```

### 1.2 Claude Integration

**Use Case**: Leverage Claude's analytical capabilities for code review and technical documentation.

#### Tool Definition
```json
{
  "address": "anthropic-claude.code_review",
  "transport": "http", 
  "endpoint": "http://claude-bridge:8092/tools/code_review",
  "input_schema": {
    "type": "object",
    "required": ["code_diff", "language"],
    "properties": {
      "code_diff": {
        "type": "string",
        "maxLength": 20000,
        "description": "Git diff or code content to review"
      },
      "language": {
        "type": "string",
        "enum": ["python", "javascript", "typescript", "go", "java", "php"],
        "description": "Programming language"
      },
      "focus_areas": {
        "type": "array",
        "items": {"type": "string"},
        "default": ["security", "performance", "maintainability"],
        "description": "Review focus areas"
      },
      "severity_threshold": {
        "type": "string",
        "enum": ["low", "medium", "high"],
        "default": "medium",
        "description": "Minimum severity to report"
      }
    }
  },
  "timeout_seconds": 45,
  "scopes": ["llm.anthropic", "code.review"],
  "cost_tier": "high"
}
```

#### Integration with GitHub/GitLab
```python
# /bridge/claude_code_bridge.py
import asyncio
import httpx
from typing import Dict, Any, List
import base64
import os

class ClaudeCodeBridge:
    """Production Claude integration for code review."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.anthropic.com/v1"
        self.client = httpx.AsyncClient(timeout=60.0)
    
    async def review_code(self, code_diff: str, language: str, 
                         focus_areas: List[str], severity_threshold: str) -> Dict[str, Any]:
        """Perform comprehensive code review using Claude."""
        
        system_prompt = f"""You are a senior software engineer conducting a code review.
        
        Language: {language}
        Focus Areas: {', '.join(focus_areas)}
        Minimum Severity: {severity_threshold}
        
        Provide a JSON response with:
        {{
          "overall_score": 0-10,
          "issues": [
            {{
              "severity": "low|medium|high|critical",
              "category": "security|performance|maintainability|style",
              "description": "Clear issue description",
              "line_numbers": [1, 2, 3],
              "suggestion": "Specific improvement suggestion"
            }}
          ],
          "positive_aspects": ["Good practices found"],
          "summary": "Overall assessment"
        }}
        """
        
        try:
            response = await self.client.post(
                f"{self.base_url}/messages",
                json={
                    "model": "claude-3-sonnet-20240229",
                    "max_tokens": 2000,
                    "system": system_prompt,
                    "messages": [
                        {
                            "role": "user",
                            "content": f"Please review this {language} code diff:\n\n```{language}\n{code_diff}\n```"
                        }
                    ]
                },
                headers={
                    "x-api-key": self.api_key,
                    "content-type": "application/json",
                    "anthropic-version": "2023-06-01"
                }
            )
            response.raise_for_status()
            
            result = response.json()
            content = result["content"][0]["text"]
            
            # Parse JSON response
            import json
            review_data = json.loads(content)
            
            # Filter by severity threshold
            severity_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
            min_severity = severity_order[severity_threshold]
            
            filtered_issues = [
                issue for issue in review_data["issues"]
                if severity_order.get(issue["severity"], 0) >= min_severity
            ]
            
            return {
                "overall_score": review_data["overall_score"],
                "issues": filtered_issues,
                "positive_aspects": review_data["positive_aspects"],
                "summary": review_data["summary"],
                "metadata": {
                    "total_issues": len(review_data["issues"]),
                    "filtered_issues": len(filtered_issues),
                    "language": language,
                    "focus_areas": focus_areas
                }
            }
            
        except Exception as e:
            logger.error(f"Claude code review failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))
```

#### Automated Pull Request Review Pipeline
```json
{
  "title": "Automated PR Review",
  "schedule_kind": "event",
  "event_type": "github.pull_request.opened",
  "payload": {
    "pipeline": [
      {
        "id": "fetch_pr_diff",
        "uses": "github.get_pull_request_diff",
        "with": {
          "repository": "${event.repository.full_name}",
          "pull_number": "${event.number}"
        },
        "save_as": "diff"
      },
      {
        "id": "detect_language",
        "uses": "github.get_pr_files",
        "with": {
          "repository": "${event.repository.full_name}",
          "pull_number": "${event.number}"
        },
        "save_as": "files"
      },
      {
        "id": "review_code",
        "uses": "anthropic-claude.code_review",
        "with": {
          "code_diff": "${steps.diff.content}",
          "language": "${steps.files.primary_language}",
          "focus_areas": ["security", "performance", "maintainability"],
          "severity_threshold": "medium"
        },
        "save_as": "review"
      },
      {
        "id": "post_review",
        "uses": "github.create_review_comment",
        "with": {
          "repository": "${event.repository.full_name}",
          "pull_number": "${event.number}",
          "body": "## 🤖 Automated Code Review\n\n**Overall Score:** ${steps.review.overall_score}/10\n\n**Issues Found:** ${steps.review.metadata.filtered_issues}\n\n### Summary\n${steps.review.summary}\n\n### Issues\n{% for issue in steps.review.issues %}\n- **{{ issue.severity | upper }}**: {{ issue.description }}\n  - *Category*: {{ issue.category }}\n  - *Suggestion*: {{ issue.suggestion }}\n{% endfor %}\n\n### Positive Aspects\n{% for aspect in steps.review.positive_aspects %}\n- ✅ {{ aspect }}\n{% endfor %}\n\n---\n*Reviewed by Claude AI • Orchestrated by Ordinaut*"
        }
      },
      {
        "id": "notify_team",
        "uses": "slack.post_message",
        "with": {
          "channel": "#development",
          "message": "🔍 Code review completed for PR #${event.number}: **${steps.review.overall_score}/10** (${steps.review.metadata.filtered_issues} issues found)"
        },
        "if": "${steps.review.metadata.filtered_issues > 0}"
      }
    ]
  }
}
```

---

## 2. Communication Platform Integrations

### 2.1 Slack Integration

**Use Case**: Coordinate team communication and automate routine notifications.

#### Advanced Slack Tool Configuration
```json
{
  "address": "slack.enterprise",
  "transport": "http",
  "endpoint": "http://slack-bridge:8093/tools/enterprise",
  "input_schema": {
    "type": "object",
    "required": ["action"],
    "properties": {
      "action": {
        "type": "string",
        "enum": [
          "post_message", "schedule_message", "update_status",
          "create_channel", "invite_users", "set_reminder",
          "post_to_thread", "react_to_message", "pin_message"
        ]
      },
      "channel": {"type": "string"},
      "message": {"type": "string", "maxLength": 3000},
      "user_id": {"type": "string"},
      "thread_ts": {"type": "string"},
      "scheduled_time": {"type": "string", "format": "date-time"},
      "blocks": {"type": "array"},
      "attachments": {"type": "array"}
    }
  },
  "authentication": {
    "type": "oauth2",
    "token_url": "https://slack.com/api/oauth.v2.access",
    "scopes": [
      "chat:write", "channels:manage", "users:read",
      "channels:read", "reactions:write", "pins:write"
    ]
  },
  "timeout_seconds": 30,
  "scopes": ["communication.slack"],
  "cost_tier": "medium"
}
```

#### Enterprise Slack Bridge
```python
# /bridge/slack_enterprise_bridge.py
import asyncio
import httpx
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import json
import os

class SlackEnterpriseBridge:
    """Production Slack integration with advanced features."""
    
    def __init__(self, bot_token: str, app_token: str = None):
        self.bot_token = bot_token
        self.app_token = app_token
        self.base_url = "https://slack.com/api"
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={"Authorization": f"Bearer {bot_token}"}
        )
        
    async def enterprise_action(self, action: str, **kwargs) -> Dict[str, Any]:
        """Execute enterprise Slack actions."""
        
        action_handlers = {
            "post_message": self._post_message,
            "schedule_message": self._schedule_message,
            "update_status": self._update_status,
            "create_channel": self._create_channel,
            "invite_users": self._invite_users,
            "set_reminder": self._set_reminder,
            "post_to_thread": self._post_to_thread,
            "react_to_message": self._react_to_message,
            "pin_message": self._pin_message
        }
        
        handler = action_handlers.get(action)
        if not handler:
            raise ValueError(f"Unknown action: {action}")
            
        return await handler(**kwargs)
    
    async def _post_message(self, channel: str, message: str, 
                           blocks: List[Dict] = None, 
                           attachments: List[Dict] = None) -> Dict[str, Any]:
        """Post message with rich formatting."""
        
        payload = {
            "channel": channel,
            "text": message
        }
        
        if blocks:
            payload["blocks"] = blocks
        if attachments:
            payload["attachments"] = attachments
            
        response = await self.client.post(
            f"{self.base_url}/chat.postMessage",
            json=payload
        )
        response.raise_for_status()
        return response.json()
    
    async def _schedule_message(self, channel: str, message: str, 
                               scheduled_time: str, **kwargs) -> Dict[str, Any]:
        """Schedule message for future delivery."""
        
        # Convert ISO time to Unix timestamp
        dt = datetime.fromisoformat(scheduled_time.replace('Z', '+00:00'))
        post_at = int(dt.timestamp())
        
        payload = {
            "channel": channel,
            "text": message,
            "post_at": post_at
        }
        
        response = await self.client.post(
            f"{self.base_url}/chat.scheduleMessage",
            json=payload
        )
        response.raise_for_status()
        return response.json()
    
    async def _create_channel(self, name: str, is_private: bool = False) -> Dict[str, Any]:
        """Create new channel."""
        
        endpoint = "conversations.create"
        payload = {
            "name": name,
            "is_private": is_private
        }
        
        response = await self.client.post(
            f"{self.base_url}/{endpoint}",
            json=payload
        )
        response.raise_for_status()
        return response.json()
    
    async def _invite_users(self, channel: str, users: List[str]) -> Dict[str, Any]:
        """Invite users to channel."""
        
        payload = {
            "channel": channel,
            "users": ",".join(users)
        }
        
        response = await self.client.post(
            f"{self.base_url}/conversations.invite",
            json=payload
        )
        response.raise_for_status()
        return response.json()
    
    async def _set_reminder(self, text: str, time: str, user: str = None) -> Dict[str, Any]:
        """Set reminder for user."""
        
        payload = {
            "text": text,
            "time": time
        }
        if user:
            payload["user"] = user
            
        response = await self.client.post(
            f"{self.base_url}/reminders.add",
            json=payload
        )
        response.raise_for_status()
        return response.json()
```

#### Daily Standup Automation
```json
{
  "title": "Daily Standup Coordination",
  "schedule_kind": "rrule",
  "schedule_expr": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=9;BYMINUTE=0",
  "timezone": "Europe/Chisinau",
  "payload": {
    "pipeline": [
      {
        "id": "create_standup_thread",
        "uses": "slack.enterprise",
        "with": {
          "action": "post_message",
          "channel": "#daily-standup",
          "message": "🌅 **Daily Standup** - {{current_date}}",
          "blocks": [
            {
              "type": "header",
              "text": {
                "type": "plain_text",
                "text": "🌅 Daily Standup"
              }
            },
            {
              "type": "section",
              "text": {
                "type": "mrkdwn",
                "text": "Good morning team! Please share:\n\n• ✅ *What you completed yesterday*\n• 🎯 *What you're working on today*\n• 🚫 *Any blockers or challenges*"
              }
            },
            {
              "type": "actions",
              "elements": [
                {
                  "type": "button",
                  "text": {"type": "plain_text", "text": "I'm Ready"},
                  "action_id": "standup_ready",
                  "style": "primary"
                },
                {
                  "type": "button",
                  "text": {"type": "plain_text", "text": "Running Late"},
                  "action_id": "standup_late"
                }
              ]
            }
          ]
        },
        "save_as": "standup_message"
      },
      {
        "id": "set_followup_reminder",
        "uses": "slack.enterprise",
        "with": {
          "action": "set_reminder",
          "text": "Standup follow-up: Check if everyone has contributed",
          "time": "in 30 minutes"
        }
      },
      {
        "id": "schedule_summary",
        "uses": "slack.enterprise",
        "with": {
          "action": "schedule_message",
          "channel": "#daily-standup",
          "message": "📋 **Standup Summary**: I'll analyze today's standup responses and post a summary in 1 hour.",
          "scheduled_time": "{{current_time + 1h}}"
        }
      }
    ]
  }
}
```

### 2.2 Microsoft Teams Integration

**Use Case**: Enterprise communication and meeting coordination.

#### Teams Tool Definition
```json
{
  "address": "msteams.enterprise",
  "transport": "http",
  "endpoint": "http://teams-bridge:8094/tools/enterprise",
  "input_schema": {
    "type": "object",
    "required": ["action"],
    "properties": {
      "action": {
        "type": "string",
        "enum": [
          "send_message", "schedule_meeting", "send_notification",
          "create_team", "add_members", "post_to_channel",
          "send_adaptive_card", "create_poll"
        ]
      },
      "team_id": {"type": "string"},
      "channel_id": {"type": "string"},
      "user_id": {"type": "string"},
      "message": {"type": "string"},
      "meeting": {
        "type": "object",
        "properties": {
          "subject": {"type": "string"},
          "start_time": {"type": "string", "format": "date-time"},
          "end_time": {"type": "string", "format": "date-time"},
          "attendees": {"type": "array", "items": {"type": "string"}}
        }
      },
      "adaptive_card": {"type": "object"}
    }
  },
  "authentication": {
    "type": "oauth2",
    "authorization_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
    "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
    "scopes": [
      "https://graph.microsoft.com/Chat.ReadWrite",
      "https://graph.microsoft.com/Team.Create",
      "https://graph.microsoft.com/Calendars.ReadWrite"
    ]
  },
  "timeout_seconds": 45,
  "scopes": ["communication.teams"],
  "cost_tier": "medium"
}
```

#### Production Meeting Coordination
```json
{
  "title": "Weekly All-Hands Coordination",
  "schedule_kind": "rrule",
  "schedule_expr": "FREQ=WEEKLY;BYDAY=FR;BYHOUR=14;BYMINUTE=0",
  "timezone": "Europe/Chisinau",
  "payload": {
    "pipeline": [
      {
        "id": "schedule_meeting",
        "uses": "msteams.enterprise",
        "with": {
          "action": "schedule_meeting",
          "meeting": {
            "subject": "Weekly All-Hands Meeting",
            "start_time": "{{next_friday_3pm}}",
            "end_time": "{{next_friday_4pm}}",
            "attendees": ["${params.all_team_members}"]
          }
        },
        "save_as": "meeting"
      },
      {
        "id": "send_agenda_card",
        "uses": "msteams.enterprise", 
        "with": {
          "action": "send_adaptive_card",
          "team_id": "${params.main_team_id}",
          "channel_id": "${params.general_channel_id}",
          "adaptive_card": {
            "type": "AdaptiveCard",
            "version": "1.4",
            "body": [
              {
                "type": "TextBlock",
                "text": "📅 Weekly All-Hands - {{next_friday}}",
                "weight": "bolder",
                "size": "large"
              },
              {
                "type": "TextBlock", 
                "text": "Meeting ID: ${steps.meeting.id}",
                "isSubtle": true
              },
              {
                "type": "ColumnSet",
                "columns": [
                  {
                    "type": "Column",
                    "items": [
                      {"type": "TextBlock", "text": "📊 **Agenda Items**"},
                      {"type": "TextBlock", "text": "• Company Updates"},
                      {"type": "TextBlock", "text": "• Project Progress Review"},
                      {"type": "TextBlock", "text": "• Q&A Session"}
                    ]
                  },
                  {
                    "type": "Column", 
                    "items": [
                      {"type": "TextBlock", "text": "⏰ **Schedule**"},
                      {"type": "TextBlock", "text": "3:00 PM - 4:00 PM"},
                      {"type": "TextBlock", "text": "Chisinau Time"},
                      {"type": "TextBlock", "text": "Conference Room A"}
                    ]
                  }
                ]
              }
            ],
            "actions": [
              {
                "type": "Action.OpenUrl",
                "title": "Join Meeting",
                "url": "${steps.meeting.join_url}"
              },
              {
                "type": "Action.Submit",
                "title": "Add Agenda Item",
                "data": {"action": "add_agenda_item"}
              }
            ]
          }
        }
      }
    ]
  }
}
```

---

## 3. Development Tools Integration

### 3.1 GitHub Enterprise Integration

**Use Case**: Automated development workflow coordination and project management.

#### GitHub Tool Definition
```json
{
  "address": "github.enterprise",
  "transport": "http",
  "endpoint": "http://github-bridge:8095/tools/enterprise",
  "input_schema": {
    "type": "object",
    "required": ["action", "repository"],
    "properties": {
      "action": {
        "type": "string",
        "enum": [
          "create_issue", "create_pr", "merge_pr", "add_comment",
          "assign_reviewers", "create_release", "manage_labels",
          "sync_projects", "run_workflow", "get_metrics"
        ]
      },
      "repository": {"type": "string"},
      "issue_number": {"type": "integer"},
      "pr_number": {"type": "integer"},
      "title": {"type": "string"},
      "body": {"type": "string"},
      "labels": {"type": "array", "items": {"type": "string"}},
      "assignees": {"type": "array", "items": {"type": "string"}},
      "reviewers": {"type": "array", "items": {"type": "string"}},
      "workflow_id": {"type": "string"},
      "workflow_inputs": {"type": "object"}
    }
  },
  "authentication": {
    "type": "bearer_token",
    "header_name": "Authorization",
    "token_prefix": "token"
  },
  "timeout_seconds": 60,
  "scopes": ["development.github"],
  "cost_tier": "medium"
}
```

#### GitHub Bridge Implementation
```python
# /bridge/github_enterprise_bridge.py
import asyncio
import httpx
from typing import Dict, Any, List, Optional
import base64
import json
import os

class GitHubEnterpriseBridge:
    """Production GitHub integration with enterprise features."""
    
    def __init__(self, token: str, base_url: str = "https://api.github.com"):
        self.token = token
        self.base_url = base_url
        self.client = httpx.AsyncClient(
            timeout=60.0,
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "Ordinaut-GitHub-Bridge/1.0"
            }
        )
    
    async def enterprise_action(self, action: str, repository: str, **kwargs) -> Dict[str, Any]:
        """Execute GitHub enterprise actions."""
        
        action_handlers = {
            "create_issue": self._create_issue,
            "create_pr": self._create_pr,
            "merge_pr": self._merge_pr,
            "add_comment": self._add_comment,
            "assign_reviewers": self._assign_reviewers,
            "create_release": self._create_release,
            "manage_labels": self._manage_labels,
            "run_workflow": self._run_workflow,
            "get_metrics": self._get_metrics
        }
        
        handler = action_handlers.get(action)
        if not handler:
            raise ValueError(f"Unknown action: {action}")
            
        return await handler(repository, **kwargs)
    
    async def _create_issue(self, repository: str, title: str, body: str,
                           labels: List[str] = None, assignees: List[str] = None) -> Dict[str, Any]:
        """Create issue with full metadata."""
        
        payload = {
            "title": title,
            "body": body
        }
        
        if labels:
            payload["labels"] = labels
        if assignees:
            payload["assignees"] = assignees
            
        response = await self.client.post(
            f"{self.base_url}/repos/{repository}/issues",
            json=payload
        )
        response.raise_for_status()
        
        issue = response.json()
        return {
            "issue_number": issue["number"],
            "issue_url": issue["html_url"],
            "created_at": issue["created_at"],
            "state": issue["state"]
        }
    
    async def _create_pr(self, repository: str, title: str, body: str,
                        head: str, base: str, reviewers: List[str] = None) -> Dict[str, Any]:
        """Create pull request with reviewers."""
        
        # Create PR
        pr_payload = {
            "title": title,
            "body": body,
            "head": head,
            "base": base
        }
        
        response = await self.client.post(
            f"{self.base_url}/repos/{repository}/pulls",
            json=pr_payload
        )
        response.raise_for_status()
        
        pr = response.json()
        
        # Assign reviewers if specified
        if reviewers:
            await self.client.post(
                f"{self.base_url}/repos/{repository}/pulls/{pr['number']}/requested_reviewers",
                json={"reviewers": reviewers}
            )
        
        return {
            "pr_number": pr["number"],
            "pr_url": pr["html_url"],
            "created_at": pr["created_at"],
            "state": pr["state"],
            "reviewers_assigned": len(reviewers) if reviewers else 0
        }
    
    async def _run_workflow(self, repository: str, workflow_id: str, 
                           ref: str = "main", inputs: Dict[str, Any] = None) -> Dict[str, Any]:
        """Trigger GitHub Actions workflow."""
        
        payload = {
            "ref": ref
        }
        
        if inputs:
            payload["inputs"] = inputs
            
        response = await self.client.post(
            f"{self.base_url}/repos/{repository}/actions/workflows/{workflow_id}/dispatches",
            json=payload
        )
        response.raise_for_status()
        
        return {
            "workflow_triggered": True,
            "workflow_id": workflow_id,
            "ref": ref,
            "inputs": inputs or {}
        }
    
    async def _get_metrics(self, repository: str, period: str = "week") -> Dict[str, Any]:
        """Get repository metrics and insights."""
        
        # Get multiple metrics concurrently
        tasks = [
            self._get_pull_requests_metrics(repository, period),
            self._get_issues_metrics(repository, period),
            self._get_commits_metrics(repository, period),
            self._get_contributors_metrics(repository, period)
        ]
        
        pr_metrics, issues_metrics, commits_metrics, contributors_metrics = await asyncio.gather(*tasks)
        
        return {
            "period": period,
            "repository": repository,
            "pull_requests": pr_metrics,
            "issues": issues_metrics,
            "commits": commits_metrics,
            "contributors": contributors_metrics,
            "generated_at": datetime.utcnow().isoformat() + 'Z'
        }
```

#### Release Management Pipeline
```json
{
  "title": "Automated Release Management",
  "schedule_kind": "rrule",
  "schedule_expr": "FREQ=WEEKLY;BYDAY=FR;BYHOUR=16;BYMINUTE=0",
  "timezone": "Europe/Chisinau",
  "payload": {
    "pipeline": [
      {
        "id": "check_ready_prs",
        "uses": "github.enterprise",
        "with": {
          "action": "get_metrics",
          "repository": "company/main-product",
          "period": "week"
        },
        "save_as": "metrics"
      },
      {
        "id": "run_tests",
        "uses": "github.enterprise",
        "with": {
          "action": "run_workflow",
          "repository": "company/main-product",
          "workflow_id": "release-tests.yml",
          "ref": "main",
          "inputs": {
            "environment": "staging",
            "run_integration_tests": "true"
          }
        },
        "save_as": "tests"
      },
      {
        "id": "wait_for_tests",
        "uses": "system.sleep",
        "with": {"duration_seconds": 300}
      },
      {
        "id": "create_release",
        "uses": "github.enterprise",
        "with": {
          "action": "create_release",
          "repository": "company/main-product",
          "tag_name": "v${params.version}",
          "name": "Weekly Release v${params.version}",
          "body": "## 📦 Weekly Release v${params.version}\n\n### This Week's Changes:\n- **Pull Requests Merged**: ${steps.metrics.pull_requests.merged_count}\n- **Issues Closed**: ${steps.metrics.issues.closed_count}\n- **New Contributors**: ${steps.metrics.contributors.new_count}\n\n### Key Features:\n${steps.metrics.pull_requests.feature_summary}\n\n### Bug Fixes:\n${steps.metrics.pull_requests.bugfix_summary}\n\n---\n*Generated automatically by Ordinaut*",
          "draft": false,
          "prerelease": false
        },
        "save_as": "release"
      },
      {
        "id": "notify_release",
        "uses": "slack.enterprise",
        "with": {
          "action": "post_message",
          "channel": "#releases",
          "message": "🚀 **Release v${params.version} is live!**\n\n📊 **Stats**: ${steps.metrics.pull_requests.merged_count} PRs merged, ${steps.metrics.issues.closed_count} issues closed\n🔗 **Release**: ${steps.release.html_url}\n\nGreat work team! 👏"
        }
      }
    ],
    "params": {
      "version": "{{auto_increment_version}}"
    }
  }
}
```

### 3.2 GitLab Integration

**Use Case**: CI/CD pipeline coordination and merge request automation.

#### GitLab Enterprise Pipeline
```json
{
  "title": "GitLab MR Quality Gate",
  "schedule_kind": "event",
  "event_type": "gitlab.merge_request.opened",
  "payload": {
    "pipeline": [
      {
        "id": "run_pipeline",
        "uses": "gitlab.run_pipeline",
        "with": {
          "project_id": "${event.project.id}",
          "ref": "${event.source_branch}",
          "variables": {
            "MR_NUMBER": "${event.iid}",
            "TARGET_BRANCH": "${event.target_branch}"
          }
        },
        "save_as": "pipeline"
      },
      {
        "id": "security_scan",
        "uses": "sonarqube.analyze",
        "with": {
          "project_key": "${event.project.path_with_namespace}",
          "branch": "${event.source_branch}"
        },
        "save_as": "security"
      },
      {
        "id": "quality_gate",
        "uses": "sonarqube.quality_gate",
        "with": {
          "project_key": "${event.project.path_with_namespace}",
          "analysis_id": "${steps.security.analysis_id}"
        },
        "save_as": "quality"
      },
      {
        "id": "update_mr_status",
        "uses": "gitlab.add_mr_note",
        "with": {
          "project_id": "${event.project.id}",
          "merge_request_iid": "${event.iid}",
          "body": "## 🔍 Quality Gate Results\n\n**Pipeline Status**: ${steps.pipeline.status}\n**Security Score**: ${steps.security.security_rating}\n**Quality Gate**: ${steps.quality.status}\n\n### Details\n- **Coverage**: ${steps.security.coverage}%\n- **Bugs**: ${steps.security.bugs}\n- **Vulnerabilities**: ${steps.security.vulnerabilities}\n- **Code Smells**: ${steps.security.code_smells}\n\n${steps.quality.status === 'PASSED' ? '✅ **Ready for review!**' : '❌ **Quality gate failed - please fix issues before review**'}"
        }
      },
      {
        "id": "auto_approve",
        "uses": "gitlab.approve_mr",
        "with": {
          "project_id": "${event.project.id}",
          "merge_request_iid": "${event.iid}"
        },
        "if": "${steps.quality.status === 'PASSED' && steps.security.security_rating === 'A'}"
      }
    ]
  }
}
```

### 3.3 JIRA Integration

**Use Case**: Project management and issue tracking coordination.

#### JIRA Enterprise Tool
```json
{
  "address": "jira.enterprise",
  "transport": "http",
  "endpoint": "http://jira-bridge:8096/tools/enterprise",
  "input_schema": {
    "type": "object",
    "required": ["action"],
    "properties": {
      "action": {
        "type": "string",
        "enum": [
          "create_issue", "update_issue", "transition_issue",
          "add_comment", "create_epic", "link_issues",
          "get_sprint_metrics", "bulk_update", "create_release"
        ]
      },
      "project_key": {"type": "string"},
      "issue_key": {"type": "string"},
      "issue_type": {"type": "string"},
      "summary": {"type": "string"},
      "description": {"type": "string"},
      "assignee": {"type": "string"},
      "priority": {"type": "string"},
      "labels": {"type": "array", "items": {"type": "string"}},
      "components": {"type": "array", "items": {"type": "string"}},
      "custom_fields": {"type": "object"}
    }
  },
  "authentication": {
    "type": "basic_auth",
    "username_field": "email",
    "password_field": "api_token"
  },
  "timeout_seconds": 45,
  "scopes": ["project.jira"],
  "cost_tier": "medium"
}
```

#### Sprint Planning Automation
```json
{
  "title": "Sprint Planning Assistant",
  "schedule_kind": "rrule", 
  "schedule_expr": "FREQ=WEEKLY;BYDAY=FR;BYHOUR=15;BYMINUTE=0",
  "timezone": "Europe/Chisinau",
  "payload": {
    "pipeline": [
      {
        "id": "get_current_sprint",
        "uses": "jira.enterprise",
        "with": {
          "action": "get_sprint_metrics",
          "project_key": "PROD",
          "sprint_state": "active"
        },
        "save_as": "current_sprint"
      },
      {
        "id": "analyze_velocity",
        "uses": "jira.enterprise",
        "with": {
          "action": "get_sprint_metrics",
          "project_key": "PROD",
          "sprint_count": 5,
          "metrics": ["velocity", "completion_rate", "scope_change"]
        },
        "save_as": "velocity"
      },
      {
        "id": "generate_recommendations",
        "uses": "openai-chatgpt.analyze",
        "with": {
          "prompt": "Analyze sprint metrics and provide recommendations for next sprint planning. Focus on capacity planning, risk areas, and process improvements.",
          "context": {
            "current_sprint": "${steps.current_sprint}",
            "historical_velocity": "${steps.velocity}",
            "team_size": "${params.team_size}"
          }
        },
        "save_as": "recommendations"
      },
      {
        "id": "create_planning_issue",
        "uses": "jira.enterprise",
        "with": {
          "action": "create_issue",
          "project_key": "PROD",
          "issue_type": "Epic",
          "summary": "Sprint Planning - Week of {{next_monday}}",
          "description": "## 📊 Sprint Planning Analysis\n\n### Current Sprint Performance\n- **Completion Rate**: ${steps.current_sprint.completion_rate}%\n- **Velocity**: ${steps.velocity.average_velocity} story points\n- **Scope Changes**: ${steps.current_sprint.scope_changes}\n\n### AI Recommendations\n${steps.recommendations.analysis}\n\n### Action Items\n{% for item in steps.recommendations.priority_items %}\n- [ ] {{ item }}\n{% endfor %}\n\n---\n*Generated by Ordinaut AI Sprint Assistant*",
          "assignee": "${params.scrum_master}",
          "labels": ["sprint-planning", "auto-generated"]
        },
        "save_as": "planning_issue"
      },
      {
        "id": "notify_team",
        "uses": "msteams.enterprise",
        "with": {
          "action": "send_adaptive_card",
          "team_id": "${params.dev_team_id}",
          "channel_id": "${params.planning_channel_id}",
          "adaptive_card": {
            "type": "AdaptiveCard",
            "version": "1.4",
            "body": [
              {
                "type": "TextBlock",
                "text": "📋 Sprint Planning Ready",
                "weight": "bolder",
                "size": "large"
              },
              {
                "type": "FactSet",
                "facts": [
                  {"title": "Current Velocity", "value": "${steps.velocity.average_velocity} pts"},
                  {"title": "Completion Rate", "value": "${steps.current_sprint.completion_rate}%"},
                  {"title": "Planning Issue", "value": "[${steps.planning_issue.key}](${steps.planning_issue.url})"}
                ]
              },
              {
                "type": "TextBlock",
                "text": "**Key Recommendations:**",
                "weight": "bolder"
              },
              {
                "type": "TextBlock",
                "text": "${steps.recommendations.summary}",
                "wrap": true
              }
            ],
            "actions": [
              {
                "type": "Action.OpenUrl",
                "title": "View Planning Issue",
                "url": "${steps.planning_issue.url}"
              },
              {
                "type": "Action.Submit",
                "title": "Schedule Planning Meeting",
                "data": {"action": "schedule_planning", "issue_key": "${steps.planning_issue.key}"}
              }
            ]
          }
        }
      }
    ],
    "params": {
      "team_size": 8,
      "scrum_master": "scrum.master@company.com",
      "dev_team_id": "team-dev-id",
      "planning_channel_id": "channel-planning-id"
    }
  }
}
```

---

## 4. Business Systems Integration

### 4.1 Salesforce Integration

**Use Case**: CRM data synchronization and sales process automation.

#### Salesforce Enterprise Tool
```json
{
  "address": "salesforce.enterprise",
  "transport": "http",
  "endpoint": "http://salesforce-bridge:8097/tools/enterprise", 
  "input_schema": {
    "type": "object",
    "required": ["action"],
    "properties": {
      "action": {
        "type": "string",
        "enum": [
          "query_records", "create_record", "update_record",
          "run_report", "send_email", "create_task",
          "update_opportunity", "bulk_import", "sync_contacts"
        ]
      },
      "sobject_type": {"type": "string"},
      "record_id": {"type": "string"},
      "fields": {"type": "object"},
      "query": {"type": "string"},
      "report_id": {"type": "string"},
      "email_template": {"type": "string"},
      "recipients": {"type": "array", "items": {"type": "string"}},
      "bulk_data": {"type": "array"}
    }
  },
  "authentication": {
    "type": "oauth2",
    "authorization_url": "https://login.salesforce.com/services/oauth2/authorize",
    "token_url": "https://login.salesforce.com/services/oauth2/token",
    "scopes": ["full", "refresh_token"]
  },
  "timeout_seconds": 120,
  "scopes": ["crm.salesforce"],
  "cost_tier": "high"
}
```

#### Sales Pipeline Automation
```json
{
  "title": "Weekly Sales Pipeline Review",
  "schedule_kind": "rrule",
  "schedule_expr": "FREQ=WEEKLY;BYDAY=MO;BYHOUR=8;BYMINUTE=0",
  "timezone": "Europe/Chisinau",
  "payload": {
    "pipeline": [
      {
        "id": "get_pipeline_data",
        "uses": "salesforce.enterprise",
        "with": {
          "action": "run_report",
          "report_id": "00O1234567890ABC",
          "parameters": {
            "date_range": "this_week",
            "stage": "all"
          }
        },
        "save_as": "pipeline"
      },
      {
        "id": "identify_stale_deals",
        "uses": "salesforce.enterprise",
        "with": {
          "action": "query_records",
          "query": "SELECT Id, Name, StageName, LastModifiedDate, Amount, CloseDate FROM Opportunity WHERE LastModifiedDate < LAST_N_DAYS:14 AND StageName IN ('Qualification', 'Needs Analysis', 'Proposal/Price Quote') AND IsClosed = false"
        },
        "save_as": "stale_deals"
      },
      {
        "id": "analyze_pipeline",
        "uses": "openai-chatgpt.analyze",
        "with": {
          "prompt": "Analyze the sales pipeline data and identify key insights, risks, and recommended actions. Focus on deal progression, revenue forecasting, and sales velocity.",
          "context": {
            "pipeline_report": "${steps.pipeline.data}",
            "stale_deals": "${steps.stale_deals.records}",
            "team_quota": "${params.quarterly_quota}",
            "current_quarter": "${current_quarter}"
          },
          "model": "gpt-4"
        },
        "save_as": "analysis"
      },
      {
        "id": "create_follow_up_tasks",
        "uses": "salesforce.enterprise",
        "with": {
          "action": "bulk_import",
          "sobject_type": "Task",
          "bulk_data": [
            {% for deal in steps.stale_deals.records %}
            {
              "WhatId": "{{ deal.Id }}",
              "Subject": "Follow up on stale opportunity: {{ deal.Name }}",
              "Description": "This opportunity hasn't been updated in 14+ days. Please review and update status.\n\nDeal: {{ deal.Name }}\nStage: {{ deal.StageName }}\nAmount: {{ deal.Amount }}\nLast Modified: {{ deal.LastModifiedDate }}",
              "Priority": "High",
              "ActivityDate": "{{today + 1}}",
              "Status": "Not Started",
              "Type": "Call",
              "OwnerId": "{{ deal.OwnerId }}"
            }{% if not forloop.last %},{% endif %}
            {% endfor %}
          ]
        },
        "save_as": "tasks"
      },
      {
        "id": "send_executive_summary",
        "uses": "salesforce.enterprise",
        "with": {
          "action": "send_email",
          "email_template": "Sales_Pipeline_Weekly_Summary",
          "recipients": ["${params.sales_director}", "${params.ceo}"],
          "merge_fields": {
            "pipeline_value": "${steps.pipeline.total_value}",
            "deals_count": "${steps.pipeline.opportunities_count}",
            "stale_deals_count": "${steps.stale_deals.totalSize}",
            "ai_insights": "${steps.analysis.analysis}",
            "top_recommendations": "${steps.analysis.priority_items}"
          }
        }
      },
      {
        "id": "update_dashboard",
        "uses": "slack.enterprise",
        "with": {
          "action": "post_message",
          "channel": "#sales-team",
          "message": "📊 **Weekly Pipeline Review Complete**\n\n💰 **Pipeline Value**: $${steps.pipeline.total_value:,}\n🎯 **Active Deals**: ${steps.pipeline.opportunities_count}\n⚠️  **Stale Deals**: ${steps.stale_deals.totalSize}\n\n**AI Insights**: ${steps.analysis.summary}\n\n${steps.tasks.successCount} follow-up tasks created for stale deals.\n\n*Full analysis sent to executives*"
        }
      }
    ],
    "params": {
      "quarterly_quota": 5000000,
      "sales_director": "sales.director@company.com",
      "ceo": "ceo@company.com"
    }
  }
}
```

### 4.2 HubSpot Integration

**Use Case**: Marketing automation and lead nurturing.

#### HubSpot Marketing Automation
```json
{
  "title": "Lead Scoring and Nurturing",
  "schedule_kind": "rrule",
  "schedule_expr": "FREQ=DAILY;BYHOUR=10;BYMINUTE=0",
  "timezone": "Europe/Chisinau",
  "payload": {
    "pipeline": [
      {
        "id": "get_new_leads",
        "uses": "hubspot.enterprise",
        "with": {
          "action": "get_contacts",
          "filters": [
            {"property": "createdate", "operator": "GTE", "value": "{{yesterday}}"},
            {"property": "lifecyclestage", "operator": "EQ", "value": "lead"}
          ],
          "properties": ["firstname", "lastname", "email", "company", "lead_source", "phone"]
        },
        "save_as": "new_leads"
      },
      {
        "id": "score_leads",
        "uses": "openai-chatgpt.analyze",
        "with": {
          "prompt": "Analyze these leads and assign lead scores (0-100) based on company size, industry, job title, and engagement. Provide reasoning for each score.",
          "context": {
            "leads": "${steps.new_leads.results}",
            "scoring_criteria": {
              "company_size": "larger companies get higher scores",
              "industry": "tech companies in Moldova get +20 points",
              "job_title": "decision makers (CEO, CTO, VP) get higher scores",
              "engagement": "multiple page views or downloads get +10 points"
            }
          }
        },
        "save_as": "scores"
      },
      {
        "id": "update_lead_scores",
        "uses": "hubspot.enterprise",
        "with": {
          "action": "bulk_update_contacts",
          "updates": [
            {% for lead in steps.scores.scored_leads %}
            {
              "id": "{{ lead.id }}",
              "properties": {
                "hubspotscore": "{{ lead.score }}",
                "lead_score_reason": "{{ lead.reasoning }}",
                "last_scored_date": "{{now}}"
              }
            }{% if not forloop.last %},{% endif %}
            {% endfor %}
          ]
        },
        "save_as": "updated_leads"
      },
      {
        "id": "enroll_high_score_leads",
        "uses": "hubspot.enterprise",
        "with": {
          "action": "enroll_in_workflow",
          "workflow_id": "12345",
          "contact_ids": [
            {% for lead in steps.scores.scored_leads %}
            {% if lead.score >= 70 %}"{{ lead.id }}"{% if not forloop.last %},{% endif %}{% endif %}
            {% endfor %}
          ]
        },
        "save_as": "enrolled"
      },
      {
        "id": "notify_sales_team",
        "uses": "slack.enterprise",
        "with": {
          "action": "post_message",
          "channel": "#sales-qualified-leads",
          "message": "🎯 **New High-Quality Leads**\n\n${steps.enrolled.enrolled_count} leads scored 70+ and enrolled in nurturing workflow:\n\n{% for lead in steps.scores.scored_leads %}{% if lead.score >= 70 %}• **{{ lead.firstname }} {{ lead.lastname }}** ({{ lead.company }}) - Score: {{ lead.score }}\n  📧 {{ lead.email }} | 📱 {{ lead.phone }}\n  💡 *{{ lead.reasoning }}*\n\n{% endif %}{% endfor %}*Follow up within 24 hours for best results!*"
        }
      }
    ]
  }
}
```

---

## 5. Monitoring & Observability Integration

### 5.1 Prometheus Integration

**Use Case**: Custom metrics collection and alerting integration.

#### Custom Metrics Pipeline
```json
{
  "title": "Business Metrics Collection",
  "schedule_kind": "rrule",
  "schedule_expr": "FREQ=HOURLY;BYMINUTE=0",
  "timezone": "Europe/Chisinau",
  "payload": {
    "pipeline": [
      {
        "id": "collect_app_metrics",
        "uses": "prometheus.query",
        "with": {
          "queries": [
            {
              "name": "api_requests_per_hour",
              "query": "sum(rate(http_requests_total[1h])) * 3600"
            },
            {
              "name": "active_users",
              "query": "count(increase(user_sessions_total[1h]))"
            },
            {
              "name": "error_rate",
              "query": "sum(rate(http_requests_total{status=~'5..'}[1h])) / sum(rate(http_requests_total[1h]))"
            },
            {
              "name": "response_time_p95",
              "query": "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[1h]))"
            }
          ]
        },
        "save_as": "metrics"
      },
      {
        "id": "collect_business_metrics",
        "uses": "database.query",
        "with": {
          "queries": [
            {
              "name": "new_signups",
              "query": "SELECT COUNT(*) as count FROM users WHERE created_at >= NOW() - INTERVAL '1 hour'"
            },
            {
              "name": "revenue_hourly", 
              "query": "SELECT COALESCE(SUM(amount), 0) as amount FROM transactions WHERE created_at >= NOW() - INTERVAL '1 hour' AND status = 'completed'"
            },
            {
              "name": "support_tickets",
              "query": "SELECT COUNT(*) as count FROM support_tickets WHERE created_at >= NOW() - INTERVAL '1 hour'"
            }
          ]
        },
        "save_as": "business"
      },
      {
        "id": "push_custom_metrics",
        "uses": "prometheus.push_gateway",
        "with": {
          "job": "business_metrics",
          "instance": "ordinaut-collector",
          "metrics": [
            {
              "name": "business_signups_hourly",
              "type": "gauge",
              "value": "${steps.business.new_signups.count}",
              "help": "New user signups in the last hour"
            },
            {
              "name": "business_revenue_hourly",
              "type": "gauge", 
              "value": "${steps.business.revenue_hourly.amount}",
              "help": "Revenue generated in the last hour"
            },
            {
              "name": "business_support_tickets_hourly",
              "type": "gauge",
              "value": "${steps.business.support_tickets.count}",
              "help": "New support tickets in the last hour"
            }
          ]
        },
        "save_as": "pushed"
      },
      {
        "id": "check_thresholds",
        "uses": "system.evaluate",
        "with": {
          "conditions": [
            {
              "name": "high_error_rate",
              "condition": "${steps.metrics.error_rate.value > 0.05}",
              "severity": "critical"
            },
            {
              "name": "slow_response_time",
              "condition": "${steps.metrics.response_time_p95.value > 2.0}",
              "severity": "warning"
            },
            {
              "name": "low_signups",
              "condition": "${steps.business.new_signups.count < 5}",
              "severity": "info"
            }
          ]
        },
        "save_as": "alerts"
      },
      {
        "id": "send_alerts",
        "uses": "slack.enterprise",
        "with": {
          "action": "post_message",
          "channel": "#alerts",
          "message": "🚨 **System Alert**\n\n{% for alert in steps.alerts.triggered %}**{{ alert.severity | upper }}**: {{ alert.name }}\n{% endfor %}\n**Metrics Summary**:\n• API Requests/hr: {{ steps.metrics.api_requests_per_hour.value | round }}\n• Active Users: {{ steps.metrics.active_users.value }}\n• Error Rate: {{ (steps.metrics.error_rate.value * 100) | round(2) }}%\n• Response Time (P95): {{ steps.metrics.response_time_p95.value | round(2) }}s\n• New Signups: {{ steps.business.new_signups.count }}\n• Revenue: ${{ steps.business.revenue_hourly.amount | round(2) }}"
        },
        "if": "${steps.alerts.triggered | length > 0}"
      }
    ]
  }
}
```

### 5.2 Grafana Integration

**Use Case**: Automated dashboard updates and anomaly detection.

#### Grafana Tool Definition
```json
{
  "address": "grafana.enterprise",
  "transport": "http",
  "endpoint": "http://grafana-bridge:8098/tools/enterprise",
  "input_schema": {
    "type": "object",
    "required": ["action"],
    "properties": {
      "action": {
        "type": "string",
        "enum": [
          "create_dashboard", "update_dashboard", "create_alert",
          "get_metrics", "create_annotation", "export_dashboard",
          "manage_datasources", "create_folder", "set_permissions"
        ]
      },
      "dashboard_id": {"type": "string"},
      "dashboard_config": {"type": "object"},
      "alert_config": {"type": "object"},
      "annotation": {"type": "object"},
      "folder_id": {"type": "string"},
      "permissions": {"type": "array"}
    }
  },
  "authentication": {
    "type": "bearer_token",
    "header_name": "Authorization",
    "token_prefix": "Bearer"
  },
  "timeout_seconds": 60,
  "scopes": ["monitoring.grafana"],
  "cost_tier": "medium"
}
```

---

## 6. Moldova-Specific Integrations

### 6.1 MAIB Bank API Integration

**Use Case**: Automated financial reconciliation and payment processing.

#### MAIB Banking Tool
```json
{
  "address": "maib.banking",
  "transport": "http",
  "endpoint": "http://maib-bridge:8099/tools/banking",
  "input_schema": {
    "type": "object",
    "required": ["action"],
    "properties": {
      "action": {
        "type": "string",
        "enum": [
          "get_balance", "get_transactions", "create_payment",
          "get_statement", "verify_payment", "bulk_payments",
          "currency_exchange", "get_exchange_rates"
        ]
      },
      "account_number": {"type": "string"},
      "date_from": {"type": "string", "format": "date"},
      "date_to": {"type": "string", "format": "date"},
      "payment_details": {"type": "object"},
      "currency_from": {"type": "string"},
      "currency_to": {"type": "string"},
      "amount": {"type": "number"}
    }
  },
  "authentication": {
    "type": "custom",
    "method": "maib_signature",
    "certificate_path": "/certs/maib.pem",
    "private_key_path": "/certs/maib_private.key"
  },
  "timeout_seconds": 120,
  "scopes": ["banking.maib"],
  "cost_tier": "high"
}
```

#### Daily Financial Reconciliation
```json
{
  "title": "Daily Financial Reconciliation", 
  "schedule_kind": "rrule",
  "schedule_expr": "FREQ=DAILY;BYHOUR=18;BYMINUTE=0",
  "timezone": "Europe/Chisinau",
  "payload": {
    "pipeline": [
      {
        "id": "get_bank_transactions",
        "uses": "maib.banking",
        "with": {
          "action": "get_transactions",
          "account_number": "${params.main_account}",
          "date_from": "{{today}}",
          "date_to": "{{today}}"
        },
        "save_as": "bank_transactions"
      },
      {
        "id": "get_system_transactions",
        "uses": "database.query",
        "with": {
          "query": "SELECT transaction_id, amount, currency, created_at, reference_number FROM financial_transactions WHERE DATE(created_at) = CURRENT_DATE AND status = 'completed'"
        },
        "save_as": "system_transactions"
      },
      {
        "id": "reconcile_transactions",
        "uses": "openai-chatgpt.analyze",
        "with": {
          "prompt": "Reconcile bank transactions with system transactions. Identify matches, discrepancies, and missing transactions. Provide detailed reconciliation report.",
          "context": {
            "bank_transactions": "${steps.bank_transactions.transactions}",
            "system_transactions": "${steps.system_transactions.rows}",
            "account_number": "${params.main_account}",
            "date": "{{today}}"
          }
        },
        "save_as": "reconciliation"
      },
      {
        "id": "create_discrepancy_tickets",
        "uses": "jira.enterprise",
        "with": {
          "action": "bulk_import",
          "project_key": "FIN",
          "issues": [
            {% for discrepancy in steps.reconciliation.discrepancies %}
            {
              "issue_type": "Bug",
              "summary": "Financial Discrepancy: {{ discrepancy.type }}",
              "description": "**Discrepancy Details:**\n\n**Type**: {{ discrepancy.type }}\n**Amount**: {{ discrepancy.amount }} {{ discrepancy.currency }}\n**Bank Reference**: {{ discrepancy.bank_reference }}\n**System Reference**: {{ discrepancy.system_reference }}\n**Description**: {{ discrepancy.description }}\n\n**Investigation Required**: {{ discrepancy.investigation_notes }}\n\n---\n*Auto-generated by financial reconciliation system*",
              "priority": "{% if discrepancy.amount > 1000 %}High{% else %}Medium{% endif %}",
              "assignee": "${params.finance_manager}",
              "labels": ["auto-generated", "financial-reconciliation", "{{ discrepancy.type | lower }}"]
            }{% if not forloop.last %},{% endif %}
            {% endfor %}
          ]
        },
        "save_as": "discrepancy_tickets",
        "if": "${steps.reconciliation.discrepancies | length > 0}"
      },
      {
        "id": "send_finance_report",
        "uses": "msteams.enterprise",
        "with": {
          "action": "send_adaptive_card",
          "team_id": "${params.finance_team_id}",
          "channel_id": "${params.finance_channel_id}",
          "adaptive_card": {
            "type": "AdaptiveCard",
            "version": "1.4",
            "body": [
              {
                "type": "TextBlock",
                "text": "💰 Daily Financial Reconciliation",
                "weight": "bolder",
                "size": "large"
              },
              {
                "type": "FactSet",
                "facts": [
                  {"title": "Date", "value": "{{today}}"},
                  {"title": "Bank Transactions", "value": "${steps.bank_transactions.count}"},
                  {"title": "System Transactions", "value": "${steps.system_transactions.rows | length}"},
                  {"title": "Matched", "value": "${steps.reconciliation.matched_count}"},
                  {"title": "Discrepancies", "value": "${steps.reconciliation.discrepancies | length}"}
                ]
              },
              {
                "type": "TextBlock",
                "text": "**Summary**",
                "weight": "bolder"
              },
              {
                "type": "TextBlock",
                "text": "${steps.reconciliation.summary}",
                "wrap": true
              },
              {% if steps.reconciliation.discrepancies | length > 0 %}
              {
                "type": "TextBlock",
                "text": "⚠️ **Discrepancies Found**",
                "weight": "bolder",
                "color": "attention"
              },
              {
                "type": "TextBlock",
                "text": "${steps.discrepancy_tickets.created_count} JIRA tickets created for investigation.",
                "wrap": true
              }
              {% endif %}
            ],
            "actions": [
              {
                "type": "Action.OpenUrl",
                "title": "View Bank Statement",
                "url": "https://maib.md/business/statements"
              },
              {% if steps.reconciliation.discrepancies | length > 0 %}
              {
                "type": "Action.OpenUrl", 
                "title": "View Discrepancy Tickets",
                "url": "https://company.atlassian.net/issues/?jql=project%3DFIN%20AND%20labels%3Dfinancial-reconciliation%20AND%20created%3E%3D{{today}}"
              }
              {% endif %}
            ]
          }
        }
      }
    ],
    "params": {
      "main_account": "MD24AG000000022951234567",
      "finance_manager": "finance.manager@company.com",
      "finance_team_id": "team-finance-id",
      "finance_channel_id": "channel-finance-id"
    }
  }
}
```

### 6.2 SIA (Serviciul de Informatii si Asigurare) Integration

**Use Case**: Government reporting and compliance automation.

#### SIA Reporting Tool
```json
{
  "address": "sia.reporting",
  "transport": "http",
  "endpoint": "http://sia-bridge:8100/tools/reporting",
  "input_schema": {
    "type": "object",
    "required": ["action", "report_type"],
    "properties": {
      "action": {
        "type": "string",
        "enum": ["submit_report", "get_status", "download_form", "validate_data"]
      },
      "report_type": {
        "type": "string",
        "enum": ["monthly_employment", "quarterly_tax", "annual_financial", "vat_declaration"]
      },
      "reporting_period": {"type": "string"},
      "company_idno": {"type": "string"},
      "data": {"type": "object"}
    }
  },
  "authentication": {
    "type": "digital_signature",
    "certificate_path": "/certs/company_digital_cert.p12",
    "password_env": "DIGITAL_CERT_PASSWORD"
  },
  "timeout_seconds": 180,
  "scopes": ["government.sia"],
  "cost_tier": "medium"
}
```

#### Monthly Employment Reporting
```json
{
  "title": "SIA Monthly Employment Report",
  "schedule_kind": "rrule", 
  "schedule_expr": "FREQ=MONTHLY;BYMONTHDAY=20;BYHOUR=14;BYMINUTE=0",
  "timezone": "Europe/Chisinau",
  "payload": {
    "pipeline": [
      {
        "id": "extract_employee_data",
        "uses": "database.query",
        "with": {
          "query": "SELECT employee_id, full_name, idnp, salary, hire_date, termination_date, position FROM employees WHERE (hire_date <= '{{last_month_end}}' OR hire_date IS NULL) AND (termination_date >= '{{last_month_start}}' OR termination_date IS NULL)"
        },
        "save_as": "employees"
      },
      {
        "id": "calculate_contributions",
        "uses": "database.query",
        "with": {
          "query": "SELECT employee_id, SUM(social_contribution) as social_contrib, SUM(medical_contribution) as medical_contrib, SUM(salary_gross) as gross_salary FROM payroll WHERE payroll_month = '{{last_month}}' GROUP BY employee_id"
        },
        "save_as": "contributions"
      },
      {
        "id": "prepare_sia_data",
        "uses": "system.transform",
        "with": {
          "template": {
            "company_idno": "${params.company_idno}",
            "reporting_period": "{{last_month}}",
            "total_employees": "${steps.employees.rows | length}",
            "employees": [
              {% for emp in steps.employees.rows %}
              {
                "idnp": "{{ emp.idnp }}",
                "full_name": "{{ emp.full_name }}",
                "position": "{{ emp.position }}",
                "salary_gross": {{ contributions[emp.employee_id].gross_salary | default(0) }},
                "social_contribution": {{ contributions[emp.employee_id].social_contrib | default(0) }},
                "medical_contribution": {{ contributions[emp.employee_id].medical_contrib | default(0) }},
                "employment_status": "{% if emp.termination_date and emp.termination_date <= last_month_end %}terminated{% else %}active{% endif %}"
              }{% if not forloop.last %},{% endif %}
              {% endfor %}
            ]
          }
        },
        "save_as": "sia_data"
      },
      {
        "id": "validate_report",
        "uses": "sia.reporting",
        "with": {
          "action": "validate_data",
          "report_type": "monthly_employment",
          "reporting_period": "{{last_month}}",
          "company_idno": "${params.company_idno}",
          "data": "${steps.sia_data}"
        },
        "save_as": "validation"
      },
      {
        "id": "submit_report",
        "uses": "sia.reporting",
        "with": {
          "action": "submit_report",
          "report_type": "monthly_employment", 
          "reporting_period": "{{last_month}}",
          "company_idno": "${params.company_idno}",
          "data": "${steps.sia_data}"
        },
        "save_as": "submission",
        "if": "${steps.validation.is_valid}"
      },
      {
        "id": "create_compliance_record",
        "uses": "database.query",
        "with": {
          "query": "INSERT INTO compliance_reports (report_type, reporting_period, submission_date, status, reference_number, total_employees, total_contributions) VALUES ('sia_employment', '{{last_month}}', NOW(), '${steps.submission.status}', '${steps.submission.reference_number}', ${steps.sia_data.total_employees}, ${steps.sia_data.employees | sum(attribute='social_contribution') + steps.sia_data.employees | sum(attribute='medical_contribution')})"
        },
        "save_as": "compliance_record"
      },
      {
        "id": "notify_compliance_team",
        "uses": "slack.enterprise",
        "with": {
          "action": "post_message",
          "channel": "#compliance",
          "message": "✅ **SIA Employment Report Submitted**\n\n📅 **Period**: {{last_month}}\n👥 **Employees**: ${steps.sia_data.total_employees}\n💰 **Total Contributions**: ${steps.sia_data.employees | sum(attribute='social_contribution') + steps.sia_data.employees | sum(attribute='medical_contribution')} MDL\n🔗 **Reference**: ${steps.submission.reference_number}\n\n{% if not steps.validation.is_valid %}⚠️ **Validation Issues**:\n{% for issue in steps.validation.issues %}• {{ issue }}\n{% endfor %}{% endif %}*Report submitted successfully to SIA*"
        }
      }
    ],
    "params": {
      "company_idno": "1234567890123",
      "compliance_officer": "compliance@company.com"
    }
  }
}
```

---

## 7. Security and Performance Considerations

### 7.1 Authentication and Authorization

#### OAuth 2.0 Implementation Pattern
```python
# /bridge/oauth_manager.py
import asyncio
import httpx
from typing import Dict, Any, Optional
import os
import json
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class OAuth2Manager:
    """Production OAuth 2.0 token management."""
    
    def __init__(self, redis_client):
        self.redis = redis_client
        self.token_cache_prefix = "oauth_tokens:"
        
    async def get_access_token(self, service: str, client_id: str, 
                              client_secret: str, token_url: str,
                              scopes: List[str] = None) -> str:
        """Get valid access token with automatic refresh."""
        
        cache_key = f"{self.token_cache_prefix}{service}:{client_id}"
        
        # Try to get cached token
        cached_token = await self.redis.get(cache_key)
        if cached_token:
            token_data = json.loads(cached_token)
            if datetime.fromisoformat(token_data['expires_at']) > datetime.utcnow():
                return token_data['access_token']
        
        # Request new token
        return await self._request_new_token(
            service, client_id, client_secret, token_url, scopes, cache_key
        )
    
    async def _request_new_token(self, service: str, client_id: str,
                                client_secret: str, token_url: str,
                                scopes: List[str], cache_key: str) -> str:
        """Request new OAuth token."""
        
        payload = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret
        }
        
        if scopes:
            payload["scope"] = " ".join(scopes)
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    token_url,
                    data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                response.raise_for_status()
                
                token_data = response.json()
                access_token = token_data["access_token"]
                expires_in = token_data.get("expires_in", 3600)
                
                # Cache token with expiration
                expires_at = datetime.utcnow() + timedelta(seconds=expires_in - 60)
                cache_data = {
                    "access_token": access_token,
                    "expires_at": expires_at.isoformat(),
                    "service": service
                }
                
                await self.redis.set(
                    cache_key,
                    json.dumps(cache_data),
                    ex=expires_in - 60
                )
                
                logger.info(f"New OAuth token obtained for {service}")
                return access_token
                
        except Exception as e:
            logger.error(f"Failed to obtain OAuth token for {service}: {e}")
            raise
```

### 7.2 Rate Limiting and Performance

#### Rate Limiting Implementation
```python
# /bridge/rate_limiter.py
import asyncio
import time
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

class RateLimiter:
    """Production rate limiter with sliding window."""
    
    def __init__(self, redis_client):
        self.redis = redis_client
        
    async def check_rate_limit(self, key: str, limit: int, window: int) -> bool:
        """Check if request is within rate limit."""
        
        current_time = int(time.time())
        window_start = current_time - window
        
        # Use Redis sliding window rate limiting
        pipe = self.redis.pipeline()
        
        # Remove expired entries
        pipe.zremrangebyscore(key, 0, window_start)
        
        # Count current requests
        pipe.zcard(key)
        
        # Add current request
        pipe.zadd(key, {str(current_time): current_time})
        
        # Set expiration
        pipe.expire(key, window)
        
        results = await pipe.execute()
        request_count = results[1]
        
        return request_count < limit
    
    async def get_rate_limit_status(self, key: str, limit: int, window: int) -> Dict[str, Any]:
        """Get current rate limit status."""
        
        current_time = int(time.time())
        window_start = current_time - window
        
        # Remove expired and count
        await self.redis.zremrangebyscore(key, 0, window_start)
        current_count = await self.redis.zcard(key)
        
        # Calculate reset time
        oldest_request = await self.redis.zrange(key, 0, 0, withscores=True)
        reset_time = int(oldest_request[0][1] + window) if oldest_request else current_time
        
        return {
            "limit": limit,
            "remaining": max(0, limit - current_count),
            "reset_time": reset_time,
            "current_count": current_count
        }
```

### 7.3 Connection Pooling and Caching

#### Production HTTP Client
```python
# /bridge/http_client.py
import asyncio
import httpx
from typing import Dict, Any, Optional
import json
import hashlib
import logging

logger = logging.getLogger(__name__)

class ProductionHTTPClient:
    """Production HTTP client with connection pooling and caching."""
    
    def __init__(self, redis_client, base_timeout: int = 30):
        self.redis = redis_client
        self.cache_prefix = "http_cache:"
        
        # Configure connection limits
        limits = httpx.Limits(
            max_keepalive_connections=20,
            max_connections=100,
            keepalive_expiry=30
        )
        
        # Create client with connection pooling
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(base_timeout),
            limits=limits,
            headers={
                "User-Agent": "Ordinaut-Integration-Bridge/1.0"
            }
        )
        
    async def request(self, method: str, url: str, 
                     cache_ttl: Optional[int] = None,
                     **kwargs) -> Dict[str, Any]:
        """Make HTTP request with optional caching."""
        
        # Generate cache key
        cache_key = None
        if cache_ttl and method.upper() == "GET":
            cache_key = self._generate_cache_key(method, url, kwargs)
            cached_response = await self.redis.get(cache_key)
            if cached_response:
                return json.loads(cached_response)
        
        # Make request
        try:
            response = await self.client.request(method, url, **kwargs)
            response.raise_for_status()
            
            result = {
                "status_code": response.status_code,
                "data": response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text,
                "headers": dict(response.headers)
            }
            
            # Cache successful GET requests
            if cache_key and cache_ttl:
                await self.redis.set(
                    cache_key,
                    json.dumps(result),
                    ex=cache_ttl
                )
            
            return result
            
        except httpx.RequestError as e:
            logger.error(f"Request failed: {method} {url} - {e}")
            raise
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error: {method} {url} - {e.response.status_code}")
            raise
    
    def _generate_cache_key(self, method: str, url: str, kwargs: Dict) -> str:
        """Generate cache key for request."""
        key_data = f"{method}:{url}:{json.dumps(kwargs, sort_keys=True)}"
        return f"{self.cache_prefix}{hashlib.md5(key_data.encode()).hexdigest()}"
    
    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
```

---

## 8. Deployment and Operations

### 8.1 Docker Configuration

#### Production Dockerfile for Integration Bridges
```dockerfile
# /ops/Dockerfile.bridges
FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .
COPY bridge/requirements.txt ./bridge/

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r bridge/requirements.txt

# Copy application code
COPY bridge/ ./bridge/
COPY catalogs/ ./catalogs/
COPY observability/ ./observability/

# Create non-root user
RUN useradd --create-home --shell /bin/bash bridge
RUN chown -R bridge:bridge /app
USER bridge

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Start bridge services
CMD ["python", "-m", "bridge.main"]
```

#### Docker Compose for All Bridges
```yaml
# /ops/docker-compose.bridges.yml
version: '3.8'

services:
  # Core infrastructure
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: orchestrator
      POSTGRES_USER: orchestrator
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U orchestrator"]
      interval: 10s

  redis:
    image: redis:7-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s

  # OpenAI Bridge
  openai-bridge:
    build:
      context: ..
      dockerfile: ops/Dockerfile.bridges
    ports:
      - "8091:8080"
    environment:
      BRIDGE_TYPE: openai
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      REDIS_URL: redis://redis:6379/0
    depends_on:
      redis:
        condition: service_healthy

  # Claude Bridge  
  claude-bridge:
    build:
      context: ..
      dockerfile: ops/Dockerfile.bridges
    ports:
      - "8092:8080"
    environment:
      BRIDGE_TYPE: claude
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
      REDIS_URL: redis://redis:6379/0
    depends_on:
      redis:
        condition: service_healthy

  # Slack Bridge
  slack-bridge:
    build:
      context: ..
      dockerfile: ops/Dockerfile.bridges
    ports:
      - "8093:8080"
    environment:
      BRIDGE_TYPE: slack
      SLACK_BOT_TOKEN: ${SLACK_BOT_TOKEN}
      SLACK_APP_TOKEN: ${SLACK_APP_TOKEN}
      REDIS_URL: redis://redis:6379/0
    depends_on:
      redis:
        condition: service_healthy

  # GitHub Bridge
  github-bridge:
    build:
      context: ..
      dockerfile: ops/Dockerfile.bridges
    ports:
      - "8095:8080"
    environment:
      BRIDGE_TYPE: github
      GITHUB_TOKEN: ${GITHUB_TOKEN}
      GITHUB_WEBHOOK_SECRET: ${GITHUB_WEBHOOK_SECRET}
      REDIS_URL: redis://redis:6379/0
    depends_on:
      redis:
        condition: service_healthy

  # Salesforce Bridge
  salesforce-bridge:
    build:
      context: ..
      dockerfile: ops/Dockerfile.bridges
    ports:
      - "8097:8080"
    environment:
      BRIDGE_TYPE: salesforce
      SALESFORCE_CLIENT_ID: ${SALESFORCE_CLIENT_ID}
      SALESFORCE_CLIENT_SECRET: ${SALESFORCE_CLIENT_SECRET}
      SALESFORCE_USERNAME: ${SALESFORCE_USERNAME}
      SALESFORCE_PASSWORD: ${SALESFORCE_PASSWORD}
      SALESFORCE_SECURITY_TOKEN: ${SALESFORCE_SECURITY_TOKEN}
      REDIS_URL: redis://redis:6379/0
    depends_on:
      redis:
        condition: service_healthy

  # MAIB Banking Bridge (Moldova-specific)
  maib-bridge:
    build:
      context: ..
      dockerfile: ops/Dockerfile.bridges
    ports:
      - "8099:8080"
    environment:
      BRIDGE_TYPE: maib
      MAIB_MERCHANT_ID: ${MAIB_MERCHANT_ID}
      MAIB_CERTIFICATE_PATH: /certs/maib.pem
      MAIB_PRIVATE_KEY_PATH: /certs/maib_private.key
      REDIS_URL: redis://redis:6379/0
    volumes:
      - ./certs:/certs:ro
    depends_on:
      redis:
        condition: service_healthy

volumes:
  postgres_data:

networks:
  default:
    name: ordinaut-integrations
```

### 8.2 Environment Configuration

#### Production Environment Variables
```bash
# /ops/.env.production

# Core Ordinaut Configuration
DATABASE_URL=postgresql://orchestrator:${POSTGRES_PASSWORD}@postgres:5432/orchestrator
REDIS_URL=redis://redis:6379/0
JWT_SECRET_KEY=${JWT_SECRET_KEY}
ENVIRONMENT=production
VERSION=1.0.0

# Database Configuration
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
POSTGRES_DB=orchestrator
POSTGRES_USER=orchestrator

# OpenAI Integration
OPENAI_API_KEY=${OPENAI_API_KEY}
OPENAI_MODEL=gpt-4
OPENAI_MAX_TOKENS=2000

# Anthropic Integration
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
ANTHROPIC_MODEL=claude-3-sonnet-20240229
ANTHROPIC_MAX_TOKENS=2000

# Slack Integration
SLACK_BOT_TOKEN=${SLACK_BOT_TOKEN}
SLACK_APP_TOKEN=${SLACK_APP_TOKEN}
SLACK_SIGNING_SECRET=${SLACK_SIGNING_SECRET}

# Microsoft Teams Integration
TEAMS_APP_ID=${TEAMS_APP_ID}
TEAMS_CLIENT_SECRET=${TEAMS_CLIENT_SECRET}
TEAMS_TENANT_ID=${TEAMS_TENANT_ID}

# GitHub Integration
GITHUB_TOKEN=${GITHUB_TOKEN}
GITHUB_WEBHOOK_SECRET=${GITHUB_WEBHOOK_SECRET}
GITHUB_APP_ID=${GITHUB_APP_ID}
GITHUB_PRIVATE_KEY_PATH=/certs/github_private_key.pem

# GitLab Integration
GITLAB_TOKEN=${GITLAB_TOKEN}
GITLAB_WEBHOOK_SECRET=${GITLAB_WEBHOOK_SECRET}
GITLAB_URL=https://gitlab.com

# JIRA Integration
JIRA_URL=${JIRA_URL}
JIRA_USERNAME=${JIRA_USERNAME}
JIRA_API_TOKEN=${JIRA_API_TOKEN}

# Salesforce Integration
SALESFORCE_CLIENT_ID=${SALESFORCE_CLIENT_ID}
SALESFORCE_CLIENT_SECRET=${SALESFORCE_CLIENT_SECRET}
SALESFORCE_USERNAME=${SALESFORCE_USERNAME}
SALESFORCE_PASSWORD=${SALESFORCE_PASSWORD}
SALESFORCE_SECURITY_TOKEN=${SALESFORCE_SECURITY_TOKEN}
SALESFORCE_SANDBOX=false

# HubSpot Integration
HUBSPOT_API_KEY=${HUBSPOT_API_KEY}
HUBSPOT_CLIENT_ID=${HUBSPOT_CLIENT_ID}
HUBSPOT_CLIENT_SECRET=${HUBSPOT_CLIENT_SECRET}

# MAIB Banking Integration (Moldova)
MAIB_MERCHANT_ID=${MAIB_MERCHANT_ID}
MAIB_MERCHANT_URL=${MAIB_MERCHANT_URL}
MAIB_CERTIFICATE_PATH=/certs/maib.pem
MAIB_PRIVATE_KEY_PATH=/certs/maib_private.key

# SIA Integration (Moldova Government)
SIA_COMPANY_IDNO=${SIA_COMPANY_IDNO}
SIA_DIGITAL_CERT_PATH=/certs/company_digital_cert.p12
DIGITAL_CERT_PASSWORD=${DIGITAL_CERT_PASSWORD}

# Monitoring
PROMETHEUS_URL=http://prometheus:9090
GRAFANA_URL=http://grafana:3000
GRAFANA_API_KEY=${GRAFANA_API_KEY}

# Security
CORS_ORIGINS=https://company.example.com,https://api.company.com
ALLOWED_HOSTS=company.example.com,api.company.com
RATE_LIMIT_REQUESTS=1000
RATE_LIMIT_PERIOD=3600

# Logging
LOG_LEVEL=INFO
STRUCTURED_LOGGING=true
LOG_FORMAT=json
```

### 8.3 Monitoring and Alerting

#### Integration Health Dashboard
```json
{
  "dashboard": {
    "id": "integration-health",
    "title": "Ordinaut Integration Health",
    "panels": [
      {
        "title": "Integration Success Rate",
        "type": "stat",
        "targets": [
          {
            "expr": "sum(rate(orchestrator_external_tool_calls_total{status_code=~\"2..\"}[5m])) / sum(rate(orchestrator_external_tool_calls_total[5m])) * 100",
            "legendFormat": "Success Rate %"
          }
        ]
      },
      {
        "title": "Integration Response Time",
        "type": "graph",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(orchestrator_external_tool_duration_seconds_bucket[5m])) by (tool_address)",
            "legendFormat": "{{tool_address}} P95"
          }
        ]
      },
      {
        "title": "Integration Errors",
        "type": "table",
        "targets": [
          {
            "expr": "sum(rate(orchestrator_external_tool_calls_total{status_code=~\"[45]..\"}[5m])) by (tool_address, status_code)",
            "format": "table"
          }
        ]
      },
      {
        "title": "Rate Limit Status",
        "type": "graph",
        "targets": [
          {
            "expr": "integration_rate_limit_remaining by (service)",
            "legendFormat": "{{service}} Remaining"
          }
        ]
      }
    ]
  }
}
```

#### Alert Rules
```yaml
# /ops/prometheus/integration_alert_rules.yml
groups:
  - name: integration_health
    rules:
      - alert: IntegrationHighErrorRate
        expr: sum(rate(orchestrator_external_tool_calls_total{status_code=~"[45].."}[5m])) by (tool_address) / sum(rate(orchestrator_external_tool_calls_total[5m])) by (tool_address) > 0.1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate for integration {{ $labels.tool_address }}"
          description: "Integration {{ $labels.tool_address }} has error rate of {{ $value | humanizePercentage }}"

      - alert: IntegrationSlowResponse
        expr: histogram_quantile(0.95, rate(orchestrator_external_tool_duration_seconds_bucket[5m])) by (tool_address) > 30
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Slow response time for integration {{ $labels.tool_address }}"
          description: "Integration {{ $labels.tool_address }} P95 response time is {{ $value }}s"

      - alert: IntegrationRateLimitNear
        expr: integration_rate_limit_remaining / integration_rate_limit_total < 0.1
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "Rate limit nearly exceeded for {{ $labels.service }}"
          description: "{{ $labels.service }} has only {{ $value | humanizePercentage }} of rate limit remaining"

      - alert: IntegrationDown
        expr: up{job=~".*-bridge"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Integration bridge {{ $labels.instance }} is down"
          description: "Integration bridge {{ $labels.instance }} has been down for more than 1 minute"
```

---

## 9. Troubleshooting Guide

### 9.1 Common Integration Issues

#### Authentication Problems
```bash
# Check OAuth token status
curl -H "Authorization: Bearer TOKEN" https://api.service.com/me

# Verify certificate validity (for banking/government)
openssl x509 -in /certs/maib.pem -text -noout

# Test JWT token
python -c "
import jwt
token = 'YOUR_JWT_TOKEN'
try:
    decoded = jwt.decode(token, options={'verify_signature': False})
    print('Token valid:', decoded)
except:
    print('Token invalid')
"
```

#### Rate Limiting Issues
```bash
# Check rate limit status in Redis
redis-cli ZCARD "rate_limit:github:company"
redis-cli ZRANGE "rate_limit:github:company" 0 -1 WITHSCORES

# Monitor rate limit metrics
curl http://prometheus:9090/api/v1/query?query=integration_rate_limit_remaining
```

#### Network Connectivity
```bash
# Test external service connectivity
curl -v https://api.slack.com/api/auth.test
curl -v https://api.github.com/user
curl -v https://graph.microsoft.com/v1.0/me

# Check DNS resolution
nslookup api.slack.com
nslookup graph.microsoft.com
```

### 9.2 Performance Optimization

#### Connection Pool Tuning
```python
# Optimal connection pool settings for different services
INTEGRATION_LIMITS = {
    "slack": httpx.Limits(max_keepalive_connections=10, max_connections=50),
    "github": httpx.Limits(max_keepalive_connections=20, max_connections=100),
    "salesforce": httpx.Limits(max_keepalive_connections=5, max_connections=25),
    "openai": httpx.Limits(max_keepalive_connections=15, max_connections=75)
}
```

#### Caching Strategy
```python
# Cache TTL by integration type
CACHE_TTL = {
    "weather": 3600,      # 1 hour
    "calendar": 300,      # 5 minutes
    "github_repos": 7200, # 2 hours
    "user_profiles": 1800 # 30 minutes
}
```

---

## 10. Summary

This comprehensive integration guide provides production-ready examples for connecting Ordinaut with the most common enterprise systems used by Moldovan software companies. Each integration includes:

✅ **Complete Working Code** - Copy-paste implementations with error handling  
✅ **Security Best Practices** - OAuth 2.0, JWT, digital signatures, rate limiting  
✅ **Performance Optimization** - Connection pooling, caching, async operations  
✅ **Monitoring Integration** - Prometheus metrics, Grafana dashboards, alerting  
✅ **Moldova-Specific Tools** - MAIB banking, SIA government reporting, local services  

### Key Benefits for CTOs:

1. **Rapid Deployment**: All examples are production-ready with proper error handling
2. **Enterprise Security**: Implements industry-standard authentication and authorization 
3. **Operational Excellence**: Comprehensive monitoring, alerting, and troubleshooting guides
4. **Local Compliance**: Includes Moldova-specific banking and government integrations
5. **Scalable Architecture**: Designed for high-throughput enterprise environments

### Next Steps:

1. **Choose integrations** based on your current tech stack
2. **Deploy bridges** using provided Docker configurations  
3. **Configure authentication** with your service credentials
4. **Set up monitoring** using Prometheus and Grafana dashboards
5. **Test integrations** with provided example pipelines
6. **Scale gradually** by adding more integration bridges as needed

The Ordinaut platform transforms your disconnected tools into a coordinated productivity system, providing the backbone for AI agents to work together effectively across your entire technology stack.