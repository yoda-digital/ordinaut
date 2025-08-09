# Personal Agent Orchestrator - Engine Runtime

## Purpose

The **Engine Runtime** is the deterministic pipeline execution heart of the Personal Agent Orchestrator. It transforms declarative pipeline definitions into reliable, observable, and fault-tolerant task execution with comprehensive template rendering, JSON schema validation, and MCP tool integration.

---

## Core Components

### 1. executor.py - Deterministic Pipeline Execution Engine

**Purpose**: Main execution engine that processes pipeline definitions with strict validation, error handling, and observability.

**Key Features**:
- **Deterministic execution** with comprehensive error handling
- **Template variable resolution** using JMESPath expressions  
- **JSON Schema validation** for all tool inputs and outputs
- **Conditional execution** with JMESPath boolean expressions
- **Step isolation** with proper error propagation
- **Performance metrics** and structured logging integration
- **Pipeline validation** without execution

**Core Functions**:
```python
def run_pipeline(task: dict) -> dict:
    """
    Execute declarative pipeline with strict validation.
    
    Returns execution context with:
    - now: ISO timestamp of execution start
    - params: Original parameters from task payload
    - steps: Results keyed by save_as names
    - _execution_summary: Metrics and status
    """

def validate_pipeline(pipeline_definition: dict) -> List[str]:
    """Validate pipeline without executing - returns error list."""

def get_pipeline_metrics(execution_context: dict) -> dict:
    """Extract performance metrics from execution context."""
```

**Pipeline Structure**:
```json
{
  "payload": {
    "params": {"date": "2025-08-08", "location": "Chisinau"},
    "pipeline": [
      {
        "id": "weather",
        "uses": "weather-mcp.forecast",
        "with": {"city": "${params.location}", "date": "${params.date}"},
        "save_as": "forecast",
        "if": "params.location != 'unknown'",
        "timeout_seconds": 30
      },
      {
        "id": "notify",
        "uses": "telegram-mcp.send_message", 
        "with": {"text": "Weather: ${steps.forecast.summary}"}
      }
    ]
  }
}
```

### 2. template.py - Variable Resolution Engine

**Purpose**: Secure template variable resolution using JMESPath expressions with comprehensive error handling.

**Key Features**:
- **JMESPath-based** template resolution (`${steps.weather.temp}`)
- **Recursive traversal** of nested data structures
- **Type-safe conversions** (booleans, objects, arrays)
- **Null handling** with warnings for missing variables
- **Template extraction** for validation and analysis
- **Preview mode** for debugging template rendering

**Core Functions**:
```python
def render_templates(obj: Any, ctx: dict) -> Any:
    """
    Recursively render ${variable} expressions in data structures.
    
    Supports:
    - Simple variables: ${params.name}
    - Nested access: ${steps.weather.forecast[0].temp}  
    - JMESPath expressions: ${steps.items[?price > `100`]}
    """

def extract_template_variables(obj: Any) -> List[str]:
    """Extract all template variables from object."""

def validate_template_variables(variables: List[str], context: dict) -> List[str]:
    """Validate variables can be resolved - returns missing list."""

def preview_template_rendering(obj: Any, context: dict) -> Dict[str, Any]:
    """Preview template rendering without executing."""
```

**Template Examples**:
```python
# Context
ctx = {
    "params": {"user": "Alice", "count": 5},
    "steps": {
        "calendar": {"events": [{"title": "Meeting", "urgent": True}]},
        "weather": {"temp": 22, "condition": "sunny"}
    }
}

# Template rendering
render_templates("Hello ${params.user}", ctx)
# → "Hello Alice"

render_templates("${steps.weather.temp}°C - ${steps.weather.condition}", ctx) 
# → "22°C - sunny"

# Complex JMESPath
render_templates("${steps.calendar.events[?urgent].title}", ctx)
# → ["Meeting"]
```

### 3. registry.py - Tool Catalog Management

**Purpose**: Thread-safe tool catalog with scope-based authorization, caching, and multiple source support.

**Key Features**:
- **Multi-source catalogs** (JSON files, environment, database, built-in)
- **Scope-based access control** preventing unauthorized tool usage
- **Automatic refresh** with configurable cache TTL
- **Tool validation** ensuring proper schema definitions
- **Performance optimization** with address indexing

