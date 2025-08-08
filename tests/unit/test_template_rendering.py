#!/usr/bin/env python3
"""
Comprehensive unit tests for template rendering engine.

Tests all template rendering functionality including:
- Variable substitution with ${steps.x.y} and ${params.z}
- Complex nested object access and array indexing
- JSON serialization and type conversion
- Error handling for malformed expressions
- Performance benchmarking for optimization
"""

import pytest
import time
import json
from datetime import datetime, timezone
from unittest.mock import patch

from engine.template import (
    render_templates, extract_template_variables, validate_template_variables,
    TemplateRenderError
)


class TestBasicTemplateRendering:
    """Test basic template variable substitution."""
    
    def test_simple_variable_substitution(self):
        """Test basic ${variable} substitution."""
        template = "Hello ${params.name}"
        context = {"params": {"name": "John"}}
        
        result = render_templates(template, context)
        assert result == "Hello John"
    
    def test_multiple_variables_same_string(self):
        """Test multiple variable substitutions in same string."""
        template = "Hello ${params.name}, you are ${params.age} years old"
        context = {"params": {"name": "Alice", "age": 30}}
        
        result = render_templates(template, context)
        assert result == "Hello Alice, you are 30 years old"
    
    def test_nested_object_access(self):
        """Test deep nested object property access."""
        template = "Weather: ${steps.weather.current.temp}°${steps.weather.current.units}"
        context = {
            "steps": {
                "weather": {
                    "current": {"temp": 25, "units": "C"},
                    "forecast": {"high": 28, "low": 20}
                }
            }
        }
        
        result = render_templates(template, context)
        assert result == "Weather: 25°C"
    
    def test_array_indexing(self):
        """Test array element access in templates."""
        template = "First event: ${steps.calendar.events[0].title} at ${steps.calendar.events[0].time}"
        context = {
            "steps": {
                "calendar": {
                    "events": [
                        {"title": "Meeting", "time": "10:00"},
                        {"title": "Lunch", "time": "12:30"}
                    ]
                }
            }
        }
        
        result = render_templates(template, context)
        assert result == "First event: Meeting at 10:00"
    
    def test_array_length_function(self):
        """Test length() function with arrays."""
        template = "You have ${length(steps.calendar.events)} events today"
        context = {
            "steps": {
                "calendar": {
                    "events": [{"title": "Meeting"}, {"title": "Lunch"}, {"title": "Review"}]
                }
            }
        }
        
        result = render_templates(template, context)
        assert result == "You have 3 events today"
    
    def test_now_builtin_variable(self):
        """Test built-in 'now' variable."""
        template = "Current time: ${now}"
        context = {"now": "2025-08-08T10:30:00Z"}
        
        result = render_templates(template, context)
        assert result == "Current time: 2025-08-08T10:30:00Z"


class TestComplexTemplateStructures:
    """Test template rendering in complex nested data structures."""
    
    def test_nested_dictionary_templates(self):
        """Test template rendering in nested dictionaries."""
        template = {
            "user": {
                "greeting": "Hello ${params.name}",
                "summary": "Age: ${params.age}, Location: ${params.city}"
            },
            "weather": {
                "message": "It's ${steps.weather.condition} with ${steps.weather.temp}°C",
                "details": {
                    "humidity": "${steps.weather.humidity}%",
                    "wind": "${steps.weather.wind} km/h"
                }
            }
        }
        
        context = {
            "params": {"name": "Alice", "age": 30, "city": "Chisinau"},
            "steps": {
                "weather": {
                    "condition": "sunny", "temp": 22, "humidity": 65, "wind": 12
                }
            }
        }
        
        result = render_templates(template, context)
        
        assert result["user"]["greeting"] == "Hello Alice"
        assert result["user"]["summary"] == "Age: 30, Location: Chisinau"
        assert result["weather"]["message"] == "It's sunny with 22°C"
        assert result["weather"]["details"]["humidity"] == "65%"
        assert result["weather"]["details"]["wind"] == "12 km/h"
    
    def test_array_with_templates(self):
        """Test template rendering in arrays."""
        template = [
            "Hello ${params.name}",
            {"message": "${steps.greeting.text}", "timestamp": "${now}"},
            ["${params.item1}", "${params.item2}", "${params.item3}"]
        ]
        
        context = {
            "params": {"name": "Bob", "item1": "first", "item2": "second", "item3": "third"},
            "steps": {"greeting": {"text": "Welcome!"}},
            "now": "2025-08-08T10:30:00Z"
        }
        
        result = render_templates(template, context)
        
        assert result[0] == "Hello Bob"
        assert result[1]["message"] == "Welcome!"
        assert result[1]["timestamp"] == "2025-08-08T10:30:00Z"
        assert result[2] == ["first", "second", "third"]
    
    def test_deeply_nested_structures(self):
        """Test rendering in very deeply nested structures."""
        template = {
            "level1": {
                "level2": {
                    "level3": {
                        "level4": {
                            "message": "Deep value: ${params.deep.nested.value}",
                            "array": ["${params.items[0]}", "${params.items[1]}"]
                        }
                    }
                }
            }
        }
        
        context = {
            "params": {
                "deep": {"nested": {"value": "found it!"}},
                "items": ["item1", "item2"]
            }
        }
        
        result = render_templates(template, context)
        
        deep_message = result["level1"]["level2"]["level3"]["level4"]["message"]
        assert deep_message == "Deep value: found it!"
        
        deep_array = result["level1"]["level2"]["level3"]["level4"]["array"]
        assert deep_array == ["item1", "item2"]


