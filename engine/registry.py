# engine/registry.py
"""
Tool Registry for Ordinaut

Manages tool catalog loading, caching, and access with support for
multiple catalog sources (JSON files, environment, database).
Includes scope-based authorization and performance monitoring.
"""

import json
import os
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from datetime import datetime, timedelta
import threading

logger = logging.getLogger(__name__)

class ToolNotFoundError(Exception):
    """Tool not found in catalog."""
    pass

class ScopeViolationError(Exception):
    """Tool access violates scope restrictions."""
    pass

class CatalogRegistry:
    """Thread-safe tool catalog with caching and scope validation."""
    
    def __init__(self, cache_ttl: int = 300):
        self._catalog: List[Dict[str, Any]] = []
        self._catalog_by_address: Dict[str, Dict[str, Any]] = {}
        self._last_reload: Optional[datetime] = None
        self._cache_ttl = timedelta(seconds=cache_ttl)
        self._lock = threading.RLock()
    
    def get_tool(self, address: str, agent_scopes: Optional[Set[str]] = None) -> Dict[str, Any]:
        """
        Get tool definition by address with scope validation.
        
        Args:
            address: Tool address (e.g., "telegram-mcp.send_message")
            agent_scopes: Set of scopes that agent has access to
            
        Returns:
            Tool definition dictionary
            
        Raises:
            ToolNotFoundError: Tool not found in catalog
            ScopeViolationError: Tool requires scopes agent doesn't have
        """
        with self._lock:
            self._ensure_fresh_catalog()
            
            if address not in self._catalog_by_address:
                raise ToolNotFoundError(f"Tool not found: {address}")
            
            tool = self._catalog_by_address[address]
            
            # Check scope requirements
            if agent_scopes is not None:
                required_scopes = set(tool.get("scopes", []))
                if required_scopes and not required_scopes.issubset(agent_scopes):
                    missing_scopes = required_scopes - agent_scopes
                    raise ScopeViolationError(f"Tool {address} requires scopes {missing_scopes}")
            
            return tool
    
    def list_tools(self, agent_scopes: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
        """
        List all tools accessible to agent based on scopes.
        
        Args:
            agent_scopes: Set of scopes that agent has access to
            
        Returns:
            List of tool definitions agent can access
        """
        with self._lock:
            self._ensure_fresh_catalog()
            
            if agent_scopes is None:
                return self._catalog.copy()
            
            accessible_tools = []
            for tool in self._catalog:
                required_scopes = set(tool.get("scopes", []))
                if not required_scopes or required_scopes.issubset(agent_scopes):
                    accessible_tools.append(tool)
            
            return accessible_tools
    
    def reload_catalog(self) -> None:
        """Force reload of tool catalog from all sources."""
        with self._lock:
            self._load_catalog_from_sources()
            self._rebuild_address_index()
            self._last_reload = datetime.now()
            
            logger.info(f"Reloaded tool catalog with {len(self._catalog)} tools")
    
    def _ensure_fresh_catalog(self) -> None:
        """Ensure catalog is fresh, reload if needed."""
        now = datetime.now()
        
        if (self._last_reload is None or 
            now - self._last_reload > self._cache_ttl or 
            not self._catalog):
            self._load_catalog_from_sources()
            self._rebuild_address_index()
            self._last_reload = now
    
    def _load_catalog_from_sources(self) -> None:
        """Load catalog from all configured sources."""
        self._catalog = []
        
        # Source 1: Environment variable pointing to JSON file
        catalog_path = os.environ.get("TOOL_CATALOG_PATH")
        if catalog_path:
            self._load_from_json_file(catalog_path)
        
        # Source 2: Default catalog files in well-known locations
        default_paths = [
            "catalogs/tools.json",
            "tools.json",
            "/etc/orchestrator/tools.json",
            str(Path.home() / ".orchestrator" / "tools.json")
        ]
        
        for path in default_paths:
            if Path(path).exists():
                self._load_from_json_file(path)
                break
        
        # Source 3: Built-in tools if no external catalog found
        if not self._catalog:
            self._load_builtin_catalog()
        
        logger.info(f"Loaded {len(self._catalog)} tools from catalog sources")
    
    def _load_from_json_file(self, file_path: str) -> None:
        """Load tools from JSON catalog file."""
        try:
            with open(file_path, "r") as f:
                catalog_data = json.load(f)
            
            # Support both array format and object with "tools" key
            if isinstance(catalog_data, list):
                tools = catalog_data
            elif isinstance(catalog_data, dict) and "tools" in catalog_data:
                tools = catalog_data["tools"]
            else:
                raise ValueError("Catalog must be array of tools or object with 'tools' key")
            
            # Validate and add tools
            for tool in tools:
                self._validate_tool_definition(tool)
                self._catalog.append(tool)
            
            logger.info(f"Loaded {len(tools)} tools from {file_path}")
            
        except Exception as e:
            logger.error(f"Failed to load catalog from {file_path}: {e}")
    
    def _load_builtin_catalog(self) -> None:
        """Load built-in tool catalog for testing and examples."""
        builtin_tools = [
            # Example Telegram notification tool
            {
                "address": "telegram-mcp.send_message",
                "transport": "http",
                "endpoint": "http://telegram-bridge:8085/tools/send_message",
                "input_schema": {
                    "type": "object",
                    "required": ["chat_id", "text"],
                    "properties": {
                        "chat_id": {"type": "integer", "minimum": 1},
                        "text": {"type": "string", "minLength": 1, "maxLength": 4096},
                        "disable_preview": {"type": "boolean", "default": True}
                    }
                },
                "output_schema": {
                    "type": "object",
                    "required": ["ok", "message_id", "ts"],
                    "properties": {
                        "ok": {"type": "boolean"},
                        "message_id": {"type": "integer"},
                        "ts": {"type": "string", "format": "date-time"}
                    }
                },
                "timeout_seconds": 15,
                "scopes": ["notify"],
                "cost_tier": "low",
                "description": "Send message to Telegram chat"
            },
            
            # Example Google Calendar tool
            {
                "address": "google-calendar-mcp.list_events", 
                "transport": "http",
                "endpoint": "http://gcal-bridge:8086/tools/list_events",
                "input_schema": {
                    "type": "object",
                    "required": ["start", "end"],
                    "properties": {
                        "start": {"type": "string", "format": "date-time"},
                        "end": {"type": "string", "format": "date-time"},
                        "max": {"type": "integer", "default": 50, "maximum": 500}
                    }
                },
                "output_schema": {
                    "type": "object",
                    "required": ["items"],
                    "properties": {
                        "items": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "summary": {"type": "string"},
                                    "start": {"type": "string", "format": "date-time"},
                                    "end": {"type": "string", "format": "date-time"}
                                }
                            }
                        }
                    }
                },
                "timeout_seconds": 20,
                "scopes": ["calendar.read"],
                "cost_tier": "medium",
                "description": "List Google Calendar events in date range"
            },
            
            # Example LLM tool
            {
                "address": "llm.plan",
                "transport": "http", 
                "endpoint": "http://llm-service:8087/tools/plan",
                "input_schema": {
                    "type": "object",
                    "required": ["instruction"],
                    "properties": {
                        "instruction": {"type": "string", "minLength": 10, "maxLength": 2000},
                        "calendar": {"type": "array"},
                        "weather": {"type": "object"},
                        "emails": {"type": "array"}
                    }
                },
                "output_schema": {
                    "type": "object",
                    "required": ["text"],
                    "properties": {
                        "text": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1}
                    }
                },
                "timeout_seconds": 45,
                "scopes": ["llm"],
                "cost_tier": "high",
                "description": "Generate plan using LLM from context data"
            },
            
            # Example test/echo tool
            {
                "address": "echo.test",
                "transport": "http",
                "endpoint": "http://localhost:8090/echo", 
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string"}
                    },
                    "required": ["message"]
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "echoed": {"type": "string"},
                        "timestamp": {"type": "string", "format": "date-time"}
                    },
                    "required": ["echoed"]
                },
                "timeout_seconds": 10,
                "scopes": ["test"],
                "cost_tier": "free",
                "description": "Echo test tool for pipeline validation"
            }
        ]
        
        for tool in builtin_tools:
            self._catalog.append(tool)
        
        logger.info(f"Loaded {len(builtin_tools)} built-in tools")
    
    def _validate_tool_definition(self, tool: Dict[str, Any]) -> None:
        """Validate tool definition has required fields."""
        required_fields = ["address", "transport", "input_schema", "output_schema"]
        
        for field in required_fields:
            if field not in tool:
                raise ValueError(f"Tool missing required field: {field}")
        
        # Validate transport-specific requirements
        transport = tool["transport"]
        if transport == "http" and "endpoint" not in tool:
            raise ValueError("HTTP transport requires 'endpoint' field")
        elif transport == "mcp" and "server" not in tool:
            raise ValueError("MCP transport requires 'server' field") 
        elif transport == "stdio" and "executable" not in tool:
            raise ValueError("Stdio transport requires 'executable' field")
    
    def _rebuild_address_index(self) -> None:
        """Rebuild internal address-to-tool mapping."""
        self._catalog_by_address = {}
        for tool in self._catalog:
            address = tool["address"]
            if address in self._catalog_by_address:
                logger.warning(f"Duplicate tool address: {address}")
            self._catalog_by_address[address] = tool

