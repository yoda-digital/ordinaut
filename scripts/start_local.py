#!/usr/bin/env python3
"""
Local development startup script for Personal Agent Orchestrator.
Alternative to Docker Compose when containers aren't available.
"""
import os
import sys
import subprocess
import time
import signal
import json
import sqlite3
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def setup_sqlite_database():
    """Set up SQLite database as fallback for development"""
    db_path = project_root / "orchestrator.db"
    
    print(f"Setting up SQLite database at {db_path}")
    
    # Read and adapt PostgreSQL schema for SQLite
    schema_path = project_root / "migrations" / "version_0001.sql"
    if not schema_path.exists():
        print(f"Schema file not found: {schema_path}")
        return None
        
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Simplified schema for SQLite (remove PostgreSQL-specific features)
    sqlite_schema = """
    -- Core tables for Personal Agent Orchestrator (SQLite version)
    
    CREATE TABLE IF NOT EXISTS agent (
        id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
        name TEXT UNIQUE NOT NULL,
        scopes TEXT NOT NULL, -- JSON array as text
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE TABLE IF NOT EXISTS task (
        id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
        title TEXT NOT NULL,
        description TEXT,
        created_by TEXT NOT NULL REFERENCES agent(id),
        schedule_kind TEXT NOT NULL CHECK (schedule_kind IN ('manual', 'once', 'rrule')),
        schedule_expr TEXT,
        timezone TEXT NOT NULL DEFAULT 'UTC',
        payload TEXT NOT NULL, -- JSON as text
        priority INTEGER NOT NULL DEFAULT 3,
        dedupe_key TEXT,
        dedupe_window_seconds INTEGER,
        max_retries INTEGER NOT NULL DEFAULT 3,
        backoff_strategy TEXT NOT NULL DEFAULT 'exponential',
        concurrency_key TEXT,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE TABLE IF NOT EXISTS due_work (
        id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
        task_id TEXT NOT NULL REFERENCES task(id),
        run_at TIMESTAMP NOT NULL,
        priority INTEGER NOT NULL DEFAULT 3,
        attempt INTEGER NOT NULL DEFAULT 0,
        locked_until TIMESTAMP,
        locked_by TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE TABLE IF NOT EXISTS run_log (
        id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
        task_id TEXT NOT NULL REFERENCES task(id),
        due_work_id TEXT REFERENCES due_work(id),
        status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failure', 'timeout')),
        started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        finished_at TIMESTAMP,
        result TEXT, -- JSON as text
        error_message TEXT,
        attempt INTEGER NOT NULL DEFAULT 1
    );
    
    CREATE INDEX IF NOT EXISTS idx_due_work_run_at ON due_work(run_at);
    CREATE INDEX IF NOT EXISTS idx_due_work_task_id ON due_work(task_id);
    CREATE INDEX IF NOT EXISTS idx_run_log_task_id ON run_log(task_id);
    CREATE INDEX IF NOT EXISTS idx_run_log_status ON run_log(status);
    """
    
    cursor.executescript(sqlite_schema)
    
    # Create system agent
    cursor.execute("""
        INSERT OR IGNORE INTO agent (id, name, scopes) 
        VALUES ('00000000-0000-0000-0000-000000000001', 'system', '["notify","calendar.read"]')
    """)
    
    conn.commit()
    conn.close()
    
    print("✅ SQLite database initialized")
    return str(db_path)

def start_api_server():
    """Start the FastAPI server"""
    print("🚀 Starting FastAPI server...")
    
    # Set environment variables for SQLite
    os.environ["DATABASE_URL"] = f"sqlite:///{project_root}/orchestrator.db"
    os.environ["REDIS_URL"] = "memory://"  # In-memory fallback
    
    api_script = project_root / "run_api.py"
    if not api_script.exists():
        print(f"API script not found: {api_script}")
        return None
        
    # Start API server in background
    proc = subprocess.Popen([
        sys.executable, str(api_script)
    ], cwd=str(project_root))
    
    # Wait for server to start
    time.sleep(3)
    
    return proc