**Core Classes**:
```python
class CatalogRegistry:
    """Thread-safe tool catalog with caching and scope validation."""
    
    def get_tool(self, address: str, agent_scopes: Set[str] = None) -> Dict[str, Any]:
        """Get tool with scope validation."""
    
    def list_tools(self, agent_scopes: Set[str] = None) -> List[Dict[str, Any]]:
        """List accessible tools based on agent scopes."""
    
    def reload_catalog(self) -> None:
        """Force reload from all sources."""
```

**Tool Definition Format**:
```json
{
  "address": "telegram-mcp.send_message",
  "transport": "http",
  "endpoint": "http://telegram-bridge:8085/tools/send_message",
  "input_schema": {
    "type": "object",
    "required": ["chat_id", "text"],
    "properties": {
      "chat_id": {"type": "integer", "minimum": 1},
      "text": {"type": "string", "maxLength": 4096}
    }
  },
  "output_schema": {
    "type": "object",
    "required": ["ok", "message_id"],
    "properties": {
      "ok": {"type": "boolean"},
      "message_id": {"type": "integer"}
    }
  },
  "timeout_seconds": 15,
  "scopes": ["notify"],
  "cost_tier": "low",
  "description": "Send message to Telegram chat"
}
```

**Catalog Loading Priority**:
1. `TOOL_CATALOG_PATH` environment variable
2. `catalogs/tools.json` (project directory)
3. `tools.json` (current directory)
4. `/etc/orchestrator/tools.json` (system-wide)
5. `~/.orchestrator/tools.json` (user-specific)
6. Built-in catalog (development/testing)

### 4. mcp_client.py - MCP Bridge Implementation

**Purpose**: Universal MCP (Model Context Protocol) client supporting HTTP, stdio, and native MCP server transports.

**Key Features**:
- **Multi-transport support** (HTTP, MCP server, stdio)
- **JSON-RPC compliance** with proper error handling
- **Schema validation** for inputs and outputs
- **Timeout management** with configurable limits
- **Performance monitoring** with detailed metrics
- **Tool discovery** from MCP servers

**Core Functions**:
```python
def call_tool(address: str, tool: Dict[str, Any], args: Dict[str, Any], timeout: int = 30) -> Dict[str, Any]:
    """
    Universal tool caller supporting all MCP transports.
    
    Handles:
    - Input/output validation
    - Transport selection (http/mcp/stdio)
    - Error wrapping and timeout
    - Performance logging
    """

def discover_mcp_tools(server_endpoint: str, timeout: int = 10) -> Dict[str, Any]:
    """Discover available tools from MCP server."""
```

**Transport Types**:

**HTTP Transport** (JSON-RPC over HTTP):
```python
# Tool definition
{
  "transport": "http",
  "endpoint": "http://service:8080/tools/action"
}

# Request format
{
  "jsonrpc": "2.0",
  "id": "req_1691234567890",
  "method": "tools/call",
  "params": {"arguments": {"param1": "value1"}}
}
```

**MCP Server Transport**:
```python
# Tool definition  
{
  "transport": "mcp",
  "server": "weather-server@http://localhost:8081/mcp"
}
```

**Stdio Transport** (subprocess):
```python
# Tool definition
{
  "transport": "stdio", 
  "executable": "/usr/local/bin/mcp-weather-tool"
}
```

### 5. rruler.py - RFC-5545 RRULE Processing

**Purpose**: Complete RFC-5545 RRULE implementation with Europe/Chisinau timezone support and DST handling.

**Key Features**:
- **Full RFC-5545 compliance** with comprehensive validation
- **DST transition handling** for Europe/Chisinau timezone
- **Calendar mathematics** with edge case support
- **Performance optimization** with RRULE caching
- **Edge case analysis** (leap years, impossible dates)
- **Common pattern helpers** for typical scheduling needs

**Core Functions**:
```python
def next_occurrence(rrule_string: str, timezone_name: str = "Europe/Chisinau", 
                   after_time: Optional[datetime] = None) -> Optional[datetime]:
    """Calculate next occurrence for RRULE in timezone."""

def evaluate_rrule_in_timezone(rrule_string: str, timezone_name: str = "Europe/Chisinau",
                              count: int = 10) -> List[datetime]:
    """Get multiple occurrences with DST handling."""

def validate_rrule_syntax(rrule_string: str) -> Dict[str, Any]:
    """Comprehensive RRULE validation with detailed analysis."""

def create_common_rrule(pattern_type: str, **kwargs) -> str:
    """Generate RRULE for common patterns."""

def handle_calendar_edge_cases(rrule_string: str) -> Dict[str, Any]:
    """Analyze RRULE for calendar edge cases."""
```