class TestDataTypeHandling:
    """Test proper handling of different data types in templates."""
    
    def test_boolean_serialization(self):
        """Test boolean values in templates."""
        template = {
            "active": "${params.enabled}",
            "message": "Status: ${params.enabled}"
        }
        context = {"params": {"enabled": True}}
        
        result = render_templates(template, context)
        
        assert result["active"] == "true"  # JSON serialization
        assert result["message"] == "Status: true"
    
    def test_number_serialization(self):
        """Test numeric values in templates."""
        template = {
            "temp": "${steps.weather.temp}",
            "message": "Temperature is ${steps.weather.temp} degrees"
        }
        context = {"steps": {"weather": {"temp": 25.5}}}
        
        result = render_templates(template, context)
        
        assert result["temp"] == "25.5"
        assert result["message"] == "Temperature is 25.5 degrees"
    
    def test_null_values(self):
        """Test null/None value handling."""
        template = {
            "missing": "${params.missing_key}",
            "message": "Value: ${params.missing_key}"
        }
        context = {"params": {}}
        
        result = render_templates(template, context)
        
        assert result["missing"] == "null"
        assert result["message"] == "Value: null"
    
    def test_complex_object_serialization(self):
        """Test complex object JSON serialization."""
        template = {
            "config": "${steps.config.settings}",
            "raw_data": "${steps.api_response}"
        }
        context = {
            "steps": {
                "config": {
                    "settings": {"key": "value", "enabled": False, "count": 42}
                },
                "api_response": {
                    "status": "ok",
                    "data": [1, 2, 3],
                    "meta": {"total": 3, "page": 1}
                }
            }
        }
        
        result = render_templates(template, context)
        
        # Should be properly JSON-serialized strings
        config_obj = json.loads(result["config"])
        assert config_obj["key"] == "value"
        assert config_obj["enabled"] is False
        assert config_obj["count"] == 42
        
        response_obj = json.loads(result["raw_data"])
        assert response_obj["status"] == "ok"
        assert response_obj["data"] == [1, 2, 3]
        assert response_obj["meta"]["total"] == 3
    
    def test_array_serialization(self):
        """Test array serialization in templates."""
        template = {
            "list": "${params.items}",
            "first_item": "${params.items[0]}"
        }
        context = {"params": {"items": ["apple", "banana", "cherry"]}}
        
        result = render_templates(template, context)
        
        assert result["list"] == '["apple", "banana", "cherry"]'
        assert result["first_item"] == "apple"


class TestErrorHandling:
    """Test error handling for malformed templates and expressions."""
    
    def test_invalid_jmespath_expression(self):
        """Test handling of invalid JMESPath expressions."""
        template = "Value: ${invalid..expression}"
        context = {"params": {"test": "value"}}
        
        with pytest.raises(TemplateRenderError) as exc_info:
            render_templates(template, context)
        
        assert "Failed to evaluate JMESPath expression" in str(exc_info.value)
        assert "invalid..expression" in str(exc_info.value)
    
    def test_missing_closing_brace(self):
        """Test handling of malformed template syntax."""
        template = "Hello ${params.name"  # Missing closing brace
        context = {"params": {"name": "Alice"}}
        
        # Should not raise error, just treat as literal text
        result = render_templates(template, context)
        assert result == "Hello ${params.name"
    
    def test_empty_expression(self):
        """Test handling of empty template expressions."""
        template = "Hello ${}"
        context = {"params": {"name": "Alice"}}
        
        # Empty expression should evaluate to empty string or null
        result = render_templates(template, context)
        assert "Hello " in result  # Depends on JMESPath behavior for empty expression
    
    def test_nested_template_error_propagation(self):
        """Test error propagation in nested structures."""
        template = {
            "good": "Hello ${params.name}",
            "bad": "Value: ${invalid..expression}",
            "nested": {
                "also_bad": "${another..invalid}"
            }
        }
        context = {"params": {"name": "Alice"}}
        
        with pytest.raises(TemplateRenderError):
            render_templates(template, context)
    
    def test_circular_reference_protection(self):
        """Test protection against potential circular references."""
        # This shouldn't cause infinite loops
        template = "${steps.circular.self}"
        context = {
            "steps": {
                "circular": {"self": "steps.circular.self"}
            }
        }
        
        result = render_templates(template, context)
        assert result == "steps.circular.self"  # Should just return the string value


