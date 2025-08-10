#!/usr/bin/env python3
"""
Comprehensive test suite for the Ordinaut Pipeline Execution Engine.

Tests the complete pipeline execution flow including:
- Template rendering with ${steps.x.y} and ${params.z} syntax
- JSON Schema validation for tool inputs and outputs
- JMESPath condition evaluation
- Error handling and recovery
- MCP tool integration
"""

import os
import sys
import pytest
import json
import uuid
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.executor import (
    run_pipeline, validate_pipeline, get_pipeline_metrics,
    PipelineExecutionError, StepValidationError, ConditionEvaluationError,
    _eval_condition, _validate_step, _validate_pipeline_structure
)
from engine.template import (
    render_templates, TemplateRenderError, 
    extract_template_variables, validate_template_variables
)


class TestTemplateRendering:
    """Test template rendering functionality."""
    
    def test_basic_variable_substitution(self):
        """Test basic ${variable} substitution."""
        template = "Hello ${params.name}"
        context = {"params": {"name": "John"}}
        
        result = render_templates(template, context)
        assert result == "Hello John"
    
    def test_nested_object_access(self):
        """Test nested object property access."""
        template = "Temperature: ${steps.weather.temp}°${steps.weather.units}"
        context = {
            "steps": {
                "weather": {"temp": 25, "units": "C"}
            }
        }
        
        result = render_templates(template, context)
        assert result == "Temperature: 25°C"
    
    def test_complex_nested_structures(self):
        """Test template rendering in complex nested structures."""
        template = {
            "message": "Hello ${params.name}, age ${params.age}",
            "metadata": {
                "temp": "${steps.weather.temp}",
                "conditions": ["${steps.weather.condition}", "${params.location}"]
            }
        }
        context = {
            "params": {"name": "Alice", "age": 30, "location": "NYC"},
            "steps": {"weather": {"temp": 20, "condition": "sunny"}}
        }
        
        result = render_templates(template, context)
        
        assert result["message"] == "Hello Alice, age 30"
        assert result["metadata"]["temp"] == "20"
        assert result["metadata"]["conditions"] == ["sunny", "NYC"]
    
    def test_boolean_and_json_serialization(self):
        """Test proper handling of boolean and complex object serialization."""
        template = {
            "is_active": "${params.active}",
            "config": "${steps.config.settings}"
        }
        context = {
            "params": {"active": True},
            "steps": {
                "config": {
                    "settings": {"key": "value", "enabled": False}
                }
            }
        }
        
        result = render_templates(template, context)
        
        assert result["is_active"] == "true"
        assert result["config"] == '{"key": "value", "enabled": false}'
    
    def test_missing_variable_handling(self):
        """Test handling of missing variables."""
        template = "Hello ${params.missing_name}"
        context = {"params": {}}
        
        result = render_templates(template, context)
        assert result == "Hello null"
    
    def test_invalid_jmespath_expression(self):
        """Test handling of invalid JMESPath expressions."""
        template = "Value: ${invalid..expression}"
        context = {"params": {"test": "value"}}
        
        with pytest.raises(TemplateRenderError) as exc_info:
            render_templates(template, context)
        
        assert "Failed to evaluate JMESPath expression" in str(exc_info.value)
    
    def test_empty_context(self):
        """Test template rendering with empty context."""
        template = "Static text without variables"
        context = {}
        
        result = render_templates(template, context)
        assert result == "Static text without variables"
    
    def test_extract_template_variables(self):
        """Test extraction of template variables."""
        template = {
            "name": "${params.user_name}",
            "message": "Weather: ${steps.weather.condition} (${steps.weather.temp}°F)",
            "nested": ["${params.location}", "${steps.calendar[0].title}"]
        }
        
        variables = extract_template_variables(template)
        
        expected = [
            "params.location", "params.user_name", 
            "steps.calendar[0].title", "steps.weather.condition", "steps.weather.temp"
        ]
        assert variables == expected