**RRULE Examples**:
```python
# Business days at 9 AM
create_common_rrule('morning_briefing')
# → "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=30"

# First Monday of each month
create_common_rrule('first_monday')  
# → "FREQ=MONTHLY;BYDAY=1MO"

# Daily at specific time
create_common_rrule('daily_at_time', hour=14, minute=30)
# → "FREQ=DAILY;BYHOUR=14;BYMINUTE=30"

# Complex RRULE with validation
next_occurrence("FREQ=WEEKLY;BYDAY=MO,WE,FR;BYHOUR=9;BYMINUTE=0", "Europe/Chisinau")
# → datetime(2025, 8, 11, 9, 0, tzinfo=<DstTzInfo 'Europe/Chisinau'>)
```

**DST Handling**:
```python
def _safe_localize(dt: datetime, tz: pytz.timezone) -> datetime:
    """
    Handle DST transitions gracefully:
    - Ambiguous time (fall-back): Choose standard time
    - Non-existent time (spring-forward): Advance 1 hour
    """
```

---

## Pipeline Execution Patterns

### Standard Pipeline Flow

```python
# 1. Pipeline Definition
pipeline = {
    "params": {"location": "Chisinau", "recipient": 12345},
    "pipeline": [
        {
            "id": "weather",
            "uses": "weather-mcp.forecast", 
            "with": {"city": "${params.location}"},
            "save_as": "forecast"
        },
        {
            "id": "notify",
            "uses": "telegram-mcp.send_message",
            "with": {
                "chat_id": "${params.recipient}",
                "text": "Weather in ${params.location}: ${steps.forecast.summary}"
            }
        }
    ]
}

# 2. Execution  
task = {"id": "weather-001", "payload": pipeline}
result = run_pipeline(task)

# 3. Result Structure
{
    "now": "2025-08-08T14:30:00+03:00",
    "params": {"location": "Chisinau", "recipient": 12345},
    "steps": {
        "forecast": {"summary": "Sunny, 25°C", "temp": 25},
        "notify": {"ok": True, "message_id": 789}
    },
    "_execution_summary": {
        "success": True,
        "total_steps": 2,
        "executed_steps": 2,
        "execution_time_seconds": 1.23
    }
}
```

### Conditional Execution

```python
pipeline = {
    "params": {"alert_threshold": 30, "current_temp": 35},
    "pipeline": [
        {
            "id": "check_weather",
            "uses": "weather-mcp.current",
            "with": {"city": "Chisinau"},
            "save_as": "weather"
        },
        {
            "id": "heat_alert",
            "uses": "telegram-mcp.send_message",
            "with": {"text": "Heat alert! Temperature: ${steps.weather.temp}°C"},
            "if": "steps.weather.temp > params.alert_threshold"
        }
    ]
}
```

### Error Handling Pattern

```python
try:
    result = run_pipeline(task)
    metrics = get_pipeline_metrics(result)
    
    if metrics["success"]:
        print(f"Pipeline completed in {metrics['execution_time_seconds']:.2f}s")
    else:
        print(f"Pipeline failed at step {metrics['failed_step_index']}: {metrics['error']}")
        
except PipelineExecutionError as e:
    print(f"Pipeline execution failed: {e}")
    if e.step_id:
        print(f"Failed step: {e.step_id}")
        
except StepValidationError as e:
    print(f"Step validation failed: {e}")
    
except ConditionEvaluationError as e:
    print(f"Condition evaluation failed: {e}")
```

---

## Tool Registry and MCP Integration

### Tool Catalog Management

```python
# Get tool with scope validation
tool = get_tool_with_scopes("telegram-mcp.send_message", {"notify"})

# List tools available to agent
agent_scopes = {"calendar.read", "notify", "weather.read"}
available_tools = list_tools_for_agent(agent_scopes)

# Force catalog reload
reload_tool_catalog()
```

### MCP Tool Discovery

