#!/usr/bin/env python3
"""
Comprehensive Pipeline Execution Engine Tests.

Tests the complete pipeline execution system including:
- Template rendering with ${steps.x.y} variable substitution
- Tool catalog integration and MCP client calls
- JSON Schema validation for inputs and outputs
- Conditional logic with JMESPath expressions
- Error handling, retries, and pipeline recovery
- Performance benchmarks and timeout handling

Tests the deterministic execution of declarative pipelines.
"""

import pytest
import asyncio
import json
import time
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.executor import PipelineExecutor, ExecutionContext, PipelineError
from engine.template import TemplateRenderer, TemplateError
from engine.registry import ToolRegistry, ToolNotFoundError
from engine.mcp_client import MCPClient, MCPError


@pytest.mark.pipeline
class TestPipelineExecution:
    """Test core pipeline execution functionality."""
    
    def test_simple_pipeline_execution(self, mock_tool_catalog):
        """Test execution of simple single-step pipeline."""
        # Setup mock tool catalog
        registry = ToolRegistry()
        registry.load_tools(mock_tool_catalog)
        
        # Setup mock MCP client
        mock_mcp = Mock()
        mock_mcp.call_tool = AsyncMock(return_value={
            "result": "Hello World processed",
            "status": "success"
        })
        
        # Create executor
        executor = PipelineExecutor(registry, mock_mcp)
        
        # Define simple pipeline
        pipeline = {
            "pipeline": [
                {
                    "id": "greeting",
                    "uses": "test-tool.execute",
                    "with": {"message": "Hello World"},
                    "save_as": "result"
                }
            ]
        }
        
        # Execute pipeline
        result = asyncio.run(executor.execute(pipeline))
        
        assert result["success"] is True
        assert "result" in result["outputs"]
        assert result["outputs"]["result"]["result"] == "Hello World processed"
        
        # Verify tool was called with correct parameters
        mock_mcp.call_tool.assert_called_once()
        call_args = mock_mcp.call_tool.call_args
        assert call_args[0][0] == "test-tool.execute"
        assert call_args[1]["message"] == "Hello World"
    
    def test_multi_step_pipeline_with_data_flow(self, mock_tool_catalog):
        """Test multi-step pipeline with data flowing between steps."""
        registry = ToolRegistry()
        registry.load_tools(mock_tool_catalog)
        
        # Mock different responses for different tools
        mock_mcp = Mock()
        
        async def mock_tool_call(tool_address, **kwargs):
            if tool_address == "echo.test":
                return {"echoed": kwargs["message"]}
            elif tool_address == "weather.forecast":
                return {
                    "temp": 22,
                    "condition": "sunny",
                    "humidity": 65
                }
            elif tool_address == "telegram.send_message":
                return {"message_id": 12345}
            else:
                raise Exception(f"Unknown tool: {tool_address}")
        
        mock_mcp.call_tool = AsyncMock(side_effect=mock_tool_call)
        
        executor = PipelineExecutor(registry, mock_mcp)
        
        # Define multi-step pipeline
        pipeline = {
            "pipeline": [
                {
                    "id": "echo_step",
                    "uses": "echo.test",
                    "with": {"message": "Weather request"},
                    "save_as": "echo_result"
                },
                {
                    "id": "weather_step", 
                    "uses": "weather.forecast",
                    "with": {"location": "Chisinau"},
                    "save_as": "weather_data"
                },
                {
                    "id": "notify_step",
                    "uses": "telegram.send_message",
                    "with": {
                        "chat_id": 12345,
                        "text": "Weather: ${steps.weather_data.temp}°C, ${steps.weather_data.condition}"
                    },
                    "save_as": "notification"
                }
            ]
        }
        
        # Execute pipeline
        result = asyncio.run(executor.execute(pipeline))
        
        assert result["success"] is True
        assert len(result["outputs"]) == 3
        
        # Check data flow between steps
        assert result["outputs"]["echo_result"]["echoed"] == "Weather request"
        assert result["outputs"]["weather_data"]["temp"] == 22
        assert result["outputs"]["notification"]["message_id"] == 12345
        
        # Verify template rendering worked in final step
        notify_call = mock_mcp.call_tool.call_args_list[2]  # Third call
        assert "22°C" in notify_call[1]["text"]
        assert "sunny" in notify_call[1]["text"]
    
    def test_conditional_execution_with_jmespath(self, mock_tool_catalog):
        """Test conditional pipeline execution using JMESPath expressions."""
        registry = ToolRegistry()
        registry.load_tools(mock_tool_catalog)
        
        mock_mcp = Mock()
        mock_mcp.call_tool = AsyncMock(return_value={
            "temp": 5,  # Cold temperature
            "condition": "rain",
            "humidity": 80
        })
        
        executor = PipelineExecutor(registry, mock_mcp)
        
        # Pipeline with conditional logic
        pipeline = {
            "pipeline": [
                {
                    "id": "weather_check",
                    "uses": "weather.forecast",
                    "with": {"location": "Chisinau"},
                    "save_as": "weather"
                },
                {
                    "id": "cold_weather_alert",
                    "uses": "telegram.send_message",
                    "with": {
                        "chat_id": 12345,
                        "text": "Cold weather alert: ${steps.weather.temp}°C"
                    },
                    "save_as": "alert",
                    "when": "${steps.weather.temp} < `10`"  # JMESPath condition
                },
                {
                    "id": "warm_weather_message",
                    "uses": "telegram.send_message", 
                    "with": {
                        "chat_id": 12345,
                        "text": "Nice weather: ${steps.weather.temp}°C"
                    },
                    "save_as": "message",
                    "when": "${steps.weather.temp} >= `10`"
                }
            ]
        }
        
        result = asyncio.run(executor.execute(pipeline))
        
        assert result["success"] is True
        assert "weather" in result["outputs"]
        assert "alert" in result["outputs"]  # Should execute (temp < 10)
        assert "message" not in result["outputs"]  # Should not execute (temp not >= 10)
    
    def test_pipeline_error_handling_and_recovery(self, mock_tool_catalog):
        """Test pipeline error handling and recovery mechanisms."""
        registry = ToolRegistry()
        registry.load_tools(mock_tool_catalog)
        
        # Mock that fails on first call, succeeds on retry
        mock_mcp = Mock()
        call_count = 0
        
        async def failing_tool_call(tool_address, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Network timeout")
            return {"result": "success after retry"}
        
        mock_mcp.call_tool = AsyncMock(side_effect=failing_tool_call)
        
        executor = PipelineExecutor(registry, mock_mcp)
        
        pipeline = {
            "pipeline": [
                {
                    "id": "failing_step",
                    "uses": "test-tool.execute",
                    "with": {"message": "test"},
                    "save_as": "result",
                    "retry": {
                        "max_attempts": 3,
                        "delay_seconds": 0.1,
                        "backoff": "exponential"
                    }
                }
            ]
        }
        
        result = asyncio.run(executor.execute(pipeline))
        
        assert result["success"] is True
        assert result["outputs"]["result"]["result"] == "success after retry"
        assert call_count == 2  # Failed once, succeeded on retry
    
    def test_pipeline_timeout_handling(self, mock_tool_catalog):
        """Test pipeline step timeout handling."""
        registry = ToolRegistry()
        registry.load_tools(mock_tool_catalog)
        
        # Mock slow tool
        mock_mcp = Mock()
        
        async def slow_tool_call(tool_address, **kwargs):
            await asyncio.sleep(5)  # Longer than timeout
            return {"result": "too slow"}
        
        mock_mcp.call_tool = AsyncMock(side_effect=slow_tool_call)
        
        executor = PipelineExecutor(registry, mock_mcp)
        
        pipeline = {
            "pipeline": [
                {
                    "id": "slow_step",
                    "uses": "test-tool.execute", 
                    "with": {"message": "test"},
                    "save_as": "result",
                    "timeout_seconds": 1  # Short timeout
                }
            ]
        }
        
        result = asyncio.run(executor.execute(pipeline))
        
        assert result["success"] is False
        assert "timeout" in result["error"].lower()
        assert "slow_step" in result["failed_step"]
    
    def test_parallel_pipeline_execution(self, mock_tool_catalog):
        """Test parallel execution of independent pipeline steps."""
        registry = ToolRegistry()
        registry.load_tools(mock_tool_catalog)
        
        # Mock tools with different response times
        mock_mcp = Mock()
        call_times = {}
        
        async def timed_tool_call(tool_address, **kwargs):
            start_time = time.time()
            if "fast" in kwargs.get("message", ""):
                await asyncio.sleep(0.1)
                result = {"result": "fast response", "duration": 0.1}
            else:
                await asyncio.sleep(0.3)
                result = {"result": "slow response", "duration": 0.3}
            
            call_times[tool_address] = time.time() - start_time
            return result
        
        mock_mcp.call_tool = AsyncMock(side_effect=timed_tool_call)
        
        executor = PipelineExecutor(registry, mock_mcp)
        
        # Pipeline with parallel steps
        pipeline = {
            "pipeline": [
                {
                    "id": "fast_step",
                    "uses": "test-tool.execute",
                    "with": {"message": "fast task"},
                    "save_as": "fast_result",
                    "parallel": True
                },
                {
                    "id": "slow_step", 
                    "uses": "echo.test",
                    "with": {"message": "slow task"},
                    "save_as": "slow_result",
                    "parallel": True
                },
                {
                    "id": "final_step",
                    "uses": "telegram.send_message",
                    "with": {
                        "chat_id": 12345,
                        "text": "Fast: ${steps.fast_result.result}, Slow: ${steps.slow_result.echoed}"
                    },
                    "save_as": "summary"
                }
            ]
        }
        
        start_time = time.time()
        result = asyncio.run(executor.execute(pipeline))
        total_time = time.time() - start_time
        
        assert result["success"] is True
        assert "fast_result" in result["outputs"]
        assert "slow_result" in result["outputs"] 
        assert "summary" in result["outputs"]
        
        # Parallel execution should be faster than sequential (< 0.5s instead of 0.4s)
        assert total_time < 0.5


@pytest.mark.pipeline
class TestTemplateRendering:
    """Test template rendering engine."""
    
    def test_simple_variable_substitution(self):
        """Test basic ${variable} substitution."""
        renderer = TemplateRenderer()
        
        context = {
            "params": {"name": "John", "age": 30},
            "steps": {}
        }
        
        template = "Hello ${params.name}, you are ${params.age} years old"
        result = renderer.render(template, context)
        
        assert result == "Hello John, you are 30 years old"
    
    def test_nested_object_access(self):
        """Test accessing nested object properties."""
        renderer = TemplateRenderer()
        
        context = {
            "params": {},
            "steps": {
                "weather": {
                    "temp": 22,
                    "details": {
                        "humidity": 65,
                        "wind": {"speed": 10, "direction": "NW"}
                    }
                }
            }
        }
        
        template = "Temp: ${steps.weather.temp}°C, Humidity: ${steps.weather.details.humidity}%, Wind: ${steps.weather.details.wind.speed}mph ${steps.weather.details.wind.direction}"
        result = renderer.render(template, context)
        
        assert result == "Temp: 22°C, Humidity: 65%, Wind: 10mph NW"
    
    def test_array_access_and_iteration(self):
        """Test array access and basic iteration."""
        renderer = TemplateRenderer()
        
        context = {
            "params": {},
            "steps": {
                "events": [
                    {"title": "Meeting", "time": "9:00"},
                    {"title": "Lunch", "time": "12:00"}
                ]
            }
        }
        
        # Array access by index
        template = "First event: ${steps.events[0].title} at ${steps.events[0].time}"
        result = renderer.render(template, context)
        assert result == "First event: Meeting at 9:00"
    
    def test_json_serialization_in_templates(self):
        """Test JSON serialization in templates.""" 
        renderer = TemplateRenderer()
        
        context = {
            "params": {},
            "steps": {
                "data": {
                    "items": [1, 2, 3],
                    "config": {"debug": True}
                }
            }
        }
        
        # Test JSON serialization
        template = '{"payload": ${steps.data | json}}'
        result = renderer.render(template, context)
        
        # Should be valid JSON
        parsed = json.loads(result)
        assert parsed["payload"]["items"] == [1, 2, 3]
        assert parsed["payload"]["config"]["debug"] is True
    
    def test_conditional_template_rendering(self):
        """Test conditional rendering in templates."""
        renderer = TemplateRenderer()
        
        context = {
            "params": {"send_email": True, "debug": False},
            "steps": {"weather": {"temp": 25}}
        }
        
        # Conditional text based on parameters
        template = """Weather: ${steps.weather.temp}°C
${params.send_email ? 'Email will be sent' : 'No email'}
Debug mode: ${params.debug ? 'enabled' : 'disabled'}"""
        
        result = renderer.render(template, context)
        
        assert "Weather: 25°C" in result
        assert "Email will be sent" in result
        assert "disabled" in result
    
    def test_template_error_handling(self):
        """Test error handling for invalid templates."""
        renderer = TemplateRenderer()
        
        context = {"params": {}, "steps": {}}
        
        # Invalid variable reference
        with pytest.raises(TemplateError):
            renderer.render("Hello ${nonexistent.variable}", context)
        
        # Invalid syntax
        with pytest.raises(TemplateError):
            renderer.render("Hello ${unclosed.variable", context)
    
    def test_template_security(self):
        """Test template security - no code execution."""
        renderer = TemplateRenderer()
        
        context = {"params": {}, "steps": {}}
        
        # Should not execute arbitrary code
        dangerous_templates = [
            "${__import__('os').system('rm -rf /')}",
            "${eval('1+1')}",
            "${exec('print(\"hacked\")')}"
        ]
        
        for template in dangerous_templates:
            with pytest.raises(TemplateError):
                renderer.render(template, context)
    
    @pytest.mark.benchmark
    def test_template_rendering_performance(self, benchmark):
        """Benchmark template rendering performance."""
        renderer = TemplateRenderer()
        
        # Complex context with nested data
        context = {
            "params": {
                "user": "testuser",
                "settings": {"theme": "dark", "lang": "en"}
            },
            "steps": {
                "api_call": {
                    "data": [{"id": i, "name": f"item_{i}"} for i in range(100)],
                    "metadata": {"count": 100, "timestamp": "2025-01-10T10:00:00Z"}
                }
            }
        }
        
        template = """User: ${params.user}
Theme: ${params.settings.theme}
Language: ${params.settings.lang}
Data count: ${steps.api_call.metadata.count}
First item: ${steps.api_call.data[0].name}
Last item: ${steps.api_call.data[99].name}
Timestamp: ${steps.api_call.metadata.timestamp}"""
        
        def render_template():
            return renderer.render(template, context)
        
        result = benchmark(render_template)
        
        # Verify result correctness
        assert "User: testuser" in result
        assert "Theme: dark" in result
        assert "Data count: 100" in result


@pytest.mark.pipeline
class TestToolRegistry:
    """Test tool catalog and registry functionality."""
    
    def test_tool_registration(self, mock_tool_catalog):
        """Test tool registration and lookup."""
        registry = ToolRegistry()
        registry.load_tools(mock_tool_catalog)
        
        # Test tool lookup
        tool = registry.get_tool("test-tool.execute")
        assert tool is not None
        assert tool["address"] == "test-tool.execute"
        assert tool["transport"] == "http"
        assert "input_schema" in tool
        assert "output_schema" in tool
        
        # Test scopes
        assert "test" in tool["scopes"]
    
    def test_tool_not_found(self):
        """Test handling of non-existent tools."""
        registry = ToolRegistry()
        
        with pytest.raises(ToolNotFoundError):
            registry.get_tool("nonexistent.tool")
    
    def test_scope_based_tool_filtering(self, mock_tool_catalog):
        """Test filtering tools by agent scopes."""
        registry = ToolRegistry()
        registry.load_tools(mock_tool_catalog)
        
        # Filter tools by scope
        weather_tools = registry.get_tools_by_scope("weather.read")
        assert len(weather_tools) > 0
        assert all("weather.read" in tool["scopes"] for tool in weather_tools)
        
        notify_tools = registry.get_tools_by_scope("notify")
        assert len(notify_tools) > 0
        assert all("notify" in tool["scopes"] for tool in notify_tools)
    
    def test_tool_schema_validation(self, mock_tool_catalog):
        """Test that tool schemas are valid."""
        registry = ToolRegistry()
        
        # Test invalid tool definition
        invalid_tool = {
            "address": "invalid.tool",
            "transport": "http",
            # Missing required fields like input_schema, output_schema
        }
        
        with pytest.raises(ValueError):
            registry.validate_tool_definition(invalid_tool)
    
    def test_dynamic_tool_loading(self):
        """Test dynamic loading of tools from different sources."""
        registry = ToolRegistry()
        
        # Load from dict
        tools = [
            {
                "address": "dynamic.tool",
                "transport": "http",
                "endpoint": "http://localhost:9000/dynamic",
                "input_schema": {"type": "object", "properties": {"param": {"type": "string"}}},
                "output_schema": {"type": "object", "properties": {"result": {"type": "string"}}},
                "timeout_seconds": 30,
                "scopes": ["dynamic"]
            }
        ]
        
        registry.load_tools(tools)
        tool = registry.get_tool("dynamic.tool")
        assert tool["address"] == "dynamic.tool"
        assert tool["endpoint"] == "http://localhost:9000/dynamic"


@pytest.mark.pipeline
class TestJSONSchemaValidation:
    """Test JSON Schema validation for tool inputs/outputs."""
    
    def test_input_validation_success(self, mock_tool_catalog):
        """Test successful input validation."""
        registry = ToolRegistry()
        registry.load_tools(mock_tool_catalog)
        
        tool = registry.get_tool("weather.forecast")
        
        # Valid input
        valid_input = {"location": "Chisinau"}
        
        # Should not raise exception
        registry.validate_tool_input(tool, valid_input)
    
    def test_input_validation_failure(self, mock_tool_catalog):
        """Test input validation failure."""
        registry = ToolRegistry()
        registry.load_tools(mock_tool_catalog)
        
        tool = registry.get_tool("weather.forecast")
        
        # Invalid input - missing required field
        invalid_input = {"wrong_field": "value"}
        
        with pytest.raises(ValueError) as exc_info:
            registry.validate_tool_input(tool, invalid_input)
        
        assert "validation" in str(exc_info.value).lower()
    
    def test_output_validation_success(self, mock_tool_catalog):
        """Test successful output validation."""
        registry = ToolRegistry()
        registry.load_tools(mock_tool_catalog)
        
        tool = registry.get_tool("weather.forecast")
        
        # Valid output
        valid_output = {
            "temp": 22,
            "condition": "sunny",
            "humidity": 65
        }
        
        # Should not raise exception
        registry.validate_tool_output(tool, valid_output)
    
    def test_output_validation_failure(self, mock_tool_catalog):
        """Test output validation failure."""
        registry = ToolRegistry()
        registry.load_tools(mock_tool_catalog)
        
        tool = registry.get_tool("weather.forecast")
        
        # Invalid output - wrong type for temp
        invalid_output = {
            "temp": "twenty-two",  # Should be number
            "condition": "sunny"
        }
        
        with pytest.raises(ValueError) as exc_info:
            registry.validate_tool_output(tool, invalid_output)
        
        assert "validation" in str(exc_info.value).lower()


@pytest.mark.pipeline
class TestMCPIntegration:
    """Test Model Context Protocol client integration."""
    
    @pytest.mark.asyncio
    async def test_mcp_http_tool_call(self):
        """Test MCP HTTP tool call."""
        # Mock HTTP response
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "result": {"temp": 22, "condition": "sunny"}
            }
            mock_post.return_value = mock_response
            
            client = MCPClient()
            
            result = await client.call_tool_http(
                endpoint="http://localhost:8091/weather",
                payload={"location": "Chisinau"},
                timeout=30
            )
            
            assert result["temp"] == 22
            assert result["condition"] == "sunny"
            
            # Verify HTTP call was made correctly
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args[1]
            assert call_kwargs["timeout"] == 30
            assert json.loads(call_kwargs["content"])["location"] == "Chisinau"
    
    @pytest.mark.asyncio
    async def test_mcp_stdio_tool_call(self):
        """Test MCP stdio tool call."""
        with patch('asyncio.create_subprocess_exec') as mock_subprocess:
            # Mock subprocess
            mock_process = Mock()
            mock_process.communicate = AsyncMock(return_value=(
                json.dumps({"result": "stdio response"}).encode(),
                b""
            ))
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process
            
            client = MCPClient()
            
            result = await client.call_tool_stdio(
                command=["python", "/path/to/tool.py"],
                payload={"input": "test"},
                timeout=30
            )
            
            assert result["result"] == "stdio response"
    
    @pytest.mark.asyncio
    async def test_mcp_error_handling(self):
        """Test MCP client error handling."""
        with patch('httpx.AsyncClient.post') as mock_post:
            # Mock HTTP error
            mock_post.side_effect = Exception("Connection refused")
            
            client = MCPClient()
            
            with pytest.raises(MCPError) as exc_info:
                await client.call_tool_http(
                    endpoint="http://nonexistent:8000/tool",
                    payload={},
                    timeout=30
                )
            
            assert "Connection refused" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_mcp_timeout_handling(self):
        """Test MCP client timeout handling."""
        with patch('httpx.AsyncClient.post') as mock_post:
            # Mock slow response
            async def slow_response(*args, **kwargs):
                await asyncio.sleep(5)
                return Mock(status_code=200, json=lambda: {"result": "too slow"})
            
            mock_post.side_effect = slow_response
            
            client = MCPClient()
            
            with pytest.raises(MCPError) as exc_info:
                await client.call_tool_http(
                    endpoint="http://localhost:8000/slow",
                    payload={},
                    timeout=1  # Short timeout
                )
            
            assert "timeout" in str(exc_info.value).lower()


