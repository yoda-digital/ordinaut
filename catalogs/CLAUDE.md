# Ordinaut - Tool Catalogs Directory

## Purpose and Role

The `catalogs/` directory contains tool catalog definitions that describe all available tools and services that can be used in pipeline executions. These catalogs serve as the authoritative registry for tool discovery, validation, and integration within the Ordinaut ecosystem.

## Directory Contents

### Core Catalog Files
- **`tools.json`** - Primary tool catalog with complete tool definitions
- **Future catalogs may include:**
  - `enterprise_tools.json` - Enterprise-specific tool integrations
  - `custom_tools.json` - User-defined custom tools
  - `deprecated_tools.json` - Legacy tools maintained for compatibility

## Tool Catalog Schema

### Top-Level Structure
```json
{
  "version": "1.0",
  "description": "Ordinaut Tool Catalog",
  "last_updated": "2025-08-08T00:00:00Z",
  "tools": [
    // Array of tool definitions
  ],
  "categories": {
    // Tool categorization metadata
  },
  "compatibility": {
    // Version compatibility information
  }
}
```

### Tool Definition Schema
Each tool in the catalog follows this comprehensive structure:

```json
{
  "address": "service-name.tool-function",
  "transport": "http|stdio|websocket",
  "endpoint": "http://service:port/path",
  "input_schema": {
    // JSON Schema for input validation
  },
  "output_schema": {
    // JSON Schema for output validation
  },
  "timeout_seconds": 30,
  "scopes": ["scope1", "scope2"],
  "cost_tier": "free|low|medium|high",
  "description": "Human-readable tool description",
  "examples": [
    // Usage examples with input/output
  ],
  "metadata": {
    // Additional tool metadata
  }
}
```

## Tool Categories and Integration Patterns

### Communication Tools
Tools for external communication and notifications:

```json
{
  "address": "telegram-mcp.send_message",
  "transport": "http",
  "endpoint": "http://telegram-bridge:8085/tools/send_message",
  "scopes": ["notify"],
  "cost_tier": "low",
  "category": "communication",
  "rate_limits": {
    "requests_per_minute": 30,
    "burst_limit": 10
  }
}
```

**Integration Pattern:**
- HTTP-based MCP bridge services
- Async message delivery with retry logic
- Rate limiting and quota management
- Message formatting and templating support

### Data Retrieval Tools
Tools for fetching external data:

```json
{
  "address": "google-calendar-mcp.list_events",
  "transport": "http", 
  "endpoint": "http://gcal-bridge:8086/tools/list_events",
  "scopes": ["calendar.read"],
  "cost_tier": "medium",
  "category": "data_retrieval",
  "caching": {
    "ttl_seconds": 300,
    "cache_key_template": "${tool_address}:${input.start}:${input.end}"
  }
}
```

**Integration Pattern:**
- OAuth2 authentication handling
- Response caching for performance
- Pagination support for large datasets
- Error handling for API rate limits

### AI and Processing Tools
Tools for content processing and AI operations:

```json
{
  "address": "llm.summarize",
  "transport": "http",
  "endpoint": "http://llm-service:8087/tools/summarize",
  "scopes": ["llm"],
  "cost_tier": "high",
  "category": "ai_processing",
  "resource_limits": {
    "max_concurrent_requests": 5,
    "max_tokens_per_request": 10000,
    "estimated_cost_per_request": 0.02
  }
}
```

**Integration Pattern:**
- Token counting and cost estimation
- Concurrent request limiting
- Response streaming for long operations
- Model version management

### Testing and Development Tools
Tools for system testing and debugging:

```json
{
  "address": "echo.test",
  "transport": "http",
  "endpoint": "http://localhost:8090/echo",
  "scopes": ["test"],
  "cost_tier": "free",
  "category": "testing",
  "development_only": true
}
```

## Tool Registration and Discovery

