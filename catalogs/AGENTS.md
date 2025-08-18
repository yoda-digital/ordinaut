# Ordinaut - Catalogs Directory (Current State)

## ⚠️ **CURRENT STATE (August 2025)**

**FUNCTIONALITY REMOVED**: The tool catalog system has been removed from the Ordinaut core system as part of the architectural refactoring to create a pure task scheduler foundation.

## Purpose and Role

The `catalogs/` directory **previously** contained tool catalog definitions. This functionality has been **removed from the core system** and will be **reimplemented as extensions**.

**Current Status:**
- ❌ **Tool Catalogs**: Removed from core system
- ❌ **Tool Discovery**: No longer part of core scheduler
- ❌ **Tool Validation**: Framework preserved, catalogs removed
- ✅ **Directory Structure**: Maintained for future extension development

## Directory Contents (Current)

### Current Files
- **`CLAUDE.md`** - Documentation about current system state
- **`AGENTS.md`** - This file - agent configuration documentation

### Previously Removed Files
- ❌ **`tools.json`** - Tool catalog removed (August 2025)
- ❌ **Enterprise tool catalogs** - Functionality removed from core
- ❌ **Custom tool definitions** - Will be implemented as extensions

## Future Extension Architecture

When tool functionality is reimplemented as extensions, the architecture will follow this pattern:

### Extension-Based Tool Integration
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   AI Assistant │    │  MCP Extension   │    │ Ordinaut Core   │
│  (Claude/GPT)   │◄──►│     Server       │◄──►│ (Pure Scheduler)│
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │                      ▲
                                ▼                      │
                       ┌──────────────────┐           │ REST API
                       │ Tool Extensions  │           │
                       │ (HTTP Services)  │───────────┘
                       └──────────────────┘
```

### Future Tool Definition Schema
Extensions will register tools using a structure similar to:

```json
{
  "address": "weather-mcp.forecast",
  "description": "Get weather forecast for a location", 
  "input_schema": {
    "type": "object",
    "required": ["location"],
    "properties": {
      "location": {"type": "string", "description": "City name"}
    }
  },
  "output_schema": {
    "type": "object", 
    "required": ["temperature", "condition"],
    "properties": {
      "temperature": {"type": "number"},
      "condition": {"type": "string"}
    }
  }
}
```

## Current Development Status

**Core System Status**: ✅ **COMPLETE**
- Pure task scheduler operational
- Pipeline structure processing working
- Template resolution functional 
- Tool simulation implemented
- REST APIs ready for extension integration

**Extension Development Status**: 🔄 **PLANNED**
- MCP server extension design complete
- Tool integration architecture specified  
- REST API contracts defined
- Implementation pending

## Migration Path

When implementing tool extensions:

1. **MCP Server Extension** - Receives requests from AI assistants
2. **Tool Service Extensions** - Implement actual tool functionality  
3. **Registration System** - Extensions register available tools via REST API
4. **Pipeline Integration** - Core scheduler calls extensions for tool execution
5. **Context Preservation** - Same pipeline result format maintained

**Developer Note**: The core scheduler now provides a clean, stable foundation for extension development. All scheduling, persistence, and pipeline processing work correctly with tool simulation.

---

*This directory will serve as the foundation for future extension-based tool integration when MCP and tool functionality are reimplemented as separate services.*