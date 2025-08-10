# engine/mcp_client.py
"""
MCP Bridge for Ordinaut

Implements both HTTP and stdio transports for calling MCP tools.
Handles JSON Schema validation, error handling, timeout, and performance monitoring.
"""

import json
import asyncio
import subprocess
import tempfile
import os
import time
import logging
from typing import Dict, Any, Optional, Tuple
from jsonschema import validate, ValidationError
import httpx

logger = logging.getLogger(__name__)

class MCPError(Exception):
    """Base exception for MCP-related errors."""
    pass

class MCPTransportError(MCPError):
    """Transport-level errors (network, process, etc.)."""
    pass

class MCPValidationError(MCPError):
    """Schema validation errors."""
    pass

class MCPTimeoutError(MCPError):
    """Tool execution timeout."""
    pass

def call_tool(address: str, tool: Dict[str, Any], args: Dict[str, Any], timeout: int = 30) -> Dict[str, Any]:
    """
    Call a tool via MCP or HTTP transport with full error handling and validation.
    
    Args:
        address: Tool address (e.g., "telegram-mcp.send_message")
        tool: Tool definition from catalog with transport, endpoint, schemas
        args: Arguments to pass to the tool
        timeout: Execution timeout in seconds
        
    Returns:
        Tool execution result
        
    Raises:
        MCPValidationError: Input/output validation failed
        MCPTransportError: Transport-level error
        MCPTimeoutError: Execution timeout
    """
    start_time = time.time()
    transport = tool.get("transport", "http")
    
    # Validate input against schema
    try:
        validate(instance=args, schema=tool["input_schema"])
    except ValidationError as e:
        raise MCPValidationError(f"Input validation failed for {address}: {e.message}")
    
    try:
        if transport == "http":
            result = _call_http_tool(tool["endpoint"], args, timeout)
        elif transport == "mcp":
            result = _call_mcp_tool(tool["server"], address, args, timeout)
        elif transport == "stdio":
            result = _call_stdio_tool(tool["executable"], address, args, timeout)
        else:
            raise MCPTransportError(f"Unsupported transport: {transport}")
            
        # Validate output against schema
        try:
            validate(instance=result, schema=tool["output_schema"])
        except ValidationError as e:
            raise MCPValidationError(f"Output validation failed for {address}: {e.message}")
            
        # Log performance metrics
        duration = time.time() - start_time
        logger.info(f"Tool {address} executed in {duration:.3f}s", extra={
            "tool_address": address,
            "transport": transport,
            "duration_seconds": duration,
            "success": True
        })
        
        return result
        
    except (MCPTransportError, MCPValidationError, MCPTimeoutError):
        # Re-raise our own exceptions
        raise
    except Exception as e:
        # Wrap unexpected errors
        duration = time.time() - start_time
        logger.error(f"Tool {address} failed after {duration:.3f}s: {e}", extra={
            "tool_address": address,
            "transport": transport,
            "duration_seconds": duration,
            "success": False,
            "error": str(e)
        })
        raise MCPTransportError(f"Tool execution failed: {e}")