```python
# Discover tools from MCP server
tools = discover_mcp_tools("http://weather-server:8080")

# Call tool with full validation
result = call_tool(
    address="weather-mcp.forecast",
    tool=tool_definition,
    args={"city": "Chisinau", "days": 3},
    timeout=30
)
```

---

## RRULE Processing and Scheduling

### Next Occurrence Calculation

```python
# Simple daily recurrence
next_time = next_occurrence("FREQ=DAILY;BYHOUR=9", "Europe/Chisinau")

# Complex business hours pattern  
rrule = "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=14;BYMINUTE=30"
next_time = next_occurrence(rrule, "Europe/Chisinau")

# Preview next 5 occurrences
occurrences = get_next_n_occurrences(rrule, n=5, timezone_name="Europe/Chisinau")
```

### RRULE Validation and Analysis

```python
# Comprehensive validation
validation = validate_rrule_syntax("FREQ=MONTHLY;BYDAY=1MO;BYHOUR=9")
if not validation['valid']:
    print("Validation errors:", validation['errors'])

# Edge case analysis
analysis = handle_calendar_edge_cases("FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=29")
if analysis['leap_year_feb29']:
    print("Warning: RRULE only triggers on leap years")

# Performance optimization analysis
optimization = optimize_rrule_for_scheduler("FREQ=SECONDLY")
print(f"Complexity score: {optimization['complexity_score']}/10")
```

---

## Template Resolution System

### Variable Extraction and Validation

```python
# Extract all template variables
template = {
    "message": "Hello ${params.name}, weather is ${steps.weather.condition}",
    "recipients": ["${params.primary_contact}", "${params.backup_contact}"]
}

variables = extract_template_variables(template)
# → ['params.name', 'steps.weather.condition', 'params.primary_contact', 'params.backup_contact']

# Validate variables can be resolved
context = {"params": {"name": "Alice"}, "steps": {}}
missing = validate_template_variables(variables, context)
# → ['steps.weather.condition', 'params.primary_contact', 'params.backup_contact']
```

### Advanced Template Features

```python
# JMESPath filtering and transformation
ctx = {
    "steps": {
        "calendar": {
            "events": [
                {"title": "Meeting", "urgent": True, "time": "09:00"},
                {"title": "Lunch", "urgent": False, "time": "12:00"}
            ]
        }
    }
}

# Filter urgent events
template = "Urgent: ${steps.calendar.events[?urgent].title}"
result = render_templates(template, ctx)
# → "Urgent: ['Meeting']"

# Complex transformations
template = "Next meeting: ${steps.calendar.events[0].title} at ${steps.calendar.events[0].time}"
result = render_templates(template, ctx)  
# → "Next meeting: Meeting at 09:00"
```

---

## Performance and Observability

### Execution Metrics

```python
# Pipeline metrics extraction
metrics = get_pipeline_metrics(execution_context)
print(f"""
Pipeline Execution Summary:
- Success: {metrics['success']}
- Total Steps: {metrics['total_steps']}
- Executed: {metrics['executed_steps']} 
- Skipped: {metrics['skipped_steps']}
- Duration: {metrics['execution_time_seconds']:.2f}s
- Rate: {metrics['steps_per_second']:.1f} steps/sec
""")
```

### Error Classification

The engine provides detailed error types for proper handling:

- **PipelineExecutionError**: General pipeline execution failures
- **StepValidationError**: JSON schema validation failures  
- **ConditionEvaluationError**: JMESPath condition evaluation failures
- **TemplateRenderError**: Template variable resolution failures
- **ToolNotFoundError**: Tool not found in catalog
- **ScopeViolationError**: Agent lacks required scopes
- **MCPError**: MCP transport and communication errors
- **RRuleValidationError**: RRULE syntax or logic errors
- **RRuleTimezoneError**: Timezone-related RRULE errors

---

## Integration with Orchestrator Components

### Worker Integration

```python
# workers/runner.py calls engine
from engine.executor import run_pipeline

def process_work_item(task):
    try:
        result = run_pipeline(task)
        record_success(task["id"], result)
    except Exception as e:
        record_failure(task["id"], str(e))
```

### Scheduler Integration