class TestPipelineValidation:
    """Test pipeline structure validation."""
    
    def test_valid_pipeline_structure(self):
        """Test validation of valid pipeline structure."""
        pipeline = {
            "payload": {
                "pipeline": [
                    {"id": "step1", "uses": "echo.test", "with": {"message": "hello"}},
                    {"id": "step2", "uses": "echo.test", "with": {"message": "${steps.step1.output}"}}
                ]
            }
        }
        
        errors = validate_pipeline(pipeline)
        
        # Should pass basic structure validation (tool availability checked separately)
        structure_errors = [e for e in errors if "unknown tool" not in e]
        assert len(structure_errors) == 0
    
    def test_invalid_pipeline_structure(self):
        """Test validation of invalid pipeline structures."""
        # Test missing pipeline field
        invalid_pipeline = {"payload": {}}
        errors = validate_pipeline(invalid_pipeline)
        assert any("missing 'payload.pipeline' field" in error for error in errors)
        
        # Test non-list pipeline
        invalid_pipeline = {"payload": {"pipeline": "not a list"}}
        errors = validate_pipeline(invalid_pipeline)
        assert any("Pipeline must be a list" in error for error in errors)
        
        # Test duplicate step IDs
        invalid_pipeline = {
            "payload": {
                "pipeline": [
                    {"id": "duplicate", "uses": "echo.test"},
                    {"id": "duplicate", "uses": "echo.test"}
                ]
            }
        }
        errors = validate_pipeline(invalid_pipeline)
        assert any("Duplicate step IDs" in error for error in errors)
    
    def test_step_validation(self):
        """Test individual step validation."""
        # Valid step
        valid_step = {"id": "test", "uses": "echo.test", "with": {"msg": "hello"}}
        _validate_step(valid_step, 0)  # Should not raise
        
        # Missing 'uses' field
        with pytest.raises(PipelineExecutionError, match="missing required 'uses' field"):
            _validate_step({"id": "test"}, 0)
        
        # Empty 'uses' field
        with pytest.raises(PipelineExecutionError, match="must be a non-empty string"):
            _validate_step({"id": "test", "uses": ""}, 0)


class TestConditionEvaluation:
    """Test JMESPath condition evaluation."""
    
    def test_simple_boolean_conditions(self):
        """Test simple boolean condition evaluation."""
        context = {"params": {"enabled": True, "count": 5}}
        
        # True conditions
        assert _eval_condition("params.enabled", context) == True
        assert _eval_condition("params.count > `3`", context) == True
        assert _eval_condition("params.count == `5`", context) == True
        
        # False conditions
        context["params"]["enabled"] = False
        assert _eval_condition("params.enabled", context) == False
        assert _eval_condition("params.count > `10`", context) == False
    
    def test_complex_conditions(self):
        """Test complex JMESPath conditions."""
        context = {
            "steps": {
                "weather": {"temp": 25, "condition": "sunny"},
                "calendar": {"events": [{"title": "Meeting"}, {"title": "Lunch"}]}
            },
            "params": {"threshold": 20}
        }
        
        # Complex path conditions
        assert _eval_condition("steps.weather.temp > params.threshold", context) == True
        assert _eval_condition("steps.weather.condition == `sunny`", context) == True
        assert _eval_condition("length(steps.calendar.events) > `1`", context) == True
        assert _eval_condition("steps.calendar.events[0].title == `Meeting`", context) == True
    
    def test_condition_error_handling(self):
        """Test error handling in condition evaluation."""
        context = {"params": {"test": "value"}}
        
        # Invalid JMESPath expression
        with pytest.raises(ConditionEvaluationError):
            _eval_condition("invalid..expression", context)
    
    def test_null_condition_handling(self):
        """Test handling of null/missing values in conditions."""
        context = {"params": {}}
        
        # Missing value should be treated as False
        result = _eval_condition("params.missing_key", context)
        assert result == False


