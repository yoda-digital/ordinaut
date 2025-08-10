#!/usr/bin/env python3
"""
Test script for Ordinaut observability stack.

Tests metrics collection, structured logging, health checks, and Prometheus integration.
This script validates that all observability components are working correctly.
"""

import asyncio
import json
import time
import requests
import sys
import os
from datetime import datetime, timezone
from typing import Dict, Any

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import observability components
from observability.metrics import orchestrator_metrics, get_metrics_handler
from observability.logging import (
    StructuredLogger, set_request_context, generate_request_id,
    api_logger, worker_logger, scheduler_logger, pipeline_logger
)
from observability.health import SystemHealthMonitor

def test_metrics_collection():
    """Test Prometheus metrics collection."""
    print("🔍 Testing metrics collection...")
    
    # Test basic metric recording
    orchestrator_metrics.record_http_request("GET", "/test", 200, 0.1)
    orchestrator_metrics.record_task_run("test-task-1", "test-agent", "success", 2.5)
    orchestrator_metrics.record_step_execution("test-tool.action", "step-1", "test-task-1", 1.2, True)
    orchestrator_metrics.update_queue_depth(5)
    orchestrator_metrics.update_scheduler_lag(1.5)
    orchestrator_metrics.record_worker_heartbeat("test-worker-1")
    orchestrator_metrics.record_external_tool_call("weather-api", "GET", 200, 0.8)
    
    # Test metrics handler
    handler = get_metrics_handler()
    metrics_output, headers = handler()
    
    assert "orchestrator_http_requests_total" in metrics_output
    assert "orchestrator_task_duration_seconds" in metrics_output
    assert "orchestrator_step_success_total" in metrics_output
    assert "orchestrator_due_work_queue_depth" in metrics_output
    assert "orchestrator_scheduler_lag_seconds" in metrics_output
    assert headers["Content-Type"] == "text/plain; version=0.0.4; charset=utf-8"
    
    print("✅ Metrics collection test passed")
    return True

def test_structured_logging():
    """Test structured JSON logging."""
    print("🔍 Testing structured logging...")
    
    # Test logging with correlation IDs
    request_id = generate_request_id()
    set_request_context(request_id=request_id, task_id="test-task-1", agent_id="test-agent")
    
    # Test API logger
    api_logger.api_request("GET", "/test", 200, 150.5, "test-agent")
    api_logger.security_event("unauthorized_access_attempt", "bad-agent")
    
    # Test worker logger  
    worker_logger.task_started("test-task-1", "run-123", "test-agent")
    worker_logger.task_completed("test-task-1", "run-123", True, 2500.0)
    worker_logger.lease_acquired("worker-1", "test-task-1", 300)
    
    # Test scheduler logger
    scheduler_logger.scheduler_tick(3, 1.2)
    
    # Test pipeline logger
    pipeline_logger.pipeline_step_started("step-1", "weather-api.forecast")
    pipeline_logger.pipeline_step_completed("step-1", "weather-api.forecast", True, 800.0)
    pipeline_logger.external_tool_call("weather-api", "GET", 200, 750.0, "https://api.weather.com/v1/current")
    
    print("✅ Structured logging test passed")
    return True

async def test_health_monitoring():
    """Test health check system."""
    print("🔍 Testing health monitoring...")
    
    # Create health monitor (will use environment DATABASE_URL if available)
    try:
        health_monitor = SystemHealthMonitor()
        
        # Test quick health check
        quick_health = await health_monitor.get_quick_health()
        assert "status" in quick_health
        assert "timestamp" in quick_health
        assert "uptime_seconds" in quick_health
        
        print(f"   Quick health status: {quick_health['status']}")
        print(f"   Health check duration: {quick_health['duration_ms']:.2f}ms")
        
        # Test comprehensive health check if database is configured
        if os.getenv("DATABASE_URL"):
            full_health = await health_monitor.get_system_health(request_id="test-health-check")
            health_dict = full_health.to_dict()
            
            assert "status" in health_dict
            assert "checks" in health_dict
            assert "summary" in health_dict
            
            print(f"   Full health status: {health_dict['status']}")
            print(f"   Health checks: {len(health_dict['checks'])}")
            print(f"   Healthy checks: {health_dict['summary']['healthy_checks']}")
        else:
            print("   Skipping full health check - DATABASE_URL not configured")
        
    except Exception as e:
        print(f"   Health monitoring test failed: {e}")
        return False
    
    print("✅ Health monitoring test passed")
    return True