@pytest.mark.benchmark
class TestPipelinePerformance:
    """Performance benchmarks for pipeline execution."""
    
    def test_simple_pipeline_performance(self, benchmark, mock_tool_catalog):
        """Benchmark simple pipeline execution performance."""
        registry = ToolRegistry()
        registry.load_tools(mock_tool_catalog)
        
        mock_mcp = Mock()
        mock_mcp.call_tool = AsyncMock(return_value={"result": "benchmark response"})
        
        executor = PipelineExecutor(registry, mock_mcp)
        
        pipeline = {
            "pipeline": [
                {
                    "id": "benchmark_step",
                    "uses": "test-tool.execute",
                    "with": {"message": "performance test"},
                    "save_as": "result"
                }
            ]
        }
        
        def execute_pipeline():
            return asyncio.run(executor.execute(pipeline))
        
        result = benchmark(execute_pipeline)
        assert result["success"] is True
    
    def test_complex_pipeline_performance(self, benchmark, mock_tool_catalog):
        """Benchmark complex multi-step pipeline performance."""
        registry = ToolRegistry()
        registry.load_tools(mock_tool_catalog)
        
        # Mock different tool responses
        async def mock_tool_responses(tool_address, **kwargs):
            await asyncio.sleep(0.01)  # Simulate network delay
            return {"result": f"response from {tool_address}"}
        
        mock_mcp = Mock()
        mock_mcp.call_tool = AsyncMock(side_effect=mock_tool_responses)
        
        executor = PipelineExecutor(registry, mock_mcp)
        
        # Complex pipeline with 10 steps and data dependencies
        pipeline = {
            "pipeline": [
                {
                    "id": f"step_{i}",
                    "uses": "test-tool.execute" if i % 2 == 0 else "echo.test",
                    "with": {
                        "message": f"step {i}" if i == 0 else f"Previous: ${steps.step_{i-1}.result}"
                    },
                    "save_as": f"result_{i}"
                }
                for i in range(10)
            ]
        }
        
        def execute_complex_pipeline():
            return asyncio.run(executor.execute(pipeline))
        
        result = benchmark(execute_complex_pipeline)
        assert result["success"] is True
        assert len(result["outputs"]) == 10
    
    def test_template_rendering_performance_under_load(self, benchmark):
        """Benchmark template rendering with large data sets."""
        renderer = TemplateRenderer()
        
        # Large context with complex nested data
        large_context = {
            "params": {"batch_size": 1000},
            "steps": {
                "data_processing": {
                    "items": [
                        {
                            "id": i,
                            "name": f"item_{i}",
                            "metadata": {
                                "tags": [f"tag_{j}" for j in range(5)],
                                "score": i * 0.1
                            }
                        }
                        for i in range(1000)
                    ],
                    "summary": {
                        "total": 1000,
                        "processed": 1000,
                        "errors": 0
                    }
                }
            }
        }
        
        # Complex template with multiple variable references
        complex_template = """Batch Processing Report
Batch size: ${params.batch_size}
Total items: ${steps.data_processing.summary.total}
Processed: ${steps.data_processing.summary.processed}
Errors: ${steps.data_processing.summary.errors}

Sample items:
- First: ${steps.data_processing.items[0].name} (score: ${steps.data_processing.items[0].metadata.score})
- Last: ${steps.data_processing.items[999].name} (score: ${steps.data_processing.items[999].metadata.score})

Tags from first item: ${steps.data_processing.items[0].metadata.tags[0]}, ${steps.data_processing.items[0].metadata.tags[1]}"""
        
        def render_large_template():
            return renderer.render(complex_template, large_context)
        
        result = benchmark(render_large_template)
        
        # Verify correctness
        assert "Batch size: 1000" in result
        assert "item_0" in result
        assert "item_999" in result