def _call_http_tool(endpoint: str, args: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    """Call tool via HTTP endpoint with proper MCP-style request/response."""
    try:
        # MCP over HTTP uses JSON-RPC-like format
        request_payload = {
            "jsonrpc": "2.0",
            "id": f"req_{int(time.time() * 1000)}",
            "method": "tools/call",
            "params": {
                "arguments": args
            }
        }
        
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                endpoint, 
                json=request_payload,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            
            result = response.json()
            
            # Handle JSON-RPC error responses
            if "error" in result:
                error_info = result["error"]
                raise MCPTransportError(f"MCP error {error_info.get('code', 'unknown')}: {error_info.get('message', 'Unknown error')}")
            
            # Return the actual result
            return result.get("result", {})
            
    except httpx.TimeoutException:
        raise MCPTimeoutError(f"HTTP request timed out after {timeout}s")
    except httpx.RequestError as e:
        raise MCPTransportError(f"HTTP request failed: {e}")
    except httpx.HTTPStatusError as e:
        raise MCPTransportError(f"HTTP error {e.response.status_code}: {e.response.text}")

def _call_mcp_tool(server: str, tool_name: str, args: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    """Call tool via MCP server (HTTP-based MCP server)."""
    # For MCP servers, we need to connect to the server and call the tool
    # This is a simplified implementation - production would use proper MCP client
    
    # Extract server endpoint from server name
    # Convention: server name can be "server@endpoint" or just "server"
    if "@" in server:
        server_name, endpoint = server.split("@", 1)
    else:
        # Default MCP server endpoint pattern
        endpoint = f"http://localhost:8080/mcp/{server}"
    
    try:
        request_payload = {
            "jsonrpc": "2.0",
            "id": f"mcp_{int(time.time() * 1000)}",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": args
            }
        }
        
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                endpoint,
                json=request_payload,
                headers={"Content-Type": "application/vnd.mcp+json"}
            )
            response.raise_for_status()
            
            result = response.json()
            
            if "error" in result:
                error_info = result["error"]
                raise MCPTransportError(f"MCP server error {error_info.get('code', 'unknown')}: {error_info.get('message', 'Unknown error')}")
            
            return result.get("result", {})
            
    except httpx.TimeoutException:
        raise MCPTimeoutError(f"MCP server request timed out after {timeout}s")
    except httpx.RequestError as e:
        raise MCPTransportError(f"MCP server request failed: {e}")
    except httpx.HTTPStatusError as e:
        raise MCPTransportError(f"MCP server HTTP error {e.response.status_code}: {e.response.text}")

def _call_stdio_tool(executable: str, tool_name: str, args: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    """Call tool via stdio MCP transport (subprocess communication)."""
    try:
        # Create MCP request
        request = {
            "jsonrpc": "2.0",
            "id": f"stdio_{int(time.time() * 1000)}",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": args
            }
        }
        
        request_json = json.dumps(request) + "\n"
        
        # Start subprocess
        process = subprocess.Popen(
            executable,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=os.environ.copy()
        )
        
        try:
            # Send request and get response
            stdout, stderr = process.communicate(input=request_json, timeout=timeout)
            
            if process.returncode != 0:
                raise MCPTransportError(f"MCP process exited with code {process.returncode}: {stderr}")
            
            # Parse response
            response = json.loads(stdout.strip())
            
            if "error" in response:
                error_info = response["error"]
                raise MCPTransportError(f"MCP stdio error {error_info.get('code', 'unknown')}: {error_info.get('message', 'Unknown error')}")
            
            return response.get("result", {})
            
        except subprocess.TimeoutExpired:
            process.kill()
            raise MCPTimeoutError(f"MCP stdio process timed out after {timeout}s")
            
    except json.JSONDecodeError as e:
        raise MCPTransportError(f"Invalid JSON response from MCP process: {e}")
    except Exception as e:
        raise MCPTransportError(f"MCP stdio execution failed: {e}")

def discover_mcp_tools(server_endpoint: str, timeout: int = 10) -> Dict[str, Any]:
    """
    Discover available tools from an MCP server.
    
    Args:
        server_endpoint: HTTP endpoint of MCP server
        timeout: Discovery timeout in seconds
        
    Returns:
        Dictionary mapping tool names to their schemas
    """
    try:
        request_payload = {
            "jsonrpc": "2.0",
            "id": f"discover_{int(time.time() * 1000)}",
            "method": "tools/list",
            "params": {}
        }
        
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                server_endpoint,
                json=request_payload,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            
            result = response.json()
            
            if "error" in result:
                error_info = result["error"]
                raise MCPTransportError(f"Discovery error {error_info.get('code', 'unknown')}: {error_info.get('message', 'Unknown error')}")
            
            tools = result.get("result", {}).get("tools", [])
            
            # Convert to our internal format
            tool_catalog = {}
            for tool in tools:
                tool_catalog[tool["name"]] = {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "input_schema": tool.get("inputSchema", {"type": "object"}),
                    "output_schema": {"type": "object"}  # MCP doesn't specify output schemas
                }
            
            return tool_catalog
            
    except httpx.TimeoutException:
        raise MCPTimeoutError(f"Tool discovery timed out after {timeout}s")
    except httpx.RequestError as e:
        raise MCPTransportError(f"Discovery request failed: {e}")
    except Exception as e:
        raise MCPTransportError(f"Tool discovery failed: {e}")