def start_scheduler():
    """Start the APScheduler service"""
    print("⏰ Starting scheduler...")
    
    scheduler_script = project_root / "scheduler" / "tick.py"
    if not scheduler_script.exists():
        print(f"Scheduler script not found: {scheduler_script}")
        return None
    
    proc = subprocess.Popen([
        sys.executable, str(scheduler_script)
    ], cwd=str(project_root))
    
    return proc

def start_workers():
    """Start worker processes"""
    print("👷 Starting workers...")
    
    worker_script = project_root / "workers" / "runner.py"
    if not worker_script.exists():
        print(f"Worker script not found: {worker_script}")
        return None
    
    # Start 2 worker processes
    workers = []
    for i in range(2):
        proc = subprocess.Popen([
            sys.executable, str(worker_script)
        ], cwd=str(project_root), env={
            **os.environ,
            "WORKER_ID": f"worker-{i+1}"
        })
        workers.append(proc)
    
    return workers

def test_system():
    """Test system components"""
    print("🧪 Testing system components...")
    
    import requests
    
    # Test API health
    try:
        response = requests.get("http://localhost:8080/health", timeout=5)
        if response.status_code == 200:
            print("✅ API server healthy")
        else:
            print(f"⚠️  API server responding with status {response.status_code}")
    except Exception as e:
        print(f"❌ API server test failed: {e}")
        return False
    
    # Test task creation
    try:
        briefing_payload = project_root / "payloads" / "morning_briefing.json"
        if briefing_payload.exists():
            with open(briefing_payload) as f:
                task_data = json.load(f)
            
            response = requests.post("http://localhost:8080/tasks", 
                                   json=task_data, timeout=10)
            if response.status_code == 201:
                task_id = response.json().get("id")
                print(f"✅ Morning briefing task created: {task_id}")
                
                # Test immediate execution
                run_response = requests.post(f"http://localhost:8080/tasks/{task_id}/run_now", 
                                           timeout=5)
                if run_response.status_code == 200:
                    print("✅ Task queued for immediate execution")
                else:
                    print(f"⚠️  Task execution request failed: {run_response.status_code}")
            else:
                print(f"❌ Task creation failed: {response.status_code} - {response.text}")
                return False
        else:
            print("⚠️  Morning briefing payload not found")
    except Exception as e:
        print(f"❌ Task creation test failed: {e}")
        return False
    
    return True

def cleanup(processes):
    """Clean up processes on exit"""
    print("🧹 Shutting down services...")
    
    for proc in processes:
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

def main():
    """Main startup orchestration"""
    print("🎯 Personal Agent Orchestrator - Local Development Mode")
    print("=" * 60)
    
    # Set up database
    db_path = setup_sqlite_database()
    if not db_path:
        print("❌ Database setup failed")
        return 1
    
    processes = []
    
    try:
        # Start API server
        api_proc = start_api_server()
        if api_proc:
            processes.append(api_proc)
        
        # Start scheduler
        scheduler_proc = start_scheduler()
        if scheduler_proc:
            processes.append(scheduler_proc)
        
        # Start workers
        worker_procs = start_workers()
        if worker_procs:
            processes.extend(worker_procs)
        
        # Wait for services to stabilize
        time.sleep(5)
        
        # Test system
        if test_system():
            print("✅ System integration successful!")
            print("\n🎉 Personal Agent Orchestrator is running!")
            print("📊 API: http://localhost:8080")
            print("📋 Health: http://localhost:8080/health")
            print("📚 Docs: http://localhost:8080/docs")
            print("\nPress Ctrl+C to stop...")
            
            # Keep running
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
        else:
            print("❌ System integration tests failed")
            return 1
            
    except KeyboardInterrupt:
        pass
    finally:
        cleanup(processes)
    
    print("👋 Personal Agent Orchestrator stopped")
    return 0

if __name__ == "__main__":
    exit(main())