class TestPipelineExecution:
    """Test complete pipeline execution."""
    
    @pytest.fixture
    def mock_catalog(self):
        """Mock tool catalog for testing."""
        return [
            {
                "address": "echo.test",
                "transport": "http",
                "endpoint": "http://localhost:8090/echo",
                "input_schema": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"]
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"echoed": {"type": "string"}},
                    "required": ["echoed"]
                },
                "timeout_seconds": 30
            },
            {
                "address": "math.add",
                "transport": "http", 
                "endpoint": "http://localhost:8090/add",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "a": {"type": "number"},
                        "b": {"type": "number"}
                    },
                    "required": ["a", "b"]
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"result": {"type": "number"}},
                    "required": ["result"]
                },
                "timeout_seconds": 10
            }
        ]
    
    def test_basic_pipeline_execution(self, mock_catalog):
        """Test basic pipeline execution with template rendering."""
        task = {
            "id": "test-task-123",
            "title": "Test Pipeline",
            "payload": {
                "params": {"name": "World"},
                "pipeline": [
                    {
                        "id": "greet",
                        "uses": "echo.test",
                        "with": {"message": "Hello ${params.name}"},
                        "save_as": "greeting"
                    }
                ]
            }
        }
        
        # Mock dependencies
        with patch('engine.executor.load_catalog', return_value=mock_catalog):
            with patch('engine.executor.call_tool') as mock_call_tool:
                mock_call_tool.return_value = {"echoed": "Hello World"}
                
                result = run_pipeline(task)
        
        # Verify execution context
        assert result["params"]["name"] == "World"
        assert result["steps"]["greeting"]["echoed"] == "Hello World"
        assert result["_task_id"] == "test-task-123"
        assert result["_task_title"] == "Test Pipeline"
        assert result["_execution_summary"]["success"] == True
        assert result["_execution_summary"]["executed_steps"] == 1
        assert result["_execution_summary"]["skipped_steps"] == 0
        
        # Verify tool was called correctly
        mock_call_tool.assert_called_once()
        call_args = mock_call_tool.call_args
        assert call_args[0][0] == "echo.test"  # address
        assert call_args[0][2] == {"message": "Hello World"}  # rendered args
    
    def test_multi_step_pipeline_with_dependencies(self, mock_catalog):
        """Test pipeline with multiple steps and inter-step dependencies."""
        task = {
            "id": "test-multi-step",
            "payload": {
                "params": {"x": 10, "y": 5},
                "pipeline": [
                    {
                        "id": "calculate",
                        "uses": "math.add",
                        "with": {"a": "${params.x}", "b": "${params.y}"},
                        "save_as": "sum"
                    },
                    {
                        "id": "report",
                        "uses": "echo.test",
                        "with": {"message": "Result: ${steps.sum.result}"},
                        "save_as": "message"
                    }
                ]
            }
        }
        
        with patch('engine.executor.load_catalog', return_value=mock_catalog):
            with patch('engine.executor.call_tool') as mock_call_tool:
                # Mock tool responses
                mock_call_tool.side_effect = [
                    {"result": 15},  # math.add response
                    {"echoed": "Result: 15"}  # echo.test response
                ]
                
                result = run_pipeline(task)
        
        # Verify execution
        assert result["steps"]["sum"]["result"] == 15
        assert result["steps"]["message"]["echoed"] == "Result: 15"
        assert result["_execution_summary"]["executed_steps"] == 2
        assert result["_execution_summary"]["success"] == True
        
        # Verify both tools were called
        assert mock_call_tool.call_count == 2
    
    def test_conditional_step_execution(self, mock_catalog):
        """Test conditional step execution using 'if' clauses."""
        task = {
            "id": "test-conditional",
            "payload": {
                "params": {"enabled": True, "disabled": False},
                "pipeline": [
                    {
                        "id": "enabled_step",
                        "uses": "echo.test",
                        "with": {"message": "This should run"},
                        "if": "params.enabled",
                        "save_as": "enabled_result"
                    },
                    {
                        "id": "disabled_step",
                        "uses": "echo.test", 
                        "with": {"message": "This should not run"},
                        "if": "params.disabled",
                        "save_as": "disabled_result"
                    }
                ]
            }
        }
        
        with patch('engine.executor.load_catalog', return_value=mock_catalog):
            with patch('engine.executor.call_tool') as mock_call_tool:
                mock_call_tool.return_value = {"echoed": "This should run"}
                
                result = run_pipeline(task)
        
        # Verify conditional execution
        assert "enabled_result" in result["steps"]
        assert "disabled_result" not in result["steps"]
        assert result["_execution_summary"]["executed_steps"] == 1
        assert result["_execution_summary"]["skipped_steps"] == 1
        
        # Only one tool call should have been made
        mock_call_tool.assert_called_once()
    
    def test_pipeline_error_handling(self, mock_catalog):
        """Test pipeline error handling and recovery."""
        task = {
            "id": "test-error",
            "payload": {
                "pipeline": [
                    {
                        "id": "failing_step",
                        "uses": "echo.test",
                        "with": {"message": "test"}
                    }
                ]
            }
        }
        
        with patch('engine.executor.load_catalog', return_value=mock_catalog):
            with patch('engine.executor.call_tool') as mock_call_tool:
                # Mock tool failure
                mock_call_tool.side_effect = Exception("Tool execution failed")
                
                with pytest.raises(PipelineExecutionError) as exc_info:
                    run_pipeline(task)
                
                assert "tool execution failed" in str(exc_info.value).lower()
                assert exc_info.value.step_id == "failing_step"
                assert exc_info.value.step_index == 0
    
    def test_input_validation_error(self, mock_catalog):
        """Test input validation error handling."""
        task = {
            "id": "test-validation",
            "payload": {
                "pipeline": [
                    {
                        "id": "invalid_input",
                        "uses": "echo.test",
                        "with": {"wrong_field": "test"}  # Missing required 'message' field
                    }
                ]
            }
        }
        
        with patch('engine.executor.load_catalog', return_value=mock_catalog):
            with pytest.raises(StepValidationError) as exc_info:
                run_pipeline(task)
            
            assert "input validation failed" in str(exc_info.value)
            assert exc_info.value.step_id == "invalid_input"
    
    def test_output_validation_error(self, mock_catalog):
        """Test output validation error handling."""
        task = {
            "id": "test-output-validation",
            "payload": {
                "pipeline": [
                    {
                        "id": "invalid_output",
                        "uses": "echo.test",
                        "with": {"message": "test"}
                    }
                ]
            }
        }
        
        with patch('engine.executor.load_catalog', return_value=mock_catalog):
            with patch('engine.executor.call_tool') as mock_call_tool:
                # Mock invalid tool response
                mock_call_tool.return_value = {"wrong_field": "value"}
                
                with pytest.raises(StepValidationError) as exc_info:
                    run_pipeline(task)
                
                assert "output validation failed" in str(exc_info.value)
    
    def test_template_rendering_error(self, mock_catalog):
        """Test template rendering error handling."""
        task = {
            "id": "test-template-error",
            "payload": {
                "pipeline": [
                    {
                        "id": "template_error",
                        "uses": "echo.test",
                        "with": {"message": "${invalid..expression}"}
                    }
                ]
            }
        }
        
        with patch('engine.executor.load_catalog', return_value=mock_catalog):
            with pytest.raises(PipelineExecutionError) as exc_info:
                run_pipeline(task)
            
            assert "template rendering failed" in str(exc_info.value)
    
    def test_unknown_tool_error(self, mock_catalog):
        """Test handling of unknown tool references."""
        task = {
            "id": "test-unknown-tool",
            "payload": {
                "pipeline": [
                    {
                        "id": "unknown_tool",
                        "uses": "nonexistent.tool",
                        "with": {"message": "test"}
                    }
                ]
            }
        }
        
        with patch('engine.executor.load_catalog', return_value=mock_catalog):
            with pytest.raises(PipelineExecutionError) as exc_info:
                run_pipeline(task)
            
            assert "unknown tool" in str(exc_info.value)
            assert exc_info.value.step_id == "unknown_tool"