```python
# scheduler/tick.py uses RRULE processor
from engine.rruler import next_occurrence

def schedule_task(task):
    if task["schedule_kind"] == "rrule":
        next_time = next_occurrence(task["schedule_expr"], task["timezone"])
        if next_time:
            enqueue_due_work(task["id"], next_time)
```

### API Integration

```python
# api/routes/tasks.py validates pipelines
from engine.executor import validate_pipeline

@app.post("/tasks")
def create_task(task_data):
    errors = validate_pipeline(task_data)
    if errors:
        raise HTTPException(400, detail=errors)
    # ... create task
```

---

## Development and Testing Patterns

### Pipeline Validation

```python
# Validate before deployment
def validate_pipeline_safe(pipeline_def):
    errors = validate_pipeline(pipeline_def)
    if errors:
        raise ValueError(f"Pipeline validation failed: {errors}")
    
    # Check template variables
    if "pipeline" in pipeline_def.get("payload", {}):
        variables = extract_template_variables(pipeline_def["payload"]["pipeline"])
        # Ensure variables follow naming conventions
        for var in variables:
            if not var.startswith(("params.", "steps.", "now")):
                errors.append(f"Invalid variable scope: {var}")
```

### Tool Testing

```python
# Test tool catalog
def test_tool_availability():
    catalog = load_catalog()
    for tool in catalog:
        try:
            # Validate tool definition
            required_fields = ["address", "transport", "input_schema", "output_schema"]
            for field in required_fields:
                assert field in tool, f"Tool {tool['address']} missing {field}"
            
            print(f"✓ Tool {tool['address']} is valid")
        except Exception as e:
            print(f"✗ Tool {tool['address']} failed: {e}")
```

### RRULE Testing

```python
# Test RRULE processing
def test_rrule_patterns():
    test_cases = [
        ("FREQ=DAILY;BYHOUR=9", "Simple daily"),
        ("FREQ=WEEKLY;BYDAY=MO,WE,FR", "Three days a week"),
        ("FREQ=MONTHLY;BYDAY=1MO", "First Monday"),
        ("FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=29", "Leap year only")
    ]
    
    for rrule, description in test_cases:
        try:
            result = validate_rrule_syntax(rrule)
            next_time = next_occurrence(rrule, "Europe/Chisinau")
            print(f"✓ {description}: Next at {next_time}")
        except Exception as e:
            print(f"✗ {description}: {e}")
```

---

## Configuration and Environment

### Environment Variables

```bash
# Tool catalog location
export TOOL_CATALOG_PATH="/path/to/tools.json"

# MCP server endpoints
export MCP_WEATHER_SERVER="http://weather:8080"
export MCP_TELEGRAM_SERVER="http://telegram:8080"
```

### Catalog Configuration

```json
{
  "tools": [
    {
      "address": "weather-mcp.forecast",
      "transport": "http", 
      "endpoint": "${MCP_WEATHER_SERVER}/tools/forecast",
      "input_schema": {...},
      "output_schema": {...},
      "timeout_seconds": 30,
      "scopes": ["weather.read"]
    }
  ]
}
```

---

## Best Practices

### Pipeline Design
1. **Keep steps atomic** - each step should do one thing well
2. **Use meaningful step IDs** - aids debugging and metrics
3. **Validate inputs early** - fail fast with clear error messages  
4. **Handle null values** - template variables may resolve to null
5. **Set appropriate timeouts** - prevent hanging operations

### Template Variables
1. **Use consistent naming** - `params.x` for inputs, `steps.x.y` for results
2. **Validate variables exist** - use `validate_template_variables()`
3. **Handle missing data** - provide defaults or conditional logic
4. **Avoid complex JMESPath** - keep expressions readable

### Tool Integration
1. **Define strict schemas** - both input and output validation
2. **Use appropriate scopes** - principle of least privilege  
3. **Set realistic timeouts** - account for network latency
4. **Handle all error cases** - network, validation, business logic

### RRULE Patterns
1. **Test edge cases** - leap years, DST transitions, month boundaries
2. **Use timezone awareness** - always specify timezone explicitly
3. **Validate before storage** - catch syntax errors early
4. **Consider performance** - high-frequency rules impact scheduler

---

*The Engine Runtime provides the reliable, deterministic foundation that transforms declarative pipeline definitions into coordinated agent actions. Every component is designed for production use with comprehensive error handling, validation, and observability.*