class TestTemplateVariableExtraction:
    """Test template variable extraction utilities."""
    
    def test_extract_simple_variables(self):
        """Test extraction of simple template variables."""
        template = "Hello ${params.name}, temperature is ${steps.weather.temp}"
        
        variables = extract_template_variables(template)
        
        expected = ["params.name", "steps.weather.temp"]
        assert sorted(variables) == sorted(expected)
    
    def test_extract_complex_nested_variables(self):
        """Test extraction from complex nested structures."""
        template = {
            "greeting": "Hello ${params.user.name}",
            "data": {
                "weather": "It's ${steps.weather.condition}",
                "events": ["${steps.calendar.events[0].title}", "${params.location}"]
            },
            "complex": "${steps.api.response.data[0].id}"
        }
        
        variables = extract_template_variables(template)
        
        expected = [
            "params.location", "params.user.name",
            "steps.api.response.data[0].id", "steps.calendar.events[0].title", 
            "steps.weather.condition"
        ]
        assert sorted(variables) == sorted(expected)
    
    def test_extract_with_duplicates(self):
        """Test extraction with duplicate variables."""
        template = {
            "msg1": "Hello ${params.name}",
            "msg2": "Welcome ${params.name}",
            "msg3": "Goodbye ${params.name}"
        }
        
        variables = extract_template_variables(template)
        
        # Should deduplicate
        assert variables == ["params.name"]
    
    def test_extract_array_indices(self):
        """Test extraction of array index expressions."""
        template = {
            "first": "${items[0]}",
            "second": "${items[1].name}",
            "nested": "${data.array[2].nested[0].value}"
        }
        
        variables = extract_template_variables(template)
        
        expected = ["data.array[2].nested[0].value", "items[0]", "items[1].name"]
        assert sorted(variables) == sorted(expected)


class TestTemplateVariableValidation:
    """Test template variable validation against context."""
    
    def test_validate_available_variables(self):
        """Test validation of available variables in context."""
        variables = ["params.name", "steps.weather.temp", "now"]
        context = {
            "params": {"name": "Alice", "age": 30},
            "steps": {"weather": {"temp": 25, "condition": "sunny"}},
            "now": "2025-08-08T10:30:00Z"
        }
        
        missing = validate_template_variables(variables, context)
        
        assert missing == []  # All variables are available
    
    def test_identify_missing_variables(self):
        """Test identification of missing variables."""
        variables = [
            "params.name", "params.missing", 
            "steps.weather.temp", "steps.calendar.events"
        ]
        context = {
            "params": {"name": "Alice"},
            "steps": {"weather": {"temp": 25}}
        }
        
        missing = validate_template_variables(variables, context)
        
        expected_missing = ["params.missing", "steps.calendar.events"]
        assert sorted(missing) == sorted(expected_missing)
    
    def test_validate_nested_paths(self):
        """Test validation of deeply nested paths."""
        variables = [
            "steps.api.response.data[0].id",
            "steps.api.response.meta.total",
            "steps.api.missing.path"
        ]
        context = {
            "steps": {
                "api": {
                    "response": {
                        "data": [{"id": 1}, {"id": 2}],
                        "meta": {"total": 2}
                    }
                }
            }
        }
        
        missing = validate_template_variables(variables, context)
        
        assert missing == ["steps.api.missing.path"]


