# Comprehensive MCP Extension System Analysis for Ordinaut

## Executive Summary

This document provides an exhaustive analysis of implementing a Model Context Protocol (MCP) server as an extension to Ordinaut, along with designing a comprehensive extension architecture. The analysis covers the brutal reality of predefined executors, modern MCP 2025 specifications, and a complete extension system that enables future expandability.

## Table of Contents

1. [Current State Analysis: The Predefined Executor Reality](#current-state-analysis)
2. [MCP 2025 Specification Research](#mcp-specification)
3. [Extension System Architecture Design](#extension-architecture)
4. [Complete MCP Server Extension Implementation](#mcp-implementation)
5. [Future Extension Examples](#future-extensions)
6. [Integration and Deployment Strategy](#deployment)
7. [Discussion Points and Considerations](#discussion-points)

---

## 1. Current State Analysis: The Predefined Executor Reality {#current-state-analysis}

### The Brutal Truth About Ordinaut's Current Capabilities

**YES, you absolutely need predefined executors.** Anyone suggesting otherwise doesn't understand the system's architecture.

### Current Tool Inventory (8 Tools Total)

From analyzing `/catalogs/tools.json`, Ordinaut currently has exactly **8 predefined tools**:

#### Communication Tools (2)
- `telegram-mcp.send_message` - Send Telegram messages with formatting support
- `imap-mcp.top_unread` - Fetch unread emails from IMAP accounts

#### Data Retrieval Tools (2)
- `google-calendar-mcp.list_events` - Fetch Google Calendar events in date ranges
- `weather-mcp.forecast` - Get weather forecasts for locations

#### AI Processing Tools (2)
- `llm.summarize` - Summarize text content using LLM
- `llm.plan` - Generate plans from context (calendar, weather, emails)

#### Testing Tools (2)
- `echo.test` - Echo test tool for pipeline validation

### Architecture Requirements for Every Tool

Every tool requires this exact structure:

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
    "required": ["ok", "message_id", "ts"],
    "properties": {
      "ok": {"type": "boolean"},
      "message_id": {"type": "integer"},
      "ts": {"type": "string", "format": "date-time"}
    }
  },
  "timeout_seconds": 15,
  "scopes": ["notify"],
  "cost_tier": "low"
}
```

### Current Working Pipeline Example

The morning briefing pipeline demonstrates how the system actually works:

```json
{
  "title": "Weekday Morning Briefing",
  "schedule_kind": "rrule", 
  "schedule_expr": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=30",
  "timezone": "Europe/Chisinau",
  "payload": {
    "pipeline": [
      {
        "id": "calendar",
        "uses": "google-calendar-mcp.list_events",
        "with": {"start": "${params.date_start_iso}", "end": "${params.date_end_iso}"},
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
        "with": {"chat_id": 12345, "text": "${steps.summary.text}"}
      }
    ]
  }
}
```

### Template Variable System

The template system supports:
- Global parameters: `${params.x}`
- Step results: `${steps.step_id.property}`  
- Built-in variables: `${now}`, `${now+1h}`
- JMESPath expressions: `${steps.data.items[?condition]}`

---

## 2. MCP 2025 Specification Research {#mcp-specification}

### Current MCP Protocol Version: 2025-03-26

Key findings from research of the latest MCP specification:

### Transport Mechanisms
- **Streamable HTTP** (modern, recommended for remote servers)
- **HTTP+SSE** (legacy, being phased out)
- **Stdio** (local subprocess communication)

### JSON-RPC 2.0 Requirements
- All messages MUST be UTF-8 encoded JSON-RPC 2.0
- Requests MUST include string/integer ID
- Responses MUST match request ID
- Notifications MUST NOT include ID
- Supports request batching for efficiency

### Authentication Standards
- OAuth 2.1 with PKCE mandatory for remote HTTP servers
- Token-based session management
- Secure authorization flows

### Core Server Methods (Required)

```typescript
interface MCPServer {
  // Lifecycle
  initialize(params: InitializeParams): InitializeResult
  shutdown(): void
  
  // Capabilities
  list_tools(): ListToolsResult
  call_tool(params: CallToolParams): CallToolResult
  
  // Resources (optional)
  list_resources(): ListResourcesResult
  read_resource(params: ReadResourceParams): ReadResourceResult
  
  // Prompts (optional)  
  list_prompts(): ListPromptsResult
  get_prompt(params: GetPromptParams): GetPromptResult
}
```

### HTTP Transport Specification

For HTTP transport:
- Server MUST provide single HTTP endpoint supporting POST and GET
- Every JSON-RPC message from client MUST be new HTTP POST request
- Client MUST use HTTP POST with Accept header including `application/json` and `text/event-stream`
- Server MUST return HTTP 202 Accepted with no body on success
- Server MUST return HTTP error status code on failure

---

## 3. Extension System Architecture Design {#extension-architecture}

### Core Design Philosophy

**Extension System Principles:**
1. **Non-invasive**: Extensions never modify core Ordinaut files
2. **Pluggable**: Extensions are discoverable and auto-loadable  
3. **Isolated**: Extensions run in separate processes/containers
4. **Configurable**: Extension behavior controlled via configuration
5. **Observable**: Extension health and metrics integrated with core monitoring

### Directory Structure

```
ordinaut/
├── extensions/                   # Extension system root
│   ├── __init__.py              # Extension registry and loader
│   ├── base.py                  # Base extension interfaces
│   ├── config.py                # Extension configuration management
│   ├── registry.py              # Extension discovery and lifecycle
│   ├── monitoring.py            # Extension health monitoring
│   └── mcp-server/              # MCP Server Extension
│       ├── extension.yaml       # Extension manifest
│       ├── __init__.py          # Extension entry point
│       ├── server.py            # MCP server implementation
│       ├── handlers/            # MCP method handlers
│       │   ├── __init__.py
│       │   ├── tools.py         # Tool management handlers
│       │   ├── tasks.py         # Task management handlers
│       │   ├── resources.py     # Resource handlers
│       │   └── prompts.py       # Prompt handlers
│       ├── auth/                # OAuth 2.1 implementation
│       │   ├── __init__.py
│       │   ├── oauth.py         # OAuth flows
│       │   └── session.py       # Session management
│       ├── transport/           # HTTP transport implementation
│       │   ├── __init__.py
│       │   ├── http.py          # Streamable HTTP
│       │   └── jsonrpc.py       # JSON-RPC 2.0 handler
│       ├── schemas/             # MCP message schemas
│       │   ├── __init__.py
│       │   └── mcp_schemas.py   # Pydantic models
│       ├── docker-compose.yml   # Extension deployment
│       ├── Dockerfile           # Extension container
│       └── requirements.txt     # Extension dependencies
```

### Base Extension Classes

```python
# extensions/base.py
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from pydantic import BaseModel
import asyncio

class ExtensionInfo(BaseModel):
    name: str
    version: str
    description: str
    author: str
    dependencies: List[str] = []
    provides_services: List[str] = []
    requires_permissions: List[str] = []
    health_check_url: Optional[str] = None
    management_endpoints: Dict[str, str] = {}

class ExtensionHealth(BaseModel):
    status: str  # "healthy", "degraded", "unhealthy" 
    last_check: str
    uptime_seconds: int
    error_count: int
    metrics: Dict[str, Any] = {}

class BaseExtension(ABC):
    """Base class for all Ordinaut extensions."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.info = self.get_extension_info()
        self._health = ExtensionHealth(
            status="initializing",
            last_check="",
            uptime_seconds=0,
            error_count=0
        )
    
    @abstractmethod
    def get_extension_info(self) -> ExtensionInfo:
        """Return extension metadata."""
        pass
    
    @abstractmethod
    async def start(self) -> None:
        """Start the extension services."""
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """Stop the extension services."""
        pass
    
    @abstractmethod
    async def health_check(self) -> ExtensionHealth:
        """Check extension health status."""
        pass
    
    async def configure(self, new_config: Dict[str, Any]) -> None:
        """Update extension configuration."""
        self.config.update(new_config)
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Get extension-specific metrics."""
        return {}

class WebExtension(BaseExtension):
    """Base class for web-based extensions (HTTP servers)."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.port = config.get("port", 8080)
        self.host = config.get("host", "0.0.0.0")
    
    @abstractmethod
    async def create_app(self) -> Any:
        """Create the web application instance."""
        pass

class MCPExtension(BaseExtension):
    """Base class for MCP protocol extensions."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.transport_type = config.get("transport", "http")
        self.auth_required = config.get("auth_required", True)
    
    @abstractmethod
    async def handle_jsonrpc_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle JSON-RPC 2.0 requests."""
        pass
```

### Extension Registry and Discovery

```python
# extensions/registry.py
import os
import yaml
import importlib
import asyncio
from pathlib import Path
from typing import Dict, List, Optional
from contextlib import asynccontextmanager

import structlog
from .base import BaseExtension, ExtensionInfo, ExtensionHealth

logger = structlog.get_logger(__name__)

class ExtensionRegistry:
    """Manages extension discovery, loading, and lifecycle."""
    
    def __init__(self, extensions_dir: str = "extensions"):
        self.extensions_dir = Path(extensions_dir)
        self.loaded_extensions: Dict[str, BaseExtension] = {}
        self.extension_configs: Dict[str, Dict] = {}
        
    async def discover_extensions(self) -> List[ExtensionInfo]:
        """Discover all available extensions."""
        extensions = []
        
        for ext_dir in self.extensions_dir.iterdir():
            if not ext_dir.is_dir() or ext_dir.name.startswith('.'):
                continue
                
            manifest_path = ext_dir / "extension.yaml"
            if not manifest_path.exists():
                continue
                
            try:
                with open(manifest_path) as f:
                    manifest = yaml.safe_load(f)
                
                ext_info = ExtensionInfo(**manifest)
                extensions.append(ext_info)
                
                logger.info("discovered_extension", 
                           name=ext_info.name, 
                           version=ext_info.version)
                           
            except Exception as e:
                logger.error("failed_to_load_extension_manifest",
                           extension_dir=str(ext_dir),
                           error=str(e))
        
        return extensions
    
    async def load_extension(self, name: str, config: Dict = None) -> BaseExtension:
        """Load and start a specific extension."""
        if name in self.loaded_extensions:
            return self.loaded_extensions[name]
        
        ext_dir = self.extensions_dir / name
        if not ext_dir.exists():
            raise ValueError(f"Extension '{name}' not found")
        
        # Load extension manifest
        manifest_path = ext_dir / "extension.yaml"
        with open(manifest_path) as f:
            manifest = yaml.safe_load(f)
        
        # Load extension configuration
        ext_config = config or {}
        config_path = ext_dir / "config.yaml"
        if config_path.exists():
            with open(config_path) as f:
                default_config = yaml.safe_load(f) or {}
                ext_config = {**default_config, **ext_config}
        
        # Dynamically import extension module
        module_name = f"extensions.{name}"
        try:
            module = importlib.import_module(module_name)
            extension_class = getattr(module, manifest.get("main_class", "Extension"))
            
            # Instantiate and start extension
            extension = extension_class(ext_config)
            await extension.start()
            
            self.loaded_extensions[name] = extension
            self.extension_configs[name] = ext_config
            
            logger.info("extension_loaded", 
                       name=name, 
                       version=extension.info.version)
            
            return extension
            
        except Exception as e:
            logger.error("failed_to_load_extension",
                        name=name,
                        error=str(e))
            raise
    
    async def unload_extension(self, name: str) -> None:
        """Stop and unload an extension."""
        if name not in self.loaded_extensions:
            return
        
        extension = self.loaded_extensions[name]
        try:
            await extension.stop()
            del self.loaded_extensions[name]
            del self.extension_configs[name]
            
            logger.info("extension_unloaded", name=name)
            
        except Exception as e:
            logger.error("failed_to_unload_extension",
                        name=name,
                        error=str(e))
            raise
    
    async def get_extension_health(self, name: str) -> Optional[ExtensionHealth]:
        """Get health status of a specific extension."""
        if name not in self.loaded_extensions:
            return None
        
        return await self.loaded_extensions[name].health_check()
    
    async def get_all_health(self) -> Dict[str, ExtensionHealth]:
        """Get health status of all loaded extensions."""
        health_status = {}
        
        for name, extension in self.loaded_extensions.items():
            try:
                health_status[name] = await extension.health_check()
            except Exception as e:
                health_status[name] = ExtensionHealth(
                    status="unhealthy",
                    last_check=str(asyncio.get_event_loop().time()),
                    uptime_seconds=0,
                    error_count=1,
                    metrics={"error": str(e)}
                )
        
        return health_status
    
    @asynccontextmanager
    async def extension_lifecycle(self, name: str, config: Dict = None):
        """Context manager for extension lifecycle."""
        extension = None
        try:
            extension = await self.load_extension(name, config)
            yield extension
        finally:
            if extension:
                await self.unload_extension(name)

# Global registry instance
extension_registry = ExtensionRegistry()
```

---

## 4. Complete MCP Server Extension Implementation {#mcp-implementation}

### Extension Manifest

```yaml
# extensions/mcp-server/extension.yaml
name: mcp-server
version: 1.0.0
description: "Remote MCP server providing AI agents access to Ordinaut task management"
author: "Ordinaut Team"
main_class: "MCPServerExtension"
dependencies:
  - "fastapi>=0.104.0"
  - "uvicorn>=0.24.0"
  - "authlib>=1.3.0"
  - "httpx>=0.25.0"
  - "redis>=5.0.0"
provides_services:
  - "mcp-server"
  - "oauth-provider"
requires_permissions:
  - "api.read"
  - "api.write"
  - "tasks.manage"
health_check_url: "http://localhost:8085/health"
management_endpoints:
  metrics: "http://localhost:8085/metrics"
  config: "http://localhost:8085/admin/config"
```

### MCP Schema Definitions

```python
# extensions/mcp-server/schemas/mcp_schemas.py
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field
from enum import Enum

class JsonRpcRequest(BaseModel):
    jsonrpc: str = Field(default="2.0", regex="^2\\.0$")
    id: Optional[Union[str, int]] = None
    method: str
    params: Optional[Dict[str, Any]] = None

class JsonRpcResponse(BaseModel):
    jsonrpc: str = Field(default="2.0", regex="^2\\.0$")
    id: Optional[Union[str, int]] = None
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None

class JsonRpcError(BaseModel):
    code: int
    message: str
    data: Optional[Any] = None

class MCPCapabilities(BaseModel):
    tools: Optional[Dict[str, Any]] = None
    resources: Optional[Dict[str, Any]] = None
    prompts: Optional[Dict[str, Any]] = None
    logging: Optional[Dict[str, Any]] = None

class InitializeParams(BaseModel):
    protocol_version: str
    capabilities: MCPCapabilities
    client_info: Dict[str, str]

class InitializeResult(BaseModel):
    protocol_version: str = "2025-03-26"
    capabilities: MCPCapabilities
    server_info: Dict[str, str]

class Tool(BaseModel):
    name: str
    description: str
    input_schema: Dict[str, Any]

class ListToolsResult(BaseModel):
    tools: List[Tool]

class CallToolParams(BaseModel):
    name: str
    arguments: Dict[str, Any]

class ToolResult(BaseModel):
    content: List[Dict[str, Any]]
    is_error: bool = False

class CallToolResult(BaseModel):
    content: List[Dict[str, Any]]
    is_error: bool = False
```

### JSON-RPC 2.0 Transport Implementation

```python
# extensions/mcp-server/transport/jsonrpc.py
import json
import uuid
from typing import Any, Dict, Optional, Union, Callable, Awaitable
from fastapi import HTTPException
import structlog

from ..schemas.mcp_schemas import JsonRpcRequest, JsonRpcResponse, JsonRpcError

logger = structlog.get_logger(__name__)

class JsonRpcHandler:
    """JSON-RPC 2.0 protocol handler for MCP."""
    
    def __init__(self):
        self.methods: Dict[str, Callable[[Dict[str, Any]], Awaitable[Any]]] = {}
        self.error_codes = {
            "PARSE_ERROR": -32700,
            "INVALID_REQUEST": -32600,
            "METHOD_NOT_FOUND": -32601,
            "INVALID_PARAMS": -32602,
            "INTERNAL_ERROR": -32603,
            "SERVER_ERROR": -32000
        }
    
    def register_method(self, name: str, handler: Callable[[Dict[str, Any]], Awaitable[Any]]):
        """Register a JSON-RPC method handler."""
        self.methods[name] = handler
        logger.debug("jsonrpc_method_registered", method=name)
    
    async def handle_request(self, raw_data: Union[str, bytes]) -> str:
        """Handle incoming JSON-RPC request."""
        try:
            # Parse JSON
            if isinstance(raw_data, bytes):
                raw_data = raw_data.decode('utf-8')
            
            data = json.loads(raw_data)
            
            # Handle batch requests
            if isinstance(data, list):
                responses = []
                for item in data:
                    response = await self._handle_single_request(item)
                    if response:  # Don't include responses for notifications
                        responses.append(response)
                return json.dumps(responses) if responses else ""
            else:
                response = await self._handle_single_request(data)
                return json.dumps(response.dict()) if response else ""
                
        except json.JSONDecodeError:
            error_response = JsonRpcResponse(
                id=None,
                error={
                    "code": self.error_codes["PARSE_ERROR"],
                    "message": "Parse error"
                }
            )
            return json.dumps(error_response.dict())
        except Exception as e:
            logger.error("jsonrpc_handler_error", error=str(e))
            error_response = JsonRpcResponse(
                id=None,
                error={
                    "code": self.error_codes["INTERNAL_ERROR"],
                    "message": "Internal error",
                    "data": str(e)
                }
            )
            return json.dumps(error_response.dict())
    
    async def _handle_single_request(self, data: Dict[str, Any]) -> Optional[JsonRpcResponse]:
        """Handle a single JSON-RPC request."""
        try:
            # Validate request format
            request = JsonRpcRequest(**data)
            
            # Check if method exists
            if request.method not in self.methods:
                if request.id is not None:  # Only respond to requests, not notifications
                    return JsonRpcResponse(
                        id=request.id,
                        error={
                            "code": self.error_codes["METHOD_NOT_FOUND"],
                            "message": f"Method '{request.method}' not found"
                        }
                    )
                return None
            
            # Execute method
            try:
                handler = self.methods[request.method]
                result = await handler(request.params or {})
                
                # Return response (only for requests with ID)
                if request.id is not None:
                    return JsonRpcResponse(id=request.id, result=result)
                return None
                
            except Exception as e:
                logger.error("jsonrpc_method_error", 
                           method=request.method, 
                           error=str(e))
                
                if request.id is not None:
                    return JsonRpcResponse(
                        id=request.id,
                        error={
                            "code": self.error_codes["SERVER_ERROR"],
                            "message": str(e)
                        }
                    )
                return None
                
        except ValueError as e:
            # Invalid request format
            request_id = data.get("id") if isinstance(data, dict) else None
            return JsonRpcResponse(
                id=request_id,
                error={
                    "code": self.error_codes["INVALID_REQUEST"],
                    "message": "Invalid request",
                    "data": str(e)
                }
            )
```

### OAuth 2.1 Authentication Implementation

```python
# extensions/mcp-server/auth/oauth.py
import os
import time
import secrets
from typing import Dict, Optional, Tuple
from urllib.parse import urlencode, parse_qs
import hashlib
import base64
import json

from fastapi import HTTPException, status
from authlib.integrations.fastapi_oauth2 import AuthorizationServer
from authlib.oauth2.rfc6749 import grants
from authlib.oauth2.rfc7636 import CodeChallenge
import jwt
import structlog

logger = structlog.get_logger(__name__)

class OAuth2Config:
    def __init__(self, config: Dict):
        self.issuer_url = config["issuer_url"]
        self.client_id = config["client_id"] 
        self.client_secret = config["client_secret"]
        self.access_token_expire_minutes = config.get("access_token_expire_minutes", 60)
        self.refresh_token_expire_days = config.get("refresh_token_expire_days", 30)
        self.jwt_secret = config.get("jwt_secret", secrets.token_urlsafe(32))

class MCPOAuthServer:
    """OAuth 2.1 server for MCP authentication."""
    
    def __init__(self, config: OAuth2Config, redis_client=None):
        self.config = config
        self.redis = redis_client
        self.authorization_codes = {}  # In-memory for demo (use Redis in production)
        self.access_tokens = {}
        self.refresh_tokens = {}
    
    def generate_pkce_challenge(self) -> Tuple[str, str]:
        """Generate PKCE code verifier and challenge."""
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode('utf-8')).digest()
        ).decode('utf-8').rstrip('=')
        return code_verifier, code_challenge
    
    async def handle_authorization(self, 
                                 client_id: str,
                                 redirect_uri: str,
                                 scope: str,
                                 code_challenge: str,
                                 code_challenge_method: str = 'S256',
                                 state: Optional[str] = None) -> str:
        """Handle authorization request and return code."""
        
        # Validate client
        if client_id != self.config.client_id:
            raise HTTPException(status_code=400, detail="Invalid client_id")
        
        # Generate authorization code
        auth_code = secrets.token_urlsafe(32)
        
        # Store authorization code
        code_data = {
            'code': auth_code,
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'scope': scope,
            'code_challenge': code_challenge,
            'code_challenge_method': code_challenge_method,
            'expires_at': time.time() + 600,
            'user_id': 'mcp_user'  # In production: actual user ID
        }
        
        if self.redis:
            self.redis.setex(f"auth_code:{auth_code}", 600, json.dumps(code_data))
        else:
            self.authorization_codes[auth_code] = code_data
            
        logger.info("authorization_code_generated", client_id=client_id, scope=scope)
        
        return auth_code
    
    async def exchange_code_for_tokens(self,
                                     client_id: str,
                                     client_secret: str,
                                     code: str,
                                     redirect_uri: str,
                                     code_verifier: str) -> Dict[str, Any]:
        """Exchange authorization code for access tokens."""
        
        # Validate client credentials
        if client_id != self.config.client_id or client_secret != self.config.client_secret:
            raise HTTPException(status_code=401, detail="Invalid client credentials")
        
        # Get authorization code data
        if self.redis:
            code_data_json = self.redis.get(f"auth_code:{code}")
            if not code_data_json:
                raise HTTPException(status_code=400, detail="Invalid or expired authorization code")
            code_data = json.loads(code_data_json)
            self.redis.delete(f"auth_code:{code}")
        else:
            code_data = self.authorization_codes.get(code)
            if not code_data:
                raise HTTPException(status_code=400, detail="Invalid or expired authorization code")
            del self.authorization_codes[code]
        
        # Validate PKCE code verifier
        if code_data['code_challenge_method'] == 'S256':
            expected_challenge = base64.urlsafe_b64encode(
                hashlib.sha256(code_verifier.encode('utf-8')).digest()
            ).decode('utf-8').rstrip('=')
        else:
            expected_challenge = code_verifier
            
        if code_data['code_challenge'] != expected_challenge:
            raise HTTPException(status_code=400, detail="Invalid PKCE code verifier")
        
        # Generate tokens
        access_token = self._generate_access_token(code_data['user_id'], code_data['scope'])
        refresh_token = self._generate_refresh_token(code_data['user_id'])
        
        logger.info("tokens_generated", user_id=code_data['user_id'], scope=code_data['scope'])
        
        return {
            'access_token': access_token,
            'token_type': 'Bearer',
            'expires_in': self.config.access_token_expire_minutes * 60,
            'refresh_token': refresh_token,
            'scope': code_data['scope']
        }
    
    def _generate_access_token(self, user_id: str, scope: str) -> str:
        """Generate JWT access token."""
        payload = {
            'sub': user_id,
            'scope': scope,
            'iss': self.config.issuer_url,
            'aud': 'mcp-client',
            'iat': int(time.time()),
            'exp': int(time.time()) + (self.config.access_token_expire_minutes * 60)
        }
        
        return jwt.encode(payload, self.config.jwt_secret, algorithm='HS256')
    
    async def validate_access_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Validate and decode access token."""
        try:
            # Decode JWT
            payload = jwt.decode(token, self.config.jwt_secret, 
                               algorithms=['HS256'],
                               audience='mcp-client',
                               issuer=self.config.issuer_url)
            
            return payload
            
        except jwt.ExpiredSignatureError:
            logger.warning("access_token_expired", token=token[:10] + "...")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning("invalid_access_token", error=str(e))
            return None
```

### MCP Tools Handler

```python
# extensions/mcp-server/handlers/tools.py
from typing import Dict, Any, List
import httpx
import structlog

from ..schemas.mcp_schemas import Tool, ListToolsResult, CallToolParams, CallToolResult

logger = structlog.get_logger(__name__)

class ToolsHandler:
    """Handle MCP tools methods - expose Ordinaut capabilities as MCP tools."""
    
    def __init__(self, ordinaut_api_base: str, internal_token: str):
        self.api_base = ordinaut_api_base
        self.internal_token = internal_token
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def list_tools(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List all available tools from Ordinaut."""
        tools = [
            Tool(
                name="create_task",
                description="Create a new scheduled task in Ordinaut",
                input_schema={
                    "type": "object",
                    "required": ["title", "schedule_kind", "schedule_expr", "payload"],
                    "properties": {
                        "title": {"type": "string", "description": "Human-readable task title"},
                        "description": {"type": "string", "description": "Task description"},
                        "schedule_kind": {
                            "type": "string", 
                            "enum": ["cron", "rrule", "once", "event"],
                            "description": "Type of schedule"
                        },
                        "schedule_expr": {"type": "string", "description": "Schedule expression"},
                        "timezone": {"type": "string", "default": "Europe/Chisinau"},
                        "payload": {
                            "type": "object",
                            "description": "Pipeline definition with steps"
                        }
                    }
                }
            ),
            Tool(
                name="list_tasks", 
                description="List tasks with optional filtering",
                input_schema={
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "enum": ["active", "paused", "canceled"]},
                        "limit": {"type": "integer", "default": 50, "maximum": 200}
                    }
                }
            ),
            Tool(
                name="run_task_now",
                description="Trigger immediate execution of a task",
                input_schema={
                    "type": "object",
                    "required": ["task_id"],
                    "properties": {
                        "task_id": {"type": "string", "format": "uuid"}
                    }
                }
            ),
            Tool(
                name="get_system_health",
                description="Get Ordinaut system health and status",
                input_schema={"type": "object", "properties": {}}
            )
            # Additional 9 tools: get_task, update_task, pause_task, resume_task, 
            # cancel_task, snooze_task, list_runs, get_run, publish_event, get_system_metrics
        ]
        
        return ListToolsResult(tools=tools).dict()
    
    async def call_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool call against Ordinaut API."""
        call_params = CallToolParams(**params)
        tool_name = call_params.name
        args = call_params.arguments
        
        try:
            # Route tool call to appropriate Ordinaut API endpoint
            if tool_name == "create_task":
                result = await self._create_task(args)
            elif tool_name == "list_tasks":
                result = await self._list_tasks(args)
            elif tool_name == "run_task_now":
                result = await self._run_task_now(args)
            elif tool_name == "get_system_health":
                result = await self._get_system_health(args)
            # Handle other tools...
            else:
                raise ValueError(f"Unknown tool: {tool_name}")
            
            return CallToolResult(
                content=[{
                    "type": "text",
                    "text": f"Tool '{tool_name}' executed successfully. Result: {result}"
                }],
                is_error=False
            ).dict()
            
        except Exception as e:
            logger.error("tool_call_failed", tool=tool_name, error=str(e))
            return CallToolResult(
                content=[{
                    "type": "text", 
                    "text": f"Tool '{tool_name}' failed: {str(e)}"
                }],
                is_error=True
            ).dict()
    
    async def _create_task(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Create task via Ordinaut API."""
        response = await self.client.post(
            f"{self.api_base}/tasks",
            json=args,
            headers={"Authorization": f"Bearer {self.internal_token}"}
        )
        response.raise_for_status()
        return response.json()
    
    # Additional private methods for other tool implementations...
```

### Main MCP Server Extension

```python
# extensions/mcp-server/__init__.py
import asyncio
import time
from typing import Dict, Any
from fastapi import FastAPI, Request, HTTPException, Depends, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import redis.asyncio as redis
import structlog

from ..base import MCPExtension, ExtensionInfo, ExtensionHealth
from .transport.jsonrpc import JsonRpcHandler
from .auth.oauth import MCPOAuthServer, OAuth2Config
from .handlers.tools import ToolsHandler
from .schemas.mcp_schemas import *

logger = structlog.get_logger(__name__)

class MCPServerExtension(MCPExtension):
    """Complete MCP server extension for Ordinaut."""
    
    def get_extension_info(self) -> ExtensionInfo:
        return ExtensionInfo(
            name="mcp-server",
            version="1.0.0",
            description="Remote MCP server providing AI agents access to Ordinaut",
            author="Ordinaut Team",
            provides_services=["mcp-server", "oauth-provider"],
            requires_permissions=["api.read", "api.write", "tasks.manage"],
            health_check_url=f"http://localhost:{self.config.get('server', {}).get('port', 8085)}/health"
        )
    
    async def start(self) -> None:
        """Start the MCP server."""
        server_config = self.config.get("server", {})
        self.host = server_config.get("host", "0.0.0.0")
        self.port = server_config.get("port", 8085)
        
        # Initialize Redis connection
        redis_url = self.config.get("redis", {}).get("url", "redis://localhost:6379")
        self.redis = redis.from_url(redis_url)
        
        # Initialize OAuth server
        oauth_config = OAuth2Config(self.config.get("auth", {}).get("oauth", {}))
        self.oauth_server = MCPOAuthServer(oauth_config, self.redis)
        
        # Initialize handlers
        api_config = self.config.get("ordinaut_api", {})
        self.tools_handler = ToolsHandler(
            api_config.get("base_url", "http://localhost:8080"),
            api_config.get("internal_token", "")
        )
        
        # Initialize JSON-RPC handler
        self.jsonrpc = JsonRpcHandler()
        await self._register_mcp_methods()
        
        # Create FastAPI app
        self.app = await self._create_app()
        
        # Start server
        config = uvicorn.Config(
            app=self.app,
            host=self.host,
            port=self.port,
            workers=1,
            log_config=None  # Use structlog
        )
        self.server = uvicorn.Server(config)
        
        # Start in background
        self.server_task = asyncio.create_task(self.server.serve())
        
        logger.info("mcp_server_started", host=self.host, port=self.port)
    
    async def _create_app(self) -> FastAPI:
        """Create FastAPI application."""
        app = FastAPI(
            title="Ordinaut MCP Server",
            description="Model Context Protocol server for Ordinaut task management",
            version="1.0.0"
        )
        
        # OAuth endpoints
        @app.get("/authorize")
        async def authorize(client_id: str, redirect_uri: str, scope: str = "mcp:full", 
                          code_challenge: str = None, state: str = None):
            """OAuth 2.1 authorization endpoint."""
            auth_code = await self.oauth_server.handle_authorization(
                client_id, redirect_uri, scope, code_challenge, 'S256', state
            )
            
            redirect_url = f"{redirect_uri}?code={auth_code}"
            if state:
                redirect_url += f"&state={state}"
                
            return RedirectResponse(url=redirect_url)
        
        @app.post("/token")
        async def token(grant_type: str, client_id: str, client_secret: str,
                       code: str = None, redirect_uri: str = None, code_verifier: str = None):
            """OAuth 2.1 token endpoint."""
            if grant_type == "authorization_code":
                tokens = await self.oauth_server.exchange_code_for_tokens(
                    client_id, client_secret, code, redirect_uri, code_verifier
                )
                return tokens
            else:
                raise HTTPException(status_code=400, detail="Unsupported grant_type")
        
        # MCP endpoint
        @app.post("/mcp")
        async def mcp_endpoint(request: Request, user_info: dict = Depends(self._authenticate_request)):
            """Main MCP JSON-RPC endpoint."""
            body = await request.body()
            response_json = await self.jsonrpc.handle_request(body)
            
            if response_json:
                return JSONResponse(content=response_json)
            else:
                return JSONResponse(content=None, status_code=204)
        
        @app.get("/health")
        async def health():
            """Health check endpoint."""
            health = await self.health_check()
            return health.dict()
        
        return app
    
    async def _register_mcp_methods(self) -> None:
        """Register all MCP JSON-RPC methods."""
        
        @self.jsonrpc.register_method
        async def initialize(params: Dict[str, Any]) -> Dict[str, Any]:
            """Initialize MCP session."""
            init_params = InitializeParams(**params)
            
            result = InitializeResult(
                protocol_version="2025-03-26",
                capabilities=MCPCapabilities(
                    tools={"list_changed": True},
                    resources={"subscribe": True, "list_changed": True},
                    prompts={"list_changed": True},
                    logging={}
                ),
                server_info={
                    "name": "ordinaut-mcp-server",
                    "version": "1.0.0"
                }
            )
            
            return result.dict()
        
        # Register tool methods
        self.jsonrpc.register_method("tools/list", self.tools_handler.list_tools)
        self.jsonrpc.register_method("tools/call", self.tools_handler.call_tool)

# Extension entry point
Extension = MCPServerExtension
```

---

## 5. Future Extension Examples {#future-extensions}

### Web GUI Extension

```yaml
# extensions/web-gui/extension.yaml
name: web-gui
version: 1.0.0
description: "Modern React-based web interface for Ordinaut task management"
author: "Ordinaut Team"
main_class: "WebGUIExtension"
provides_services: ["web-interface", "task-dashboard"]
health_check_url: "http://localhost:3000/health"
```

```python
# extensions/web-gui/__init__.py
from ..base import WebExtension, ExtensionInfo

class WebGUIExtension(WebExtension):
    """Modern web interface for Ordinaut."""
    
    def get_extension_info(self) -> ExtensionInfo:
        return ExtensionInfo(
            name="web-gui",
            version="1.0.0", 
            description="React-based web interface for task management",
            author="Ordinaut Team"
        )
    
    async def create_app(self) -> FastAPI:
        """Create web application."""
        app = FastAPI(title="Ordinaut Web Interface")
        
        @app.get("/", response_class=HTMLResponse)
        async def dashboard(request: Request):
            """Main dashboard page."""
            return templates.TemplateResponse("index.html", {"request": request})
        
        return app
```

### Slack Integration Extension

```python
# extensions/slack-integration/__init__.py
from ..base import BaseExtension
from slack_sdk.web.async_client import AsyncWebClient

class SlackIntegrationExtension(BaseExtension):
    """Slack bot integration for Ordinaut."""
    
    async def start(self) -> None:
        """Start Slack integration."""
        slack_config = self.config.get("slack", {})
        self.slack_client = AsyncWebClient(token=slack_config.get("bot_token"))
        # Setup webhook server and event listeners
```

---

## 6. Integration and Deployment Strategy {#deployment}

### Core Integration with Ordinaut

```python
# extensions/__init__.py - Core extension loader
async def load_extension_system(ordinaut_config: Dict) -> None:
    """Initialize and load all extensions."""
    extensions_config = ordinaut_config.get("extensions", {})
    
    # Auto-discover extensions
    available_extensions = await extension_registry.discover_extensions()
    
    # Load enabled extensions
    enabled_extensions = extensions_config.get("enabled", [])
    for ext_name in enabled_extensions:
        ext_config = extensions_config.get("configs", {}).get(ext_name, {})
        await extension_registry.load_extension(ext_name, ext_config)
```

### Main Ordinaut Configuration

```yaml
# ordinaut_config.yaml - Main configuration with extensions
extensions:
  enabled:
    - "mcp-server"
    - "web-gui"
    - "slack-integration"
  
  configs:
    mcp-server:
      server:
        port: 8085
      auth:
        oauth:
          client_secret: "${MCP_OAUTH_SECRET}"
      ordinaut_api:
        base_url: "http://localhost:8080"
        internal_token: "${ORDINAUT_INTERNAL_TOKEN}"
```

### Docker Deployment

```yaml
# extensions/docker-compose.extensions.yml
version: '3.8'

services:
  mcp-server:
    build: ./mcp-server
    ports:
      - "8085:8085"
    environment:
      - ORDINAUT_API_URL=http://api:8080
      - REDIS_URL=redis://redis:6379
      - MCP_OAUTH_SECRET=${MCP_OAUTH_SECRET}
    depends_on:
      - redis
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8085/health"]
      interval: 30s
```

### Quick Start

```bash
# 1. Enable extension system in Ordinaut
cd /path/to/ordinaut
mkdir -p extensions

# 2. Deploy MCP server extension
docker-compose -f docker-compose.yml -f extensions/docker-compose.extensions.yml up -d

# 3. Test MCP server
curl http://localhost:8085/health
```

### AI Agent Integration Example

```python
# Example: Claude Desktop connecting to Ordinaut MCP server
{
  "mcpServers": {
    "ordinaut": {
      "command": "npx",
      "args": [
        "@modelcontextprotocol/server-fetch",
        "http://localhost:8085/mcp"
      ],
      "env": {
        "ORDINAUT_AUTH_TOKEN": "your-oauth-token"
      }
    }
  }
}
```

---

## 7. Discussion Points and Considerations {#discussion-points}

### Critical Questions for Architecture Review

#### 1. MCP Server Design Decisions

**Question**: Is the proposed MCP server architecture sufficiently compliant with the 2025-03-26 specification?

**Considerations**:
- JSON-RPC 2.0 implementation completeness
- OAuth 2.1 with PKCE security model
- Tool discovery and capability negotiation
- Error handling and edge cases

#### 2. Extension System Architecture

**Question**: Does the extension system provide the right balance of flexibility vs. complexity?

**Considerations**:
- Extension isolation vs. performance overhead
- Configuration management complexity
- Inter-extension communication patterns
- Lifecycle management reliability

#### 3. Security Model

**Question**: Is the OAuth 2.1 implementation sufficient for production use?

**Considerations**:
- Token storage and revocation mechanisms
- Session management with Redis
- PKCE implementation correctness
- Scope-based authorization granularity

#### 4. Performance and Scalability

**Question**: Can the extension system handle production load?

**Considerations**:
- Extension startup and shutdown times
- Resource utilization per extension
- Database connection pooling across extensions
- Horizontal scaling strategies

#### 5. Operational Complexity

**Question**: Is the system manageable in production?

**Considerations**:
- Extension health monitoring
- Debugging across extension boundaries
- Configuration management complexity
- Deployment orchestration

### Potential Architecture Alternatives

#### Alternative 1: Monolithic MCP Integration
- Integrate MCP server directly into main API
- Pros: Simpler deployment, shared database connections
- Cons: Tight coupling, harder to maintain

#### Alternative 2: Plugin-based Architecture
- Extensions as Python plugins loaded at runtime
- Pros: Simpler than microservices, shared memory
- Cons: Less isolation, harder to scale

#### Alternative 3: Event-driven Extension Communication
- Extensions communicate via Redis events only
- Pros: Loose coupling, better fault tolerance
- Cons: More complex data flow, harder to debug

### Implementation Priorities

#### Phase 1: Core MCP Server (Immediate)
1. JSON-RPC 2.0 transport implementation
2. OAuth 2.1 authentication
3. Basic tool handler for Ordinaut API
4. Docker deployment

#### Phase 2: Extension System (1-2 weeks)
1. Extension registry and discovery
2. Health monitoring integration
3. Configuration management
4. Web GUI extension example

#### Phase 3: Production Hardening (2-4 weeks)
1. Performance optimization
2. Security audit
3. Comprehensive testing
4. Operational documentation

### Risk Assessment

#### High Risk Items
1. **OAuth 2.1 Security**: Complex implementation with many edge cases
2. **Extension Lifecycle**: Process management and error recovery
3. **Performance Overhead**: Multiple containers and network calls

#### Medium Risk Items
1. **Configuration Complexity**: Managing multi-extension configs
2. **Debugging Complexity**: Tracing issues across extension boundaries
3. **Deployment Orchestration**: Docker compose complexity

#### Low Risk Items
1. **JSON-RPC Implementation**: Well-defined specification
2. **Tool Handler Logic**: Straightforward API proxying
3. **Extension Discovery**: Simple file-based system

### Success Metrics

#### Technical Metrics
- MCP server response time < 100ms P95
- Extension startup time < 30 seconds
- System availability > 99.9%
- Memory usage < 1GB per extension

#### Business Metrics
- AI agent integration time < 1 hour
- Extension development time < 1 week
- Operational overhead < 10% of main system

---

## Conclusion

This comprehensive analysis presents a complete architecture for implementing a remote MCP server as an extension to Ordinaut, along with a flexible extension system for future expandability. The proposed solution addresses the brutal reality of predefined executors while providing a path forward for AI agent integration through standardized protocols.

The architecture balances flexibility with operational simplicity, security with performance, and extensibility with maintainability. However, several critical decisions require careful consideration, particularly around security implementation, performance optimization, and operational complexity.

The next steps should focus on validating the MCP 2025 specification compliance, prototyping the OAuth 2.1 implementation, and testing the extension lifecycle management under various failure scenarios.