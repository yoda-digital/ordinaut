#!/usr/bin/env python3
"""
Quick system integration test for Personal Agent Orchestrator.
Tests API endpoints and basic functionality.
"""
import os
import sys
import time
import json
import requests
import subprocess
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def setup_environment():
    """Set up environment variables"""
    os.environ["DATABASE_URL"] = f"sqlite:///{project_root}/orchestrator.db"
    os.environ["REDIS_URL"] = "memory://"
    os.environ["ENVIRONMENT"] = "development"
    os.environ["DEBUG"] = "true"

def start_api_background():
    """Start API in background"""
    print("🚀 Starting API service in background...")
    
    proc = subprocess.Popen([
        sys.executable, "-m", "uvicorn",
        "api.main:app",
        "--host", "127.0.0.1",
        "--port", "8080",
        "--log-level", "error"  # Minimize logs
    ], cwd=str(project_root), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Wait for startup
    for i in range(10):
        try:
            response = requests.get("http://127.0.0.1:8080/health", timeout=1)
            if response.status_code == 200:
                print("✅ API service started successfully")
                return proc
        except:
            pass
        time.sleep(0.5)
    
    print("❌ API service failed to start in time")
    return None

def test_health_endpoint():
    """Test health endpoint"""
    print("🔍 Testing health endpoint...")
    
    try:
        response = requests.get("http://127.0.0.1:8080/health", timeout=5)
        if response.status_code == 200:
            health_data = response.json()
            print(f"✅ Health endpoint responded: {health_data.get('status', 'unknown')}")
            return True
        else:
            print(f"❌ Health endpoint returned {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Health endpoint failed: {e}")
        return False

def test_docs_endpoint():
    """Test API documentation endpoint"""
    print("📚 Testing docs endpoint...")
    
    try:
        response = requests.get("http://127.0.0.1:8080/docs", timeout=5)
        if response.status_code == 200:
            print("✅ API docs accessible")
            return True
        else:
            print(f"❌ API docs returned {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ API docs failed: {e}")
        return False

def test_openapi_schema():
    """Test OpenAPI schema endpoint"""
    print("🔧 Testing OpenAPI schema...")
    
    try:
        response = requests.get("http://127.0.0.1:8080/openapi.json", timeout=5)
        if response.status_code == 200:
            schema = response.json()
            print(f"✅ OpenAPI schema available (version: {schema.get('openapi', 'unknown')})")
            return True
        else:
            print(f"❌ OpenAPI schema returned {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ OpenAPI schema failed: {e}")
        return False

def cleanup(processes):
    """Clean up processes"""
    print("🧹 Cleaning up...")
    for proc in processes:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()

def main():
    """Main test flow"""
    print("🎯 Personal Agent Orchestrator - System Integration Test")
    print("=" * 60)
    
    setup_environment()
    
    processes = []
    tests_passed = 0
    total_tests = 0
    
    try:
        # Start API service
        api_proc = start_api_background()
        if not api_proc:
            return 1
        processes.append(api_proc)
        
        # Run tests
        tests = [
            test_health_endpoint,
            test_docs_endpoint, 
            test_openapi_schema
        ]
        
        for test_func in tests:
            total_tests += 1
            if test_func():
                tests_passed += 1
            time.sleep(0.5)  # Brief pause between tests
        
        print()
        print("📊 Test Results:")
        print(f"   Passed: {tests_passed}/{total_tests}")
        
        if tests_passed == total_tests:
            print("🎉 All integration tests PASSED!")
            print()
            print("✅ Personal Agent Orchestrator is operational")
            print("🌐 API accessible at: http://127.0.0.1:8080")
            print("📚 API docs at: http://127.0.0.1:8080/docs")
            return 0
        else:
            print("❌ Some integration tests FAILED")
            return 1
            
    except Exception as e:
        print(f"❌ Test suite failed: {e}")
        return 1
    finally:
        cleanup(processes)

if __name__ == "__main__":
    exit(main())