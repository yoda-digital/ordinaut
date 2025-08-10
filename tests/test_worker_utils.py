#!/usr/bin/env python3
"""
Test utilities for worker testing.

Provides TaskWorker class and other utilities needed for testing.
"""

import asyncio
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from sqlalchemy import text, Engine


class TaskWorker:
    """Simplified TaskWorker for testing purposes."""
    
    def __init__(self, worker_id: str, db_engine: Engine):
        self.worker_id = worker_id
        self.db_engine = db_engine
        self.processed_tasks = []
        self.errors = []
    
    async def lease_work(self, timeout_minutes: int = 5) -> Optional[Dict[str, Any]]:
        """Lease a work item from the due_work table."""
        try:
            with self.db_engine.begin() as conn:
                # Try to lease work with SKIP LOCKED
                work_result = conn.execute(text("""
                    SELECT id, task_id FROM due_work 
                    WHERE run_at <= now() 
                      AND (locked_until IS NULL OR locked_until < now())
                    ORDER BY run_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                """))
                
                work_row = work_result.fetchone()
                if not work_row:
                    return None
                
                work_id, task_id = work_row
                
                # Lease the work
                lease_time = datetime.now(timezone.utc) + timedelta(minutes=timeout_minutes)
                conn.execute(text("""
                    UPDATE due_work 
                    SET locked_until = :lease_time, locked_by = :worker_id
                    WHERE id = :work_id
                """), {
                    "lease_time": lease_time,
                    "worker_id": self.worker_id,
                    "work_id": work_id
                })
                
                return {
                    "work_id": work_id,
                    "task_id": task_id,
                    "lease_time": lease_time
                }
        
        except Exception as e:
            self.errors.append(f"Failed to lease work: {e}")
            return None
    
    async def complete_work(self, work_id: str, success: bool, output: Dict = None, error: str = None):
        """Complete a work item and record the result."""
        try:
            with self.db_engine.begin() as conn:
                # Get task details
                task_result = conn.execute(text("""
                    SELECT dw.task_id FROM due_work dw WHERE dw.id = :work_id
                """), {"work_id": work_id})
                
                task_row = task_result.fetchone()
                if not task_row:
                    raise ValueError(f"Work item {work_id} not found")
                
                task_id = task_row.task_id
                
                # Record task run
                conn.execute(text("""
                    INSERT INTO task_run (id, task_id, lease_owner, started_at, 
                                        finished_at, success, attempt, output, error)
                    VALUES (gen_random_uuid(), :task_id, :lease_owner, :started_at, 
                           :finished_at, :success, :attempt, :output::jsonb, :error)
                """), {
                    "task_id": task_id,
                    "lease_owner": self.worker_id,
                    "started_at": datetime.now(timezone.utc),
                    "finished_at": datetime.now(timezone.utc),
                    "success": success,
                    "attempt": 1,
                    "output": json.dumps(output) if output else None,
                    "error": error
                })
                
                # Clean up due work
                conn.execute(text("DELETE FROM due_work WHERE id = :work_id"), 
                            {"work_id": work_id})
                
                if success:
                    self.processed_tasks.append(task_id)
        
        except Exception as e:
            self.errors.append(f"Failed to complete work {work_id}: {e}")
    
    async def process_available_work(self, max_items: int = 10):
        """Process available work items."""
        processed_count = 0
        
        while processed_count < max_items:
            work = await self.lease_work()
            if not work:
                break  # No more work available
            
            try:
                # Simulate work processing
                await asyncio.sleep(0.001)  # Minimal processing time
                
                await self.complete_work(
                    work["work_id"], 
                    success=True, 
                    output={"result": f"Processed by {self.worker_id}"}
                )
                processed_count += 1
                
            except Exception as e:
                await self.complete_work(
                    work["work_id"],
                    success=False,
                    error=str(e)
                )
                break
        
        return processed_count