# workers/coordinator.py
import os
import time
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine, text
from typing import List, Dict, Any, Optional

logging.basicConfig(level=logging.INFO)

class WorkerCoordinator:
    """Manages worker coordination, health monitoring, and load balancing."""
    
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.eng = create_engine(db_url, pool_pre_ping=True, future=True)
    
    def get_active_workers(self, since_minutes: int = 5) -> List[Dict[str, Any]]:
        """Get list of workers that have sent heartbeat within specified minutes."""
        with self.eng.begin() as cx:
            rows = cx.execute(text("""
                SELECT worker_id, last_seen, processed_count, pid, hostname,
                       EXTRACT(EPOCH FROM (now() - last_seen)) as seconds_since_heartbeat
                FROM worker_heartbeat
                WHERE last_seen > now() - interval '%s minutes'
                ORDER BY last_seen DESC
            """ % since_minutes)).mappings().fetchall()
            return [dict(row) for row in rows]
    
    def get_worker_stats(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed statistics for a specific worker."""
        with self.eng.begin() as cx:
            # Get heartbeat info
            heartbeat = cx.execute(text("""
                SELECT * FROM worker_heartbeat WHERE worker_id = :worker_id
            """), {"worker_id": worker_id}).mappings().first()
            
            if not heartbeat:
                return None
            
            # Get current leases
            leases = cx.execute(text("""
                SELECT COUNT(*) as active_leases,
                       MIN(locked_until) as earliest_lease_expiry,
                       MAX(locked_until) as latest_lease_expiry
                FROM due_work 
                WHERE locked_by = :worker_id AND locked_until > now()
            """), {"worker_id": worker_id}).mappings().first()
            
            # Get recent processing stats
            recent_stats = cx.execute(text("""
                SELECT COUNT(*) as recent_runs,
                       COUNT(*) FILTER (WHERE success = true) as recent_successes,
                       COUNT(*) FILTER (WHERE success = false) as recent_failures,
                       AVG(EXTRACT(EPOCH FROM (finished_at - started_at))) as avg_duration_seconds
                FROM task_run
                WHERE lease_owner = :worker_id 
                  AND started_at > now() - interval '1 hour'
            """), {"worker_id": worker_id}).mappings().first()
            
            return {
                "worker_id": worker_id,
                "heartbeat": dict(heartbeat),
                "leases": dict(leases),
                "recent_stats": dict(recent_stats)
            }
    
    def cleanup_stale_leases(self, stale_threshold_minutes: int = 10) -> int:
        """Clean up leases from workers that haven't sent heartbeat recently."""
        with self.eng.begin() as cx:
            result = cx.execute(text("""
                UPDATE due_work 
                SET locked_until = NULL, locked_by = NULL
                WHERE locked_by IS NOT NULL 
                  AND locked_by NOT IN (
                    SELECT worker_id FROM worker_heartbeat 
                    WHERE last_seen > now() - interval '%s minutes'
                  )
            """ % stale_threshold_minutes))
            
            cleaned_count = result.rowcount
            if cleaned_count > 0:
                logging.info(f"Cleaned up {cleaned_count} stale leases")
            
            return cleaned_count
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """Get comprehensive queue and processing statistics."""
        with self.eng.begin() as cx:
            # Queue depth and age
            queue_stats = cx.execute(text("""
                SELECT 
                    COUNT(*) as total_pending,
                    COUNT(*) FILTER (WHERE run_at <= now()) as ready_now,
                    COUNT(*) FILTER (WHERE locked_until IS NOT NULL AND locked_until > now()) as currently_leased,
                    COUNT(*) FILTER (WHERE locked_until IS NOT NULL AND locked_until <= now()) as expired_leases,
                    MIN(run_at) as oldest_pending,
                    MAX(run_at) as newest_pending,
                    EXTRACT(EPOCH FROM (now() - MIN(run_at))) as oldest_age_seconds
                FROM due_work
            """)).mappings().first()
            
            # Processing stats (last hour)
            processing_stats = cx.execute(text("""
                SELECT 
                    COUNT(*) as total_runs,
                    COUNT(*) FILTER (WHERE success = true) as successful_runs,
                    COUNT(*) FILTER (WHERE success = false) as failed_runs,
                    AVG(EXTRACT(EPOCH FROM (finished_at - started_at))) as avg_duration_seconds,
                    MAX(EXTRACT(EPOCH FROM (finished_at - started_at))) as max_duration_seconds,
                    COUNT(DISTINCT lease_owner) as active_workers
                FROM task_run
                WHERE started_at > now() - interval '1 hour'
            """)).mappings().first()
            
            # Task priority distribution
            priority_stats = cx.execute(text("""
                SELECT 
                    t.priority,
                    COUNT(*) as pending_count
                FROM due_work dw
                JOIN task t ON dw.task_id = t.id
                WHERE dw.run_at <= now() AND (dw.locked_until IS NULL OR dw.locked_until <= now())
                GROUP BY t.priority
                ORDER BY t.priority DESC
            """)).mappings().fetchall()
            
            return {
                "queue": dict(queue_stats),
                "processing": dict(processing_stats),
                "priority_distribution": [dict(row) for row in priority_stats],
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    def rebalance_work(self, max_lease_per_worker: int = 5) -> Dict[str, Any]:
        """Implement load balancing by limiting leases per worker."""
        active_workers = self.get_active_workers()
        if not active_workers:
            return {"status": "no_active_workers", "actions": []}
        
        actions = []
        total_redistributed = 0
        
        with self.eng.begin() as cx:
            for worker in active_workers:
                worker_id = worker["worker_id"]
                
                # Count current leases for this worker
                current_leases = cx.execute(text("""
                    SELECT COUNT(*) as lease_count
                    FROM due_work
                    WHERE locked_by = :worker_id AND locked_until > now()
                """), {"worker_id": worker_id}).scalar()
                
                if current_leases > max_lease_per_worker:
                    # Release excess leases (oldest first)
                    released = cx.execute(text("""
                        UPDATE due_work
                        SET locked_until = NULL, locked_by = NULL
                        WHERE id IN (
                            SELECT id FROM due_work
                            WHERE locked_by = :worker_id AND locked_until > now()
                            ORDER BY locked_until ASC
                            LIMIT :excess_count
                        )
                    """), {
                        "worker_id": worker_id,
                        "excess_count": current_leases - max_lease_per_worker
                    }).rowcount
                    
                    if released > 0:
                        actions.append(f"Released {released} excess leases from {worker_id}")
                        total_redistributed += released
        
        return {
            "status": "completed",
            "total_redistributed": total_redistributed,
            "actions": actions,
            "active_workers": len(active_workers)
        }

def monitor_worker_health(db_url: str, unhealthy_threshold_minutes: int = 5):
    """Monitor worker health and log alerts for unhealthy workers."""
    coordinator = WorkerCoordinator(db_url)
    
    # Get workers that should be active
    all_workers = coordinator.eng.execute(text("""
        SELECT worker_id, last_seen, 
               EXTRACT(EPOCH FROM (now() - last_seen)) as seconds_since_heartbeat
        FROM worker_heartbeat
        ORDER BY last_seen DESC
    """)).mappings().fetchall()
    
    unhealthy_workers = []
    for worker in all_workers:
        if worker["seconds_since_heartbeat"] > (unhealthy_threshold_minutes * 60):
            unhealthy_workers.append({
                "worker_id": worker["worker_id"],
                "last_seen": worker["last_seen"],
                "seconds_since_heartbeat": worker["seconds_since_heartbeat"]
            })
    
    if unhealthy_workers:
        logging.warning(f"Found {len(unhealthy_workers)} unhealthy workers:")
        for worker in unhealthy_workers:
            logging.warning(f"  {worker['worker_id']}: last seen {worker['seconds_since_heartbeat']:.0f}s ago")
        
        # Clean up their stale leases
        cleaned = coordinator.cleanup_stale_leases(unhealthy_threshold_minutes)
        if cleaned > 0:
            logging.info(f"Cleaned up {cleaned} stale leases from unhealthy workers")
    
    return {
        "total_workers": len(all_workers),
        "unhealthy_workers": len(unhealthy_workers),
        "unhealthy_details": unhealthy_workers
    }

if __name__ == "__main__":
    # Health monitoring script
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL environment variable required")
        exit(1)
    
    logging.info("Starting worker health monitoring")
    
    while True:
        try:
            health_report = monitor_worker_health(db_url)
            coordinator = WorkerCoordinator(db_url)
            queue_stats = coordinator.get_queue_stats()
            
            logging.info(f"Queue stats: {queue_stats['queue']['ready_now']} ready, "
                        f"{queue_stats['queue']['currently_leased']} leased, "
                        f"{queue_stats['processing']['active_workers']} active workers")
            
            # Rebalance if needed
            if queue_stats["queue"]["ready_now"] > 10:  # Threshold for rebalancing
                rebalance_result = coordinator.rebalance_work()
                if rebalance_result["total_redistributed"] > 0:
                    logging.info(f"Rebalanced work: {rebalance_result}")
            
            time.sleep(30)  # Check every 30 seconds
            
        except KeyboardInterrupt:
            logging.info("Shutting down worker health monitoring")
            break
        except Exception as e:
            logging.error(f"Error in health monitoring: {e}")
            time.sleep(10)