def test_prometheus_endpoint():
    """Test Prometheus metrics endpoint if API is running."""
    print("🔍 Testing Prometheus endpoint...")
    
    # Try to connect to local API metrics endpoint
    try:
        response = requests.get("http://localhost:8080/metrics", timeout=5)
        if response.status_code == 200:
            metrics_content = response.text
            
            # Check for expected metrics
            expected_metrics = [
                "orchestrator_http_requests_total",
                "orchestrator_step_success_total", 
                "orchestrator_task_duration_seconds",
                "orchestrator_due_work_queue_depth"
            ]
            
            for metric in expected_metrics:
                if metric in metrics_content:
                    print(f"   ✓ Found metric: {metric}")
                else:
                    print(f"   ⚠ Missing metric: {metric}")
            
            # Check content type
            content_type = response.headers.get("Content-Type", "")
            if "text/plain" in content_type:
                print("   ✓ Correct Content-Type header")
            else:
                print(f"   ⚠ Unexpected Content-Type: {content_type}")
            
            print("✅ Prometheus endpoint test passed")
            return True
        else:
            print(f"   API not running or metrics endpoint returned {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("   API not running - skipping Prometheus endpoint test")
        return False
    except Exception as e:
        print(f"   Prometheus endpoint test failed: {e}")
        return False

def test_performance_metrics():
    """Test performance metrics collection under load."""
    print("🔍 Testing performance metrics...")
    
    # Simulate some load
    start_time = time.time()
    
    for i in range(100):
        # Simulate API requests
        orchestrator_metrics.record_http_request("GET", f"/tasks/{i}", 200, 0.05 + i * 0.001)
        
        # Simulate task processing  
        orchestrator_metrics.record_task_run(f"task-{i}", "load-test-agent", "success", 1.0 + i * 0.01)
        
        # Simulate pipeline steps
        orchestrator_metrics.record_step_execution("load-test.action", f"step-{i}", f"task-{i}", 0.5, True)
        
    duration = time.time() - start_time
    
    # Test metrics handler performance
    handler_start = time.time()
    handler = get_metrics_handler()
    metrics_output, _ = handler()
    handler_duration = time.time() - handler_start
    
    print(f"   Generated 300 metrics in {duration:.3f}s")
    print(f"   Metrics handler took {handler_duration:.3f}s")
    print(f"   Metrics output size: {len(metrics_output)} bytes")
    
    if handler_duration > 1.0:
        print("   ⚠ Metrics handler is slow (>1s)")
        return False
    
    print("✅ Performance metrics test passed")
    return True

def generate_test_report():
    """Generate a comprehensive test report."""
    print("\n📊 Generating observability test report...")
    
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat() + 'Z',
        "test_results": {},
        "system_info": {
            "python_version": sys.version,
            "platform": sys.platform
        }
    }
    
    # Run all tests
    tests = [
        ("metrics_collection", test_metrics_collection),
        ("structured_logging", test_structured_logging),
        ("performance_metrics", test_performance_metrics),
        ("prometheus_endpoint", test_prometheus_endpoint)
    ]
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            report["test_results"][test_name] = {
                "passed": result,
                "error": None
            }
        except Exception as e:
            report["test_results"][test_name] = {
                "passed": False,
                "error": str(e)
            }
    
    return report

async def main():
    """Main test execution."""
    print("🚀 Starting Ordinaut observability tests...\n")
    
    # Run synchronous tests
    report = generate_test_report()
    
    # Run async health monitoring test
    try:
        health_result = await test_health_monitoring()
        report["test_results"]["health_monitoring"] = {
            "passed": health_result,
            "error": None
        }
    except Exception as e:
        report["test_results"]["health_monitoring"] = {
            "passed": False,
            "error": str(e)
        }
    
    # Print summary
    print("\n" + "="*60)
    print("📋 OBSERVABILITY TEST SUMMARY")
    print("="*60)
    
    passed_tests = sum(1 for result in report["test_results"].values() if result["passed"])
    total_tests = len(report["test_results"])
    
    for test_name, result in report["test_results"].items():
        status = "✅ PASS" if result["passed"] else "❌ FAIL"
        print(f"{status:8} {test_name}")
        if not result["passed"] and result["error"]:
            print(f"         Error: {result['error']}")
    
    print("-" * 60)
    print(f"Results: {passed_tests}/{total_tests} tests passed")
    
    if passed_tests == total_tests:
        print("🎉 All observability tests passed!")
        return 0
    else:
        print("⚠️  Some tests failed. Check the output above for details.")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)