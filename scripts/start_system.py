#!/usr/bin/env python3
"""
Simplified system startup script for Ordinaut.
Starts individual components with proper error handling.
"""
import os
import sys
import subprocess
import time
import signal
import json
import sqlite3
import threading
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

print(f"🎯 Ordinaut - System Integration")
print(f"📁 Project Root: {project_root}")
print("=" * 60)

def setup_environment():
    """Set up environment variables"""
    os.environ["DATABASE_URL"] = f"sqlite:///{project_root}/orchestrator.db"
    os.environ["REDIS_URL"] = "memory://"
    os.environ["ENVIRONMENT"] = "development"
    os.environ["DEBUG"] = "true"
    print(f"🔧 Environment configured:")
    print(f"   DATABASE_URL: {os.environ['DATABASE_URL']}")
    print(f"   REDIS_URL: {os.environ['REDIS_URL']}")

def setup_sqlite_database():
    """Set up SQLite database with schema"""
    db_path = project_root / "orchestrator.db"
    print(f"🗄️  Setting up SQLite database: {db_path}")
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Simplified schema for immediate functionality
    schema = """
    -- Core tables (SQLite version)
    CREATE TABLE IF NOT EXISTS agent (
        id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
        name TEXT UNIQUE NOT NULL,
        scopes TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE TABLE IF NOT EXISTS task (
        id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
        title TEXT NOT NULL,
        description TEXT,
        created_by TEXT NOT NULL,
        schedule_kind TEXT NOT NULL CHECK (schedule_kind IN ('manual', 'once', 'rrule')),
        schedule_expr TEXT,
        timezone TEXT NOT NULL DEFAULT 'UTC',
        payload TEXT NOT NULL,
        priority INTEGER NOT NULL DEFAULT 3,
        max_retries INTEGER NOT NULL DEFAULT 3,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE TABLE IF NOT EXISTS due_work (
        id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
        task_id TEXT NOT NULL,
        run_at TIMESTAMP NOT NULL,
        priority INTEGER NOT NULL DEFAULT 3,
        attempt INTEGER NOT NULL DEFAULT 0,
        locked_until TIMESTAMP,
        locked_by TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE TABLE IF NOT EXISTS run_log (
        id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
        task_id TEXT NOT NULL,
        due_work_id TEXT,
        status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failure', 'timeout')),
        started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        finished_at TIMESTAMP,
        result TEXT,
        error_message TEXT,
        attempt INTEGER NOT NULL DEFAULT 1
    );
    
    CREATE INDEX IF NOT EXISTS idx_due_work_run_at ON due_work(run_at);
    CREATE INDEX IF NOT EXISTS idx_task_active ON task(is_active);
    """
    
    cursor.executescript(schema)
    
    # Create system agent
    cursor.execute("""
        INSERT OR IGNORE INTO agent (id, name, scopes) 
        VALUES ('00000000-0000-0000-0000-000000000001', 'system', '["notify","calendar.read"]')
    """)
    
    conn.commit()
    conn.close()
    print("✅ Database initialized with schema and system agent")

def start_api_service():
    """Start the API service in a subprocess"""
    print("🚀 Starting API service...")
    
    try:
        # Use a simple approach - start API directly with uvicorn module
        proc = subprocess.Popen([
            sys.executable, "-m", "uvicorn",
            "api.main:app",
            "--host", "0.0.0.0",
            "--port", "8080",
            "--log-level", "info"
        ], cwd=str(project_root))
        
        # Wait a moment for startup
        time.sleep(3)
        
        # Check if process is still running
        if proc.poll() is None:
            print("✅ API service started successfully")
            return proc
        else:
            print("❌ API service failed to start")
            return None
            
    except Exception as e:
        print(f"❌ Failed to start API service: {e}")
        return None

def test_api_health():
    """Test API health endpoint"""
    print("🧪 Testing API health...")
    
    try:
        import requests
        response = requests.get("http://localhost:8080/health", timeout=5)
        if response.status_code == 200:
            print("✅ API health check passed")
            return True
        else:
            print(f"⚠️  API returned status {response.status_code}")
            return False
    except ImportError:
        print("⚠️  Requests library not available, skipping health check")
        return True
    except Exception as e:
        print(f"❌ API health check failed: {e}")
        return False

def create_sample_task():
    """Create the morning briefing task"""
    print("📝 Creating morning briefing task...")
    
    try:
        import requests
        
        # Load task payload
        payload_file = project_root / "payloads" / "morning_briefing.json"
        if not payload_file.exists():
            print(f"⚠️  Payload file not found: {payload_file}")
            return None
            
        with open(payload_file) as f:
            task_data = json.load(f)
        
        response = requests.post(
            "http://localhost:8080/tasks",
            json=task_data,
            timeout=10
        )
        
        if response.status_code == 201:
            task_result = response.json()
            task_id = task_result.get("id")
            print(f"✅ Morning briefing task created: {task_id}")
            
            # Queue for immediate execution
            run_response = requests.post(
                f"http://localhost:8080/tasks/{task_id}/run_now",
                timeout=5
            )
            
            if run_response.status_code == 200:
                print("✅ Task queued for immediate execution")
            else:
                print(f"⚠️  Failed to queue task: {run_response.status_code}")
                
            return task_id
        else:
            print(f"❌ Task creation failed: {response.status_code} - {response.text}")
            return None
            
    except ImportError:
        print("⚠️  Requests library not available, skipping task creation")
        return None
    except Exception as e:
        print(f"❌ Task creation failed: {e}")
        return None

def main():
    """Main integration flow"""
    processes = []
    
    try:
        # Step 1: Environment setup
        setup_environment()
        
        # Step 2: Database setup
        setup_sqlite_database()
        
        # Step 3: Start API service
        api_proc = start_api_service()
        if api_proc:
            processes.append(api_proc)
        
        # Step 4: Test system
        if test_api_health():
            # Step 5: Create sample task
            task_id = create_sample_task()
            
            print()
            print("🎉 Ordinaut Integration Complete!")
            print("=" * 60)
            print("🌐 API Server: http://localhost:8080")
            print("📚 API Documentation: http://localhost:8080/docs")
            print("🔍 Health Check: http://localhost:8080/health")
            if task_id:
                print(f"📋 Sample Task ID: {task_id}")
            print()
            print("✅ System Status: OPERATIONAL")
            print("⚠️  Note: Running in simplified mode with SQLite")
            print("🛑 Press Ctrl+C to stop all services")
            
            # Keep running
            try:
                while True:
                    time.sleep(1)
                    # Check if API process is still running
                    if api_proc and api_proc.poll() is not None:
                        print("⚠️  API process died, restarting...")
                        api_proc = start_api_service()
                        if not api_proc:
                            break
                        processes = [api_proc]
            except KeyboardInterrupt:
                print("\n🛑 Shutdown requested...")
        else:
            print("❌ System health check failed")
            return 1
            
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        return 1
    finally:
        # Cleanup
        print("🧹 Stopping services...")
        for proc in processes:
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        
        print("👋 Ordinaut stopped")
    
    return 0

if __name__ == "__main__":
    exit(main())