### Catalog Loading Process
```python
# engine/registry.py implementation pattern
class ToolRegistry:
    def __init__(self, catalog_path: str):
        self.catalog = self.load_catalog(catalog_path)
        self.tools = self.index_tools()
    
    def load_catalog(self, path: str) -> dict:
        with open(path) as f:
            catalog = json.load(f)
        self.validate_catalog_schema(catalog)
        return catalog
    
    def get_tool(self, address: str) -> dict:
        if address not in self.tools:
            raise ToolNotFoundError(f"Tool {address} not found in catalog")
        return self.tools[address]
    
    def list_tools_by_scope(self, scopes: list) -> list:
        return [
            tool for tool in self.tools.values() 
            if any(scope in tool.get("scopes", []) for scope in scopes)
        ]
```

### Dynamic Tool Discovery
```python
# Runtime tool availability checking
async def check_tool_availability(tool: dict) -> bool:
    """Verify tool endpoint is accessible"""
    if tool["transport"] == "http":
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{tool['endpoint']}/health",
                    timeout=5.0
                )
                return response.status_code == 200
        except httpx.RequestError:
            return False
    return True
```

## Schema Validation and Type Safety

### Input/Output Schema Enforcement
```python
from jsonschema import validate, ValidationError

def validate_tool_input(tool: dict, input_data: dict) -> None:
    """Validate pipeline step input against tool schema"""
    try:
        validate(instance=input_data, schema=tool["input_schema"])
    except ValidationError as e:
        raise PipelineValidationError(
            f"Tool {tool['address']} input validation failed: {e.message}"
        )

def validate_tool_output(tool: dict, output_data: dict) -> None:
    """Validate tool response against output schema"""
    try:
        validate(instance=output_data, schema=tool["output_schema"])
    except ValidationError as e:
        logger.warning(f"Tool {tool['address']} output validation failed: {e.message}")
        # Log but don't fail - allow for schema evolution
```

### Schema Evolution and Versioning
```json
{
  "address": "calendar.list_events",
  "schema_version": "2.1.0",
  "input_schema": {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "version": "2.1.0",
    "backward_compatible_with": ["2.0.0", "1.5.0"],
    "properties": {
      // Schema definition
    }
  }
}
```

## Security and Access Control

### Scope-Based Authorization
```python
class ScopedToolRegistry:
    def __init__(self, catalog_path: str, allowed_scopes: set):
        self.catalog = self.load_catalog(catalog_path)
        self.allowed_scopes = allowed_scopes
        self.tools = self.filter_tools_by_scope()
    
    def filter_tools_by_scope(self) -> dict:
        """Only include tools agent has permission to use"""
        filtered = {}
        for tool in self.catalog["tools"]:
            tool_scopes = set(tool.get("scopes", []))
            if tool_scopes.intersection(self.allowed_scopes):
                filtered[tool["address"]] = tool
        return filtered
```

### Tool Security Metadata
```json
{
  "address": "secure-tool.action",
  "security": {
    "requires_authentication": true,
    "authentication_method": "bearer_token",
    "data_sensitivity": "high",
    "audit_required": true,
    "allowed_environments": ["production", "staging"]
  },
  "compliance": {
    "gdpr_compliant": true,
    "data_retention_days": 90,
    "encryption_required": true
  }
}
```

## Performance and Monitoring

### Cost Management
```json
{
  "address": "expensive-ai.process",
  "cost_tier": "high",
  "cost_metadata": {
    "estimated_cost_usd": 0.05,
    "billing_unit": "per_request",
    "budget_category": "ai_processing",
    "cost_tracking_enabled": true
  },
  "usage_limits": {
    "max_requests_per_hour": 100,
    "max_requests_per_day": 1000,
    "concurrent_request_limit": 3
  }
}
```