class TestPipelineMetrics:
    """Test pipeline execution metrics extraction."""
    
    def test_successful_execution_metrics(self):
        """Test metrics for successful pipeline execution."""
        execution_context = {
            "_task_id": "test-123",
            "_task_title": "Test Task",
            "_execution_summary": {
                "success": True,
                "total_steps": 3,
                "executed_steps": 2,
                "skipped_steps": 1,
                "execution_time_seconds": 1.5
            }
        }
        
        metrics = get_pipeline_metrics(execution_context)
        
        assert metrics["success"] == True
        assert metrics["total_steps"] == 3
        assert metrics["executed_steps"] == 2
        assert metrics["skipped_steps"] == 1
        assert metrics["execution_time_seconds"] == 1.5
        assert metrics["steps_per_second"] == pytest.approx(1.33, abs=0.01)
        assert metrics["task_id"] == "test-123"
        assert metrics["task_title"] == "Test Task"
        assert metrics["error"] is None
        assert metrics["failed_step_index"] is None
    
    def test_failed_execution_metrics(self):
        """Test metrics for failed pipeline execution."""
        execution_context = {
            "_task_id": "failed-456",
            "_execution_summary": {
                "success": False,
                "total_steps": 2,
                "executed_steps": 1,
                "skipped_steps": 0,
                "failed_step_index": 1,
                "execution_time_seconds": 0.8,
                "error": "Tool execution failed"
            }
        }
        
        metrics = get_pipeline_metrics(execution_context)
        
        assert metrics["success"] == False
        assert metrics["failed_step_index"] == 1
        assert metrics["error"] == "Tool execution failed"