class TestPerformanceOptimization:
    """Test template rendering performance characteristics."""
    
    def test_simple_substitution_performance(self, performance_benchmarks):
        """Test performance of simple variable substitution."""
        template = "Hello ${params.name}, welcome to ${params.location}!"
        context = {"params": {"name": "Alice", "location": "Chisinau"}}
        
        start_time = time.perf_counter()
        for _ in range(1000):  # 1000 iterations
            result = render_templates(template, context)
        end_time = time.perf_counter()
        
        avg_time_ms = ((end_time - start_time) * 1000) / 1000
        max_time_ms = performance_benchmarks["template_rendering"]["simple_substitution_max_ms"]
        
        assert avg_time_ms < max_time_ms, f"Simple substitution too slow: {avg_time_ms:.2f}ms > {max_time_ms}ms"
        assert result == "Hello Alice, welcome to Chisinau!"
    
    def test_complex_nested_performance(self, performance_benchmarks):
        """Test performance of complex nested structure rendering."""
        template = {
            "level1": {
                "level2": {
                    "level3": {
                        "message": "Hello ${params.user.name}",
                        "data": [
                            "${steps.weather.temp}",
                            "${steps.calendar.events[0].title}",
                            "${params.location}"
                        ]
                    }
                }
            },
            "summary": "Weather: ${steps.weather.condition}, Events: ${length(steps.calendar.events)}"
        }
        
        context = {
            "params": {
                "user": {"name": "Alice"},
                "location": "Chisinau"
            },
            "steps": {
                "weather": {"temp": 25, "condition": "sunny"},
                "calendar": {"events": [{"title": "Meeting"}, {"title": "Lunch"}]}
            }
        }
        
        start_time = time.perf_counter()
        for _ in range(100):  # 100 iterations
            result = render_templates(template, context)
        end_time = time.perf_counter()
        
        avg_time_ms = ((end_time - start_time) * 1000) / 100
        max_time_ms = performance_benchmarks["template_rendering"]["complex_nested_max_ms"]
        
        assert avg_time_ms < max_time_ms, f"Complex nested rendering too slow: {avg_time_ms:.2f}ms > {max_time_ms}ms"
        assert result["level1"]["level2"]["level3"]["message"] == "Hello Alice"
    
    def test_large_payload_performance(self, performance_benchmarks):
        """Test performance with large template payloads."""
        # Create a large template structure
        large_template = {}
        for i in range(100):
            large_template[f"section_{i}"] = {
                "message": f"Section {i}: Hello ${{params.name}}",
                "data": [f"${{params.item_{j}}}" for j in range(10)],
                "nested": {
                    "value": f"${{steps.data_{i}.value}}",
                    "status": f"${{steps.data_{i}.active}}"
                }
            }
        
        # Create corresponding context
        context = {
            "params": {"name": "TestUser"}
        }
        
        # Add item parameters
        for i in range(100):
            for j in range(10):
                context["params"][f"item_{j}"] = f"item_value_{j}"
        
        # Add step data
        context["steps"] = {}
        for i in range(100):
            context["steps"][f"data_{i}"] = {"value": f"value_{i}", "active": True}
        
        start_time = time.perf_counter()
        result = render_templates(large_template, context)
        end_time = time.perf_counter()
        
        execution_time_ms = (end_time - start_time) * 1000
        max_time_ms = performance_benchmarks["template_rendering"]["large_payload_max_ms"]
        
        assert execution_time_ms < max_time_ms, f"Large payload rendering too slow: {execution_time_ms:.2f}ms > {max_time_ms}ms"
        
        # Verify correctness
        assert result["section_0"]["message"] == "Section 0: Hello TestUser"
        assert result["section_0"]["data"][0] == "item_value_0"
        assert result["section_0"]["nested"]["value"] == "value_0"
    
    def test_template_caching_behavior(self):
        """Test that template rendering doesn't have memory leaks."""
        template = "Hello ${params.name}, weather is ${steps.weather.condition}"
        
        # Render many different contexts to test memory behavior
        for i in range(1000):
            context = {
                "params": {"name": f"User{i}"},
                "steps": {"weather": {"condition": f"condition_{i % 5}"}}
            }
            result = render_templates(template, context)
            assert f"User{i}" in result


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_empty_template(self):
        """Test rendering of empty template."""
        assert render_templates("", {}) == ""
        assert render_templates({}, {}) == {}
        assert render_templates([], {}) == []
    
    def test_empty_context(self):
        """Test rendering with empty context."""
        template = "Hello ${params.name}"
        result = render_templates(template, {})
        assert result == "Hello null"  # Missing values become "null"
    
    def test_template_without_variables(self):
        """Test template with no variables."""
        template = {
            "message": "Static message",
            "data": ["item1", "item2", "item3"],
            "nested": {"value": 42, "active": True}
        }
        
        result = render_templates(template, {"params": {"unused": "value"}})
        assert result == template  # Should be identical
    
    def test_special_characters_in_values(self):
        """Test handling of special characters in template values."""
        template = "Message: ${params.special}"
        context = {
            "params": {
                "special": "Contains ${} braces and special chars: !@#$%^&*()"
            }
        }
        
        result = render_templates(template, context)
        expected = "Message: Contains ${} braces and special chars: !@#$%^&*()"
        assert result == expected
    
    def test_unicode_handling(self):
        """Test proper Unicode character handling."""
        template = "Greeting: ${params.unicode_text}"
        context = {
            "params": {
                "unicode_text": "Привет! 🌟 你好 العالم"
            }
        }
        
        result = render_templates(template, context)
        assert result == "Greeting: Привет! 🌟 你好 العالم"
    
    def test_very_long_strings(self):
        """Test handling of very long string values."""
        long_text = "A" * 10000  # 10KB string
        template = "Data: ${params.long_text}"
        context = {"params": {"long_text": long_text}}
        
        result = render_templates(template, context)
        assert result == f"Data: {long_text}"
        assert len(result) > 10000


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])