### Performance Monitoring
```json
{
  "address": "slow-service.query",
  "performance": {
    "average_response_time_ms": 2500,
    "p95_response_time_ms": 5000,
    "success_rate": 0.995,
    "recommended_timeout_ms": 8000
  },
  "monitoring": {
    "health_check_endpoint": "/health",
    "metrics_endpoint": "/metrics",
    "alert_thresholds": {
      "error_rate": 0.05,
      "response_time_p95": 10000
    }
  }
}
```

## Catalog Management and Updates

### Catalog Versioning
```bash
# Version control for catalog changes
git tag -a catalog-v1.2.0 -m "Add weather forecasting tools"
git push origin catalog-v1.2.0

# Automated catalog validation
.github/workflows/validate-catalog.yml:
  - name: Validate Tool Catalog
    run: |
      python scripts/validate_catalog.py catalogs/tools.json
      python scripts/test_tool_connectivity.py catalogs/tools.json
```

### Hot Reloading
```python
class HotReloadableRegistry:
    def __init__(self, catalog_path: str):
        self.catalog_path = catalog_path
        self.last_modified = None
        self.tools = {}
        self.reload_if_changed()
    
    def reload_if_changed(self):
        """Check for catalog file changes and reload"""
        current_mtime = os.path.getmtime(self.catalog_path)
        if current_mtime != self.last_modified:
            logger.info("Catalog file changed, reloading...")
            self.tools = self.load_catalog(self.catalog_path)
            self.last_modified = current_mtime
```

## Best Practices and Guidelines

### Tool Definition Standards
- **Consistent Naming**: Use `service-name.action-verb` format
- **Complete Schemas**: Include both input and output validation
- **Rich Examples**: Provide realistic usage examples
- **Clear Descriptions**: Write human-readable tool descriptions
- **Proper Scoping**: Assign minimal necessary scopes

### Schema Design Principles
- **Forward Compatibility**: Design schemas to accommodate future changes
- **Required vs Optional**: Minimize required fields, provide sensible defaults
- **Validation Depth**: Balance strictness with flexibility
- **Error Messages**: Provide actionable validation error messages

### Performance Considerations
- **Timeout Values**: Set realistic timeouts based on tool behavior
- **Caching Strategy**: Cache expensive or stable operations
- **Rate Limiting**: Respect external service limits
- **Batch Operations**: Support bulk operations where possible

## Troubleshooting and Debugging

### Common Issues
- **Schema Validation Errors**: Check input/output format compliance
- **Tool Not Found**: Verify tool address and catalog loading
- **Permission Denied**: Check agent scopes against tool requirements
- **Timeout Errors**: Adjust timeout values or check service health

### Debugging Tools
```python
# Catalog debugging utilities
def debug_tool_catalog(catalog_path: str):
    """Print catalog statistics and potential issues"""
    catalog = load_catalog(catalog_path)
    print(f"Total tools: {len(catalog['tools'])}")
    
    # Check for duplicate addresses
    addresses = [tool['address'] for tool in catalog['tools']]
    duplicates = [addr for addr in addresses if addresses.count(addr) > 1]
    if duplicates:
        print(f"Duplicate addresses found: {duplicates}")
    
    # Check for unreachable endpoints
    for tool in catalog['tools']:
        if not check_tool_availability(tool):
            print(f"Tool {tool['address']} appears unreachable")
```

## Future Enhancements

### Planned Features
- **Dynamic Tool Discovery**: Auto-discover tools from service mesh
- **A/B Testing**: Support for tool version testing and gradual rollouts
- **Cost Optimization**: Automatic selection of cheapest equivalent tools
- **Health Monitoring**: Real-time tool availability and performance tracking

### Integration Roadmap
- **Plugin System**: Support for third-party tool catalog extensions
- **Marketplace**: Community-contributed tool definitions
- **AI-Generated Tools**: LLM-assisted tool discovery and definition creation
- **Visual Tool Builder**: GUI for creating and testing tool definitions

---

*The catalogs directory serves as the comprehensive registry of all available tools, ensuring type safety, proper authorization, and seamless integration across the Ordinaut ecosystem.*