class TestIntegrationScenarios:
    """Test realistic integration scenarios."""
    
    def test_morning_briefing_pipeline(self):
        """Test a realistic morning briefing pipeline."""
        # Create comprehensive tool catalog
        catalog = [
            {
                "address": "google-calendar.list_events",
                "transport": "http",
                "input_schema": {
                    "type": "object", 
                    "properties": {"start": {"type": "string"}, "end": {"type": "string"}},
                    "required": ["start", "end"]
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"events": {"type": "array"}},
                    "required": ["events"]
                }
            },
            {
                "address": "weather.forecast",
                "transport": "http",
                "input_schema": {
                    "type": "object",
                    "properties": {"location": {"type": "string"}},
                    "required": ["location"]
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"summary": {"type": "string"}, "temp": {"type": "number"}},
                    "required": ["summary", "temp"]
                }
            },
            {
                "address": "telegram.send_message",
                "transport": "http",
                "input_schema": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}, "chat_id": {"type": "integer"}},
                    "required": ["text", "chat_id"]
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"message_id": {"type": "integer"}},
                    "required": ["message_id"]
                }
            }
        ]
        
        task = {
            "id": "morning-briefing-001",
            "title": "Daily Morning Briefing",
            "payload": {
                "params": {
                    "date_start": "2025-08-08T00:00:00Z",
                    "date_end": "2025-08-08T23:59:59Z",
                    "location": "Chisinau",
                    "chat_id": 12345
                },
                "pipeline": [
                    {
                        "id": "calendar",
                        "uses": "google-calendar.list_events",
                        "with": {
                            "start": "${params.date_start}",
                            "end": "${params.date_end}"
                        },
                        "save_as": "events"
                    },
                    {
                        "id": "weather",
                        "uses": "weather.forecast", 
                        "with": {"location": "${params.location}"},
                        "save_as": "forecast"
                    },
                    {
                        "id": "notify",
                        "uses": "telegram.send_message",
                        "with": {
                            "chat_id": "${params.chat_id}",
                            "text": "Good morning! Weather: ${steps.forecast.summary} (${steps.forecast.temp}°C). You have ${length(steps.events.events)} events today."
                        },
                        "if": "length(steps.events.events) > `0` || steps.forecast.temp > `0`"
                    }
                ]
            }
        }
        
        with patch('engine.executor.load_catalog', return_value=catalog):
            with patch('engine.executor.call_tool') as mock_call_tool:
                # Mock tool responses
                mock_call_tool.side_effect = [
                    {"events": [{"title": "Team Meeting"}, {"title": "Lunch"}]},
                    {"summary": "Sunny", "temp": 22},
                    {"message_id": 789}
                ]
                
                result = run_pipeline(task)
        
        # Verify execution
        assert result["_execution_summary"]["success"] == True
        assert result["_execution_summary"]["executed_steps"] == 3
        assert len(result["steps"]["events"]["events"]) == 2
        assert result["steps"]["forecast"]["summary"] == "Sunny"
        assert result["steps"]["forecast"]["temp"] == 22
        
        # Verify final message call
        final_call_args = mock_call_tool.call_args_list[2]
        message_text = final_call_args[0][2]["text"]
        assert "Weather: Sunny (22°C)" in message_text
        assert "You have 2 events today" in message_text
    
    def test_error_recovery_scenarios(self):
        """Test various error recovery scenarios."""
        catalog = [
            {
                "address": "unreliable.service",
                "transport": "http",
                "input_schema": {"type": "object", "properties": {}},
                "output_schema": {"type": "object", "properties": {"result": {"type": "string"}}}
            }
        ]
        
        # Test missing payload
        with pytest.raises(PipelineExecutionError, match="Task payload must be a dictionary"):
            run_pipeline({"id": "test"})
        
        # Test missing pipeline
        with pytest.raises(PipelineExecutionError, match="missing 'pipeline' field"):
            run_pipeline({"id": "test", "payload": {}})
        
        # Test empty pipeline
        result = run_pipeline({
            "id": "empty-pipeline",
            "payload": {"pipeline": []}
        })
        assert result["_execution_summary"]["success"] == True
        assert result["_execution_summary"]["executed_steps"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])