# Global registry instance
_registry = CatalogRegistry()

def load_catalog() -> List[Dict[str, Any]]:
    """Load tool catalog (backwards compatibility function)."""
    return _registry.list_tools()

def get_tool(catalog: List[Dict[str, Any]], address: str) -> Dict[str, Any]:
    """Get tool definition by address (backwards compatibility function).""" 
    # Ignore the passed catalog and use the registry
    return _registry.get_tool(address)

def get_tool_with_scopes(address: str, agent_scopes: Set[str]) -> Dict[str, Any]:
    """Get tool with scope validation."""
    return _registry.get_tool(address, agent_scopes)

def list_tools_for_agent(agent_scopes: Set[str]) -> List[Dict[str, Any]]:
    """List tools accessible to agent."""
    return _registry.list_tools(agent_scopes)

def reload_tool_catalog() -> None:
    """Reload tool catalog from sources."""
    _registry.reload_catalog()

def load_active_tasks(db_url: str) -> List[Dict[str, Any]]:
    """Load active tasks from database for scheduler."""
    from sqlalchemy import create_engine, text
    
    try:
        eng = create_engine(db_url, pool_pre_ping=True, future=True)
        with eng.begin() as cx:
            rows = cx.execute(text("SELECT * FROM task WHERE status = 'active'")).mappings().fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Failed to load active tasks: {e}")
        return []